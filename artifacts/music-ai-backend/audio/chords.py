"""
Chord Engine: Advanced chord detection using chroma features + music theory.
Uses template matching with extended chord vocabulary.
"""

import logging
import numpy as np
import librosa
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Extended chord templates (12-dimensional chroma)
CHORD_TEMPLATES = {}


def build_chord_templates():
    """Build comprehensive chord template dictionary."""
    templates = {}
    for root_idx, root in enumerate(NOTE_NAMES):
        def make_template(intervals):
            t = np.zeros(12)
            for interval in intervals:
                t[(root_idx + interval) % 12] = 1.0
            return t

        # Major chords
        templates[f"{root}"] = make_template([0, 4, 7])
        templates[f"{root}maj7"] = make_template([0, 4, 7, 11])
        templates[f"{root}6"] = make_template([0, 4, 7, 9])
        templates[f"{root}add9"] = make_template([0, 2, 4, 7])

        # Minor chords
        templates[f"{root}m"] = make_template([0, 3, 7])
        templates[f"{root}m7"] = make_template([0, 3, 7, 10])
        templates[f"{root}m9"] = make_template([0, 2, 3, 7, 10])

        # Dominant 7th
        templates[f"{root}7"] = make_template([0, 4, 7, 10])
        templates[f"{root}9"] = make_template([0, 2, 4, 7, 10])
        templates[f"{root}13"] = make_template([0, 4, 7, 9, 10])

        # Diminished / Augmented
        templates[f"{root}dim"] = make_template([0, 3, 6])
        templates[f"{root}dim7"] = make_template([0, 3, 6, 9])
        templates[f"{root}aug"] = make_template([0, 4, 8])

        # Suspended
        templates[f"{root}sus2"] = make_template([0, 2, 7])
        templates[f"{root}sus4"] = make_template([0, 5, 7])

    # Normalize templates
    for k in templates:
        norm = np.linalg.norm(templates[k])
        if norm > 0:
            templates[k] = templates[k] / norm
    return templates


CHORD_TEMPLATES = build_chord_templates()

# Roman numeral mapping for common keys
SCALE_DEGREES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
}

ROMAN_NUMERALS_MAJOR = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
ROMAN_NUMERALS_MINOR = ["i", "ii°", "III", "iv", "v", "VI", "VII"]


def get_roman_numeral(chord: str, key: str, mode: str) -> str:
    """Convert chord symbol to Roman numeral relative to key."""
    key_root = key.replace("m", "")
    try:
        key_idx = NOTE_NAMES.index(key_root)
    except ValueError:
        return "?"

    chord_root = chord.replace("m", "").replace("7", "").replace("maj", "").replace("dim", "").replace("aug", "").replace("sus", "").replace("add", "").replace("2", "").replace("4", "").replace("6", "").replace("9", "").replace("13", "")
    chord_root = chord_root.strip()

    try:
        chord_idx = NOTE_NAMES.index(chord_root) if chord_root in NOTE_NAMES else -1
    except ValueError:
        return "?"

    if chord_idx < 0:
        return "?"

    interval = (chord_idx - key_idx) % 12
    scale = SCALE_DEGREES.get(mode, SCALE_DEGREES["major"])

    try:
        degree = scale.index(interval)
        romans = ROMAN_NUMERALS_MINOR if mode == "minor" else ROMAN_NUMERALS_MAJOR
        return romans[degree]
    except ValueError:
        return "?"


def match_chord(chroma_vec: np.ndarray, top_k: int = 4) -> List[tuple]:
    """Match chroma vector to best chord templates. Returns top-k matches."""
    norm = np.linalg.norm(chroma_vec)
    if norm < 0.01:
        return [("N.C.", 0.0)]

    chroma_norm = chroma_vec / norm
    scores = {}
    for chord_name, template in CHORD_TEMPLATES.items():
        score = float(np.dot(chroma_norm, template))
        scores[chord_name] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def analyze_chords(y: np.ndarray, sr: int, rhythm: dict, key: dict) -> Dict[str, Any]:
    """
    Chord analysis synced to beat grid.
    Analyzes chroma at each beat position and returns chord timeline.
    """
    logger.info("Running chord analysis...")

    hop_length = 512
    beat_times = rhythm.get("beatGrid", [])
    global_key = key.get("globalKey", "C")
    mode = key.get("mode", "major")

    if not beat_times:
        beat_times = [0.0]

    # Compute chroma with harmonic/percussive separation for cleaner chords
    y_harm = librosa.effects.harmonic(y, margin=8)
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop_length, bins_per_octave=36, n_chroma=12)

    chord_events = []
    lead_sheet_parts = []

    # Analyze chords per beat (or per 2 beats for stability)
    step = 2  # Analyze per 2 beats for stability
    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop_length)

    for i in range(0, len(beat_times) - step, step):
        start_time = float(beat_times[i])
        end_time = float(beat_times[min(i + step, len(beat_times) - 1)])

        start_frame = beat_frames[i]
        end_frame = beat_frames[min(i + step, len(beat_frames) - 1)]

        # Get chroma for this segment
        seg_chroma = chroma[:, start_frame:end_frame].mean(axis=1)
        matches = match_chord(seg_chroma, top_k=4)

        if not matches:
            continue

        best_chord, best_score = matches[0]
        alternatives = [m[0] for m in matches[1:4]]
        roman = get_roman_numeral(best_chord, global_key, mode)
        confidence = max(0.0, min(1.0, best_score))

        chord_events.append({
            "startTime": round(start_time, 3),
            "endTime": round(end_time, 3),
            "chord": best_chord,
            "romanNumeral": roman,
            "confidence": round(confidence, 3),
            "alternatives": alternatives,
        })
        lead_sheet_parts.append(f"{best_chord}({roman})")

    # Build lead sheet string (chord names per measure)
    lead_sheet = " | ".join(lead_sheet_parts[:16]) if lead_sheet_parts else ""

    avg_confidence = float(np.mean([c["confidence"] for c in chord_events])) if chord_events else 0.0
    low_conf_count = sum(1 for c in chord_events if c["confidence"] < 0.5)

    warnings = []
    if not chord_events:
        warnings.append("No chord events detected — audio may be non-harmonic or too short")
    elif avg_confidence < 0.5:
        warnings.append(f"Low average chord confidence ({avg_confidence:.0%}) — harmonic content may be sparse")
    if low_conf_count > len(chord_events) * 0.4:
        warnings.append(f"{low_conf_count}/{len(chord_events)} chords have low confidence — consider manual review")

    alternatives = list({c["alternatives"][0] for c in chord_events if c.get("alternatives")} )[:5]

    logger.info(f"Detected {len(chord_events)} chord events, avg confidence={avg_confidence:.2f}")

    return {
        "chords": chord_events,
        "leadSheet": lead_sheet,
        "confidence": round(avg_confidence, 3),
        "alternatives": alternatives,
        "warnings": warnings,
        "model": "chroma-cqt-template",
    }


# ─── Chord Substitution Engine ─────────────────────────────────────────────────

CHORD_SUBSTITUTIONS: dict[str, list[dict]] = {
    "C":    [{"chord": "Em",   "type": "mediant",      "description": "Mediant substitution"},
             {"chord": "Am",   "type": "relative",     "description": "Relative minor"},
             {"chord": "C/E",  "type": "inversion",    "description": "First inversion"}],
    "Am":   [{"chord": "C",    "type": "relative",     "description": "Relative major"},
             {"chord": "Am7",  "type": "extension",    "description": "Add 7th"},
             {"chord": "Am/E", "type": "inversion",    "description": "First inversion"}],
    "G":    [{"chord": "G7",   "type": "extension",    "description": "Dominant 7th"},
             {"chord": "Bdim", "type": "tritone_sub",  "description": "Leading tone dim"},
             {"chord": "Db7",  "type": "tritone_sub",  "description": "Tritone substitution"}],
    "G7":   [{"chord": "Db7",  "type": "tritone_sub",  "description": "Tritone sub"},
             {"chord": "Bdim", "type": "diminished",   "description": "Diminished sub"}],
    "F":    [{"chord": "Dm",   "type": "parallel",     "description": "Parallel minor"},
             {"chord": "F7",   "type": "extension",    "description": "Subdominant 7th"}],
    "Dm":   [{"chord": "F",    "type": "relative",     "description": "Relative major"},
             {"chord": "Dm7",  "type": "extension",    "description": "Add 7th"}],
    "Em":   [{"chord": "C",    "type": "mediant",      "description": "Mediant sub"},
             {"chord": "Em7",  "type": "extension",    "description": "Add 7th"}],
    "E":    [{"chord": "E7",   "type": "extension",    "description": "Dominant 7th"},
             {"chord": "Bb7",  "type": "tritone_sub",  "description": "Tritone substitution"}],
    "D":    [{"chord": "D7",   "type": "extension",    "description": "Dominant 7th"},
             {"chord": "F#m",  "type": "mediant",      "description": "Mediant sub"}],
    "A":    [{"chord": "A7",   "type": "extension",    "description": "Dominant 7th"},
             {"chord": "Eb7",  "type": "tritone_sub",  "description": "Tritone substitution"}],
    "Am7":  [{"chord": "C",    "type": "relative",     "description": "Relative major"},
             {"chord": "Fmaj7","type": "subdominant",  "description": "Subdominant maj7"}],
    "Cmaj7":[{"chord": "Em7",  "type": "mediant",      "description": "Mediant maj7"},
             {"chord": "Am7",  "type": "relative",     "description": "Relative minor 7th"}],
}


def get_chord_substitutions(chord_name: str, style: str = "jazz") -> list[dict]:
    """
    Return substitution options for a given chord.

    Args:
        chord_name: Chord symbol e.g. "Am", "G7", "Cmaj7"
        style: "jazz" | "pop" | "classical" — affects which subs are returned

    Returns:
        List of dicts with keys: chord, type, description
    """
    # Try exact match first, then root-only match
    subs = CHORD_SUBSTITUTIONS.get(chord_name)
    if subs is None:
        # Strip extensions to find root
        root = chord_name
        for suffix in ["maj7", "m7b5", "m7", "dim7", "dim", "aug", "sus4", "sus2", "7", "m"]:
            root = root.replace(suffix, "")
        subs = CHORD_SUBSTITUTIONS.get(root, [])

    # Filter by style
    if style == "pop":
        subs = [s for s in subs if s["type"] not in ["tritone_sub", "diminished"]]
    elif style == "classical":
        subs = [s for s in subs if s["type"] in ["inversion", "relative", "mediant"]]

    return subs[:4]  # max 4 suggestions
