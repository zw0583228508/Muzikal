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


def _detect_pitch_basic_pitch(
    stem_path: Optional[str],
    y: np.ndarray,
    sr: int,
) -> Optional[MelodyResult]:
    """
    basic-pitch (Spotify) note event detection.
    Returns a MelodyResult with note events (no pitch curve).
    basic-pitch is better at precise onset/offset times than torchcrepe.
    """
    try:
        import tempfile, soundfile as sf
        from basic_pitch.inference import predict, Model
        from basic_pitch import ICASSP_2022_MODEL_PATH

        # Determine source audio
        if stem_path and __import__("os").path.exists(stem_path):
            audio_path = stem_path
        else:
            # Write temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, y, sr)
                audio_path = f.name

        logger.info("basic-pitch: running on %s", audio_path)
        model = Model(ICASSP_2022_MODEL_PATH)
        model_output, midi_data, note_events = predict(audio_path, model)

        if note_events is None or len(note_events) == 0:
            logger.info("basic-pitch: no notes detected")
            return None

        # note_events: list of (start_time, end_time, pitch_midi, amplitude, pitch_bends)
        notes: List[NoteEvent] = []
        for ev in note_events:
            start_t  = float(ev[0])
            end_t    = float(ev[1])
            pitch    = int(round(ev[2]))
            amplitude = float(ev[3])
            dur = end_t - start_t
            if dur < MIN_NOTE_DURATION:
                continue
            velocity = min(127, max(1, int(amplitude * 127)))
            notes.append(NoteEvent(
                pitch=pitch,
                pitch_name=_midi_to_name(pitch),
                start=round(start_t, 4),
                end=round(end_t, 4),
                duration=round(dur, 4),
                velocity=velocity,
                confidence=round(float(amplitude), 3),
            ))

        if not notes:
            return None

        mean_hz = float(np.mean([
            440.0 * 2.0 ** ((n.pitch - 69) / 12.0) for n in notes
        ]))
        avg_conf = float(np.mean([n.confidence for n in notes]))

        logger.info("basic-pitch: %d note events, mean_conf=%.2f", len(notes), avg_conf)
        return MelodyResult(
            pitch_curve=[],
            notes=notes,
            global_confidence=round(avg_conf, 3),
            voiced_fraction=1.0,
            mean_pitch_hz=round(mean_hz, 2),
            source="basic_pitch_vocals",
        )

    except Exception as e:
        logger.warning("basic-pitch failed: %s", e)
        return None


def detect_melody(bundle, stems=None, force: bool = False) -> MelodyResult:
    """
    Main melody detection entry point.
    Primary:   torchcrepe on vocals stem (frame-level pitch curve)
    Secondary: basic-pitch on vocals stem (precise note events)
    Fallback:  pyin on full mix
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = "melody_detector"

    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Melody cache hit for %s", file_hash[:8])
            return MelodyResult.model_validate(cached)

    vocals_path: Optional[str] = None
    if stems and stems.vocals.available and stems.vocals.path:
        vocals_path = stems.vocals.path

    # ── Primary: torchcrepe (frame-level pitch curve) ───────────────────────
    if vocals_path:
        times, pitches, conf, source = _detect_pitch_torchcrepe(
            bundle.y_mono, bundle.sr, stem_path=vocals_path
        )
    else:
        times, pitches, conf, source = _detect_pitch_pyin(bundle.y_mono, bundle.sr)

    # ── Secondary: basic-pitch (note-event level) ───────────────────────────
    bp_result = _detect_pitch_basic_pitch(vocals_path, bundle.y_mono, bundle.sr)

    # Segment pitch curve into discrete notes (torchcrepe source)
    crepe_notes = _segment_notes(times, pitches, conf)

    # Merge notes: prefer basic-pitch events (better onset/offset),
    # use torchcrepe notes as fill where basic-pitch is silent
    if bp_result and bp_result.notes:
        # Build merged note list: basic-pitch notes fill the main events
        # torchcrepe provides additional voices/harmonics
        merged_notes = _merge_note_sources(bp_result.notes, crepe_notes)
        source = "merged_crepe_basicpitch"
    else:
        merged_notes = crepe_notes

    # Build pitch curve from torchcrepe (downsampled to max 2000 points)
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

    # If basic-pitch had higher confidence, use that
    if bp_result and bp_result.global_confidence > global_confidence:
        global_confidence = float(np.mean([global_confidence, bp_result.global_confidence]))

    result = MelodyResult(
        pitch_curve=pitch_curve,
        notes=merged_notes,
        global_confidence=round(global_confidence, 3),
        voiced_fraction=round(voiced_fraction, 3),
        mean_pitch_hz=round(mean_pitch, 2),
        source=source,
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info(
        "Melody: %d notes (%s crepe + %s bp), voiced=%.1f%%, conf=%.2f, src=%s",
        len(merged_notes),
        len(crepe_notes),
        len(bp_result.notes) if bp_result else 0,
        voiced_fraction * 100,
        global_confidence,
        source,
    )
    return result


def _merge_note_sources(
    primary: List[NoteEvent],
    secondary: List[NoteEvent],
    gap_fill_threshold: float = 0.1,
) -> List[NoteEvent]:
    """
    Merge two note event lists.
    primary notes take precedence; secondary notes fill gaps in primary.
    """
    if not secondary:
        return primary
    if not primary:
        return secondary

    # Build occupied time intervals from primary
    occupied = [(n.start, n.end) for n in primary]
    occupied.sort()

    def _is_gap(start: float, end: float) -> bool:
        """True if the time window has no primary note."""
        for occ_start, occ_end in occupied:
            if occ_start <= start + gap_fill_threshold and occ_end >= end - gap_fill_threshold:
                return False
            if occ_start > end:
                break
        return True

    fill_notes = [n for n in secondary if _is_gap(n.start, n.end)]
    merged = list(primary) + fill_notes
    merged.sort(key=lambda n: n.start)
    return merged
