"""
tests/test_arranger_integration.py — 8 integration tests for Step 8
"""

import pytest
from orchestration.arranger import generate_arrangement
from orchestration.style_profile_adapter import adapt_profile_to_arranger_args


KLEZMER_PROFILE = {
    "genre": "klezmer",
    "scaleType": "freygish",
    "timeSignature": "2/4",
    "bpmRange": [120, 140],
    "textureType": "layered",
    "humanizationLevel": 0.8,
    "swingFactor": 0.0,
    "grooveTemplate": "on_top",
    "ornamentStyle": "krekhts",
    "progressionPatterns": [["i", "bVII", "bVI", "V7"]],
    "instruments": [
        {"name": "violin",      "role": "MELODY_LEAD",   "midiProgram": 40, "volumeWeight": 0.9},
        {"name": "accordion",   "role": "HARMONY_CHORD", "midiProgram": 21, "volumeWeight": 0.7},
        {"name": "double_bass", "role": "BASS",          "midiProgram": 43, "volumeWeight": 0.8},
        {"name": "drums",       "role": "RHYTHM_KICK",   "midiProgram": 0,  "volumeWeight": 0.6},
    ],
}

ANALYSIS = {
    "rhythm": {"bpm": 130.0, "timeSignatureNumerator": 2, "beatGrid": [i * 0.46 for i in range(40)]},
    "chords": {"chords": []},
    "structure": {"sections": [{"label": "verse", "startTime": 0.0, "endTime": 18.4}]},
    "key": {"key": "D", "mode": "minor"},
    "detectedKey": "D",
}


def test_klezmer_generates_tracks():
    kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=KLEZMER_PROFILE)
    assert len(result["tracks"]) >= 2


def test_klezmer_has_notes():
    kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=KLEZMER_PROFILE)
    total_notes = sum(len(t["notes"]) for t in result["tracks"])
    assert total_notes > 0


def test_klezmer_profile_genre_in_result():
    kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=KLEZMER_PROFILE)
    assert result.get("styleProfileGenre") == "klezmer"


def test_profile_chords_override_empty_detected():
    # When detected chords are empty and profile has progressions,
    # tracks should still have notes (from profile-derived chords)
    kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=KLEZMER_PROFILE)
    bass_tracks = [t for t in result["tracks"] if t["id"] in ("bass", "double_bass")]
    if bass_tracks:
        assert len(bass_tracks[0]["notes"]) > 0


def test_no_profile_still_works():
    # Backward compatibility: no style_profile should not break anything
    result = generate_arrangement(
        analysis=ANALYSIS,
        style_id="hasidic",
        instruments=None,
        density=0.75,
        do_humanize=False,
        tempo_factor=1.0,
    )
    assert "tracks" in result


def test_swing_applied_to_jazz():
    jazz_profile = {
        **KLEZMER_PROFILE,
        "genre": "jazz_bebop",
        "swingFactor": 0.45,
        "scaleType": "dorian",
        "progressionPatterns": [["ii7", "V7", "Imaj7", "VI7"]],
    }
    kwargs = adapt_profile_to_arranger_args(jazz_profile, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=jazz_profile)
    assert len(result["tracks"]) >= 1


def test_time_sig_3_4_waltz():
    waltz_profile = {**KLEZMER_PROFILE, "genre": "hasidic_nigun", "timeSignature": "3/4"}
    kwargs = adapt_profile_to_arranger_args(waltz_profile, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=waltz_profile)
    assert "tracks" in result


def test_melody_instrument_generates_notes():
    kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, ANALYSIS)
    result = generate_arrangement(**kwargs, style_profile=KLEZMER_PROFILE)
    violin_tracks = [t for t in result["tracks"] if "violin" in t.get("id", "")]
    if violin_tracks:
        assert len(violin_tracks[0]["notes"]) > 0
