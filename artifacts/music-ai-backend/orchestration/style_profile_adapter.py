"""
StyleProfile → Arranger Adapter

Converts a StyleProfile dict (from ConversationAgent / StyleEnricher)
into the exact arguments that generate_arrangement() expects.

This is the ONLY file that knows about both worlds.
arranger.py must not be aware of StyleProfile internals.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Map StyleProfile instrument names → arranger.py INSTRUMENTS keys
INSTRUMENT_NAME_MAP: dict[str, str] = {
    "clarinet":       "brass",        # fallback until clarinet added to INSTRUMENTS
    "violin":         "violin",
    "accordion":      "accordion",
    "tsimbl":         "tsimbl",
    "double_bass":    "double_bass",
    "tuba":           "brass",
    "trumpet":        "trumpet",
    "oud":            "oud",
    "darbuka":        "darbuka",
    "nay":            "nay",
    "qanun":          "qanun",
    "guitar":         "guitar",
    "piano":          "piano",
    "bass":           "bass",
    "drums":          "drums",
    "kick":           "drums",
    "strings":        "strings",
    "pad":            "pad",
    "choir":          "choir",
    "voice_wordless": "choir",
    "flute":          "nay",          # closest GM program
    "saxophone":      "saxophone",
    "synth_pad":      "pad",
    "lead_synth":     "lead_synth",
    "brass":          "brass",
}

# Map StyleProfile.scaleType → arranger harmonic_tendency
SCALE_TO_HARMONIC: dict[str, str] = {
    "freygish":           "phrygian_dominant",
    "minor":              "minor",
    "major":              "major",
    "dorian":             "dorian",
    "phrygian":           "phrygian",
    "maqam_hijaz":        "hijaz",
    "maqam_rast":         "major",
    "harmonic_minor":     "minor",
    "double_harmonic":    "double_harmonic",
    "pentatonic_minor":   "minor",
    "pentatonic_major":   "major",
}


def adapt_profile_to_arranger_args(
    profile: dict,
    analysis: dict,
    persona_id: Optional[str] = None,
) -> dict:
    """
    Main entry point.
    Returns a dict of kwargs ready to pass to generate_arrangement().
    """
    style_id = _derive_style_id(profile)
    instruments = _extract_instruments(profile)
    density = _derive_density(profile)
    tempo_factor = _derive_tempo_factor(profile, analysis)

    logger.info(
        f"Adapter: style_id={style_id}, instruments={instruments}, "
        f"density={density:.2f}, tempo_factor={tempo_factor:.2f}"
    )

    patched_analysis = _patch_analysis_with_profile(analysis, profile)

    return {
        "analysis":     patched_analysis,
        "style_id":     style_id,
        "instruments":  instruments,
        "density":      density,
        "do_humanize":  profile.get("humanizationLevel", 0.7) > 0.3,
        "tempo_factor": tempo_factor,
        "persona_id":   persona_id or profile.get("personaId"),
    }


def _derive_style_id(profile: dict) -> str:
    """
    Map profile.genre to the closest style_id in STYLES dict.
    Priority: exact match → parent_genre match → 'pop' fallback.
    """
    from orchestration.arranger import STYLES

    genre = profile.get("genre", "").lower().replace(" ", "_")
    if genre in STYLES:
        return genre

    GENRE_PARENT_MAP: dict[str, str] = {
        "klezmer":         "hasidic",
        "hasidic_nigun":   "hasidic",
        "sephardic":       "middle_eastern",
        "maqam_hijaz":     "middle_eastern",
        "flamenco":        "acoustic",
        "bossa_nova":      "bossa_nova",
        "tango":           "acoustic",
        "afrobeat":        "pop",
        "jazz_bebop":      "jazz",
        "celtic":          "acoustic",
        "blues":           "jazz",
        "gospel":          "rnb",
        "soul":            "rnb",
        "reggae":          "pop",
        "latin":           "bossa_nova",
        "cumbia":          "pop",
        "salsa":           "jazz",
        "baroque":         "classical",
        "romantic":        "classical",
        "ambient":         "ambient",
        "trap":            "hiphop",
        "edm":             "electronic",
        "house":           "electronic",
    }
    parent = GENRE_PARENT_MAP.get(genre)
    if parent and parent in STYLES:
        logger.info(f"Genre '{genre}' mapped to parent style '{parent}'")
        return parent

    logger.warning(f"Unknown genre '{genre}', falling back to pop")
    return "pop"


def _extract_instruments(profile: dict) -> list[str]:
    """
    Convert InstrumentConfig[] from profile to canonical arranger instrument names.
    Preserves role ordering: MELODY → HARMONY → BASS → RHYTHM → COLOR.
    """
    from orchestration.arranger import INSTRUMENTS as ARRANGER_INSTRUMENTS

    ROLE_ORDER = {
        "MELODY_LEAD": 0, "MELODY_COUNTER": 1,
        "HARMONY_CHORD": 2, "HARMONY_PAD": 3,
        "BASS": 4,
        "RHYTHM_KICK": 5, "RHYTHM_SNARE": 6, "RHYTHM_PERC": 7,
        "COLOR": 8, "DRONE": 9,
    }

    raw_instruments = profile.get("instruments", [])
    if not raw_instruments:
        return ["drums", "bass", "piano"]

    mapped = []
    seen: set[str] = set()
    sorted_insts = sorted(
        raw_instruments,
        key=lambda i: ROLE_ORDER.get(i.get("role", "COLOR"), 9)
    )

    for inst_cfg in sorted_insts:
        name = inst_cfg.get("name", "").lower().replace(" ", "_")
        canonical = INSTRUMENT_NAME_MAP.get(name, name)
        if canonical in ARRANGER_INSTRUMENTS and canonical not in seen:
            mapped.append(canonical)
            seen.add(canonical)

    if not mapped:
        logger.warning("No instruments mapped, using defaults: drums, bass, piano")
        return ["drums", "bass", "piano"]

    if "drums" not in mapped and "darbuka" not in mapped:
        mapped.append("drums")
    if "bass" not in mapped and "double_bass" not in mapped:
        mapped.append("bass")

    return mapped


def _derive_density(profile: dict) -> float:
    """Derive a base density float (0.0–1.0) from profile.textureType."""
    TEXTURE_DENSITY = {
        "sparse":  0.35,
        "medium":  0.60,
        "layered": 0.75,
        "dense":   0.90,
    }
    texture = profile.get("textureType", "layered").lower()
    return TEXTURE_DENSITY.get(texture, 0.70)


def _derive_tempo_factor(profile: dict, analysis: dict) -> float:
    """
    If analysis has a detected BPM and profile has a bpmRange,
    return the factor needed to bring the arrangement BPM to the target.
    Otherwise return 1.0.
    """
    detected_bpm = analysis.get("rhythm", {}).get("bpm", 0)
    bpm_range = profile.get("bpmRange", [])
    if not detected_bpm or not bpm_range or len(bpm_range) < 2:
        return 1.0
    target_bpm = (bpm_range[0] + bpm_range[1]) / 2.0
    factor = target_bpm / detected_bpm
    return max(0.5, min(2.0, round(factor, 3)))


def _patch_analysis_with_profile(analysis: dict, profile: dict) -> dict:
    """
    Inject profile harmonic data into the analysis dict so that
    chord generators in arranger.py use the correct scale/mode.
    Does not overwrite detected values — only fills gaps.
    """
    patched = dict(analysis)

    scale_type = profile.get("scaleType", "")
    harmonic = SCALE_TO_HARMONIC.get(scale_type, "minor")

    patched["_profileHarmonicTendency"] = harmonic
    patched["_profileScaleType"] = scale_type
    patched["_profileChordVocabulary"] = profile.get("chordVocabulary", [])
    patched["_profileProgressionPatterns"] = profile.get("progressionPatterns", [])
    patched["_profileOrnamentStyle"] = profile.get("ornamentStyle", "none")
    patched["_profileSwingFactor"] = profile.get("swingFactor", 0.0)
    patched["_profileGrooveTemplate"] = profile.get("grooveTemplate", "on_top")
    patched["_profileTimeSignature"] = profile.get("timeSignature", "4/4")
    patched["_isFallback"] = profile.get("isFallback", False)

    return patched
