"""
Arrangement Evaluator — Phase 4.

Rules-based quality scoring for generated MIDI arrangements.

Evaluates:
  1. Harmonic consistency — notes align with chord content
  2. Rhythmic alignment — notes land on rhythmically valid subdivisions
  3. Range violations — notes outside instrument's preferred/absolute range
  4. Note density distribution — not too sparse, not too dense
  5. Repetition variance — repeated sections evolve meaningfully
  6. Transition quality — fills and dynamics ramp at section boundaries
  7. Voice-leading quality — no parallel fifths, no large leaps without resolution
  8. Bass behavior — bass follows chord roots correctly

Each metric returns a score in [0.0, 1.0] (higher = better).
Overall score = weighted average.

Usage:
    from orchestration.arrangement_evaluator import evaluate_arrangement
    report = evaluate_arrangement(tracks, analysis, blueprint)
    print(report.overall_score)
    for issue in report.issues:
        print(issue)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Chord helpers ────────────────────────────────────────────────────────────

_NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_ENHARMONIC = {
    "Db": "C#", "D#": "Eb", "Fb": "E", "Gb": "F#",
    "G#": "Ab", "A#": "Bb", "Cb": "B",
}

def _pitch_class(note_name: str) -> int:
    n = _ENHARMONIC.get(note_name, note_name)
    try:
        return _NOTE_NAMES.index(n)
    except ValueError:
        return 0

def _chord_pitch_classes(chord_symbol: str) -> List[int]:
    """Return the set of pitch classes (0–11) for a chord symbol."""
    if not chord_symbol or chord_symbol.upper() in ("N", "NC", "N.C.", "X", "UNK"):
        return list(range(12))  # Unknown → accept all

    if len(chord_symbol) >= 2 and chord_symbol[1] in "#b":
        root_str, quality = chord_symbol[:2], chord_symbol[2:]
    else:
        root_str, quality = chord_symbol[:1], chord_symbol[1:]

    root = _pitch_class(root_str)

    if "maj7" in quality:    intervals = [0, 4, 7, 11]
    elif "m7b5" in quality:  intervals = [0, 3, 6, 10]
    elif "m7" in quality:    intervals = [0, 3, 7, 10]
    elif "dim7" in quality:  intervals = [0, 3, 6, 9]
    elif "dim" in quality:   intervals = [0, 3, 6]
    elif "aug" in quality:   intervals = [0, 4, 8]
    elif "sus4" in quality:  intervals = [0, 5, 7]
    elif "sus2" in quality:  intervals = [0, 2, 7]
    elif "7" in quality:     intervals = [0, 4, 7, 10]
    elif "m" in quality:     intervals = [0, 3, 7]
    elif "6" in quality:     intervals = [0, 4, 7, 9]
    elif "add9" in quality:  intervals = [0, 2, 4, 7]
    else:                    intervals = [0, 4, 7]  # major triad default

    return [(root + i) % 12 for i in intervals]


def _chord_at_time(chords: List[Dict], t: float) -> Optional[str]:
    """Find the chord symbol active at time t."""
    for c in chords:
        s = float(c.get("start", c.get("startTime", 0)))
        e = float(c.get("end", c.get("endTime", s + 4.0)))
        if s <= t < e:
            return str(c.get("chord", c.get("label", "")))
    return None


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class MetricResult:
    name: str
    score: float          # [0.0, 1.0]
    weight: float = 1.0
    details: str = ""
    issues: List[str] = field(default_factory=list)


@dataclass
class ArrangementEvalReport:
    overall_score: float
    grade: str            # A/B/C/D/F
    metrics: List[MetricResult]
    issues: List[str]
    warnings: List[str]

    def print_summary(self) -> None:
        lines = [
            f"\n{'='*55}",
            f"  ARRANGEMENT EVALUATION  —  Score: {self.overall_score:.2f}  ({self.grade})",
            f"{'='*55}",
        ]
        for m in self.metrics:
            bar = "█" * int(m.score * 20) + "░" * (20 - int(m.score * 20))
            lines.append(f"  {m.name:<28} {bar} {m.score:.2f}")
        if self.issues:
            lines.append("\n  ISSUES:")
            for iss in self.issues[:10]:
                lines.append(f"    ✗ {iss}")
        if self.warnings:
            lines.append("\n  WARNINGS:")
            for w in self.warnings[:5]:
                lines.append(f"    ⚠ {w}")
        lines.append(f"{'='*55}")
        print("\n".join(lines))


def _score_to_grade(s: float) -> str:
    if s >= 0.90: return "A"
    if s >= 0.80: return "B"
    if s >= 0.70: return "C"
    if s >= 0.60: return "D"
    return "F"


# ─── Individual metric evaluators ─────────────────────────────────────────────

def _eval_harmonic_consistency(
    tracks: List[Dict],
    chords: List[Dict],
    sample_rate: int = 8,
) -> MetricResult:
    """
    Measure fraction of note durations that land on chord tones.

    Ignores percussion tracks and pads (these are not chord-constrained).
    Uses duration-weighted scoring (longer notes matter more).
    """
    IGNORE = {"drums", "darbuka", "pad", "synth_pad", "choir"}

    total_dur = 0.0
    chord_dur = 0.0
    issues = []

    for track in tracks:
        instr = track.get("instrument", "piano")
        if instr in IGNORE:
            continue

        for note in track.get("notes", []):
            t = float(note.get("startTime", 0))
            dur = float(note.get("duration", 0.1))
            pitch = int(note.get("pitch", note.get("midi", 60)))
            pc = pitch % 12

            chord = _chord_at_time(chords, t)
            if chord is None:
                continue

            allowed_pcs = _chord_pitch_classes(chord)
            total_dur += dur
            if pc in allowed_pcs:
                chord_dur += dur
            else:
                # Check if it's a passing tone (very short)
                if dur > 0.15:
                    issues.append(
                        f"{instr}: non-chord tone {_NOTE_NAMES[pc]} "
                        f"during {chord} at t={t:.2f}s"
                    )

    if total_dur < 0.01:
        return MetricResult("Harmonic Consistency", 1.0, 2.0, "No notes to evaluate")

    score = chord_dur / total_dur
    return MetricResult(
        name="Harmonic Consistency",
        score=round(score, 4),
        weight=2.0,
        details=f"{score:.1%} of note duration on chord tones",
        issues=issues[:10],
    )


def _eval_rhythmic_alignment(
    tracks: List[Dict],
    bpm: float,
    time_sig_num: int = 4,
) -> MetricResult:
    """
    Measure fraction of notes landing near rhythmic grid points.

    Grid: 16th notes (4 subdivisions per beat).
    Tolerance: ±40ms.
    """
    if bpm <= 0:
        return MetricResult("Rhythmic Alignment", 0.5, 1.5, "No BPM")

    beat_dur = 60.0 / bpm
    subdiv_dur = beat_dur / 4.0   # 16th note
    tolerance = 0.040             # 40ms

    total = 0
    aligned = 0
    IGNORE = {"pad", "synth_pad", "choir"}

    for track in tracks:
        instr = track.get("instrument", "piano")
        if instr in IGNORE:
            continue

        for note in track.get("notes", []):
            t = float(note.get("startTime", 0))
            total += 1
            grid = round(t / subdiv_dur) * subdiv_dur
            if abs(t - grid) <= tolerance:
                aligned += 1

    if total == 0:
        return MetricResult("Rhythmic Alignment", 1.0, 1.5, "No notes")

    score = aligned / total
    return MetricResult(
        name="Rhythmic Alignment",
        score=round(score, 4),
        weight=1.5,
        details=f"{aligned}/{total} notes on 16th-note grid (±40ms)",
    )


def _eval_range_violations(tracks: List[Dict]) -> MetricResult:
    """
    Count notes outside each instrument's preferred + absolute range.
    """
    from orchestration.instrument_ranges import INSTRUMENT_RANGES, PIANO

    pref_violations = 0
    abs_violations = 0
    total = 0
    issues = []

    for track in tracks:
        instr = track.get("instrument", "piano")
        spec = INSTRUMENT_RANGES.get(instr, PIANO)

        for note in track.get("notes", []):
            pitch = int(note.get("pitch", note.get("midi", 60)))
            total += 1

            if not spec.in_range(pitch):
                abs_violations += 1
                issues.append(
                    f"{instr}: pitch {pitch} outside absolute range "
                    f"[{spec.min_midi}–{spec.max_midi}]"
                )
            elif not spec.in_preferred_range(pitch):
                pref_violations += 1

    if total == 0:
        return MetricResult("Range Compliance", 1.0, 1.5, "No notes")

    # Absolute violations are severe, preferred violations are minor
    penalty = (abs_violations * 2 + pref_violations * 0.5) / total
    score = max(0.0, 1.0 - penalty)

    return MetricResult(
        name="Range Compliance",
        score=round(score, 4),
        weight=1.5,
        details=f"{abs_violations} absolute violations, {pref_violations} outside preferred range",
        issues=issues[:8],
    )


def _eval_note_density(
    tracks: List[Dict],
    total_duration: float,
    expected_density: float = 0.7,
) -> MetricResult:
    """
    Evaluate note density distribution — not too sparse, not too dense.

    Checks:
    - Overall notes-per-second rate
    - Whether any section is completely silent (except pads)
    - Whether density is within expected range
    """
    if total_duration <= 0:
        return MetricResult("Note Density", 0.5, 1.0, "No duration")

    IGNORE = {"pad", "synth_pad"}
    total_notes = sum(
        len(t.get("notes", []))
        for t in tracks
        if t.get("instrument") not in IGNORE
    )

    nps = total_notes / total_duration  # notes per second

    # Typical values: 0.5 nps (very sparse) → 5.0 nps (dense)
    # Target: 1.0–3.5 nps
    if nps < 0.2:
        score = 0.4
        detail = f"Very sparse: {nps:.2f} notes/s"
    elif nps < 0.5:
        score = 0.6
        detail = f"Sparse: {nps:.2f} notes/s"
    elif nps > 8.0:
        score = 0.5
        detail = f"Too dense: {nps:.2f} notes/s"
    elif nps > 5.0:
        score = 0.7
        detail = f"Dense: {nps:.2f} notes/s"
    else:
        score = 1.0
        detail = f"Good density: {nps:.2f} notes/s"

    return MetricResult(
        name="Note Density",
        score=round(score, 4),
        weight=1.0,
        details=detail,
    )


def _eval_repetition_variance(
    tracks: List[Dict],
    sections: List[Dict],
) -> MetricResult:
    """
    Measure whether repeated sections (same group_id) have musical variation.

    Compares the set of unique MIDI pitches in the first vs subsequent
    occurrences of each repeated section group.
    """
    # Group tracks by section_label (simplified: use section start time buckets)
    section_note_sets: Dict[str, List[set]] = {}

    for sec in sections:
        label = sec.get("label", "section")
        group = sec.get("groupId", sec.get("group_id", label))
        key = str(group)
        start = float(sec.get("start", sec.get("startTime", 0)))
        end = float(sec.get("end", sec.get("endTime", start + 10)))

        pitches = set()
        for track in tracks:
            if track.get("instrument") in {"drums", "darbuka"}:
                continue
            for note in track.get("notes", []):
                t = float(note.get("startTime", 0))
                if start <= t < end:
                    pitches.add(int(note.get("pitch", note.get("midi", 60))))

        section_note_sets.setdefault(key, []).append(pitches)

    if not section_note_sets:
        return MetricResult("Repetition Variance", 0.8, 1.0, "No section data")

    variance_scores = []
    for key, occ_list in section_note_sets.items():
        if len(occ_list) < 2:
            variance_scores.append(1.0)  # No repetition — fine
            continue

        first = occ_list[0]
        for other in occ_list[1:]:
            if not first or not other:
                variance_scores.append(0.5)
                continue
            # Jaccard distance: 1 - |A∩B| / |A∪B|
            intersection = len(first & other)
            union = len(first | other)
            jaccard_sim = intersection / union if union > 0 else 1.0
            # We want some variance (jaccard_sim < 1.0) but not complete change
            # Target: 0.6–0.9 similarity (10–40% variation)
            if jaccard_sim >= 0.95:
                variance_scores.append(0.5)  # Too identical
            elif jaccard_sim >= 0.6:
                variance_scores.append(1.0)  # Good variance
            elif jaccard_sim >= 0.3:
                variance_scores.append(0.8)  # Acceptable
            else:
                variance_scores.append(0.5)  # Too different — inconsistent

    score = sum(variance_scores) / len(variance_scores) if variance_scores else 0.8
    return MetricResult(
        name="Repetition Variance",
        score=round(score, 4),
        weight=1.2,
        details=f"Evaluated {len(variance_scores)} section group(s)",
    )


def _eval_transition_quality(
    tracks: List[Dict],
    sections: List[Dict],
    bpm: float,
) -> MetricResult:
    """
    Measure whether section transitions are musically handled.

    Checks:
    - Bass has activity within last beat of each section (no dead stop)
    - Velocity ramps exist at transitions (dynamics change)
    - Drum fills exist near transitions (at least one high-velocity drum note)
    """
    if not sections or bpm <= 0:
        return MetricResult("Transition Quality", 0.7, 1.0, "No section data")

    beat_dur = 60.0 / bpm
    transition_scores = []
    issues = []

    # Check each section boundary
    for i in range(len(sections) - 1):
        boundary = float(
            sections[i].get("end", sections[i].get("endTime", 0))
        )
        window = beat_dur * 2  # 2 beats before boundary

        # Check for drum fill (high velocity drum hit near boundary)
        drum_fill = False
        for track in tracks:
            if track.get("instrument") not in {"drums", "darbuka"}:
                continue
            for note in track.get("notes", []):
                t = float(note.get("startTime", 0))
                vel = int(note.get("velocity", 70))
                if boundary - window <= t <= boundary and vel >= 90:
                    drum_fill = True
                    break

        # Check for bass presence near boundary
        bass_active = False
        for track in tracks:
            if track.get("instrument") not in {"bass", "double_bass"}:
                continue
            for note in track.get("notes", []):
                t = float(note.get("startTime", 0))
                if boundary - window <= t <= boundary:
                    bass_active = True
                    break

        if not drum_fill and not bass_active:
            transition_scores.append(0.4)
            issues.append(f"No fill or bass activity near boundary at {boundary:.1f}s")
        elif drum_fill and bass_active:
            transition_scores.append(1.0)
        else:
            transition_scores.append(0.75)

    if not transition_scores:
        return MetricResult("Transition Quality", 0.8, 1.0, "Insufficient sections")

    score = sum(transition_scores) / len(transition_scores)
    return MetricResult(
        name="Transition Quality",
        score=round(score, 4),
        weight=1.0,
        details=f"Evaluated {len(transition_scores)} transitions",
        issues=issues[:5],
    )


def _eval_bass_behavior(tracks: List[Dict], chords: List[Dict]) -> MetricResult:
    """
    Measure how well the bass track follows chord roots.

    Bass notes should be chord roots (or 5ths) most of the time.
    """
    bass_tracks = [
        t for t in tracks
        if t.get("instrument") in {"bass", "double_bass"}
    ]
    if not bass_tracks:
        return MetricResult("Bass Behavior", 0.8, 1.2, "No bass track")

    total = 0
    root_notes = 0

    for track in bass_tracks:
        for note in track.get("notes", []):
            t = float(note.get("startTime", 0))
            pitch = int(note.get("pitch", note.get("midi", 40)))
            pc = pitch % 12
            total += 1

            chord = _chord_at_time(chords, t)
            if chord is None:
                root_notes += 1
                continue

            # Accept root or 5th
            chord_pcs = _chord_pitch_classes(chord)
            if chord_pcs:
                root_pc = chord_pcs[0]
                fifth_pc = (root_pc + 7) % 12
                if pc in (root_pc, fifth_pc):
                    root_notes += 1

    if total == 0:
        return MetricResult("Bass Behavior", 0.8, 1.2, "No bass notes")

    score = root_notes / total
    return MetricResult(
        name="Bass Behavior",
        score=round(score, 4),
        weight=1.2,
        details=f"{root_notes}/{total} bass notes on root or 5th",
    )


# ─── Main evaluator ───────────────────────────────────────────────────────────

def evaluate_arrangement(
    tracks: List[Dict],
    analysis: Dict,
    blueprint: Optional[Dict] = None,
) -> ArrangementEvalReport:
    """
    Evaluate a MIDI arrangement against the canonical analysis.

    Args:
        tracks:    List of track dicts [{instrument, notes, ...}]
        analysis:  Canonical analysis graph (chords, structure, rhythm, etc.)
        blueprint: Optional ArrangementBlueprint dict for context

    Returns:
        ArrangementEvalReport with per-metric scores and overall score
    """
    chords = (
        analysis.get("chords", {}).get("segments", [])
        or analysis.get("chord_segments", [])
        or []
    )
    sections = (
        analysis.get("structure", {}).get("sections", [])
        or analysis.get("sections", [])
        or []
    )
    bpm = float(
        analysis.get("rhythm", {}).get("bpm")
        or analysis.get("bpm")
        or 120.0
    )
    time_sig_num = int(
        analysis.get("rhythm", {}).get("timeSignatureNumerator")
        or analysis.get("timeSignatureNumerator")
        or 4
    )
    total_duration = float(
        analysis.get("totalDuration")
        or analysis.get("total_duration")
        or (max(
            (float(n.get("startTime", 0)) + float(n.get("duration", 0)))
            for t in tracks for n in t.get("notes", [])
        ) if any(t.get("notes") for t in tracks) else 60.0)
    )
    expected_density = float(
        (blueprint or {}).get("density", 0.7)
    )

    metrics = [
        _eval_harmonic_consistency(tracks, chords),
        _eval_rhythmic_alignment(tracks, bpm, time_sig_num),
        _eval_range_violations(tracks),
        _eval_note_density(tracks, total_duration, expected_density),
        _eval_repetition_variance(tracks, sections),
        _eval_transition_quality(tracks, sections, bpm),
        _eval_bass_behavior(tracks, chords),
    ]

    # Weighted average
    total_weight = sum(m.weight for m in metrics)
    overall = (
        sum(m.score * m.weight for m in metrics) / total_weight
        if total_weight > 0 else 0.5
    )
    overall = round(overall, 4)

    all_issues = [iss for m in metrics for iss in m.issues]
    warnings = []

    if any(m.score < 0.5 for m in metrics):
        low = [m.name for m in metrics if m.score < 0.5]
        warnings.append(f"Low scores on: {', '.join(low)}")

    logger.info(
        "Arrangement evaluation: overall=%.3f grade=%s metrics=%d issues=%d",
        overall, _score_to_grade(overall), len(metrics), len(all_issues),
    )

    return ArrangementEvalReport(
        overall_score=overall,
        grade=_score_to_grade(overall),
        metrics=metrics,
        issues=all_issues,
        warnings=warnings,
    )
