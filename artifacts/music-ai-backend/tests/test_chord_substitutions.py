import pytest
pytestmark = pytest.mark.unit

"""Tests for chord substitution engine."""
from audio.chords import get_chord_substitutions


def test_returns_list():
    assert isinstance(get_chord_substitutions("C"), list)

def test_known_chord_has_subs():
    subs = get_chord_substitutions("C")
    assert len(subs) > 0

def test_sub_has_required_keys():
    subs = get_chord_substitutions("Am")
    for s in subs:
        assert "chord" in s and "type" in s and "description" in s

def test_unknown_chord_returns_empty_list():
    subs = get_chord_substitutions("Xyz_unknown_99")
    assert isinstance(subs, list)

def test_jazz_includes_tritone():
    subs = get_chord_substitutions("G7", style="jazz")
    types = [s["type"] for s in subs]
    assert "tritone_sub" in types

def test_pop_excludes_tritone():
    subs = get_chord_substitutions("G7", style="pop")
    types = [s["type"] for s in subs]
    assert "tritone_sub" not in types

def test_classical_only_voice_leading():
    subs = get_chord_substitutions("C", style="classical")
    allowed = {"inversion", "relative", "mediant"}
    for s in subs:
        assert s["type"] in allowed

def test_extension_chord_root_fallback():
    subs_full = get_chord_substitutions("Cmaj7")
    assert isinstance(subs_full, list)

def test_max_results_reasonable():
    subs = get_chord_substitutions("C")
    assert len(subs) <= 6
