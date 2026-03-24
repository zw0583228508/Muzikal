"""
Beat / tempo / downbeat tracking.

Primary:  madmom RNNBeatProcessor + DBNBeatTrackingProcessor on drums stem
Secondary: madmom RNNDownBeatProcessor for downbeat / time-signature
Fallback: librosa.beat.beat_track on full mix mono

Output: TempoResult with global BPM, beat times, downbeat times, meter.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np
import librosa

from analysis.schemas import TempoResult
from analysis.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Lazy-loaded madmom processors (heavy to instantiate)
_rnn_beat_proc = None
_dbn_beat_proc = None
_rnn_downbeat_proc = None
_dbn_downbeat_proc = None


def _get_madmom_beat_procs():
    global _rnn_beat_proc, _dbn_beat_proc
    if _rnn_beat_proc is None:
        # Apply Python 3.11 compatibility patch before importing madmom
        import collections, collections.abc
        for _n in ["MutableSequence", "MutableMapping", "MutableSet",
                   "Callable", "Iterator", "Iterable", "Mapping", "Sequence", "Set"]:
            if not hasattr(collections, _n):
                setattr(collections, _n, getattr(collections.abc, _n))

        from madmom.features.beats import RNNBeatProcessor, DBNBeatTrackingProcessor
        _rnn_beat_proc = RNNBeatProcessor()
        _dbn_beat_proc = DBNBeatTrackingProcessor(fps=100)
        logger.info("madmom beat processors loaded")
    return _rnn_beat_proc, _dbn_beat_proc


def _get_madmom_downbeat_procs():
    global _rnn_downbeat_proc, _dbn_downbeat_proc
    if _rnn_downbeat_proc is None:
        import collections, collections.abc
        for _n in ["MutableSequence", "MutableMapping", "MutableSet",
                   "Callable", "Iterator", "Iterable", "Mapping", "Sequence", "Set"]:
            if not hasattr(collections, _n):
                setattr(collections, _n, getattr(collections.abc, _n))

        from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
        _rnn_downbeat_proc = RNNDownBeatProcessor()
        _dbn_downbeat_proc = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4])
        logger.info("madmom downbeat processors loaded")
    return _rnn_downbeat_proc, _dbn_downbeat_proc


def _bpm_from_beats(beats: np.ndarray) -> float:
    """Compute median BPM from an array of beat timestamps."""
    if len(beats) < 2:
        return 120.0
    intervals = np.diff(beats)
    intervals = intervals[(intervals > 0.2) & (intervals < 4.0)]  # 15–300 BPM range
    if len(intervals) == 0:
        return 120.0
    median_interval = float(np.median(intervals))
    return round(60.0 / median_interval, 2)


def _compute_bpm_curve(beats: np.ndarray, window: int = 8) -> List[dict]:
    """Compute local BPM over a sliding window of beats."""
    if len(beats) < window + 1:
        return []
    curve = []
    for i in range(len(beats) - window):
        segment = beats[i: i + window + 1]
        local_bpm = _bpm_from_beats(segment)
        curve.append({"time": float(beats[i + window // 2]), "bpm": local_bpm})
    return curve


def _detect_meter(downbeats: np.ndarray, beats: np.ndarray) -> Tuple[int, int]:
    """Estimate time signature from ratio of beats to downbeats."""
    if len(downbeats) < 2 or len(beats) < 4:
        return 4, 4

    beats_per_bar_counts: dict = {}
    for i in range(len(downbeats) - 1):
        start, end = downbeats[i], downbeats[i + 1]
        count = np.sum((beats >= start) & (beats < end))
        beats_per_bar_counts[int(count)] = beats_per_bar_counts.get(int(count), 0) + 1

    if not beats_per_bar_counts:
        return 4, 4

    most_common = max(beats_per_bar_counts, key=beats_per_bar_counts.get)
    # Map to nearest valid time signature
    if most_common in (2,):
        return 2, 4
    elif most_common in (3,):
        return 3, 4
    elif most_common in (6,):
        return 6, 8
    elif most_common in (5,):
        return 5, 4
    else:
        return 4, 4


def _track_beats_madmom(audio_path: str) -> Tuple[np.ndarray, np.ndarray, float]:
    """Run madmom RNN+DBN beat tracking. Returns (beats, downbeats, confidence)."""
    try:
        rnn_beat, dbn_beat = _get_madmom_beat_procs()
        rnn_down, dbn_down = _get_madmom_downbeat_procs()

        act = rnn_beat(audio_path)
        beats = dbn_beat(act)  # Array of beat times in seconds

        # Downbeats
        act_down = rnn_down(audio_path)
        downbeats_raw = dbn_down(act_down)  # [[time, beat_number], ...]
        downbeats = downbeats_raw[downbeats_raw[:, 1] == 1, 0] if len(downbeats_raw) else beats[:1]

        # Confidence from activation strength at detected beats
        fps = 100
        confidence = float(np.mean([
            float(act[min(int(b * fps), len(act) - 1)])
            for b in beats if int(b * fps) < len(act)
        ])) if len(beats) > 0 else 0.5

        return beats, downbeats, min(1.0, confidence * 2.0)
    except Exception as e:
        logger.warning("madmom beat tracking failed: %s", e)
        return np.array([]), np.array([]), 0.0


def _track_beats_librosa(y: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray, float]:
    """Librosa beat tracking fallback."""
    try:
        tempo, beat_frames = librosa.beat.beat_track(
            y=y, sr=sr, trim=True, units="time"
        )
        beats = beat_frames if isinstance(beat_frames, np.ndarray) else np.array(beat_frames)

        # Estimate downbeats (every 4th beat)
        downbeats = beats[::4] if len(beats) >= 4 else beats[:1]

        # Confidence is lower for librosa (no RNN)
        return beats, downbeats, 0.60
    except Exception as e:
        logger.warning("librosa beat tracking failed: %s", e)
        return np.array([0.0]), np.array([0.0]), 0.1


def track_beats(
    bundle,
    stems=None,
    force: bool = False,
) -> TempoResult:
    """
    Main beat tracking entry point.
    Uses drums stem with madmom when available, falls back to full-mix librosa.
    """
    file_hash = bundle.file_hash or "no_hash"
    stage = "beat_tracker"

    if not force:
        cached = cache_get(file_hash, stage)
        if cached is not None:
            logger.info("Beat cache hit for %s", file_hash[:8])
            return TempoResult.model_validate(cached)

    # Prefer drums stem with madmom
    source = "librosa_fullmix"
    beats = np.array([])
    downbeats = np.array([])
    confidence = 0.0

    drums_path = None
    if stems and stems.drums.available and stems.drums.path:
        drums_path = stems.drums.path

    if drums_path:
        logger.info("Running madmom on drums stem: %s", drums_path)
        beats, downbeats, confidence = _track_beats_madmom(drums_path)
        if len(beats) > 4:
            source = "madmom_drums"
        else:
            logger.warning("madmom on drums gave too few beats, trying full mix")

    if len(beats) < 4:
        # Try madmom on full mix
        logger.info("Trying madmom on full mix")
        beats, downbeats, confidence = _track_beats_madmom(bundle.file_path)
        if len(beats) > 4:
            source = "madmom_fullmix"

    if len(beats) < 4:
        # Fallback to librosa
        logger.info("Falling back to librosa beat tracking")
        beats, downbeats, confidence = _track_beats_librosa(bundle.y_mono, bundle.sr)
        source = "librosa_fullmix"

    bpm_global = _bpm_from_beats(beats)
    bpm_curve = _compute_bpm_curve(beats)
    meter_num, meter_den = _detect_meter(downbeats, beats)

    # Compute alternatives (half/double tempo)
    alternatives = [
        {"bpm": round(bpm_global / 2, 2), "label": "half_tempo"},
        {"bpm": round(bpm_global * 2, 2), "label": "double_tempo"},
    ]

    result = TempoResult(
        bpm_global=bpm_global,
        bpm_curve=bpm_curve,
        beats=beats.tolist() if isinstance(beats, np.ndarray) else list(beats),
        downbeats=downbeats.tolist() if isinstance(downbeats, np.ndarray) else list(downbeats),
        meter=f"{meter_num}/{meter_den}",
        meter_numerator=meter_num,
        meter_denominator=meter_den,
        confidence=round(confidence, 3),
        source=source,
        alternatives=alternatives,
    )

    cache_set(file_hash, stage, result.model_dump())
    logger.info("BPM=%.1f meter=%s/%s conf=%.2f src=%s", bpm_global, meter_num, meter_den, confidence, source)
    return result
