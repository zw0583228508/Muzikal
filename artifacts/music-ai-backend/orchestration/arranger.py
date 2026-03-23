"""
Arrangement & Orchestration Engine.
Generates multi-track MIDI arrangements based on analysis + style.
Loads style profiles from configs/styles/arranger_profiles.yaml.
"""

import os
import logging
import random
import math
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ─── Locate workspace root ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.environ.get(
    "WORKSPACE_ROOT",
    os.path.normpath(os.path.join(_HERE, "..", "..", "..")),
)


def _load_arranger_profiles() -> Dict[str, Any]:
    """Load arranger_profiles.yaml. Falls back to empty dict on failure."""
    profiles_path = os.path.join(WORKSPACE_ROOT, "configs", "styles", "arranger_profiles.yaml")
    try:
        import yaml  # type: ignore
        with open(profiles_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        logger.info(f"Loaded {len(profiles)} arranger profiles from {profiles_path}")
        return profiles
    except Exception as e:
        logger.warning(f"Could not load arranger_profiles.yaml: {e}")
        return {}


ARRANGER_PROFILES: Dict[str, Any] = _load_arranger_profiles()

# ─── Instrument definitions ───────────────────────────────────────────────────
INSTRUMENTS = {
    "drums":       {"channel": 9, "program": 0,  "color": "#e74c3c"},
    "bass":        {"channel": 1, "program": 33, "color": "#8e44ad"},
    "piano":       {"channel": 2, "program": 0,  "color": "#2980b9"},
    "guitar":      {"channel": 3, "program": 25, "color": "#27ae60"},
    "strings":     {"channel": 4, "program": 48, "color": "#f39c12"},
    "pad":         {"channel": 5, "program": 88, "color": "#1abc9c"},
    "lead_synth":  {"channel": 6, "program": 80, "color": "#e67e22"},
    "brass":       {"channel": 7, "program": 61, "color": "#c0392b"},
    "violin":      {"channel": 4, "program": 40, "color": "#d35400"},
    "accordion":   {"channel": 5, "program": 21, "color": "#7f8c8d"},
    "oud":         {"channel": 3, "program": 105,"color": "#795548"},
    "darbuka":     {"channel": 9, "program": 0,  "color": "#6d4c41"},
    "synth_pad":   {"channel": 5, "program": 88, "color": "#1abc9c"},
    "double_bass": {"channel": 1, "program": 43, "color": "#4a235a"},
    "trumpet":     {"channel": 7, "program": 56, "color": "#922b21"},
    "saxophone":   {"channel": 6, "program": 65, "color": "#b7950b"},
    "choir":       {"channel": 5, "program": 52, "color": "#1a5276"},
    "tsimbl":      {"channel": 4, "program": 11, "color": "#784212"},
    "nay":         {"channel": 6, "program": 73, "color": "#117a65"},
    "qanun":       {"channel": 4, "program": 46, "color": "#4a235a"},
}

# ─── Base style configs (fallback when profiles don't cover a style) ──────────
STYLES: Dict[str, Any] = {
    "pop":           {"instruments": ["drums", "bass", "piano", "guitar", "strings", "pad"], "density": 0.75},
    "jazz":          {"instruments": ["drums", "bass", "piano", "guitar", "brass"], "density": 0.65},
    "rnb":           {"instruments": ["drums", "bass", "piano", "guitar", "strings", "pad"], "density": 0.80},
    "classical":     {"instruments": ["strings", "brass", "piano"], "density": 0.85},
    "electronic":    {"instruments": ["drums", "bass", "pad", "lead_synth"], "density": 0.90},
    "rock":          {"instruments": ["drums", "bass", "guitar", "piano"], "density": 0.85},
    "bossa_nova":    {"instruments": ["drums", "bass", "guitar", "piano"], "density": 0.55},
    "ambient":       {"instruments": ["pad", "strings", "piano"], "density": 0.30},
    "hasidic":       {"instruments": ["drums", "bass", "violin", "accordion", "strings", "brass"], "density": 0.80,
                      "harmonic_tendencies": ["minor", "phrygian", "dorian"], "rhythm_feel": "freylekhs"},
    "middle_eastern":{"instruments": ["drums", "bass", "oud", "strings", "pad"], "density": 0.72,
                      "harmonic_tendencies": ["phrygian_dominant", "double_harmonic", "hijaz"], "rhythm_feel": "maqsum"},
    "hiphop":        {"instruments": ["drums", "bass", "pad", "lead_synth"], "density": 0.88},
    "ballad":        {"instruments": ["piano", "strings", "pad", "bass"], "density": 0.45},
    "cinematic":     {"instruments": ["strings", "brass", "piano", "pad", "drums"], "density": 0.90},
    "wedding":       {"instruments": ["drums", "bass", "piano", "brass", "strings", "guitar"], "density": 0.85},
    "acoustic":      {"instruments": ["guitar", "bass", "piano"], "density": 0.40},
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def chord_to_midi_notes(chord: str, octave: int = 4) -> List[int]:
    """Convert chord symbol to list of MIDI pitch numbers."""
    NOTE_MAP = {
        "C": 60, "C#": 61, "Db": 61, "D": 62, "D#": 63, "Eb": 63,
        "E": 64, "F": 65, "F#": 66, "Gb": 66, "G": 67, "G#": 68,
        "Ab": 68, "A": 69, "A#": 70, "Bb": 70, "B": 71,
    }
    if len(chord) >= 2 and chord[1] in "#b":
        root_name, quality = chord[:2], chord[2:]
    else:
        root_name, quality = chord[:1], chord[1:]

    root_midi = NOTE_MAP.get(root_name, 60)
    root_midi = 48 + (root_midi % 12)  # Normalise to octave 4–5

    if "maj7" in quality:    intervals = [0, 4, 7, 11]
    elif "m7b5" in quality:  intervals = [0, 3, 6, 10]
    elif "m7" in quality:    intervals = [0, 3, 7, 10]
    elif "dim7" in quality:  intervals = [0, 3, 6, 9]
    elif "dim" in quality:   intervals = [0, 3, 6]
    elif "aug" in quality:   intervals = [0, 4, 8]
    elif "sus4" in quality:  intervals = [0, 5, 7]
    elif "sus2" in quality:  intervals = [0, 2, 7]
    elif "7" in quality:     intervals = [0, 4, 7, 10]
    elif "m" in quality:     intervals = [0, 3, 7]
    elif "6" in quality:     intervals = [0, 4, 7, 9]
    elif "add9" in quality:  intervals = [0, 2, 4, 7]
    else:                    intervals = [0, 4, 7]

    return [root_midi + i for i in intervals]


def quantize_to_grid(t: float, beat_duration: float, subdivisions: int = 4) -> float:
    """Snap a time value to the nearest rhythmic subdivision."""
    grid = beat_duration / subdivisions
    return round(round(t / grid) * grid, 4)


def humanize(notes: List[Dict], timing_jitter: float = 0.01, velocity_jitter: int = 8) -> List[Dict]:
    """Apply subtle timing and velocity humanization."""
    humanized = []
    for note in notes:
        n = note.copy()
        n["startTime"] = max(0.0, note["startTime"] + random.gauss(0, timing_jitter))
        n["velocity"] = max(20, min(127, note["velocity"] + random.randint(-velocity_jitter, velocity_jitter)))
        humanized.append(n)
    return humanized


def _section_density(style_id: str, section_label: str, base_density: float) -> float:
    """Return density for a given section using the arranger profile, or fallback."""
    profile = ARRANGER_PROFILES.get(style_id, {})
    label_key = section_label.lower()
    if label_key in profile:
        section_cfg = profile[label_key]
        return float(section_cfg.get("density", base_density))
    # Heuristics for unspecified sections
    heuristics = {"intro": 0.45, "verse": 0.65, "chorus": 0.90, "bridge": 0.55, "outro": 0.40, "solo": 0.80}
    return heuristics.get(label_key, base_density)


def _section_instruments(style_id: str, section_label: str, base_instruments: List[str]) -> List[str]:
    """Return instrument list for a given section from profile, or fallback."""
    profile = ARRANGER_PROFILES.get(style_id, {})
    label_key = section_label.lower()
    if label_key in profile:
        section_cfg = profile[label_key]
        raw = section_cfg.get("instruments", [])
        if raw:
            # Map profile instrument names to our canonical INSTRUMENTS dict keys
            mapped = []
            for inst in raw:
                inst_key = inst.lower().replace(" ", "_").replace("-", "_")
                if inst_key in INSTRUMENTS:
                    mapped.append(inst_key)
                elif inst_key in base_instruments:
                    mapped.append(inst_key)
                # else skip unknown instruments silently
            return mapped or base_instruments
    return base_instruments


# ─── Pattern generators ────────────────────────────────────────────────────────

def generate_drum_pattern(
    beat_grid: List[float], time_sig: int, style: str, density: float,
    analysis: Optional[Dict] = None,
) -> List[Dict]:
    """Generate drum MIDI notes for a segment of the beat grid."""
    analysis = analysis or {}
    profile_ts = analysis.get("_profileTimeSignature", "4/4")
    if profile_ts == "3/4":
        time_sig = 3
    elif profile_ts == "6/8":
        time_sig = 6
    elif profile_ts == "7/8":
        time_sig = 7

    notes = []
    KICK = 36; SNARE = 38; CLOSED_HH = 42; OPEN_HH = 46
    CRASH = 49; TOM1 = 50; TOM2 = 47

    for i, beat_time in enumerate(beat_grid):
        beat_in_measure = i % time_sig
        next_time = beat_grid[i + 1] if i + 1 < len(beat_grid) else beat_time + 0.5
        bd = (next_time - beat_time) * 0.95

        # Kick
        if beat_in_measure == 0:
            notes.append({"startTime": round(beat_time, 3), "duration": round(bd * 0.3, 3), "pitch": KICK, "velocity": 100})
        elif beat_in_measure == 2 and random.random() < 0.6:
            notes.append({"startTime": round(beat_time, 3), "duration": round(bd * 0.3, 3), "pitch": KICK, "velocity": 90})

        # Snare
        if beat_in_measure in [1, 3]:
            vel = 95 if style not in ["ambient", "ballad"] else 60
            notes.append({"startTime": round(beat_time, 3), "duration": round(bd * 0.2, 3), "pitch": SNARE, "velocity": vel})

        # Hi-hat
        if density > 0.5:
            for sub in range(2):
                hh_time = beat_time + (next_time - beat_time) * sub / 2
                vel = 70 if sub == 0 else 55
                notes.append({"startTime": round(hh_time, 3), "duration": 0.05, "pitch": CLOSED_HH, "velocity": vel})
        else:
            notes.append({"startTime": round(beat_time, 3), "duration": 0.05, "pitch": CLOSED_HH, "velocity": 65})

        # Crash on section downbeats
        if beat_in_measure == 0 and i % (time_sig * 4) == 0:
            notes.append({"startTime": round(beat_time, 3), "duration": round(bd * 0.5, 3), "pitch": CRASH, "velocity": 85})

        # Hasidic freylekhs: add off-beat snare
        if style == "hasidic" and beat_in_measure == 0:
            notes.append({"startTime": round(beat_time + bd * 0.75, 3), "duration": 0.05, "pitch": SNARE, "velocity": 70})

        # Maqsum (Middle Eastern): accented beats 1 and 3-and
        if style == "middle_eastern":
            if beat_in_measure == 0:
                notes.append({"startTime": round(beat_time, 3), "duration": 0.1, "pitch": 41, "velocity": 95})  # darbuka dum
            if beat_in_measure == 2:
                notes.append({"startTime": round(beat_time + bd * 0.5, 3), "duration": 0.07, "pitch": 43, "velocity": 85})  # tek

    return notes


def generate_bass_line(chord_events: List[Dict], beat_grid: List[float], style: str) -> List[Dict]:
    """Generate bass line following chord roots."""
    notes = []
    beat_duration = (beat_grid[1] - beat_grid[0]) if len(beat_grid) > 1 else 0.5

    for chord_ev in chord_events:
        chord = chord_ev.get("chord", "C")
        start = chord_ev["startTime"]
        end = chord_ev["endTime"]
        dur = end - start

        midi_notes = chord_to_midi_notes(chord, octave=3)
        if not midi_notes:
            continue
        root = midi_notes[0] - 12  # Drop octave

        notes.append({"startTime": round(start, 3), "duration": round(dur * 0.45, 3), "pitch": root, "velocity": 88})

        if style == "jazz" and dur > 0.8:
            mid = start + dur * 0.5
            fifth = root + 7
            notes.append({"startTime": round(mid, 3), "duration": round(dur * 0.4, 3), "pitch": fifth, "velocity": 75})
        elif style in ["hasidic", "middle_eastern"] and dur > 0.6:
            # Oom-pah pattern
            notes.append({"startTime": round(start + dur * 0.5, 3), "duration": round(dur * 0.35, 3), "pitch": root + 7, "velocity": 72})
        elif style == "hiphop":
            # 808 sub bass — long sustain
            notes[-1]["duration"] = round(dur * 0.9, 3)
            notes[-1]["velocity"] = 100

    return notes


def generate_piano_voicings(chord_events: List[Dict], style: str, density: float) -> List[Dict]:
    """Generate piano chord voicings."""
    notes = []
    for chord_ev in chord_events:
        chord = chord_ev.get("chord", "C")
        start = chord_ev["startTime"]
        end = chord_ev["endTime"]
        duration = end - start
        midi_notes = chord_to_midi_notes(chord, octave=4)
        if not midi_notes:
            continue

        if style in ["pop", "rock"]:
            for pitch in midi_notes:
                notes.append({"startTime": round(start, 3), "duration": round(duration * 0.85, 3), "pitch": pitch, "velocity": 72})
        elif style == "jazz":
            offset = random.choice([0.0, 0.1, 0.25])
            for pitch in midi_notes:
                notes.append({"startTime": round(start + offset, 3), "duration": round(duration * 0.5, 3), "pitch": pitch, "velocity": 65})
        elif style in ["rnb", "bossa_nova"]:
            for j, pitch in enumerate(midi_notes):
                arp_t = start + j * (duration / max(len(midi_notes), 1)) * 0.5
                notes.append({"startTime": round(arp_t, 3), "duration": round(duration * 0.4, 3), "pitch": pitch, "velocity": 68})
        elif style == "ballad":
            # Slow arpeggiated roll
            for j, pitch in enumerate(midi_notes):
                notes.append({"startTime": round(start + j * 0.08, 3), "duration": round(duration * 0.9, 3), "pitch": pitch, "velocity": 60})
        elif style in ["hasidic", "middle_eastern"]:
            # Block chords with slight accent
            for pitch in midi_notes:
                notes.append({"startTime": round(start, 3), "duration": round(duration * 0.75, 3), "pitch": pitch, "velocity": 78})
        else:
            for pitch in midi_notes:
                notes.append({"startTime": round(start, 3), "duration": round(duration * 0.9, 3), "pitch": pitch, "velocity": 70})

    return notes


def generate_string_pad(chord_events: List[Dict], style: str = "pop") -> List[Dict]:
    """Generate lush string/pad voicings."""
    notes = []
    for chord_ev in chord_events:
        chord = chord_ev.get("chord", "C")
        start = chord_ev["startTime"]
        end = chord_ev["endTime"]
        midi_notes = chord_to_midi_notes(chord, octave=5)

        vel = 45 if style in ["ambient", "ballad"] else 55
        for pitch in midi_notes:
            notes.append({"startTime": round(start, 3), "duration": round((end - start) * 0.98, 3), "pitch": pitch, "velocity": vel})
    return notes


def generate_guitar_strum(chord_events: List[Dict], style: str, beat_grid: List[float]) -> List[Dict]:
    """Generate guitar strum pattern."""
    notes = []
    beat_dur = (beat_grid[1] - beat_grid[0]) if len(beat_grid) > 1 else 0.5

    for chord_ev in chord_events:
        chord = chord_ev.get("chord", "C")
        start = chord_ev["startTime"]
        end = chord_ev["endTime"]
        dur = end - start
        midi_notes = chord_to_midi_notes(chord, octave=4)

        if style in ["acoustic", "bossa_nova"]:
            # Fingerpicked arpeggio
            for j, pitch in enumerate(midi_notes[:4]):
                t = start + j * (beat_dur / 4)
                if t < end:
                    notes.append({"startTime": round(t, 3), "duration": round(beat_dur * 0.3, 3), "pitch": pitch + 12, "velocity": 62})
        elif style == "rock":
            # Power chord — just root + fifth
            for pitch in midi_notes[:2]:
                notes.append({"startTime": round(start, 3), "duration": round(dur * 0.6, 3), "pitch": pitch, "velocity": 85})
        else:
            # Basic strums every 2 beats
            t = start
            while t < end - 0.1:
                for pitch in midi_notes[:4]:
                    notes.append({"startTime": round(t, 3), "duration": round(beat_dur * 0.4, 3), "pitch": pitch, "velocity": 68})
                t += beat_dur * 2

    return notes


# ─── Section-aware arrangement ────────────────────────────────────────────────

def _beats_in_range(beat_grid: List[float], start: float, end: float) -> List[float]:
    return [b for b in beat_grid if start <= b < end]


def _chords_in_range(chord_events: List[Dict], start: float, end: float) -> List[Dict]:
    return [c for c in chord_events if c["startTime"] >= start and c["startTime"] < end]


def generate_arrangement(
    analysis: dict,
    style_id: str,
    instruments: Optional[List[str]],
    density: float,
    do_humanize: bool,
    tempo_factor: float,
    persona_id: Optional[str] = None,
    style_profile: Optional[dict] = None,
) -> Dict[str, Any]:
    """Generate full multi-track MIDI arrangement with section-aware profiles.

    Args:
        persona_id: Optional arranger persona ID (e.g. 'hasidic-wedding').
                    When provided, persona weights are applied to instrument volumes
                    and persona metadata is embedded in the result.
        style_profile: Optional StyleProfile dict from ConversationAgent.
                       When provided, its swing/ornament/time_signature data is
                       injected into analysis so pattern generators pick it up.
    """
    logger.info(f"Generating arrangement: style={style_id}, density={density}, persona={persona_id}")

    result_extra: Dict[str, Any] = {}
    if style_profile:
        analysis = dict(analysis)
        analysis["_profileSwingFactor"] = style_profile.get("swingFactor", 0.0)
        analysis["_profileOrnamentStyle"] = style_profile.get("ornamentStyle", "none")
        analysis["_profileTimeSignature"] = style_profile.get("timeSignature", "4/4")
        analysis["_profileGrooveTemplate"] = style_profile.get("grooveTemplate", "on_top")
        result_extra = {
            "styleProfileGenre": style_profile.get("genre", ""),
            "styleProfileEra": style_profile.get("era", ""),
            "styleProfileRegion": style_profile.get("region", ""),
            "isFallback": style_profile.get("isFallback", False),
        }
        logger.info(f"StyleProfile injected: genre={result_extra['styleProfileGenre']}")

    style_config = STYLES.get(style_id, STYLES["pop"])
    profile = ARRANGER_PROFILES.get(style_id, {})
    base_instruments = instruments or style_config["instruments"]

    rhythm = analysis.get("rhythm", {})
    chords_data = analysis.get("chords", {})
    structure_data = analysis.get("structure", {})

    beat_grid: List[float] = rhythm.get("beatGrid", [])
    time_sig: int = rhythm.get("timeSignatureNumerator", 4)
    bpm: float = rhythm.get("bpm", 120.0) * tempo_factor
    chord_events: List[Dict] = chords_data.get("chords", [])
    sections: List[Dict] = structure_data.get("sections", [])

    # Synthetic beat grid if missing
    if not beat_grid:
        beat_duration = 60.0 / bpm
        total_duration = (
            sum(s["endTime"] - s["startTime"] for s in sections)
            if sections else 60.0
        )
        beat_grid = [i * beat_duration for i in range(int(total_duration / beat_duration))]

    total_duration = beat_grid[-1] if beat_grid else 60.0
    beat_duration = (beat_grid[1] - beat_grid[0]) if len(beat_grid) > 1 else 60.0 / bpm

    # Build per-track note lists, per section if structure is available
    track_notes: Dict[str, List[Dict]] = {k: [] for k in ["drums", "bass", "piano", "strings", "guitar", "lead_synth", "brass", "pad"]}
    track_notes.update({k: [] for k in base_instruments})

    def process_segment(seg_start: float, seg_end: float, seg_label: str):
        seg_density = _section_density(style_id, seg_label, density)
        seg_instruments = _section_instruments(style_id, seg_label, base_instruments)
        seg_beats = _beats_in_range(beat_grid, seg_start, seg_end)
        seg_chords = _chords_in_range(chord_events, seg_start, seg_end)

        if "drums" in seg_instruments and seg_beats:
            notes = generate_drum_pattern(seg_beats, time_sig, style_id, seg_density)
            if do_humanize:
                notes = humanize(notes, 0.008, 10)
            track_notes["drums"].extend(notes)

        if "bass" in seg_instruments and seg_chords:
            notes = generate_bass_line(seg_chords, seg_beats or beat_grid, style_id)
            if do_humanize:
                notes = humanize(notes, 0.005, 6)
            track_notes["bass"].extend(notes)

        if "piano" in seg_instruments and seg_chords:
            notes = generate_piano_voicings(seg_chords, style_id, seg_density)
            if do_humanize:
                notes = humanize(notes, 0.012, 8)
            track_notes["piano"].extend(notes)

        if any(i in seg_instruments for i in ["strings", "pad", "synth_pad"]) and seg_chords:
            notes = generate_string_pad(seg_chords, style_id)
            if do_humanize:
                notes = humanize(notes, 0.015, 5)
            track_notes["strings"].extend(notes)

        if "guitar" in seg_instruments and seg_chords:
            notes = generate_guitar_strum(seg_chords, style_id, seg_beats or beat_grid)
            if do_humanize:
                notes = humanize(notes, 0.010, 7)
            track_notes["guitar"].extend(notes)

    if sections:
        for section in sections:
            process_segment(section["startTime"], section["endTime"], section.get("label", "verse"))
    else:
        process_segment(0.0, total_duration, "verse")

    # Build track objects for active instruments
    TRACK_META: Dict[str, Dict] = {
        "drums":     {"name": "Drums",          "instrument": "Drum Kit",       "channel": 9, "color": INSTRUMENTS["drums"]["color"],      "volume": 0.85, "pan": 0.0},
        "bass":      {"name": "Bass",           "instrument": "Electric Bass",  "channel": 1, "color": INSTRUMENTS["bass"]["color"],       "volume": 0.80, "pan": -0.1},
        "piano":     {"name": "Piano",          "instrument": "Grand Piano",    "channel": 2, "color": INSTRUMENTS["piano"]["color"],      "volume": 0.70, "pan": 0.1},
        "strings":   {"name": "Strings / Pad",  "instrument": "String Ensemble","channel": 4, "color": INSTRUMENTS["strings"]["color"],    "volume": 0.60, "pan": 0.0},
        "guitar":    {"name": "Guitar",         "instrument": "Electric Guitar","channel": 3, "color": INSTRUMENTS["guitar"]["color"],     "volume": 0.72, "pan": 0.2},
        "lead_synth":{"name": "Lead Synth",     "instrument": "Synth Lead",     "channel": 6, "color": INSTRUMENTS["lead_synth"]["color"],"volume": 0.68, "pan": 0.0},
        "brass":     {"name": "Brass",          "instrument": "Brass Section",  "channel": 7, "color": INSTRUMENTS["brass"]["color"],     "volume": 0.65, "pan": -0.1},
        "pad":       {"name": "Pad",            "instrument": "Synth Pad",      "channel": 5, "color": INSTRUMENTS["pad"]["color"],       "volume": 0.55, "pan": 0.0},
        "violin":    {"name": "Violin",         "instrument": "Violin",         "channel": 4, "color": INSTRUMENTS.get("violin", {}).get("color", "#d35400"), "volume": 0.72, "pan": 0.15},
        "accordion": {"name": "Accordion",      "instrument": "Accordion",      "channel": 5, "color": INSTRUMENTS.get("accordion", {}).get("color", "#7f8c8d"), "volume": 0.68, "pan": -0.15},
        "oud":       {"name": "Oud",            "instrument": "Oud/Guitar",     "channel": 3, "color": INSTRUMENTS.get("oud", {}).get("color", "#795548"), "volume": 0.70, "pan": 0.1},
    }

    tracks = []
    seen = set()
    for inst in base_instruments:
        if inst in seen:
            continue
        seen.add(inst)
        notes = track_notes.get(inst, [])
        if not notes:
            continue
        meta = TRACK_META.get(inst, {"name": inst.title(), "instrument": inst.title(), "channel": 2, "color": "#999", "volume": 0.65, "pan": 0.0})
        tracks.append({
            "id": inst,
            "name": meta["name"],
            "instrument": meta["instrument"],
            "channel": meta["channel"],
            "color": meta["color"],
            "notes": notes,
            "volume": meta["volume"],
            "pan": meta["pan"],
            "muted": False,
            "soloed": False,
        })

    # Build harmonic plan summary
    harmonic_plan = []
    if sections and chord_events:
        for section in sections:
            seg_chords = _chords_in_range(chord_events, section["startTime"], section["endTime"])
            unique_chords = list(dict.fromkeys(c.get("chord", "") for c in seg_chords if c.get("chord")))
            harmonic_plan.append({
                "section": section.get("label", "section"),
                "startTime": section["startTime"],
                "endTime": section["endTime"],
                "chords": unique_chords[:8],
            })

    # Build transitions between adjacent sections
    TRANSITION_TYPES = {
        ("intro", "verse"):   "lift",
        ("verse", "chorus"):  "build",
        ("chorus", "verse"):  "drop",
        ("verse", "bridge"):  "shift",
        ("bridge", "chorus"): "build",
        ("chorus", "outro"):  "fade",
        ("outro", "end"):     "end",
    }
    transitions = []
    for i in range(len(sections) - 1):
        a = sections[i].get("label", "").lower()
        b = sections[i + 1].get("label", "").lower()
        t_type = TRANSITION_TYPES.get((a, b), "crossfade")
        transitions.append({
            "fromSection": a,
            "toSection": b,
            "type": t_type,
            "atTime": round(sections[i + 1]["startTime"], 3),
        })

    # Build instrumentation plan per section
    instrumentation_plan = {
        "styleId": style_id,
        "tracks": [
            {
                "instrument": inst,
                "role": {
                    "drums": "rhythm", "bass": "low-end", "piano": "harmony",
                    "guitar": "rhythm/melody", "strings": "texture", "pad": "atmosphere",
                    "lead_synth": "melody", "brass": "accent", "violin": "melody",
                    "accordion": "harmony", "oud": "melody", "darbuka": "rhythm",
                }.get(inst, "support"),
                "density": round(density * _section_density(style_id, sections[0].get("label", "verse") if sections else "verse", density), 2),
                "sections": [sec.get("label", "all") for sec in sections],
            }
            for inst in base_instruments
        ],
    }

    logger.info(f"Generated {len(tracks)} tracks, {len(harmonic_plan)} section plans, {len(transitions)} transitions")

    result = {
        "styleId": style_id,
        "tracks": tracks,
        "totalDurationSeconds": round(total_duration, 2),
        "sections": sections,
        "harmonicPlan": harmonic_plan,
        "transitions": transitions,
        "instrumentationPlan": instrumentation_plan,
        "profileUsed": bool(profile),
        "generationParams": {
            "density": density,
            "tempo_factor": tempo_factor,
            "humanize": do_humanize,
            "section_count": len(sections),
            "transition_count": len(transitions),
            "persona_id": persona_id,
        },
    }

    # Merge StyleProfile metadata into result
    result.update(result_extra)

    # Apply persona overlays (volume weights, metadata embedding)
    if persona_id:
        try:
            from orchestration.persona_loader import apply_persona_to_arrangement
            result = apply_persona_to_arrangement(result, persona_id, style_id)
        except Exception as pe:
            logger.warning(f"Could not apply persona '{persona_id}': {pe}")

    return result
