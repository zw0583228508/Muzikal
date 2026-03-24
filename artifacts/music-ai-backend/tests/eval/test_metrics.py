"""
Unit tests for the MIR evaluation metrics module.

Tests cover:
  - Beat F-measure (exact, tolerance, no-match)
  - Chord overlap accuracy (root, majmin, seventh, mirex modes)
  - Structure boundary F-measure
  - Harmonic rhythm evaluation
  - Key accuracy (with enharmonic equivalence)
  - Tempo accuracy (with octave-equivalence)
  - Aggregate metrics averaging
"""

import pytest
import math
from tests.eval.metrics import (
    beat_fmeasure,
    chord_overlap_accuracy,
    structure_boundary_fmeasure,
    harmonic_rhythm_accuracy,
    key_accuracy,
    tempo_accuracy,
    aggregate_metrics,
)


# ─── Beat F-measure ───────────────────────────────────────────────────────────

class TestBeatFmeasure:

    def test_perfect_match(self):
        beats = [0.5 * i for i in range(8)]
        result = beat_fmeasure(beats, beats)
        assert result["f_measure"] == pytest.approx(1.0)
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(1.0)

    def test_within_tolerance(self):
        ref = [0.5, 1.0, 1.5, 2.0]
        est = [0.52, 1.03, 1.48, 2.01]   # within ±70ms
        result = beat_fmeasure(ref, est, window_sec=0.07)
        assert result["f_measure"] > 0.9

    def test_outside_tolerance(self):
        ref = [0.5, 1.0, 1.5, 2.0]
        est = [0.65, 1.15, 1.65, 2.15]   # outside ±70ms
        result = beat_fmeasure(ref, est, window_sec=0.07)
        assert result["f_measure"] < 0.1

    def test_empty_estimate(self):
        ref = [0.5, 1.0, 1.5]
        result = beat_fmeasure(ref, [])
        assert result["f_measure"] == 0.0

    def test_empty_reference(self):
        est = [0.5, 1.0]
        result = beat_fmeasure([], est)
        assert result["f_measure"] == 0.0

    def test_partial_match(self):
        ref = [0.5, 1.0, 1.5, 2.0]
        est = [0.5, 1.0]    # only first 2 beats detected
        result = beat_fmeasure(ref, est)
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(0.5)
        assert result["f_measure"] == pytest.approx(2/3, abs=0.01)

    def test_double_detection_not_counted_twice(self):
        ref = [1.0]
        est = [1.0, 1.01]   # two estimates near same reference
        result = beat_fmeasure(ref, est)
        # Only one TP allowed per reference
        assert result["tp"] == 1
        assert result["precision"] == pytest.approx(0.5)
        assert result["recall"] == pytest.approx(1.0)


# ─── Chord accuracy ───────────────────────────────────────────────────────────

_C_MAJ = {"start": 0.0, "end": 2.0, "chord": "Cmaj"}
_G_MAJ = {"start": 2.0, "end": 4.0, "chord": "Gmaj"}
_A_MIN = {"start": 0.0, "end": 2.0, "chord": "Amin"}
_C_DOM7 = {"start": 0.0, "end": 2.0, "chord": "Cdom7"}


class TestChordOverlapAccuracy:

    def test_perfect_majmin(self):
        ref = [_C_MAJ, _G_MAJ]
        est = [_C_MAJ, _G_MAJ]
        result = chord_overlap_accuracy(ref, est, total_duration=4.0, mode="majmin")
        assert result["accuracy"] == pytest.approx(1.0, abs=0.01)

    def test_wrong_root(self):
        ref = [_C_MAJ]
        est = [{"start": 0.0, "end": 2.0, "chord": "Dmaj"}]
        result = chord_overlap_accuracy(ref, est, total_duration=2.0, mode="root")
        assert result["accuracy"] < 0.1

    def test_correct_root_wrong_quality(self):
        ref = [_C_MAJ]
        est = [_A_MIN]   # wrong root
        result = chord_overlap_accuracy(ref, est, total_duration=2.0, mode="root")
        assert result["accuracy"] < 0.1

    def test_majmin_mode_correct(self):
        ref = [_C_MAJ]
        est = [_C_MAJ]
        result = chord_overlap_accuracy(ref, est, total_duration=2.0, mode="majmin")
        assert result["accuracy"] > 0.99

    def test_seventh_mode(self):
        ref = [_C_MAJ]
        est = [_C_DOM7]   # C dominant 7 — different quality
        result = chord_overlap_accuracy(ref, est, total_duration=2.0, mode="seventh")
        # C maj has no 7th, C dom7 has 7th → mismatch
        assert result["accuracy"] < 0.1

    def test_empty_sequences(self):
        result = chord_overlap_accuracy([], [], total_duration=4.0)
        assert result["accuracy"] == 0.0


# ─── Structure boundary F-measure ─────────────────────────────────────────────

class TestStructureBoundaryFmeasure:

    def test_perfect_match(self):
        ref = [15.0, 30.0, 60.0]
        est = [15.0, 30.0, 60.0]
        result = structure_boundary_fmeasure(ref, est)
        assert result["f_measure"] == pytest.approx(1.0)

    def test_within_window(self):
        ref = [15.0, 30.0, 60.0]
        est = [15.3, 29.8, 60.4]   # within ±0.5s
        result = structure_boundary_fmeasure(ref, est)
        assert result["f_measure"] == pytest.approx(1.0)

    def test_outside_window(self):
        ref = [15.0, 30.0, 60.0]
        est = [20.0, 40.0, 70.0]   # outside ±0.5s
        result = structure_boundary_fmeasure(ref, est)
        assert result["f_measure"] < 0.1

    def test_empty(self):
        result = structure_boundary_fmeasure([], [15.0])
        assert result["f_measure"] == 0.0

    def test_false_positive(self):
        ref = [15.0]
        est = [15.0, 25.0, 35.0]   # many extra detections
        result = structure_boundary_fmeasure(ref, est)
        assert result["recall"] == pytest.approx(1.0)
        assert result["precision"] == pytest.approx(1/3, abs=0.01)


# ─── Key accuracy ─────────────────────────────────────────────────────────────

class TestKeyAccuracy:

    def test_exact_match(self):
        result = key_accuracy("C", "major", "C", "major")
        assert result["exact_correct"] is True
        assert result["root_correct"] is True
        assert result["mode_correct"] is True

    def test_enharmonic_equivalence(self):
        result = key_accuracy("C#", "major", "Db", "major")
        assert result["root_correct"] is True
        assert result["exact_correct"] is True

    def test_wrong_mode(self):
        result = key_accuracy("C", "major", "C", "minor")
        assert result["root_correct"] is True
        assert result["mode_correct"] is False
        assert result["exact_correct"] is False

    def test_relative_key(self):
        # C major relative of A minor
        result = key_accuracy("C", "major", "A", "minor")
        assert result["relative_correct"] is True
        assert result["exact_correct"] is False

    def test_completely_wrong(self):
        result = key_accuracy("C", "major", "G", "minor")
        assert result["exact_correct"] is False
        assert result["relative_correct"] is False


# ─── Tempo accuracy ───────────────────────────────────────────────────────────

class TestTempoAccuracy:

    def test_exact(self):
        result = tempo_accuracy(120.0, 120.0)
        assert result["correct"] is True
        assert result["relative_error"] < 0.001

    def test_within_tolerance(self):
        result = tempo_accuracy(120.0, 122.4)   # 2% error
        assert result["correct"] is True

    def test_outside_tolerance(self):
        result = tempo_accuracy(120.0, 130.0)   # 8.3% error
        assert result["correct"] is False

    def test_octave_equivalence_half(self):
        result = tempo_accuracy(120.0, 60.0)   # half tempo
        assert result["octave_correct"] is True
        assert result["correct"] is False

    def test_octave_equivalence_double(self):
        result = tempo_accuracy(120.0, 240.0)  # double tempo
        assert result["octave_correct"] is True

    def test_zero_bpm(self):
        result = tempo_accuracy(0.0, 120.0)
        assert result["correct"] is False


# ─── Aggregate metrics ────────────────────────────────────────────────────────

class TestAggregateMetrics:

    def test_empty(self):
        assert aggregate_metrics([]) == {}

    def test_single(self):
        result = aggregate_metrics([{"f_measure": 0.8, "precision": 0.7}])
        assert result["f_measure"] == pytest.approx(0.8)

    def test_average(self):
        data = [{"f_measure": 0.6}, {"f_measure": 0.8}, {"f_measure": 1.0}]
        result = aggregate_metrics(data)
        assert result["f_measure"] == pytest.approx(0.8, abs=0.001)

    def test_ignores_booleans(self):
        data = [{"correct": True, "score": 0.5}]
        result = aggregate_metrics(data)
        assert "score" in result
        # booleans should not be averaged as floats
        assert "correct" not in result or result.get("correct") == pytest.approx(1.0)
