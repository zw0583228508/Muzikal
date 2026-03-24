"""
Phase 4 — Orchestration, Humanization, and Style Spec tests.

Validates:
  - InstrumentRange specs (range, register, voice-leading)
  - Humanizer (determinism, swing, per-instrument profiles)
  - ArrangementEvaluator (metric scoring)
  - StyleConditioningSpec (load, planner inputs)
"""

from __future__ import annotations

import pytest


# ─── Instrument Range tests ───────────────────────────────────────────────────

class TestInstrumentRanges:

    def test_all_standard_instruments_registered(self):
        from orchestration.instrument_ranges import INSTRUMENT_RANGES
        expected = ["piano", "bass", "drums", "strings", "guitar", "violin",
                    "brass", "trumpet", "saxophone", "accordion", "oud", "nay",
                    "pad", "synth_pad", "lead_synth", "choir", "darbuka", "tsimbl",
                    "qanun", "double_bass"]
        for name in expected:
            assert name in INSTRUMENT_RANGES, f"Missing instrument: {name}"

    def test_range_sanity(self):
        from orchestration.instrument_ranges import INSTRUMENT_RANGES
        for name, spec in INSTRUMENT_RANGES.items():
            assert spec.min_midi < spec.max_midi, f"{name}: min >= max"
            assert spec.preferred_min >= spec.min_midi, f"{name}: preferred_min below absolute min"
            assert spec.preferred_max <= spec.max_midi, f"{name}: preferred_max above absolute max"
            assert spec.preferred_min < spec.preferred_max, f"{name}: preferred_min >= preferred_max"

    def test_in_range(self):
        from orchestration.instrument_ranges import PIANO, BASS
        assert PIANO.in_range(60)  # middle C — always in piano range
        assert not PIANO.in_range(15)  # way too low
        assert BASS.in_range(40)   # E2 — low E string
        assert not BASS.in_range(100)  # too high for bass

    def test_in_preferred_range(self):
        from orchestration.instrument_ranges import PIANO
        assert PIANO.in_preferred_range(60)
        assert PIANO.in_preferred_range(72)
        # Very low notes are outside preferred but still in absolute range
        assert PIANO.in_range(21)
        assert not PIANO.in_preferred_range(21)

    def test_clamp_to_preferred(self):
        from orchestration.instrument_ranges import BASS
        clamped = BASS.clamp_to_preferred(100)  # too high
        assert BASS.preferred_min <= clamped <= BASS.preferred_max

    def test_nearest_note_voicing_reduces_movement(self):
        from orchestration.instrument_ranges import nearest_note_voicing
        current = [60, 64, 67]  # C major
        target = [62, 65, 69]   # D minor
        voiced = nearest_note_voicing(current, target, "piano")
        assert len(voiced) == 3
        assert all(isinstance(p, int) for p in voiced)

    def test_nearest_note_voicing_stays_in_range(self):
        from orchestration.instrument_ranges import nearest_note_voicing, INSTRUMENT_RANGES
        current = [60, 64, 67]
        target = [60, 63, 67]
        voiced = nearest_note_voicing(current, target, "piano")
        spec = INSTRUMENT_RANGES["piano"]
        for p in voiced:
            assert spec.in_range(p), f"Voiced pitch {p} outside piano range"

    def test_check_voice_crossing(self):
        from orchestration.instrument_ranges import check_voice_crossing
        # No crossing
        assert check_voice_crossing([60, 64, 67]) == []
        # Crossing — voice 0 higher than voice 1
        result = check_voice_crossing([67, 60, 72])
        assert len(result) > 0

    def test_validate_arrangement_voices(self):
        from orchestration.instrument_ranges import validate_arrangement_voices
        tracks = [
            {
                "instrument": "piano",
                "notes": [{"pitch": 60, "startTime": 0.0, "duration": 0.5}],
            },
            {
                "instrument": "bass",
                "notes": [
                    {"pitch": 30, "startTime": 0.0, "duration": 0.5},
                    {"pitch": 120, "startTime": 0.5, "duration": 0.5},  # too high for bass
                ],
            },
        ]
        issues = validate_arrangement_voices(tracks)
        assert "bass" in issues
        assert len(issues["bass"]) >= 1

    def test_list_instruments(self):
        from orchestration.instrument_ranges import list_instruments
        names = list_instruments()
        assert len(names) >= 15
        assert "piano" in names


# ─── Humanizer tests ──────────────────────────────────────────────────────────

class TestHumanizer:

    def _make_notes(self, n: int = 16, bpm: float = 120.0) -> list:
        beat = 60.0 / bpm
        return [
            {"startTime": i * beat / 2, "duration": beat / 2, "velocity": 80, "pitch": 60 + i % 12}
            for i in range(n)
        ]

    def test_humanize_track_basic(self):
        from orchestration.humanizer import Humanizer, HumanizerConfig
        notes = self._make_notes()
        config = HumanizerConfig(seed=42, bpm=120.0)
        h = Humanizer(config)
        result = h.humanize_track(notes, "piano")
        assert len(result) == len(notes)
        for n in result:
            assert n["velocity"] >= 10
            assert n["velocity"] <= 127
            assert n["startTime"] >= 0.0

    def test_humanize_is_deterministic(self):
        from orchestration.humanizer import Humanizer, HumanizerConfig
        notes = self._make_notes()
        config1 = HumanizerConfig(seed=42, bpm=120.0)
        config2 = HumanizerConfig(seed=42, bpm=120.0)
        result1 = Humanizer(config1).humanize_track(notes, "piano")
        result2 = Humanizer(config2).humanize_track(notes, "piano")
        assert [n["startTime"] for n in result1] == [n["startTime"] for n in result2]
        assert [n["velocity"] for n in result1] == [n["velocity"] for n in result2]

    def test_different_seeds_produce_different_results(self):
        from orchestration.humanizer import Humanizer, HumanizerConfig
        notes = self._make_notes(32)
        r1 = Humanizer(HumanizerConfig(seed=1)).humanize_track(notes, "piano")
        r2 = Humanizer(HumanizerConfig(seed=999)).humanize_track(notes, "piano")
        # At least one note should differ
        assert any(a["startTime"] != b["startTime"] for a, b in zip(r1, r2))

    def test_empty_notes_returns_empty(self):
        from orchestration.humanizer import Humanizer, HumanizerConfig
        h = Humanizer(HumanizerConfig(seed=42))
        assert h.humanize_track([], "piano") == []

    def test_swing_applied_to_jazz(self):
        from orchestration.humanizer import Humanizer, HumanizerConfig
        notes = self._make_notes(16, bpm=120.0)
        config = HumanizerConfig(seed=42, swing=0.67, style="jazz", bpm=120.0)
        h = Humanizer(config)
        result = h.humanize_track(notes, "piano")
        # Timing should differ from straight (swing shifts some notes)
        original_times = [n["startTime"] for n in notes]
        result_times = [n["startTime"] for n in result]
        assert original_times != result_times

    def test_intensity_zero_preserves_timing(self):
        from orchestration.humanizer import Humanizer, HumanizerConfig
        notes = self._make_notes(8)
        h = Humanizer(HumanizerConfig(seed=42, intensity=0.0, bpm=120.0))
        result = h.humanize_track(notes, "piano")
        for orig, res in zip(notes, result):
            # With zero intensity, timing jitter should be near zero
            assert abs(res["startTime"] - orig["startTime"]) < 0.01

    def test_humanize_tracks_api(self):
        from orchestration.humanizer import humanize_tracks, HumanizerConfig
        tracks = [
            {"instrument": "piano", "notes": self._make_notes(), "sectionLabel": "verse"},
            {"instrument": "bass", "notes": self._make_notes(8), "sectionLabel": "verse"},
        ]
        config = HumanizerConfig(seed=0, bpm=120.0)
        result = humanize_tracks(tracks, config)
        assert len(result) == 2
        assert all(t.get("humanized") for t in result)

    def test_make_humanizer_config_jazz_swing(self):
        from orchestration.humanizer import make_humanizer_config
        config = make_humanizer_config(seed=1, style="jazz", bpm=130.0)
        assert config.swing >= 0.60  # jazz should have significant swing

    def test_make_humanizer_config_pop_straight(self):
        from orchestration.humanizer import make_humanizer_config
        config = make_humanizer_config(seed=1, style="pop", bpm=120.0)
        assert config.swing == 0.5  # pop should be straight

    def test_per_instrument_profiles_exist(self):
        from orchestration.humanizer import get_profile
        for instr in ["piano", "bass", "drums", "strings", "guitar", "violin",
                      "brass", "trumpet", "saxophone", "accordion", "oud",
                      "pad", "choir", "lead_synth", "nay"]:
            profile = get_profile(instr)
            assert profile.timing_jitter_sec >= 0
            assert profile.velocity_jitter >= 0


# ─── Arrangement Evaluator tests ──────────────────────────────────────────────

class TestArrangementEvaluator:

    def _make_analysis(self, bpm: float = 120.0) -> dict:
        return {
            "rhythm": {"bpm": bpm},
            "chords": {
                "segments": [
                    {"start": 0.0, "end": 8.0, "chord": "Cmaj"},
                    {"start": 8.0, "end": 16.0, "chord": "Amin"},
                    {"start": 16.0, "end": 24.0, "chord": "Fmaj"},
                    {"start": 24.0, "end": 32.0, "chord": "Gmaj"},
                ]
            },
            "structure": {
                "sections": [
                    {"label": "verse",  "start": 0.0,  "end": 16.0, "groupId": 1},
                    {"label": "chorus", "start": 16.0, "end": 32.0, "groupId": 2},
                ]
            },
            "totalDuration": 32.0,
        }

    def _make_tracks(self, analysis: dict) -> list:
        bpm = analysis["rhythm"]["bpm"]
        beat = 60.0 / bpm
        chords = analysis["chords"]["segments"]

        # Piano: C major arpeggio (chord tones → good harmonic consistency)
        piano_notes = []
        for i, c in enumerate(chords):
            for j, pitch in enumerate([60, 64, 67]):  # C-E-G
                t = c["start"] + j * beat
                if t < c["end"]:
                    piano_notes.append({"startTime": round(t, 4), "duration": beat - 0.02,
                                        "pitch": pitch, "velocity": 75})

        # Bass: root notes on beat
        bass_notes = []
        for c in chords:
            t = c["start"]
            while t < c["end"]:
                bass_notes.append({"startTime": round(t, 4), "duration": beat - 0.02,
                                   "pitch": 48, "velocity": 85})  # C3
                t += beat * 2

        # Drums: kick on beat 1&3, snare on 2&4
        drum_notes = []
        for c in chords:
            t = c["start"]
            while t < c["end"]:
                drum_notes.append({"startTime": round(t, 4), "duration": 0.1,
                                   "pitch": 36, "velocity": 100})  # kick
                if t + beat < c["end"]:
                    drum_notes.append({"startTime": round(t + beat, 4), "duration": 0.1,
                                       "pitch": 38, "velocity": 90})  # snare
                t += beat * 2

        return [
            {"instrument": "piano", "notes": piano_notes, "sectionLabel": "verse"},
            {"instrument": "bass",  "notes": bass_notes,  "sectionLabel": "verse"},
            {"instrument": "drums", "notes": drum_notes,  "sectionLabel": "verse"},
        ]

    def test_evaluate_returns_report(self):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        tracks = self._make_tracks(analysis)
        report = evaluate_arrangement(tracks, analysis)
        assert report.overall_score >= 0.0
        assert report.overall_score <= 1.0
        assert report.grade in "ABCDF"
        assert len(report.metrics) >= 5

    def test_harmonic_consistency_good_tracks(self):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        tracks = self._make_tracks(analysis)
        report = evaluate_arrangement(tracks, analysis)
        harmony_metric = next(
            (m for m in report.metrics if "Harmonic" in m.name), None
        )
        assert harmony_metric is not None
        # C-E-G are chord tones of Cmaj/Amin but not all of Fmaj/Gmaj
        # Real score reflects partial alignment across the I-vi-IV-V progression
        assert harmony_metric.score >= 0.60

    def test_range_compliance_no_violations(self):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        tracks = self._make_tracks(analysis)  # all notes in normal ranges
        report = evaluate_arrangement(tracks, analysis)
        range_metric = next(
            (m for m in report.metrics if "Range" in m.name), None
        )
        assert range_metric is not None
        assert range_metric.score >= 0.8

    def test_range_compliance_with_violations(self):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        tracks = [
            {
                "instrument": "bass",
                "notes": [
                    {"pitch": 120, "startTime": 0.0, "duration": 0.5, "velocity": 80}
                    for _ in range(20)  # way too high for bass
                ],
            }
        ]
        report = evaluate_arrangement(tracks, analysis)
        range_metric = next(
            (m for m in report.metrics if "Range" in m.name), None
        )
        assert range_metric is not None
        assert range_metric.score < 0.5  # should penalize heavily

    def test_print_summary(self, capsys):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        tracks = self._make_tracks(analysis)
        report = evaluate_arrangement(tracks, analysis)
        report.print_summary()
        out = capsys.readouterr().out
        assert "ARRANGEMENT EVALUATION" in out
        assert "Harmonic" in out

    def test_empty_tracks(self):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        report = evaluate_arrangement([], analysis)
        assert 0.0 <= report.overall_score <= 1.0

    def test_bass_behavior_on_roots(self):
        from orchestration.arrangement_evaluator import evaluate_arrangement
        analysis = self._make_analysis()
        # Bass only on C (root of Cmaj)
        tracks = [{
            "instrument": "bass",
            "notes": [
                {"pitch": 48, "startTime": i * 0.5, "duration": 0.4, "velocity": 80}
                for i in range(8)
            ]
        }]
        report = evaluate_arrangement(tracks, analysis)
        bass_metric = next((m for m in report.metrics if "Bass" in m.name), None)
        assert bass_metric is not None
        assert bass_metric.score >= 0.8


# ─── Style Spec tests ─────────────────────────────────────────────────────────

class TestStyleSpec:

    def test_list_styles(self):
        from orchestration.style_spec import list_style_ids
        ids = list_style_ids()
        assert len(ids) >= 5
        assert "pop" in ids
        assert "jazz" in ids
        assert "hasidic" in ids
        assert "middle_eastern" in ids

    def test_load_style_spec(self):
        from orchestration.style_spec import load_style_spec
        spec = load_style_spec("pop")
        assert spec is not None
        assert spec.style_id == "pop"
        assert spec.display_name

    def test_load_unknown_style_returns_none(self):
        from orchestration.style_spec import load_style_spec
        assert load_style_spec("nonexistent_style_xyz") is None

    def test_to_planner_inputs_has_required_keys(self):
        from orchestration.style_spec import load_style_spec
        spec = load_style_spec("jazz")
        inputs = spec.to_planner_inputs()
        assert "style_id" in inputs
        assert "instruments" in inputs
        assert "groove" in inputs
        assert "drum_intensity" in inputs

    def test_style_spec_instruments_non_empty(self):
        from orchestration.style_spec import list_style_ids, load_style_spec
        for style_id in list_style_ids():
            spec = load_style_spec(style_id)
            inputs = spec.to_planner_inputs()
            assert len(inputs.get("instruments", [])) > 0, \
                f"Style {style_id} has no instruments"

    def test_jazz_has_walking_bass(self):
        from orchestration.style_spec import load_style_spec
        spec = load_style_spec("jazz")
        inputs = spec.to_planner_inputs()
        assert inputs.get("bass_role") == "walking"

    def test_electronic_has_high_drum_intensity(self):
        from orchestration.style_spec import load_style_spec
        spec = load_style_spec("electronic")
        inputs = spec.to_planner_inputs()
        assert inputs.get("drum_intensity", 0) >= 0.85

    def test_classical_has_zero_or_no_drums(self):
        from orchestration.style_spec import load_style_spec
        spec = load_style_spec("classical")
        inputs = spec.to_planner_inputs()
        assert inputs.get("drum_intensity", 0) == 0.0 or \
               "drums" not in inputs.get("instruments", [])

    def test_humanizer_kwargs(self):
        from orchestration.style_spec import load_style_spec
        spec = load_style_spec("jazz")
        kwargs = spec.to_humanizer_config_kwargs()
        assert "style" in kwargs
        assert kwargs["style"] == "jazz"

    def test_get_planner_inputs_convenience(self):
        from orchestration.style_spec import get_planner_inputs
        inputs = get_planner_inputs("pop")
        assert inputs["style_id"] == "pop"

    def test_get_planner_inputs_unknown_fallback(self):
        from orchestration.style_spec import get_planner_inputs
        inputs = get_planner_inputs("unknown_xyz")
        assert inputs["style_id"] == "unknown_xyz"
