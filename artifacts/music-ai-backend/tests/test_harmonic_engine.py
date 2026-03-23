import pytest
pytestmark = pytest.mark.unit

"""
tests/test_harmonic_engine.py — 22 tests for Step 8 Harmonic Engine
"""

import pytest
from orchestration.harmonic_engine import (
    roman_to_chord,
    _split_roman,
    _default_quality,
    build_chord_events_from_progression,
    apply_swing,
    get_progression_for_section,
)


# ─── roman_to_chord ───────────────────────────────────────────────────────────

def test_tonic_minor_d():
    assert roman_to_chord("i", "D", "minor") == "Dm"


def test_bVII_d_minor():
    assert roman_to_chord("bVII", "D", "minor") == "C"


def test_V7_d_minor():
    assert roman_to_chord("V7", "D", "minor") == "A7"


def test_freygish_bVI():
    # Freygish = E phrygian dominant: i=Em, bVI=C
    assert roman_to_chord("bVI", "E", "freygish") == "C"


def test_major_IV():
    assert roman_to_chord("IV", "G", "major") == "C"


def test_bossa_nova_Imaj7():
    assert roman_to_chord("Imaj7", "C", "major") == "Cmaj7"


def test_ii7_in_major():
    assert roman_to_chord("ii7", "G", "major") == "Am7"


def test_unknown_roman_defaults_to_C():
    result = roman_to_chord("", "D", "minor")
    assert isinstance(result, str)
    assert len(result) > 0


def test_enharmonic_key_Bb():
    result = roman_to_chord("I", "Bb", "major")
    assert result in ("Bb", "A#")


# ─── _split_roman ─────────────────────────────────────────────────────────────

def test_split_bVII():
    assert _split_roman("bVII") == ("bVII", "")


def test_split_V7():
    assert _split_roman("V7") == ("V", "7")


def test_split_Imaj7():
    assert _split_roman("Imaj7") == ("I", "maj7")


def test_split_im7b5():
    assert _split_roman("im7b5") == ("i", "m7b5")


# ─── build_chord_events_from_progression ──────────────────────────────────────

def test_build_returns_correct_count():
    events = build_chord_events_from_progression(["i", "bVII", "bVI", "V7"], "D", "minor", 0.0, 8.0)
    assert len(events) == 4


def test_build_chord_names_klezmer():
    events = build_chord_events_from_progression(["i", "bVII", "bVI", "V7"], "D", "freygish", 0.0, 8.0)
    assert events[0]["chord"] == "Dm"
    assert events[1]["chord"] == "C"


def test_build_timing():
    events = build_chord_events_from_progression(["I", "IV", "V", "I"], "C", "major", 0.0, 8.0)
    assert events[0]["startTime"] == 0.0
    assert events[1]["startTime"] == 2.0
    assert events[3]["endTime"] == 8.0


def test_build_fromProfile_flag():
    events = build_chord_events_from_progression(["i"], "A", "minor", 0.0, 4.0)
    assert events[0]["fromProfile"] is True


def test_build_empty_progression():
    assert build_chord_events_from_progression([], "C", "major", 0.0, 8.0) == []


# ─── apply_swing ──────────────────────────────────────────────────────────────

def test_swing_zero_no_change():
    notes = [{"startTime": 0.25, "duration": 0.2, "pitch": 60, "velocity": 80}]
    assert apply_swing(notes, 0.0)[0]["startTime"] == 0.25


def test_swing_delays_offbeat():
    notes = [{"startTime": 0.25, "duration": 0.2, "pitch": 60, "velocity": 80}]
    result = apply_swing(notes, 0.33)
    assert result[0]["startTime"] > 0.25


def test_swing_no_affect_long_notes():
    notes = [{"startTime": 0.0, "duration": 1.0, "pitch": 60, "velocity": 80}]
    assert apply_swing(notes, 0.45)[0]["startTime"] == 0.0


# ─── get_progression_for_section ──────────────────────────────────────────────

def test_get_progression_verse_returns_first():
    analysis = {"_profileProgressionPatterns": [["i", "bVII"], ["IV", "V"]]}
    result = get_progression_for_section(analysis, "verse")
    assert result == ["i", "bVII"]


def test_get_progression_chorus_returns_longest():
    analysis = {"_profileProgressionPatterns": [["i", "bVII"], ["I", "IV", "V", "I"]]}
    result = get_progression_for_section(analysis, "chorus")
    assert result == ["I", "IV", "V", "I"]


def test_get_progression_empty_patterns():
    analysis = {"_profileProgressionPatterns": []}
    result = get_progression_for_section(analysis, "verse")
    assert result == []


def test_get_progression_missing_key():
    analysis = {}
    result = get_progression_for_section(analysis, "chorus")
    assert result == []
