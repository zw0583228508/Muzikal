"""
Melody / pitch detection.

Primary:  torchcrepe on vocals stem (crepe model, frame-level F0)
Secondary: librosa pyin on vocals or full mix
Fallback: librosa yin for quick pitch estimation

Produces: pitch curve, note segmentation, voiced fraction, confidence.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import numpy as np
import librosa

from analysis.schemas import MelodyResult, NoteEvent
from analysis.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

MIDI_A4 = 69
HZ_A4 = 440.0
MIN_NOTE_DURATION = 0.05   # seconds — filter out very short notes
MIN_CONF_THRESHOLD = 0.4   # minimum confidence to classify as voiced
HOP_LENGTH = 512
SR_CREPE = 16000            # torchcrepe works at 16kHz


def _hz_to_midi(hz: np.ndarray) -> np.ndarray:
    """Convert Hz to MIDI note numbers. Unvoiced (hz <= 0) → -1."""
    midi = np.full_like(hz, -1.0)
    voiced = hz > 0
    midi[voiced] = 12 * np.log2(hz[voiced] / HZ_A4) + MIDI_A4
    return midi


def _midi_to_name(midi: int) -> str:
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = midi // 12 - 1
    note = notes[midi % 12]
    return f"{note}{octave}"


def _segment_notes(
    times: np.ndarray,
    pitches_hz: np.ndarray,
    confidences: np.ndarray,
    min_conf: float = MIN_CONF_THRESHOLD,
    min_dur: float = MIN_NOTE_DURATION,
) -> List[NoteEvent]:
    """
    Convert frame-level pitch curve into discrete note events.
    Groups consecutive voiced frames with similar pitch into notes.
    """
    if len(times) == 0:
        return []

    midi = _hz_to_midi(pitches_hz)
    voiced = (confidences >= min_conf) & (pitches_hz > 0)
    midi_rounded = np.round(midi).astype(int)

    notes: List[NoteEvent] = []
    i = 0
    while i < len(voiced):
        if not voiced[i]:
            i += 1
            continue

        # Start of a voiced segment
        start_idx = i
        current_midi = midi_rounded[i]

        # Extend while same MIDI note and voiced
        j = i + 1
        while j < len(voiced) and voiced[j] and abs(midi_rounded[j] - current_midi) <= 1:
            j += 1

        start_time = float(times[start_idx])
        end_time = float(times[j - 1])
        duration = end_time - start_time

        if duration >= min_dur:
            mean_hz = float(np.mean(pitches_hz[start_idx:j][pitches_hz[start_idx:j] > 0]))
            mean_conf = float(np.mean(confidences[start_idx:j]))
            mean_midi = int(np.round(12 * np.log2(mean_hz / HZ_A4) + MIDI_A4))

            # Velocity from confidence + loudness proxy
            velocity = int(np.clip(mean_conf * 100, 20, 120))

            notes.append(NoteEvent(
                pitch=mean_midi,
                pitch_name=_midi_to_name(mean_midi),
                start=round(start_time, 4),
                end=round(end_time, 4),
                duration=round(duration, 4),
                velocity=velocity,
                confidence=round(mean_conf, 3),
            ))

        i = j

    return notes


def _detect_pitch_torchcrepe(
    y: np.ndarray, sr: int, stem_path: Optional[str] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """
    Torchcrepe CREPE-based pitch detection.
    Returns (times, pitches_hz, confidences, source_label).
    """
    try:
        import torch
        import torchcrepe

        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load audio at 16kHz (torchcrepe requirement)
        if stem_path and os.path.exists(stem_path):
            y_16k, _ = librosa.load(stem_path, sr=SR_CREPE, mono=True)
        elif sr != SR_CREPE:
            y_16k = librosa.resample(y, orig_sr=sr, target_sr=SR_CREPE)
        else:
            y_16k = y

        # Convert to torch tensor
        audio_tensor = torch.tensor(y_16k).unsqueeze(0)  # (1, samples)

        # Hop size for 512-sample hops at 16kHz
        hop_length_16k = 160  # 10ms at 16kHz

        pitches, confidences = torchcrepe.predict(
            audio_tensor,
            SR_CREPE,
            hop_length=hop_length_16k,
            fmin=50.0,
            fmax=2006.0,
            model="full",
            batch_size=512,
            device=device,
            pad=True,
            return_periodicity=True,
        )

        # torchcrepe returns tensors of shape (1, n_frames)
        pitches_np = pitches.squeeze(0).numpy()
        conf_np = confidences.squeeze(0).numpy()

        # Build time axis
        n_frames = len(pitches_np)
        times = np.arange(n_frames) * hop_length_16k / SR_CREPE

        # Zero out low-confidence frames
        pitches_np[conf_np < MIN_CONF_THRESHOLD] = 0.0

        return times, pitches_np, conf_np, "torchcrepe_vocals"

    except Exception as e:
        logger.warning("torchcrepe failed: %s — using pyin", e)
        return _detect_pitch_pyin(y, sr)


def _detect_pitch_pyin(
    y: np.ndarray, sr: int, stem_path: Optional[str] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """
    librosa pyin pitch detection (probabilistic YIN).
    Returns (times, pitches_hz, confidences, source_label).
    """
    try:
        if stem_path and os.path.exists(stem_path):
            y_src, sr_src = librosa.load(stem_path, sr=None, mono=True)
        else:
            y_src, sr_src = y, sr

        f0, voiced_flag, voiced_probs = librosa.pyin(
            y_src, fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr_src, hop_length=HOP_LENGTH,
            fill_na=0.0,
        )

        times = librosa.times_like(f0, sr=sr_src, hop_length=HOP_LENGTH)
        f0 = np.nan_to_num(f0, nan=0.0)

        return times, f0, voiced_probs, "pyin_librosa"

    except Exception as e:
        logger.warning("pyin failed: %s — using yin", e)
        return _detect_pitch_yin(y, sr)


def _detect_pitch_yin(
    y: np.ndarray, sr: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """Fast YIN (last resort fallback, lower accuracy)."""
    try:
        f0 = librosa.yin(
            y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"),
            sr=sr, hop_length=HOP_LENGTH
        )
        times = librosa.times_like(f0, sr=sr, hop_length=HOP_LENGTH)
        conf = np.ones_like(f0) * 0.5
        conf[f0 <= 0] = 0.0
        return times, f0, conf, "yin_librosa"
    except Exception:
        return np.array([0.0]), np.array([0.0]), np.array([0.0]), "silent"


def detect_melody(bundle, stems=None, force: bool = False) -> MelodyResult:
    """
    Main melody detection entry point.
    Uses torchcrepe on vocals stem when available.
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = "melody_detector"

    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Melody cache hit for %s", file_hash[:8])
            return MelodyResult.model_validate(cached)

    vocals_path = None
    if stems and stems.vocals.available and stems.vocals.path:
        vocals_path = stems.vocals.path

    # Primary: torchcrepe on vocals
    if vocals_path:
        times, pitches, conf, source = _detect_pitch_torchcrepe(
            bundle.y_mono, bundle.sr, stem_path=vocals_path
        )
    else:
        # Fallback: pyin on full mix
        times, pitches, conf, source = _detect_pitch_pyin(bundle.y_mono, bundle.sr)

    # Segment into discrete notes
    notes = _segment_notes(times, pitches, conf)

    # Build pitch curve (downsampled to max 2000 points for API transport)
    voiced_mask = conf >= MIN_CONF_THRESHOLD
    voiced_fraction = float(voiced_mask.sum() / len(voiced_mask)) if len(voiced_mask) else 0.0

    n_pts = min(len(times), 2000)
    indices = np.linspace(0, len(times) - 1, n_pts, dtype=int)
    pitch_curve = [
        {"time": round(float(times[i]), 4), "hz": round(float(pitches[i]), 2), "conf": round(float(conf[i]), 3)}
        for i in indices if pitches[i] > 0
    ]

    mean_pitch = float(np.mean(pitches[pitches > 0])) if np.any(pitches > 0) else 0.0
    global_confidence = float(np.mean(conf[voiced_mask])) if voiced_mask.any() else 0.0

    result = MelodyResult(
        pitch_curve=pitch_curve,
        notes=notes,
        global_confidence=round(global_confidence, 3),
        voiced_fraction=round(voiced_fraction, 3),
        mean_pitch_hz=round(mean_pitch, 2),
        source=source,
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info(
        "Melody: %d notes, voiced=%.1f%%, conf=%.2f, src=%s",
        len(notes), voiced_fraction * 100, global_confidence, source
    )
    return result
