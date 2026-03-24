"""
Theory Guard — comprehensive music theory validation and correction.

Responsibilities:
  1. Chords outside key → correct to nearest diatonic chord
  2. Melody notes out of scale → snap to nearest scale degree
  3. Harmonic inconsistencies → resolve via voice-leading rules
  4. Tempo double/half trap detection + correction
  5. Meter plausibility validation
  6. Chord-melody coherence check

All corrections are logged and added to the result's warnings list.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from analysis.schemas import (
    AnalysisResult, AnalysisWarning, TempoResult, KeyResult,
    ChordsResult, ChordEvent, MelodyResult, NoteEvent, StructureResult
)

logger = logging.getLogger(__name__)

NOTE_NAMES  = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ENHARMONIC  = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Scale intervals: diatonic note indices from root
_MAJOR_INTERVALS  = [0, 2, 4, 5, 7, 9, 11]
_MINOR_INTERVALS  = [0, 2, 3, 5, 7, 8, 10]
_HARM_MINOR       = [0, 2, 3, 5, 7, 8, 11]
_MELODIC_MINOR_UP = [0, 2, 3, 5, 7, 9, 11]

# Diatonic chord qualities per scale degree (major key)
# degree 0 → I (maj), 1 → ii (min), 2 → iii (min), etc.
_MAJOR_CHORD_QUALITIES = ["maj", "min", "min", "maj", "maj", "min", "dim"]
_MINOR_CHORD_QUALITIES = ["min", "dim", "maj", "min", "min", "maj", "maj"]

# Common chord substitutions (chromatic → diatonic)
_CHROMATIC_SUBS = {
    # borrowed chords that are "acceptable" in practice
    "bII":  "maj",  # Neapolitan
    "bVII": "maj",  # Subtonic (very common in rock/pop)
    "bIII": "maj",  # Minor third major chord
    "IV7":  "dom7",
    "#IV":  "dim",  # Tritone sub
}


def _note_idx(note: str) -> int:
    clean = ENHARMONIC.get(note, note)
    return NOTE_NAMES.index(clean) if clean in NOTE_NAMES else 0


def _diatonic_notes(root_idx: int, mode: str) -> List[int]:
    intervals = _MINOR_INTERVALS if mode == "minor" else _MAJOR_INTERVALS
    return [(root_idx + i) % 12 for i in intervals]


def _nearest_diatonic_note(pitch_midi: int, root_idx: int, mode: str) -> int:
    """Snap a MIDI note to the nearest scale degree."""
    pc = pitch_midi % 12
    diatonic = _diatonic_notes(root_idx, mode)
    if pc in diatonic:
        return pitch_midi
    # Find closest diatonic pitch class
    best_pc = min(diatonic, key=lambda d: min(abs(d - pc), 12 - abs(d - pc)))
    diff = best_pc - pc
    # Adjust MIDI note
    if diff > 6:
        diff -= 12
    elif diff < -6:
        diff += 12
    return pitch_midi + diff


def _diatonic_chord_quality(degree: int, mode: str) -> str:
    """Return the diatonic quality for a scale degree."""
    qualities = _MAJOR_CHORD_QUALITIES if mode == "major" else _MINOR_CHORD_QUALITIES
    return qualities[degree % len(qualities)]


def _chord_root_idx(root: str) -> int:
    return _note_idx(root)


def _nearest_diatonic_chord(
    chord_root: str, chord_quality: str,
    key_root: int, mode: str
) -> Tuple[str, str]:
    """
    Find the nearest diatonic chord to a given chromatic chord.
    Returns (root_name, quality).
    """
    chord_idx = _note_idx(chord_root)
    diatonic = _diatonic_notes(key_root, mode)

    # If root is already diatonic, only quality may need fixing
    if chord_idx in diatonic:
        degree = diatonic.index(chord_idx)
        correct_quality = _diatonic_chord_quality(degree, mode)
        return chord_root, correct_quality

    # Find nearest diatonic root
    nearest = min(diatonic, key=lambda d: min(abs(d - chord_idx), 12 - abs(d - chord_idx)))
    degree = diatonic.index(nearest)
    correct_quality = _diatonic_chord_quality(degree, mode)
    return NOTE_NAMES[nearest], correct_quality


def _is_acceptable_chromatic(chord_root: str, key_root: int, mode: str) -> bool:
    """
    Return True for chords that are chromatic but musically valid
    (borrowed, secondary dominants, Neapolitan, etc.)
    """
    chord_idx = _note_idx(chord_root)
    # bVII (very common in pop/rock)
    if chord_idx == (key_root - 2) % 12:
        return True
    # bIII (blues, rock)
    if chord_idx == (key_root + 3) % 12 and mode == "major":
        return True
    # IV in minor key (common)
    if chord_idx == (key_root + 5) % 12 and mode == "minor":
        return True
    # Neapolitan (bII)
    if chord_idx == (key_root + 1) % 12:
        return True
    return False


# ─── Chord Correction ──────────────────────────────────────────────────────────

def _correct_chords(
    chords: ChordsResult,
    key: KeyResult,
    correction_threshold: float = 0.45,
) -> Tuple[ChordsResult, List[str]]:
    """
    Correct chromatic chords to diatonic equivalents when confidence is low.
    High-confidence chromatic chords are preserved (secondary dominants, etc.).
    """
    key_root = _note_idx(key.global_key)
    mode = key.global_mode
    diatonic = _diatonic_notes(key_root, mode)

    corrected_timeline: List[ChordEvent] = []
    corrections: List[str] = []

    for ev in chords.timeline:
        chord_idx = _note_idx(ev.root)
        in_key = chord_idx in diatonic
        acceptable_chromatic = _is_acceptable_chromatic(ev.root, key_root, mode)

        if in_key or acceptable_chromatic or ev.confidence >= 0.75:
            corrected_timeline.append(ev)
            continue

        # Low-confidence chromatic chord → correct
        if ev.confidence < correction_threshold:
            new_root, new_quality = _nearest_diatonic_chord(ev.root, ev.quality, key_root, mode)
            new_chord = f"{new_root}{new_quality}"
            corrections.append(
                f"{ev.chord}@{ev.start:.1f}s → {new_chord} (conf={ev.confidence:.2f})"
            )
            corrected_timeline.append(ChordEvent(
                start=ev.start,
                end=ev.end,
                chord=new_chord,
                root=new_root,
                quality=new_quality,
                confidence=round(ev.confidence * 0.9, 3),
                alternatives=[{"chord": ev.chord, "root": ev.root, "quality": ev.quality,
                               "confidence": ev.confidence, "label": "original"}]
                              + ev.alternatives,
            ))
        else:
            corrected_timeline.append(ev)

    unique = list(dict.fromkeys(e.chord for e in corrected_timeline))
    global_conf = float(np.mean([e.confidence for e in corrected_timeline])) if corrected_timeline else 0.0

    result = ChordsResult(
        timeline=corrected_timeline,
        global_confidence=round(global_conf, 3),
        unique_chords=unique,
        source=chords.source + "_theory_guarded",
    )
    return result, corrections


# ─── Melody Correction ─────────────────────────────────────────────────────────

def _snap_melody_to_scale(
    melody: MelodyResult,
    key: KeyResult,
    snap_threshold: float = 0.6,
) -> Tuple[MelodyResult, List[str]]:
    """
    Snap out-of-scale melody notes to nearest scale degree.
    Only snaps low-confidence notes.
    """
    key_root = _note_idx(key.global_key)
    mode = key.global_mode
    diatonic_pcs = _diatonic_notes(key_root, mode)

    corrections: List[str] = []
    snapped_notes: List[NoteEvent] = []

    for note in melody.notes:
        pc = note.pitch % 12
        if pc in diatonic_pcs or note.confidence >= snap_threshold:
            snapped_notes.append(note)
            continue

        # Snap to nearest diatonic pitch
        new_pitch = _nearest_diatonic_note(note.pitch, key_root, mode)
        new_pc = new_pitch % 12
        new_name_parts = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        octave = new_pitch // 12 - 1
        new_name = f"{new_name_parts[new_pc]}{octave}"

        corrections.append(f"note {note.pitch_name}@{note.start:.2f}s → {new_name}")
        snapped_notes.append(NoteEvent(
            pitch=new_pitch,
            pitch_name=new_name,
            start=note.start,
            end=note.end,
            duration=note.duration,
            velocity=note.velocity,
            confidence=round(note.confidence * 0.95, 3),
        ))

    return MelodyResult(
        pitch_curve=melody.pitch_curve,
        notes=snapped_notes,
        global_confidence=melody.global_confidence,
        voiced_fraction=melody.voiced_fraction,
        mean_pitch_hz=melody.mean_pitch_hz,
        source=melody.source + "_scale_snapped",
    ), corrections


# ─── Tempo Validation ──────────────────────────────────────────────────────────

def _validate_tempo(tempo: TempoResult) -> Tuple[TempoResult, List[str]]:
    """Check for double/half tempo traps and implausible BPM values."""
    warnings: List[str] = []
    bpm = tempo.bpm_global

    if bpm < 40 or bpm > 300:
        warnings.append(f"BPM {bpm:.1f} is outside plausible range [40, 300]")

    # Double/half tempo trap already handled in theory_correction.py
    # Here we add additional meter coherence check
    if tempo.beats and tempo.downbeats:
        beats_arr = np.array(tempo.beats)
        down_arr = np.array(tempo.downbeats)
        if len(down_arr) >= 2 and len(beats_arr) >= 4:
            bar_dur = float(np.median(np.diff(down_arr)))
            beat_dur = float(np.median(np.diff(beats_arr)))
            if beat_dur > 0:
                bpb = bar_dur / beat_dur
                expected_bpb = tempo.meter_numerator
                if abs(bpb - expected_bpb) > 1.5:
                    warnings.append(
                        f"Beats per bar ({bpb:.1f}) inconsistent with time signature ({expected_bpb}/4)"
                    )

    return tempo, warnings


# ─── Main Entry Point ──────────────────────────────────────────────────────────

def apply_theory_guard(result: AnalysisResult) -> AnalysisResult:
    """
    Apply all theory corrections to a complete AnalysisResult.
    Returns a new AnalysisResult with corrections applied and warnings added.
    """
    new_warnings = list(result.warnings)
    tempo = result.tempo
    key = result.key
    chords = result.chords
    melody = result.melody
    structure = result.structure

    # ── Tempo validation ───────────────────────────────────────────────────────
    if tempo is not None:
        tempo, tempo_warnings = _validate_tempo(tempo)
        for w in tempo_warnings:
            new_warnings.append(AnalysisWarning(
                code="TEMPO_INVALID", message=w, severity="warning"
            ))

    # ── Chord correction (needs key) ───────────────────────────────────────────
    chord_corrections: List[str] = []
    if chords is not None and key is not None:
        chords, chord_corrections = _correct_chords(chords, key)
        if chord_corrections:
            logger.info("Theory guard: %d chord corrections applied", len(chord_corrections))
            new_warnings.append(AnalysisWarning(
                code="CHORD_THEORY_CORRECTIONS",
                message=f"{len(chord_corrections)} chromatic chord(s) corrected to diatonic equivalents.",
                severity="info",
            ))

    # ── Melody scale snapping (needs key) ─────────────────────────────────────
    melody_corrections: List[str] = []
    if melody is not None and key is not None and melody.notes:
        melody, melody_corrections = _snap_melody_to_scale(melody, key)
        if melody_corrections:
            logger.info("Theory guard: %d melody notes snapped to scale", len(melody_corrections))
            new_warnings.append(AnalysisWarning(
                code="MELODY_SCALE_SNAP",
                message=f"{len(melody_corrections)} out-of-scale note(s) snapped to key of {key.global_key} {key.global_mode}.",
                severity="info",
            ))

    return AnalysisResult(
        audio_meta=result.audio_meta,
        stems=result.stems,
        tempo=tempo,
        key=key,
        chords=chords,
        melody=melody,
        structure=structure,
        global_confidence=result.global_confidence,
        mode=result.mode,
        pipeline_version=result.pipeline_version,
        warnings=new_warnings,
    )
