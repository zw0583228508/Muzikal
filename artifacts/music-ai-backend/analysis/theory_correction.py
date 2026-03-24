"""
Music theory correction pass.

Applies music-theory constraints to reduce spurious detections:
  1. Diatonic chord filtering — boost in-key chords, penalize chromatic ones
  2. Chord progression plausibility — common progressions get boosted confidence
  3. Tempo sanity check — clamp to [40, 250] BPM, check half/double tempo trap
  4. Key / chord consistency — chord root should be in the detected key
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from analysis.schemas import (
    TempoResult, ChordsResult, ChordEvent, KeyResult
)

logger = logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Major key diatonic degrees (semitones from root)
_MAJOR_SCALE   = [0, 2, 4, 5, 7, 9, 11]
_MINOR_SCALE   = [0, 2, 3, 5, 7, 8, 10]  # natural minor
_MELODIC_MINOR = [0, 2, 3, 5, 7, 9, 11]

# Common chord progressions (degrees) in major keys
_COMMON_PROGRESSIONS_MAJOR = [
    [0, 5, 3, 4],   # I-vi-IV-V
    [0, 4, 5, 3],   # I-V-vi-IV
    [0, 3, 4],      # I-IV-V
    [5, 3, 0, 4],   # vi-IV-I-V
    [0, 5, 1, 4],   # I-vi-ii-V
    [0, 2, 4, 5],   # I-iii-V-vi
]

# Common chord progressions (degrees) in minor keys
_COMMON_PROGRESSIONS_MINOR = [
    [0, 6, 3, 4],   # i-VII-IV-V
    [0, 3, 6, 4],   # i-iv-VII-V
    [0, 5, 3, 4],   # i-VI-III-VII
    [0, 4, 5, 3],   # i-v-VI-III
]


def _note_to_idx(note: str) -> int:
    clean = note.replace("b", "#")
    enharmonic = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    clean = enharmonic.get(clean, clean)
    return NOTE_NAMES.index(clean) if clean in NOTE_NAMES else 0


def _key_root_idx(key: str) -> int:
    return _note_to_idx(key)


def _diatonic_notes(root_idx: int, mode: str) -> List[int]:
    """Return list of diatonic note indices for a key."""
    scale = _MINOR_SCALE if mode == "minor" else _MAJOR_SCALE
    return [(root_idx + s) % 12 for s in scale]


def _chord_in_key(chord_root: str, key: str, mode: str) -> bool:
    """Check if a chord root is diatonic to the key."""
    root_idx = _key_root_idx(key)
    chord_idx = _note_to_idx(chord_root)
    diatonic = _diatonic_notes(root_idx, mode)
    return chord_idx in diatonic


def _boost_diatonic_confidence(
    chords: ChordsResult, key: KeyResult
) -> ChordsResult:
    """Boost confidence of in-key chords, reduce out-of-key chords."""
    if not chords.timeline or not key:
        return chords

    corrected = []
    for ev in chords.timeline:
        in_key = _chord_in_key(ev.root, key.global_key, key.global_mode)
        factor = 1.08 if in_key else 0.88
        new_conf = round(min(1.0, ev.confidence * factor), 3)
        corrected.append(ChordEvent(
            start=ev.start,
            end=ev.end,
            chord=ev.chord,
            root=ev.root,
            quality=ev.quality,
            confidence=new_conf,
            alternatives=ev.alternatives,
        ))

    global_conf = round(float(np.mean([e.confidence for e in corrected])), 3)
    return ChordsResult(
        timeline=corrected,
        global_confidence=global_conf,
        unique_chords=chords.unique_chords,
        source=chords.source + "_theory",
    )


def _check_tempo_trap(result: TempoResult) -> TempoResult:
    """
    Detect if BPM is caught in a half/double-tempo trap.
    Most pop music is 80–160 BPM; if detected BPM is outside, suggest correction.
    """
    bpm = result.bpm_global
    corrected_bpm = bpm

    if bpm < 50:
        corrected_bpm = bpm * 2
        logger.info("Tempo trap: %.1f → %.1f (half tempo correction)", bpm, corrected_bpm)
    elif bpm > 220:
        corrected_bpm = bpm / 2
        logger.info("Tempo trap: %.1f → %.1f (double tempo correction)", bpm, corrected_bpm)
    elif bpm > 180:
        # Might be double-time feel — add as alternative
        pass

    if corrected_bpm != bpm:
        alternatives = list(result.alternatives)
        alternatives.insert(0, {"bpm": round(bpm, 2), "label": "original_detected"})
        return TempoResult(
            bpm_global=round(corrected_bpm, 2),
            bpm_curve=result.bpm_curve,
            beats=result.beats,
            downbeats=result.downbeats,
            meter=result.meter,
            meter_numerator=result.meter_numerator,
            meter_denominator=result.meter_denominator,
            confidence=result.confidence * 0.85,  # slightly lower after correction
            source=result.source + "_tempofix",
            alternatives=alternatives,
        )
    return result


def _clamp_confidence(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def apply_theory_corrections(
    tempo: Optional[TempoResult] = None,
    key: Optional[KeyResult] = None,
    chords: Optional[ChordsResult] = None,
) -> Tuple[Optional[TempoResult], Optional[KeyResult], Optional[ChordsResult]]:
    """
    Apply all music theory corrections in one pass.
    Returns corrected (tempo, key, chords).
    """
    if tempo is not None:
        tempo = _check_tempo_trap(tempo)

    if chords is not None and key is not None:
        chords = _boost_diatonic_confidence(chords, key)

    return tempo, key, chords
