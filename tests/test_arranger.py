"""
Tests for the orchestration arranger module.
Covers: arrangement generation, transitions, instrumentation plan (T006, T011).
Run: python3 -m pytest tests/test_arranger.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "artifacts", "music-ai-backend"))

MOCK_ANALYSIS = {
    "rhythm": {
        "bpm": 120.0,
        "beatGrid": [i * 0.5 for i in range(48)],
        "timeSignatureNumerator": 4,
        "timeSignatureDenominator": 4,
    },
    "chords": {
        "chords": [
            {"chord": "Am", "startTime": 0.0,  "endTime": 6.0,  "confidence": 0.9},
            {"chord": "F",  "startTime": 6.0,  "endTime": 12.0, "confidence": 0.85},
            {"chord": "C",  "startTime": 12.0, "endTime": 18.0, "confidence": 0.88},
            {"chord": "G",  "startTime": 18.0, "endTime": 24.0, "confidence": 0.82},
        ]
    },
    "structure": {
        "sections": [
            {"label": "intro",  "startTime": 0.0,  "endTime": 6.0},
            {"label": "verse",  "startTime": 6.0,  "endTime": 12.0},
            {"label": "chorus", "startTime": 12.0, "endTime": 18.0},
            {"label": "outro",  "startTime": 18.0, "endTime": 24.0},
        ]
    },
    "key": {"globalKey": "A", "mode": "minor"},
    "melody": {"notes": []},
}


def arrange(style_id="pop"):
    from orchestration.arranger import generate_arrangement
    return generate_arrangement(
        analysis=MOCK_ANALYSIS,
        style_id=style_id,
        instruments=None,
        density=0.7,
        do_humanize=False,
        tempo_factor=1.0,
    )


class TestArrangeReturnKeys:
    def test_has_required_keys(self):
        result = arrange()
        for key in ("styleId", "tracks", "totalDurationSeconds", "sections",
                    "harmonicPlan", "transitions", "instrumentationPlan",
                    "profileUsed", "generationParams"):
            assert key in result, f"Missing key: {key}"

    def test_total_duration_positive(self):
        result = arrange()
        assert result["totalDurationSeconds"] > 0

    def test_tracks_is_list(self):
        result = arrange()
        assert isinstance(result["tracks"], list)
        assert len(result["tracks"]) > 0

    def test_each_track_has_notes(self):
        result = arrange()
        for track in result["tracks"]:
            assert "notes" in track
            assert isinstance(track["notes"], list)

    def test_style_id_preserved(self):
        result = arrange("jazz")
        assert result["styleId"] == "jazz"


class TestTransitions:
    def test_transitions_is_list(self):
        result = arrange()
        assert isinstance(result["transitions"], list)

    def test_transitions_non_empty_with_multiple_sections(self):
        result = arrange()
        assert len(result["transitions"]) > 0, "Expected at least 1 transition for 4 sections"

    def test_transitions_have_required_fields(self):
        result = arrange()
        for tr in result["transitions"]:
            assert "fromSection" in tr, f"Missing fromSection in {tr}"
            assert "toSection" in tr, f"Missing toSection in {tr}"
            assert "type" in tr, f"Missing type in {tr}"
            assert "atTime" in tr, f"Missing atTime in {tr}"

    def test_verse_to_chorus_is_build(self):
        result = arrange()
        build = [tr for tr in result["transitions"]
                 if tr["fromSection"] == "verse" and tr["toSection"] == "chorus"]
        assert len(build) > 0, "No verse→chorus transition found"
        assert any(tr["type"] == "build" for tr in build), \
            f"verse→chorus should be 'build' transition, got: {build}"

    def test_transition_count_matches_section_boundaries(self):
        result = arrange()
        n_sections = len(result["sections"])
        assert len(result["transitions"]) == n_sections - 1

    def test_transition_at_time_matches_section_start(self):
        result = arrange()
        sections = result["sections"]
        transitions = result["transitions"]
        for i, tr in enumerate(transitions):
            expected_at = sections[i + 1]["startTime"]
            assert abs(tr["atTime"] - expected_at) < 0.01, \
                f"Transition atTime {tr['atTime']} ≠ section start {expected_at}"


class TestInstrumentationPlan:
    def test_instrumentation_plan_has_tracks(self):
        result = arrange()
        plan = result["instrumentationPlan"]
        assert "tracks" in plan
        assert isinstance(plan["tracks"], list)
        assert len(plan["tracks"]) > 0

    def test_each_plan_track_has_role_and_density(self):
        result = arrange()
        for tr in result["instrumentationPlan"]["tracks"]:
            assert "instrument" in tr, f"Missing instrument in {tr}"
            assert "role" in tr, f"Missing role in {tr}"
            assert "density" in tr, f"Missing density in {tr}"
            assert 0.0 <= tr["density"] <= 1.0, f"Density out of range: {tr['density']}"

    def test_style_id_in_plan(self):
        result = arrange("hasidic")
        assert result["instrumentationPlan"]["styleId"] == "hasidic"

    def test_plan_sections_field_is_list(self):
        result = arrange()
        for tr in result["instrumentationPlan"]["tracks"]:
            assert "sections" in tr
            assert isinstance(tr["sections"], list)


class TestHarmonicPlan:
    def test_harmonic_plan_is_list(self):
        result = arrange()
        assert isinstance(result["harmonicPlan"], list)

    def test_harmonic_plan_entries_have_chords(self):
        result = arrange()
        for entry in result["harmonicPlan"]:
            assert "section" in entry, f"Missing section in {entry}"
            assert "chords" in entry, f"Missing chords in {entry}"
            assert isinstance(entry["chords"], list)

    def test_harmonic_plan_count_matches_sections(self):
        result = arrange()
        assert len(result["harmonicPlan"]) == len(result["sections"])


class TestStyleVariants:
    @pytest.mark.parametrize("style", ["pop", "jazz", "hasidic", "middle_eastern", "electronic"])
    def test_style_generates_without_error(self, style):
        result = arrange(style)
        assert result["styleId"] == style
        assert len(result["tracks"]) > 0

    @pytest.mark.parametrize("style", ["hasidic", "middle_eastern"])
    def test_ethnic_styles_have_tracks(self, style):
        result = arrange(style)
        instruments = [t["id"] for t in result["tracks"]]
        assert len(instruments) >= 2, f"Expected ≥2 instruments for {style}, got {instruments}"
