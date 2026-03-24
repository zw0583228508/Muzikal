"""
Harmonic Intelligence Layer — Chord Classifier v1.0

Post-processes a raw ChordsResult with key-aware harmonic analysis:
  1. Scale-degree labelling     (which diatonic/chromatic degree each chord root is)
  2. Harmonic-function labelling (tonic / subdominant / dominant / secondary / chromatic)
  3. Bigram transition scoring  (re-rank alternatives using key-conditional transition matrix)
  4. Cadence detection          (authentic, half, plagal, deceptive, evaded)
  5. Diatonic-ratio + harmonic-rhythm statistics

No ML weights required — uses music-theory hand-crafted statistical models.
Call `classify(chords_result, key_result) -> ChordsResult` from pipeline.py.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from analysis.schemas import (
    CadenceEvent,
    ChordEvent,
    ChordsResult,
    KeyResult,
)

logger = logging.getLogger(__name__)

# ─── Scale tables ─────────────────────────────────────────────────────────────
# Map scale degree index (0=I … 6=VII) to semitone offset from root.

_MAJOR_SCALE   = [0, 2, 4, 5, 7, 9, 11]
_MINOR_SCALE   = [0, 2, 3, 5, 7, 8, 10]   # natural minor
_DORIAN_SCALE  = [0, 2, 3, 5, 7, 9, 10]
_PHRYGIAN_SCALE= [0, 1, 3, 5, 7, 8, 10]
_LYDIAN_SCALE  = [0, 2, 4, 6, 7, 9, 11]
_MIXOLYDIAN_SCALE=[0, 2, 4, 5, 7, 9, 10]
_LOCRIAN_SCALE = [0, 1, 3, 5, 6, 8, 10]

_SCALE_INTERVALS: Dict[str, List[int]] = {
    "major":         _MAJOR_SCALE,
    "minor":         _MINOR_SCALE,
    "dorian":        _DORIAN_SCALE,
    "phrygian":      _PHRYGIAN_SCALE,
    "lydian":        _LYDIAN_SCALE,
    "mixolydian":    _MIXOLYDIAN_SCALE,
    "locrian":       _LOCRIAN_SCALE,
    "harmonic_minor":[0, 2, 3, 5, 7, 8, 11],
    "freygish":      [0, 1, 4, 5, 7, 8, 10],  # harmonic minor on V = phrygian dominant
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_ENHARMONIC: Dict[str, str] = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B",
    "E#": "F",  "B#": "C",
}

# ─── Harmonic function maps ───────────────────────────────────────────────────
# Degree index (0=I … 6=VII) → function in major / minor key

_FUNC_MAJOR: Dict[int, str] = {
    0: "tonic",       # I
    1: "subdominant", # II
    2: "tonic",       # III (mediant)
    3: "subdominant", # IV
    4: "dominant",    # V
    5: "tonic",       # VI (submediant, relative minor)
    6: "dominant",    # VII°
}

_FUNC_MINOR: Dict[int, str] = {
    0: "tonic",       # i
    1: "subdominant", # ii°
    2: "tonic",       # III (relative major)
    3: "subdominant", # iv
    4: "dominant",    # V (major V in harmonic minor)
    5: "subdominant", # VI (flat-VI)
    6: "dominant",    # VII°
}

# ─── Bigram transition matrix ─────────────────────────────────────────────────
# (from_function, to_function) → weight (higher = more expected)
# Based on tonal tension-resolution principle (Rameau, Riemann, etc.)

_BIGRAM_WEIGHTS: Dict[Tuple[str, str], float] = {
    ("tonic",       "tonic"):       0.7,
    ("tonic",       "subdominant"): 0.9,
    ("tonic",       "dominant"):    0.8,
    ("tonic",       "secondary"):   0.6,
    ("tonic",       "chromatic"):   0.4,

    ("subdominant", "tonic"):       0.7,
    ("subdominant", "subdominant"): 0.6,
    ("subdominant", "dominant"):    0.95,  # IV→V or II→V
    ("subdominant", "secondary"):   0.5,
    ("subdominant", "chromatic"):   0.4,

    ("dominant",    "tonic"):       0.98,  # V→I — strongest resolution
    ("dominant",    "tonic"):       0.98,
    ("dominant",    "subdominant"): 0.3,   # unusual but possible
    ("dominant",    "dominant"):    0.5,   # V of V
    ("dominant",    "secondary"):   0.55,
    ("dominant",    "chromatic"):   0.35,

    ("secondary",   "tonic"):       0.65,
    ("secondary",   "subdominant"): 0.6,
    ("secondary",   "dominant"):    0.75,
    ("secondary",   "secondary"):   0.5,
    ("secondary",   "chromatic"):   0.5,

    ("chromatic",   "tonic"):       0.5,
    ("chromatic",   "subdominant"): 0.5,
    ("chromatic",   "dominant"):    0.55,
    ("chromatic",   "secondary"):   0.45,
    ("chromatic",   "chromatic"):   0.4,
}


def _normalize_note(name: str) -> str:
    """Convert enharmonic spellings to sharp form."""
    return _ENHARMONIC.get(name, name)


def _note_to_idx(name: str) -> int:
    name = _normalize_note(name)
    try:
        return NOTE_NAMES.index(name)
    except ValueError:
        return 0


def _scale_degrees_for_key(key: str, mode: str) -> List[int]:
    """Return list of semitone offsets (from 0) for each diatonic degree."""
    intervals = _SCALE_INTERVALS.get(mode.lower(), _MAJOR_SCALE)
    root_idx = _note_to_idx(key)
    return [(root_idx + iv) % 12 for iv in intervals]


def _get_scale_degree(root: str, key: str, mode: str) -> Optional[int]:
    """
    Return 1-based scale degree (1=I … 7=VII) if root is diatonic, else None.
    """
    root_idx = _note_to_idx(root)
    degrees = _scale_degrees_for_key(key, mode)
    for i, deg in enumerate(degrees):
        if deg == root_idx:
            return i + 1  # 1-based
    return None


def _harmonic_function(scale_degree: Optional[int], mode: str) -> str:
    """Map scale degree → harmonic function label."""
    if scale_degree is None:
        return "chromatic"
    func_map = _FUNC_MINOR if mode.lower() in ("minor", "dorian", "phrygian", "freygish",
                                                 "harmonic_minor", "locrian") else _FUNC_MAJOR
    return func_map.get(scale_degree - 1, "chromatic")


def _bigram_boost(prev_func: Optional[str], curr_func: str) -> float:
    """Transition likelihood boost factor [0, 1]."""
    if prev_func is None:
        return 1.0
    return _BIGRAM_WEIGHTS.get((prev_func, curr_func), 0.5)


# ─── Cadence detection ────────────────────────────────────────────────────────

_CADENCE_PATTERNS: List[Tuple[str, str, str, float]] = [
    # (prev_func, curr_func, kind, strength)
    ("dominant",    "tonic",       "authentic", 0.95),
    ("subdominant", "tonic",       "plagal",    0.80),
    ("subdominant", "dominant",    "half",      0.70),
    ("tonic",       "dominant",    "half",      0.55),
    ("dominant",    "subdominant", "deceptive", 0.65),
    ("dominant",    "secondary",   "evaded",    0.50),
]


def _detect_cadences(timeline: List[ChordEvent]) -> List[CadenceEvent]:
    """Detect cadential patterns in a labelled chord timeline."""
    cadences: List[CadenceEvent] = []

    for i in range(1, len(timeline)):
        prev = timeline[i - 1]
        curr = timeline[i]
        pf = prev.harmonic_function or "chromatic"
        cf = curr.harmonic_function or "chromatic"

        for prev_func, curr_func, kind, strength in _CADENCE_PATTERNS:
            if pf == prev_func and cf == curr_func:
                # Confidence-weighted strength
                w_strength = round(strength * 0.5 * (prev.confidence + curr.confidence), 3)
                cadences.append(CadenceEvent(
                    kind=kind,
                    start=prev.start,
                    end=curr.end,
                    chords=[prev.chord, curr.chord],
                    strength=w_strength,
                ))
                break  # one cadence per boundary

    return cadences


# ─── Public API ───────────────────────────────────────────────────────────────

def classify(chords: ChordsResult, key: Optional[KeyResult]) -> ChordsResult:
    """
    Enrich a ChordsResult with harmonic-function labels, cadences, and stats.

    Args:
        chords:  Raw output from chord_detector.detect_chords()
        key:     Key/mode from key_detector (may be None — safe fallback to C major)

    Returns:
        A new ChordsResult with `harmonic_function`, `scale_degree`,
        `cadences`, `harmonic_rhythm`, and `diatonic_ratio` populated.
    """
    if not chords.timeline:
        return chords

    global_key  = key.global_key  if key else "C"
    global_mode = key.global_mode if key else "major"

    logger.info(
        "[chord_classifier] Labelling %d events in %s %s",
        len(chords.timeline), global_key, global_mode,
    )

    labelled: List[ChordEvent] = []
    prev_func: Optional[str] = None
    diatonic_count = 0

    for ev in chords.timeline:
        sd = _get_scale_degree(ev.root, global_key, global_mode)
        func = _harmonic_function(sd, global_mode)

        # Apply bigram boost to confidence
        boost = _bigram_boost(prev_func, func)
        adjusted_conf = round(min(1.0, ev.confidence * (0.85 + 0.15 * boost)), 3)

        labelled.append(ChordEvent(
            start=ev.start,
            end=ev.end,
            chord=ev.chord,
            root=ev.root,
            quality=ev.quality,
            confidence=adjusted_conf,
            alternatives=ev.alternatives,
            harmonic_function=func,
            scale_degree=sd,
        ))

        if sd is not None:
            diatonic_count += 1
        prev_func = func

    # Detect cadences
    cadences = _detect_cadences(labelled)

    # Harmonic rhythm: mean chord duration in seconds
    total_dur = sum(e.end - e.start for e in labelled)
    harm_rhythm = round(total_dur / len(labelled), 3) if labelled else 0.0

    diatonic_ratio = round(diatonic_count / len(labelled), 3) if labelled else 0.0

    logger.info(
        "[chord_classifier] Done — %d cadences, diatonic=%.0f%%, harm_rhythm=%.2fs",
        len(cadences), diatonic_ratio * 100, harm_rhythm,
    )

    return ChordsResult(
        timeline=labelled,
        global_confidence=round(
            sum(e.confidence for e in labelled) / len(labelled), 3
        ),
        unique_chords=chords.unique_chords,
        source=chords.source + "+classifier",
        cadences=cadences,
        harmonic_rhythm=harm_rhythm,
        diatonic_ratio=diatonic_ratio,
    )
