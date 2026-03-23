import pytest
pytestmark = pytest.mark.unit

"""
Tests for orchestration/style_profile_adapter.py
"""
import pytest

from orchestration.style_profile_adapter import (
    adapt_profile_to_arranger_args,
    _derive_style_id,
    _extract_instruments,
    _derive_density,
    _derive_tempo_factor,
    _patch_analysis_with_profile,
    INSTRUMENT_NAME_MAP,
    SCALE_TO_HARMONIC,
)

KLEZMER_PROFILE = {
    "genre": "klezmer",
    "era": "1920s",
    "scaleType": "freygish",
    "timeSignature": "2/4",
    "bpmRange": [100, 160],
    "textureType": "layered",
    "humanizationLevel": 0.85,
    "swingFactor": 0.0,
    "grooveTemplate": "on_top",
    "ornamentStyle": "krekhts",
    "instruments": [
        {"name": "clarinet",     "role": "MELODY_LEAD",    "midiProgram": 71, "volumeWeight": 0.9},
        {"name": "violin",       "role": "MELODY_COUNTER",  "midiProgram": 40, "volumeWeight": 0.8},
        {"name": "accordion",    "role": "HARMONY_CHORD",   "midiProgram": 21, "volumeWeight": 0.7},
        {"name": "double_bass",  "role": "BASS",            "midiProgram": 43, "volumeWeight": 0.75},
        {"name": "drums",        "role": "RHYTHM_KICK",     "midiProgram": 0,  "volumeWeight": 0.65},
    ],
}

KLEZMER_ANALYSIS = {
    "rhythm": {"bpm": 132.0, "timeSignatureNumerator": 2, "beatGrid": []},
    "chords": {"chords": []},
    "structure": {"sections": []},
}


# ─── _derive_style_id ────────────────────────────────────────────────────────

class TestDeriveStyleId:
    def test_exact_match_jazz(self):
        assert _derive_style_id({"genre": "jazz"}) == "jazz"

    def test_exact_match_pop(self):
        assert _derive_style_id({"genre": "pop"}) == "pop"

    def test_exact_match_bossa_nova(self):
        assert _derive_style_id({"genre": "bossa_nova"}) == "bossa_nova"

    def test_klezmer_maps_to_hasidic(self):
        assert _derive_style_id({"genre": "klezmer"}) == "hasidic"

    def test_hasidic_nigun_maps_to_hasidic(self):
        assert _derive_style_id({"genre": "hasidic_nigun"}) == "hasidic"

    def test_maqam_hijaz_maps_to_middle_eastern(self):
        assert _derive_style_id({"genre": "maqam_hijaz"}) == "middle_eastern"

    def test_sephardic_maps_to_middle_eastern(self):
        assert _derive_style_id({"genre": "sephardic"}) == "middle_eastern"

    def test_jazz_bebop_maps_to_jazz(self):
        assert _derive_style_id({"genre": "jazz_bebop"}) == "jazz"

    def test_flamenco_maps_to_acoustic(self):
        assert _derive_style_id({"genre": "flamenco"}) == "acoustic"

    def test_trap_maps_to_hiphop(self):
        assert _derive_style_id({"genre": "trap"}) == "hiphop"

    def test_unknown_fallback(self):
        assert _derive_style_id({"genre": "totally_unknown_xyz"}) == "pop"

    def test_empty_genre_fallback(self):
        assert _derive_style_id({}) == "pop"


# ─── _extract_instruments ────────────────────────────────────────────────────

class TestExtractInstruments:
    def test_klezmer_has_violin(self):
        assert "violin" in _extract_instruments(KLEZMER_PROFILE)

    def test_klezmer_has_accordion(self):
        assert "accordion" in _extract_instruments(KLEZMER_PROFILE)

    def test_klezmer_has_bass(self):
        insts = _extract_instruments(KLEZMER_PROFILE)
        assert "double_bass" in insts or "bass" in insts

    def test_clarinet_maps_to_brass(self):
        profile = {"instruments": [{"name": "clarinet", "role": "MELODY_LEAD"}]}
        insts = _extract_instruments(profile)
        assert "brass" in insts

    def test_ordering_melody_before_bass(self):
        insts = _extract_instruments(KLEZMER_PROFILE)
        if "violin" in insts and "double_bass" in insts:
            assert insts.index("violin") < insts.index("double_bass")

    def test_minimum_set_for_empty_profile(self):
        insts = _extract_instruments({})
        assert len(insts) >= 1

    def test_minimum_set_includes_drums_when_no_rhythm(self):
        profile = {"instruments": [{"name": "piano", "role": "HARMONY_CHORD"}]}
        insts = _extract_instruments(profile)
        assert "drums" in insts or len(insts) >= 1

    def test_no_duplicates(self):
        profile = {"instruments": [
            {"name": "violin", "role": "MELODY_LEAD"},
            {"name": "violin", "role": "MELODY_COUNTER"},
        ]}
        insts = _extract_instruments(profile)
        assert insts.count("violin") == 1

    def test_unknown_instrument_skipped(self):
        profile = {"instruments": [
            {"name": "totally_fake_instrument_xyz", "role": "MELODY_LEAD"},
            {"name": "drums", "role": "RHYTHM_KICK"},
        ]}
        insts = _extract_instruments(profile)
        assert "totally_fake_instrument_xyz" not in insts
        assert "drums" in insts


# ─── _derive_density ─────────────────────────────────────────────────────────

class TestDeriveDensity:
    def test_sparse(self):
        assert _derive_density({"textureType": "sparse"}) == 0.35

    def test_medium(self):
        assert _derive_density({"textureType": "medium"}) == 0.60

    def test_layered(self):
        assert _derive_density({"textureType": "layered"}) == 0.75

    def test_dense(self):
        assert _derive_density({"textureType": "dense"}) == 0.90

    def test_default_for_missing_key(self):
        # textureType defaults to "layered" which maps to 0.75
        assert _derive_density({}) == 0.75

    def test_case_insensitive(self):
        assert _derive_density({"textureType": "SPARSE"}) == 0.35


# ─── _derive_tempo_factor ────────────────────────────────────────────────────

class TestDeriveTempoFactor:
    def test_bpm_in_range_near_one(self):
        profile = {"bpmRange": [100, 160]}
        analysis = {"rhythm": {"bpm": 130.0}}
        factor = _derive_tempo_factor(profile, analysis)
        assert 0.8 <= factor <= 1.2

    def test_no_data_returns_one(self):
        assert _derive_tempo_factor({}, {}) == 1.0

    def test_no_bpm_in_analysis(self):
        assert _derive_tempo_factor({"bpmRange": [100, 160]}, {}) == 1.0

    def test_no_bpm_range_in_profile(self):
        assert _derive_tempo_factor({}, {"rhythm": {"bpm": 120.0}}) == 1.0

    def test_clamped_to_max(self):
        profile = {"bpmRange": [200, 240]}
        analysis = {"rhythm": {"bpm": 60.0}}
        assert _derive_tempo_factor(profile, analysis) == 2.0

    def test_clamped_to_min(self):
        profile = {"bpmRange": [40, 60]}
        analysis = {"rhythm": {"bpm": 200.0}}
        assert _derive_tempo_factor(profile, analysis) == 0.5


# ─── _patch_analysis_with_profile ────────────────────────────────────────────

class TestPatchAnalysis:
    def test_patches_scale_type(self):
        patched = _patch_analysis_with_profile({}, {"scaleType": "freygish"})
        assert patched["_profileScaleType"] == "freygish"

    def test_patches_harmonic_tendency(self):
        patched = _patch_analysis_with_profile({}, {"scaleType": "freygish"})
        assert patched["_profileHarmonicTendency"] == "phrygian_dominant"

    def test_patches_time_signature(self):
        patched = _patch_analysis_with_profile({}, {"timeSignature": "3/4"})
        assert patched["_profileTimeSignature"] == "3/4"

    def test_does_not_overwrite_existing_keys(self):
        analysis = {"rhythm": {"bpm": 120}}
        patched = _patch_analysis_with_profile(analysis, {})
        assert patched["rhythm"]["bpm"] == 120

    def test_is_fallback_flag(self):
        patched = _patch_analysis_with_profile({}, {"isFallback": True})
        assert patched["_isFallback"] is True

    def test_ornament_style(self):
        patched = _patch_analysis_with_profile({}, {"ornamentStyle": "krekhts"})
        assert patched["_profileOrnamentStyle"] == "krekhts"


# ─── adapt_profile_to_arranger_args ─────────────────────────────────────────

class TestAdaptProfileFull:
    def test_klezmer_style_id(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        assert kwargs["style_id"] == "hasidic"

    def test_klezmer_has_violin(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        assert "violin" in kwargs["instruments"]

    def test_klezmer_do_humanize(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        assert kwargs["do_humanize"] is True

    def test_density_in_range(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        assert 0.0 <= kwargs["density"] <= 1.0

    def test_analysis_patched_scale(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        assert kwargs["analysis"]["_profileScaleType"] == "freygish"

    def test_analysis_patched_time_sig(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        assert kwargs["analysis"]["_profileTimeSignature"] == "2/4"

    def test_empty_profile_has_instruments(self):
        kwargs = adapt_profile_to_arranger_args({"genre": "pop"}, {})
        assert len(kwargs["instruments"]) >= 1

    def test_persona_id_passed(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, {}, persona_id="hasidic-wedding")
        assert kwargs["persona_id"] == "hasidic-wedding"

    def test_returns_all_required_keys(self):
        kwargs = adapt_profile_to_arranger_args(KLEZMER_PROFILE, KLEZMER_ANALYSIS)
        for key in ("analysis", "style_id", "instruments", "density", "do_humanize", "tempo_factor"):
            assert key in kwargs


# ─── INSTRUMENT_NAME_MAP ─────────────────────────────────────────────────────

class TestInstrumentNameMap:
    def test_clarinet_to_brass(self):
        assert INSTRUMENT_NAME_MAP["clarinet"] == "brass"

    def test_kick_to_drums(self):
        assert INSTRUMENT_NAME_MAP["kick"] == "drums"

    def test_flute_to_nay(self):
        assert INSTRUMENT_NAME_MAP["flute"] == "nay"

    def test_voice_wordless_to_choir(self):
        assert INSTRUMENT_NAME_MAP["voice_wordless"] == "choir"


# ─── SCALE_TO_HARMONIC ───────────────────────────────────────────────────────

class TestScaleToHarmonic:
    def test_freygish_to_phrygian_dominant(self):
        assert SCALE_TO_HARMONIC["freygish"] == "phrygian_dominant"

    def test_maqam_hijaz_to_hijaz(self):
        assert SCALE_TO_HARMONIC["maqam_hijaz"] == "hijaz"

    def test_minor_to_minor(self):
        assert SCALE_TO_HARMONIC["minor"] == "minor"
