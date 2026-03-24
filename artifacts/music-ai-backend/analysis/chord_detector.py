"""
Chord detection via CQT chroma + enhanced template matching.

Primary:  Essentia HPCP on other+bass stems → chord template matching
Fallback: librosa CQT chroma → template matching

Produces a timeline of ChordEvent objects with confidence and alternatives.
Uses beat-synchronous chroma (one chord per beat / per bar) for stability.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Dict

import numpy as np
import librosa

from analysis.schemas import ChordEvent, ChordsResult
from analysis.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# ─── Chord Templates ───────────────────────────────────────────────────────────
# 12-dimensional binary templates for common chord qualities.
# Root = C (index 0), rotate to other roots.

_TEMPLATES: Dict[str, np.ndarray] = {
    "maj":   np.array([1,0,0,0,1,0,0,1,0,0,0,0], dtype=float),
    "min":   np.array([1,0,0,1,0,0,0,1,0,0,0,0], dtype=float),
    "dim":   np.array([1,0,0,1,0,0,1,0,0,0,0,0], dtype=float),
    "aug":   np.array([1,0,0,0,1,0,0,0,1,0,0,0], dtype=float),
    "maj7":  np.array([1,0,0,0,1,0,0,1,0,0,0,1], dtype=float),
    "min7":  np.array([1,0,0,1,0,0,0,1,0,0,1,0], dtype=float),
    "dom7":  np.array([1,0,0,0,1,0,0,1,0,0,1,0], dtype=float),
    "dim7":  np.array([1,0,0,1,0,0,1,0,0,1,0,0], dtype=float),
    "sus2":  np.array([1,0,1,0,0,0,0,1,0,0,0,0], dtype=float),
    "sus4":  np.array([1,0,0,0,0,1,0,1,0,0,0,0], dtype=float),
    "add9":  np.array([1,0,1,0,1,0,0,1,0,0,0,0], dtype=float),
    "min9":  np.array([1,0,1,1,0,0,0,1,0,0,1,0], dtype=float),
    "maj9":  np.array([1,0,1,0,1,0,0,1,0,0,0,1], dtype=float),
    "N":     np.zeros(12, dtype=float),  # No chord / silence
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Build full chord vocabulary: all roots × all qualities
_ALL_CHORDS: List[Tuple[int, str]] = [(r, q) for r in range(12) for q in _TEMPLATES if q != "N"]


def _chord_label(root_idx: int, quality: str) -> str:
    return f"{NOTE_NAMES[root_idx]}{quality}"


def _template_score(chroma_frame: np.ndarray, root_idx: int, quality: str) -> float:
    """Cosine similarity between chroma frame and a chord template."""
    template = np.roll(_TEMPLATES[quality], root_idx)
    denom = (np.linalg.norm(chroma_frame) * np.linalg.norm(template)) + 1e-8
    return float(np.dot(chroma_frame, template) / denom)


def _match_chord(
    chroma_frame: np.ndarray,
    top_k: int = 3,
    bass_chroma: Optional[np.ndarray] = None,
    bass_weight: float = 0.25,
) -> Tuple[int, str, float, List[dict]]:
    """
    Match a chroma frame against all chord templates.
    Optionally weights bass stem chroma to improve root detection.

    Returns (root_idx, quality, confidence, alternatives).
    """
    # Silence check
    if np.max(chroma_frame) < 0.05:
        return -1, "N", 0.1, []

    # Weighted chroma: blend mid/treble chroma with bass chroma for root
    if bass_chroma is not None and np.max(bass_chroma) > 0.01:
        bass_norm = bass_chroma / (np.linalg.norm(bass_chroma) + 1e-8)
        mid_norm  = chroma_frame / (np.linalg.norm(chroma_frame) + 1e-8)
        combined = (1.0 - bass_weight) * mid_norm + bass_weight * bass_norm
    else:
        combined = chroma_frame

    scores: List[Tuple[float, int, str]] = []
    for root, quality in _ALL_CHORDS:
        score = _template_score(combined, root, quality)
        scores.append((score, root, quality))

    scores.sort(key=lambda x: -x[0])
    best_score, best_root, best_quality = scores[0]

    # Normalize confidence to [0, 1]
    confidence = float(np.clip(best_score, 0, 1))

    alternatives = [
        {
            "chord": _chord_label(r, q),
            "root": NOTE_NAMES[r],
            "quality": q,
            "confidence": round(float(np.clip(s, 0, 1)), 3),
        }
        for s, r, q in scores[1:top_k + 1]
    ]

    return best_root, best_quality, confidence, alternatives


def _compute_bass_chroma(stems, bundle) -> Optional[np.ndarray]:
    """
    Compute low-pass chroma from bass stem (emphasises root note detection).
    """
    bass_path = getattr(getattr(stems, "bass", None), "path", None) if stems else None
    if bass_path and __import__("os").path.exists(bass_path):
        try:
            y_bass, sr_bass = librosa.load(bass_path, sr=22050, mono=True)
            # Low-pass CQT chroma — only up to ~500 Hz (octaves 0-2)
            chroma = librosa.feature.chroma_cqt(
                y=y_bass, sr=sr_bass, bins_per_octave=24, hop_length=2048,
                fmin=librosa.note_to_hz("C1"), norm=2,
            )
            return chroma  # (12, n_frames)
        except Exception as e:
            logger.debug("Bass chroma failed: %s", e)
    return None


def _compute_chroma_essentia(stem_path: str) -> Optional[np.ndarray]:
    """Compute HPCP chroma using Essentia from a stem WAV file."""
    try:
        import essentia.standard as es

        loader = es.MonoLoader(filename=stem_path, sampleRate=44100)
        audio = loader()

        windowing = es.Windowing(type="blackmanharris62")
        spectrum = es.Spectrum()
        spectral_peaks = es.SpectralPeaks(
            magnitudeThreshold=1e-5, maxPeaks=60, maxFrequency=3500,
            minFrequency=40, orderBy="magnitude", sampleRate=44100
        )
        hpcp = es.HPCP(size=12, referenceFrequency=440, maxFrequency=3500, minFrequency=40)

        frame_size = 8192
        hop_size = 4096
        frames = []

        for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size, startFromZero=True):
            windowed = windowing(frame)
            spec = spectrum(windowed)
            freqs, mags = spectral_peaks(spec)
            if len(freqs) > 0:
                hpcp_frame = hpcp(freqs, mags)
                frames.append(hpcp_frame)

        if not frames:
            return None

        return np.array(frames).T  # shape: (12, n_frames)

    except Exception as e:
        logger.warning("Essentia HPCP failed: %s", e)
        return None


def _compute_chroma_librosa(y: np.ndarray, sr: int) -> np.ndarray:
    """CQT chroma with higher resolution."""
    return librosa.feature.chroma_cqt(
        y=y, sr=sr, bins_per_octave=36, hop_length=2048, norm=2
    )


def _chroma_with_stems(bundle, stems) -> Tuple[np.ndarray, str]:
    """Get best available chroma from stems or full mix."""
    # Try Essentia on other+bass mix
    other_path = getattr(getattr(stems, "other", None), "path", None) if stems else None
    bass_path = getattr(getattr(stems, "bass", None), "path", None) if stems else None

    if other_path and __import__("os").path.exists(other_path):
        chroma = _compute_chroma_essentia(other_path)
        if chroma is not None and chroma.shape[1] > 10:
            return chroma, "essentia_other_stem"

    # Fallback: librosa CQT on mono
    chroma = _compute_chroma_librosa(bundle.y_mono, bundle.sr)
    return chroma, "librosa_cqt"


def _beat_synchronize(chroma: np.ndarray, beats: List[float], sr: int, hop_length: int = 2048) -> Tuple[np.ndarray, np.ndarray]:
    """
    Average chroma in each inter-beat interval.
    Returns (synced_chroma, beat_times_array).
    """
    if not beats or len(beats) < 2:
        return chroma, np.linspace(0, chroma.shape[1] * hop_length / sr, chroma.shape[1])

    beat_frames = librosa.time_to_frames(beats, sr=sr, hop_length=hop_length)
    beat_frames = np.clip(beat_frames, 0, chroma.shape[1] - 1)
    beat_frames = np.unique(beat_frames)

    synced = librosa.util.sync(chroma, beat_frames, aggregate=np.median)
    return synced, np.array(beats[:synced.shape[1]])


def _median_filter_sequence(sequence: List[Tuple[int, str]], window: int = 3) -> List[Tuple[int, str]]:
    """Apply median-like smoothing to a chord sequence (reduce flicker)."""
    if len(sequence) < window:
        return sequence

    smoothed = []
    half = window // 2
    for i in range(len(sequence)):
        window_slice = sequence[max(0, i - half): i + half + 1]
        # Pick most common chord in window
        counts: Dict[Tuple[int, str], int] = {}
        for item in window_slice:
            counts[item] = counts.get(item, 0) + 1
        best = max(counts, key=counts.get)
        smoothed.append(best)
    return smoothed


def detect_chords(bundle, stems=None, tempo=None, force: bool = False) -> ChordsResult:
    """
    Main chord detection entry point.
    Uses beat-synchronous chroma + bass stem weighting for stable chord detection.
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = "chord_detector"

    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Chords cache hit for %s", file_hash[:8])
            return ChordsResult.model_validate(cached)

    # Get best mid/treble chroma (Essentia HPCP or librosa CQT)
    chroma, source = _chroma_with_stems(bundle, stems)
    logger.info("Chord chroma from: %s shape=%s", source, chroma.shape)

    # Compute bass chroma for root-note weighting
    bass_chroma_full = _compute_bass_chroma(stems, bundle)
    if bass_chroma_full is not None:
        logger.info("Bass chroma available (shape=%s) — enabling root weighting", bass_chroma_full.shape)

    # Beat-synchronize for stable chord windows
    beats = []
    if tempo and tempo.beats:
        beats = tempo.beats

    hop_length = 2048
    synced_chroma, beat_times = _beat_synchronize(chroma, beats, bundle.sr, hop_length)

    # Synchronize bass chroma to same grid
    synced_bass: Optional[np.ndarray] = None
    if bass_chroma_full is not None:
        n_beat_frames = synced_chroma.shape[1]
        if beats and len(beats) >= 2:
            beat_frames_bass = librosa.time_to_frames(beats, sr=22050, hop_length=2048)
            beat_frames_bass = np.clip(beat_frames_bass, 0, bass_chroma_full.shape[1] - 1)
            beat_frames_bass = np.unique(beat_frames_bass)
            synced_bass = librosa.util.sync(bass_chroma_full, beat_frames_bass, aggregate=np.median)
        else:
            synced_bass = bass_chroma_full

    # Match each beat window to a chord
    raw_sequence: List[Tuple[int, str]] = []
    for i in range(synced_chroma.shape[1]):
        frame = synced_chroma[:, i]
        bass_frame = synced_bass[:, min(i, synced_bass.shape[1] - 1)] if synced_bass is not None else None
        root, quality, _, _ = _match_chord(frame, bass_chroma=bass_frame)
        raw_sequence.append((root, quality))

    # Smooth chord sequence
    smoothed = _median_filter_sequence(raw_sequence, window=3)

    # Build chord timeline: merge consecutive identical chords
    timeline: List[ChordEvent] = []
    if len(smoothed) > 0:
        i = 0
        while i < len(smoothed):
            root, quality = smoothed[i]
            j = i + 1
            while j < len(smoothed) and smoothed[j] == (root, quality):
                j += 1

            start = float(beat_times[i]) if i < len(beat_times) else float(i * hop_length / bundle.sr)
            end = float(beat_times[j - 1]) if j - 1 < len(beat_times) else float(j * hop_length / bundle.sr)
            # Extend last chord to duration
            if j >= len(smoothed) and bundle.duration > end:
                end = bundle.duration

            # Re-score this merged segment (with bass chroma)
            segment_chroma = synced_chroma[:, i:j].mean(axis=1)
            segment_bass = None
            if synced_bass is not None:
                end_idx = min(j, synced_bass.shape[1])
                if i < end_idx:
                    segment_bass = synced_bass[:, i:end_idx].mean(axis=1)
            best_root, best_quality, conf, alts = _match_chord(
                segment_chroma, bass_chroma=segment_bass
            )

            if best_quality == "N":
                i = j
                continue

            label = _chord_label(best_root, best_quality)
            timeline.append(ChordEvent(
                start=round(start, 3),
                end=round(end, 3),
                chord=label,
                root=NOTE_NAMES[best_root],
                quality=best_quality,
                confidence=round(conf, 3),
                alternatives=alts,
            ))
            i = j

    unique_chords = list(dict.fromkeys(e.chord for e in timeline))
    global_conf = float(np.mean([e.confidence for e in timeline])) if timeline else 0.0
    bass_tag = "_bass_weighted" if bass_chroma_full is not None else ""

    result = ChordsResult(
        timeline=timeline,
        global_confidence=round(global_conf, 3),
        unique_chords=unique_chords,
        source=source + bass_tag,
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info(
        "Chords: %d events, %d unique, conf=%.2f, bass=%s",
        len(timeline), len(unique_chords), global_conf,
        "yes" if bass_chroma_full is not None else "no"
    )
    return result
