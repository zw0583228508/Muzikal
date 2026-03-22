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

    logger.info(f"Detected {len(chord_events)} chord events")

    return {
        "chords": chord_events,
        "leadSheet": lead_sheet,
    }
