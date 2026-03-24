"""
Evaluation Metrics — Muzikal AI Pipeline.

Implements standard MIR (Music Information Retrieval) evaluation metrics:

  1. Beat F-measure (MIREX standard, window=±70ms)
  2. Chord overlap accuracy (MIREX chord evaluation, root/quality modes)
  3. Structure boundary F-measure (window=±0.5s)
  4. Harmonic rhythm evaluation (chord change time precision/recall)
  5. Key accuracy (root + mode, enharmonic equivalence)
  6. Tempo accuracy (relative error, octave-equivalence aware)

All functions are pure numpy — no external MIR dependencies required.

References:
  - Dixon (2007): Evaluation of the Audio Beat Tracking System BeatRoot
  - Mauch & Dixon (2010): Approximate Note Transcription
  - MIREX chord evaluation (2013 scheme)
  - Paulus et al. (2010): State of the Art Report: Audio-Based Music Structure Analysis
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np


# ─── Beat F-measure ───────────────────────────────────────────────────────────

def beat_fmeasure(
    ref_beats: List[float],
    est_beats: List[float],
    window_sec: float = 0.07,
) -> Dict[str, float]:
    """
    Compute MIREX beat tracking F-measure.

    For each estimated beat, it is a True Positive if there is a reference beat
    within ±window_sec. Multiple estimates cannot match the same reference.

    Args:
        ref_beats: Ground-truth beat times in seconds
        est_beats: Estimated beat times in seconds
        window_sec: Tolerance window (default: ±70ms per MIREX)

    Returns:
        dict with precision, recall, f_measure, continuity
    """
    if not ref_beats or not est_beats:
        return {"precision": 0.0, "recall": 0.0, "f_measure": 0.0}

    ref = np.array(sorted(ref_beats))
    est = np.array(sorted(est_beats))

    matched_ref: set = set()
    tp = 0

    for e_beat in est:
        diffs = np.abs(ref - e_beat)
        best_idx = int(np.argmin(diffs))
        if diffs[best_idx] <= window_sec and best_idx not in matched_ref:
            tp += 1
            matched_ref.add(best_idx)

    precision = tp / len(est) if est.size > 0 else 0.0
    recall    = tp / len(ref) if ref.size > 0 else 0.0
    f_measure = _f1(precision, recall)

    return {
        "precision":  round(precision, 4),
        "recall":     round(recall, 4),
        "f_measure":  round(f_measure, 4),
        "tp":         tp,
        "fp":         len(est) - tp,
        "fn":         len(ref) - len(matched_ref),
    }


# ─── Chord accuracy ───────────────────────────────────────────────────────────

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_ENHARMONIC = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B", "E#": "F", "B#": "C",
}

_QUALITY_ALIASES = {
    "": "maj", "M": "maj", "major": "maj",
    "m": "min", "minor": "min",
    "7": "dom7", "maj7": "maj7", "min7": "min7",
    "dim": "dim", "aug": "aug", "o": "dim", "+": "aug",
    "sus": "sus4", "sus2": "sus2", "sus4": "sus4",
}


def _normalize_note(name: str) -> str:
    name = _ENHARMONIC.get(name, name)
    return name


def _parse_chord(chord_str: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse 'C#min7' → ('C#', 'min7'), or ('N', None) for N.C."""
    if chord_str in ("N", "N.C.", "NC", "None", "no_chord"):
        return "N", None

    for root_len in (2, 1):
        root = chord_str[:root_len]
        root = _ENHARMONIC.get(root, root)
        if root in _NOTE_NAMES:
            quality_raw = chord_str[root_len:].strip(":")
            quality = _QUALITY_ALIASES.get(quality_raw, quality_raw)
            if not quality:
                quality = "maj"
            return root, quality

    return None, None


def _root_eq(r1: Optional[str], r2: Optional[str]) -> bool:
    return r1 is not None and r2 is not None and r1 == r2


def _quality_eq(q1: Optional[str], q2: Optional[str]) -> bool:
    return q1 is not None and q2 is not None and q1 == q2


def chord_overlap_accuracy(
    ref_chords: List[dict],
    est_chords: List[dict],
    total_duration: float,
    mode: str = "majmin",
) -> Dict[str, float]:
    """
    Compute MIREX-style chord overlap accuracy.

    Mode:
      "root"   — only root correctness
      "majmin" — root + major/minor distinction (most common benchmark)
      "seventh"— root + seventh quality
      "mirex"  — root + complete quality match

    Args:
        ref_chords: list of {"start", "end", "chord"} dicts
        est_chords: same format
        total_duration: total song duration for computing coverage
        mode: evaluation mode

    Returns:
        dict with accuracy, coverage, overlap_seconds, and mode
    """
    if total_duration <= 0 or not ref_chords or not est_chords:
        return {"accuracy": 0.0, "coverage": 0.0, "mode": mode}

    # Sample both sequences at fine resolution
    resolution = 0.01  # 10ms
    times = np.arange(0, total_duration, resolution)

    def chord_at(seq: List[dict], t: float) -> str:
        for ev in seq:
            if ev.get("start", 0) <= t < ev.get("end", 0):
                return ev.get("chord", "N")
        return "N"

    correct = 0
    covered = 0

    for t in times:
        rc = chord_at(ref_chords, t)
        ec = chord_at(est_chords, t)

        if rc == "N" and ec == "N":
            covered += 1
            correct += 1
            continue

        r_root, r_qual = _parse_chord(rc)
        e_root, e_qual = _parse_chord(ec)

        if r_root is None or e_root is None:
            continue

        covered += 1

        if mode == "root":
            if _root_eq(r_root, e_root):
                correct += 1

        elif mode == "majmin":
            r_mm = "maj" if r_qual in ("maj", "maj7", "add9", "sus2", "sus4", "aug") else "min"
            e_mm = "maj" if e_qual in ("maj", "maj7", "add9", "sus2", "sus4", "aug") else "min"
            if _root_eq(r_root, e_root) and r_mm == e_mm:
                correct += 1

        elif mode == "seventh":
            r_has7 = r_qual is not None and "7" in r_qual
            e_has7 = e_qual is not None and "7" in e_qual
            if _root_eq(r_root, e_root) and r_has7 == e_has7:
                correct += 1

        elif mode == "mirex":
            if _root_eq(r_root, e_root) and _quality_eq(r_qual, e_qual):
                correct += 1

    accuracy = correct / covered if covered > 0 else 0.0
    coverage = covered * resolution / total_duration

    return {
        "accuracy":         round(accuracy, 4),
        "coverage":         round(coverage, 4),
        "correct_seconds":  round(correct * resolution, 3),
        "covered_seconds":  round(covered * resolution, 3),
        "mode":             mode,
    }


# ─── Structure boundary F-measure ─────────────────────────────────────────────

def structure_boundary_fmeasure(
    ref_boundaries: List[float],
    est_boundaries: List[float],
    window_sec: float = 0.5,
) -> Dict[str, float]:
    """
    Compute structure boundary F-measure (standard MIR evaluation).

    A detected boundary is correct if there is a reference boundary
    within ±window_sec. The first and last boundaries (0.0 and total_duration)
    are excluded from evaluation.

    Args:
        ref_boundaries: Ground-truth boundary times
        est_boundaries: Estimated boundary times
        window_sec: Tolerance window (default ±0.5s per MIREX)

    Returns:
        dict with precision, recall, f_measure
    """
    # Exclude 0.0 and total_duration from ref and est
    def _filter(bounds):
        b = [b for b in bounds if b > 0.5]
        return sorted(b)

    ref = _filter(ref_boundaries)
    est = _filter(est_boundaries)

    if not ref or not est:
        return {"precision": 0.0, "recall": 0.0, "f_measure": 0.0,
                "ref_count": len(ref), "est_count": len(est)}

    ref_arr = np.array(ref)
    est_arr = np.array(est)

    matched_ref: set = set()
    tp = 0
    for e in est_arr:
        diffs = np.abs(ref_arr - e)
        idx   = int(np.argmin(diffs))
        if diffs[idx] <= window_sec and idx not in matched_ref:
            tp += 1
            matched_ref.add(idx)

    precision = tp / len(est) if est else 0.0
    recall    = tp / len(ref) if ref else 0.0

    return {
        "precision":  round(precision, 4),
        "recall":     round(recall, 4),
        "f_measure":  round(_f1(precision, recall), 4),
        "ref_count":  len(ref),
        "est_count":  len(est),
        "tp":         tp,
    }


# ─── Harmonic rhythm evaluation ───────────────────────────────────────────────

def harmonic_rhythm_accuracy(
    ref_chords: List[dict],
    est_chords: List[dict],
    window_sec: float = 0.2,
) -> Dict[str, float]:
    """
    Evaluate harmonic rhythm: how well chord change times are detected.

    Treats each chord change time as a boundary and computes P/R/F.
    """
    ref_changes = [c["start"] for c in ref_chords if c.get("start", 0) > 0.0]
    est_changes = [c["start"] for c in est_chords if c.get("start", 0) > 0.0]
    return structure_boundary_fmeasure(ref_changes, est_changes, window_sec=window_sec)


# ─── Key accuracy ─────────────────────────────────────────────────────────────

def key_accuracy(
    ref_key: str,
    ref_mode: str,
    est_key: str,
    est_mode: str,
) -> Dict[str, bool]:
    """
    Evaluate key detection with enharmonic equivalence.

    Returns:
        dict with root_correct, mode_correct, exact_correct, relative_correct
    """
    r_root = _ENHARMONIC.get(ref_key, ref_key)
    e_root = _ENHARMONIC.get(est_key, est_key)

    root_correct = r_root == e_root
    mode_correct = ref_mode.lower() == est_mode.lower()
    exact_correct = root_correct and mode_correct

    # Relative major/minor: same key signature, different starting note
    def _root_idx(r):
        try:
            return _NOTE_NAMES.index(r)
        except ValueError:
            return -1

    r_idx = _root_idx(r_root)
    e_idx = _root_idx(e_root)
    relative_correct = (
        abs(r_idx - e_idx) in (3, 9)
        and {ref_mode.lower(), est_mode.lower()} == {"major", "minor"}
    )

    return {
        "root_correct":     root_correct,
        "mode_correct":     mode_correct,
        "exact_correct":    exact_correct,
        "relative_correct": relative_correct,
    }


# ─── Tempo accuracy ───────────────────────────────────────────────────────────

def tempo_accuracy(
    ref_bpm: float,
    est_bpm: float,
    tolerance: float = 0.04,
    check_octaves: bool = True,
) -> Dict[str, float]:
    """
    Evaluate tempo accuracy with optional octave-equivalence.

    Args:
        ref_bpm: Ground-truth tempo
        est_bpm: Estimated tempo
        tolerance: Relative tolerance (default 4%)
        check_octaves: If True, also check 2× and 0.5× BPM

    Returns:
        dict with relative_error, correct (within tolerance), octave_correct
    """
    if ref_bpm <= 0 or est_bpm <= 0:
        return {"relative_error": 1.0, "correct": False, "octave_correct": False}

    def _rel_err(r, e):
        return abs(r - e) / max(r, 1e-6)

    rel_err = _rel_err(ref_bpm, est_bpm)
    correct = rel_err <= tolerance

    octave_correct = False
    if check_octaves and not correct:
        for factor in (2.0, 0.5, 3.0, 1/3.0):
            if _rel_err(ref_bpm, est_bpm * factor) <= tolerance:
                octave_correct = True
                break

    return {
        "relative_error": round(rel_err, 4),
        "correct":        correct,
        "octave_correct": octave_correct,
    }


# ─── Aggregate benchmark report ───────────────────────────────────────────────

def aggregate_metrics(results: List[Dict]) -> Dict[str, float]:
    """
    Average a list of metric dicts (from multiple songs) into a single report.

    Args:
        results: List of per-song metric dicts

    Returns:
        Averaged metrics dict
    """
    if not results:
        return {}

    aggregated: Dict[str, list] = {}
    for r in results:
        for k, v in r.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                aggregated.setdefault(k, []).append(v)

    return {
        k: round(float(np.mean(vals)), 4)
        for k, vals in aggregated.items()
        if vals
    }


# ─── Helper ───────────────────────────────────────────────────────────────────

def _f1(p: float, r: float) -> float:
    if p + r < 1e-12:
        return 0.0
    return 2 * p * r / (p + r)
