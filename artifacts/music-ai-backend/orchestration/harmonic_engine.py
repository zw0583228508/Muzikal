"""
Harmonic Engine — Step 8

Responsibilities:
  1. Translate Roman numeral chord symbols to absolute chord names
     e.g. "i" in key of D minor  ->  "Dm"
     e.g. "bVII" in key of D     ->  "C"
     e.g. "V7" in key of D minor ->  "A7"

  2. Build chord_events list from a progression pattern + detected key + duration

  3. Apply swing timing to a list of note events

Used by arranger.py when _profileProgressionPatterns is present in analysis.
Never called directly from routes — always via generate_arrangement().
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Chromatic scale — used for transposition
CHROMATIC = ["C", "C#", "D", "D#", "E", "F",
             "F#", "G", "G#", "A", "A#", "B"]

# Semitone distance from tonic for each Roman numeral degree
DEGREE_SEMITONES: dict[str, int] = {
    "I": 0,   "bII": 1,   "II": 2,   "bIII": 3,  "III": 4,
    "IV": 5,  "#IV": 6,   "bV": 6,   "V": 7,     "bVI": 8,
    "VI": 9,  "bVII": 10, "VII": 11,
    # Lowercase aliases (minor context)
    "i": 0,   "bii": 1,   "ii": 2,   "biii": 3,  "iii": 4,
    "iv": 5,  "#iv": 6,   "v": 7,    "bvi": 8,
    "vi": 9,  "bvii": 10, "vii": 11,
}

# Quality suffix mapping
QUALITY_MAP: dict[str, str] = {
    "maj7":  "maj7",
    "m7b5":  "m7b5",
    "m7":    "m7",
    "dim7":  "dim7",
    "dim":   "dim",
    "aug":   "aug",
    "sus4":  "sus4",
    "sus2":  "sus2",
    "add9":  "add9",
    "6":     "6",
    "7":     "7",
    "m":     "m",
}

# Enharmonic normalisation
_ENHARMONIC: dict[str, str] = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B",
}


def roman_to_chord(roman: str, key: str, scale_type: str = "minor") -> str:
    """
    Convert a Roman numeral symbol to an absolute chord name.

    Args:
        roman:      "i", "bVII", "V7", "Imaj7", "bVI", etc.
        key:        "D", "Am", "F#" — root note name only (strip "m" suffix)
        scale_type: "minor" | "major" | "freygish" | etc.
    Returns:
        Absolute chord name: "Dm", "C", "A7", "Bbmaj7"
    """
    if not roman:
        return "C"

    # Normalise key to root pitch class only
    key_root = key.rstrip("m").strip()
    if key_root not in CHROMATIC:
        key_root = _ENHARMONIC.get(key_root, "C")

    key_idx = CHROMATIC.index(key_root)

    # Split Roman numeral into degree + quality suffix
    degree_part, quality_suffix = _split_roman(roman)

    # Get semitone offset for this degree
    semitones = DEGREE_SEMITONES.get(degree_part)
    if semitones is None:
        logger.warning(f"Unknown Roman numeral degree: {degree_part!r}, defaulting to I")
        semitones = 0

    # Compute absolute root
    root_idx = (key_idx + semitones) % 12
    root_name = CHROMATIC[root_idx]

    # Determine default quality from degree case + scale context
    if not quality_suffix:
        quality_suffix = _default_quality(degree_part, scale_type)

    # Lowercase degree + dominant 7th → minor 7th (e.g. ii7 → iim7 = Am7)
    if quality_suffix == "7" and degree_part == degree_part.lower():
        quality_suffix = "m7"

    return root_name + quality_suffix


def _split_roman(roman: str) -> tuple[str, str]:
    """
    Split "bVIImaj7" into ("bVII", "maj7").
    Handles: flat prefix (b), sharp prefix (#), case.
    Tries longest quality suffix match first.
    """
    for quality in sorted(QUALITY_MAP.keys(), key=len, reverse=True):
        if roman.upper().endswith(quality.upper()):
            degree = roman[: -len(quality)]
            return degree, QUALITY_MAP[quality]
    return roman, ""


def _default_quality(degree: str, scale_type: str) -> str:
    """
    Return the default triad quality for a scale degree in a given scale context.
    Lowercase = minor context (i, iv, v), Uppercase = major context (I, IV, V).
    """
    is_lower = degree == degree.lower()
    has_flat = degree.startswith("b")
    stripped = degree.lstrip("b#").upper()

    if scale_type in (
        "minor", "freygish", "phrygian", "dorian", "hijaz",
        "maqam_hijaz", "double_harmonic", "harmonic_minor",
    ):
        MINOR_DEFAULTS = {
            "I": "m",   "II": "dim", "III": "",  "IV": "m",
            "V": "",    "VI": "",    "VII": "dim",
        }
        quality = MINOR_DEFAULTS.get(stripped, "m" if is_lower else "")
        # bVII in minor is the subtonic — a major chord, not diminished
        if has_flat and stripped == "VII" and not is_lower:
            quality = ""
        return quality
    else:
        MAJOR_DEFAULTS = {
            "I": "",    "II": "m",   "III": "m", "IV": "",
            "V": "",    "VI": "m",   "VII": "dim",
        }
        return MAJOR_DEFAULTS.get(stripped, "")


def build_chord_events_from_progression(
    progression: list[str],
    key: str,
    scale_type: str,
    start_time: float,
    total_duration: float,
) -> list[dict]:
    """
    Convert a Roman numeral progression to a list of chord_events dicts.

    Args:
        progression:    ["i", "bVII", "bVI", "V7"]
        key:            "D" (detected from audio analysis)
        scale_type:     "freygish"
        start_time:     0.0
        total_duration: 8.0  (seconds for this section)

    Returns:
        [{"chord": "Dm", "startTime": 0.0, "endTime": 2.0},
         {"chord": "C",  "startTime": 2.0, "endTime": 4.0}, ...]
    """
    if not progression:
        return []

    chord_dur = total_duration / len(progression)
    events = []
    for i, roman in enumerate(progression):
        chord_name = roman_to_chord(roman, key, scale_type)
        events.append({
            "chord":       chord_name,
            "startTime":   round(start_time + i * chord_dur, 3),
            "endTime":     round(start_time + (i + 1) * chord_dur, 3),
            "roman":       roman,
            "fromProfile": True,
        })
    return events


def apply_swing(notes: list[dict], swing_factor: float) -> list[dict]:
    """
    Apply swing/shuffle timing to a list of note events.

    swing_factor = 0.0  -> straight (no change)
    swing_factor = 0.33 -> light shuffle
    swing_factor = 0.45 -> jazz swing
    swing_factor = 0.5  -> dotted-eighth feel (hard swing)

    Only notes shorter than 0.4s are affected (eighth notes and shorter).
    """
    if swing_factor < 0.01:
        return notes

    result = []
    for note in notes:
        n = dict(note)
        dur = n.get("duration", 0.25)
        if dur < 0.4:
            beat_pos = n["startTime"] % 0.5
            if beat_pos > 0.2:
                delay = swing_factor * (0.5 - beat_pos)
                n["startTime"] = round(n["startTime"] + delay, 4)
        result.append(n)
    return result


def get_progression_for_section(
    analysis: dict,
    section_label: str,
) -> list[str]:
    """
    Pick the best progression from _profileProgressionPatterns for a section.
    - chorus/refrain: pick the most harmonic (longest) pattern
    - verse: pick the first pattern
    - bridge: pick the last pattern (most contrasting)
    - default: first pattern
    """
    patterns = analysis.get("_profileProgressionPatterns", [])

    if not patterns:
        return []

    label = section_label.lower()

    if label in ("chorus", "refrain"):
        return max(patterns, key=len)
    elif label in ("bridge", "solo"):
        return patterns[-1]
    else:
        return patterns[0]
