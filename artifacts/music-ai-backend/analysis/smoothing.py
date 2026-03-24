"""
Temporal smoothing for analysis results.

Reduces flicker / noise in time-series outputs:
  - BPM curve smoothing (median filter)
  - Chord timeline merging (minimum duration filter)
  - Pitch curve smoothing (Savitzky-Golay)
  - Key segment consolidation
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
from scipy.signal import medfilt, savgol_filter

from analysis.schemas import (
    TempoResult, ChordsResult, ChordEvent, MelodyResult, KeyResult, KeySegment
)

logger = logging.getLogger(__name__)


# ─── BPM Smoothing ─────────────────────────────────────────────────────────────

def smooth_bpm_curve(result: TempoResult, window: int = 5) -> TempoResult:
    """Apply median filter to BPM curve to remove tempo flicker."""
    if not result.bpm_curve or len(result.bpm_curve) < window:
        return result

    bpms = np.array([pt["bpm"] for pt in result.bpm_curve])
    times = [pt["time"] for pt in result.bpm_curve]

    # Median filter
    smoothed_bpms = medfilt(bpms, kernel_size=window if window % 2 == 1 else window + 1)

    smoothed_curve = [
        {"time": t, "bpm": round(float(b), 2)}
        for t, b in zip(times, smoothed_bpms)
    ]

    return TempoResult(
        bpm_global=result.bpm_global,
        bpm_curve=smoothed_curve,
        beats=result.beats,
        downbeats=result.downbeats,
        meter=result.meter,
        meter_numerator=result.meter_numerator,
        meter_denominator=result.meter_denominator,
        confidence=result.confidence,
        source=result.source + "_smoothed",
        alternatives=result.alternatives,
    )


# ─── Chord Smoothing ───────────────────────────────────────────────────────────

def smooth_chords(result: ChordsResult, min_duration: float = 0.5) -> ChordsResult:
    """
    Merge very short chord events into adjacent ones.
    Chords shorter than min_duration are absorbed by the longer neighbour.
    """
    if not result.timeline:
        return result

    timeline = list(result.timeline)
    changed = True

    while changed:
        changed = False
        merged: List[ChordEvent] = []
        i = 0
        while i < len(timeline):
            event = timeline[i]
            dur = event.end - event.start

            if dur < min_duration and i + 1 < len(timeline):
                # Merge with next event by extending next event backward
                next_ev = timeline[i + 1]
                merged.append(ChordEvent(
                    start=event.start,
                    end=next_ev.end,
                    chord=next_ev.chord,
                    root=next_ev.root,
                    quality=next_ev.quality,
                    confidence=round((event.confidence + next_ev.confidence) / 2, 3),
                    alternatives=next_ev.alternatives,
                ))
                i += 2
                changed = True
            else:
                merged.append(event)
                i += 1
        timeline = merged

    # Merge consecutive identical chords
    final: List[ChordEvent] = []
    for ev in timeline:
        if final and final[-1].chord == ev.chord:
            prev = final[-1]
            final[-1] = ChordEvent(
                start=prev.start,
                end=ev.end,
                chord=prev.chord,
                root=prev.root,
                quality=prev.quality,
                confidence=round((prev.confidence + ev.confidence) / 2, 3),
                alternatives=prev.alternatives,
            )
        else:
            final.append(ev)

    unique = list(dict.fromkeys(e.chord for e in final))
    global_conf = float(np.mean([e.confidence for e in final])) if final else 0.0

    return ChordsResult(
        timeline=final,
        global_confidence=round(global_conf, 3),
        unique_chords=unique,
        source=result.source + "_smoothed",
    )


# ─── Pitch Curve Smoothing ─────────────────────────────────────────────────────

def smooth_pitch_curve(result: MelodyResult, window_length: int = 11, polyorder: int = 2) -> MelodyResult:
    """Apply Savitzky-Golay smoothing to pitch curve."""
    if len(result.pitch_curve) < window_length:
        return result

    hz_vals = np.array([pt["hz"] for pt in result.pitch_curve])
    voiced_mask = hz_vals > 0

    if voiced_mask.sum() < window_length:
        return result

    # Only smooth voiced regions
    hz_smoothed = hz_vals.copy()
    try:
        wl = window_length if window_length % 2 == 1 else window_length + 1
        smoothed_all = savgol_filter(hz_vals, wl, polyorder)
        hz_smoothed[voiced_mask] = np.maximum(0, smoothed_all[voiced_mask])
    except Exception:
        pass

    smoothed_curve = [
        {"time": pt["time"], "hz": round(float(hz_smoothed[i]), 2), "conf": pt["conf"]}
        for i, pt in enumerate(result.pitch_curve)
    ]

    return MelodyResult(
        pitch_curve=smoothed_curve,
        notes=result.notes,
        global_confidence=result.global_confidence,
        voiced_fraction=result.voiced_fraction,
        mean_pitch_hz=result.mean_pitch_hz,
        source=result.source + "_smoothed",
    )


# ─── Key Smoothing ─────────────────────────────────────────────────────────────

def consolidate_key_segments(result: KeyResult, min_duration: float = 15.0) -> KeyResult:
    """
    Remove very short key segments (< min_duration seconds).
    Short segments are merged with the previous one.
    """
    if not result.segments:
        return result

    segments = list(result.segments)
    merged: List[KeySegment] = []

    for seg in segments:
        dur = seg.end - seg.start
        if merged and dur < min_duration:
            prev = merged[-1]
            merged[-1] = KeySegment(
                start=prev.start,
                end=seg.end,
                key=prev.key,
                mode=prev.mode,
                confidence=round((prev.confidence + seg.confidence) / 2, 3),
            )
        else:
            merged.append(seg)

    # Redetect modulations from consolidated segments
    from analysis.key_detector import _detect_modulations
    modulations = _detect_modulations(merged)

    return KeyResult(
        global_key=result.global_key,
        global_mode=result.global_mode,
        global_confidence=result.global_confidence,
        segments=merged,
        modulations=modulations,
        alternatives=result.alternatives,
        source=result.source + "_smoothed",
    )
