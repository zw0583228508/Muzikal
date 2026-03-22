"""
Arrangement & Orchestration Engine.
Generates multi-track MIDI arrangements based on analysis + style.
"""

import logging
import random
import math
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Instrument definitions with MIDI program numbers
INSTRUMENTS = {
    "drums": {"channel": 9, "program": 0, "color": "#e74c3c"},
    "bass": {"channel": 1, "program": 33, "color": "#8e44ad"},
    "piano": {"channel": 2, "program": 0, "color": "#2980b9"},
    "guitar": {"channel": 3, "program": 25, "color": "#27ae60"},
    "strings": {"channel": 4, "program": 48, "color": "#f39c12"},
    "pad": {"channel": 5, "program": 88, "color": "#1abc9c"},
    "lead_synth": {"channel": 6, "program": 80, "color": "#e67e22"},
    "brass": {"channel": 7, "program": 61, "color": "#c0392b"},
}

# Style definitions: rhythm patterns, instrument sets, harmonic tendencies
STYLES = {
    "pop": {
        "name": "Pop",
        "genre": "Pop",
        "description": "Radio-friendly pop with clean production and melodic hooks",
        "tags": ["modern", "melodic", "commercial"],
        "instruments": ["drums", "bass", "piano", "guitar", "strings", "pad"],
        "density": 0.75,
    },
    "jazz": {
        "name": "Jazz",
        "genre": "Jazz",
        "description": "Swing jazz with complex harmony and improvised feel",
        "tags": ["swing", "complex", "improvised"],
        "instruments": ["drums", "bass", "piano", "guitar", "brass"],
        "density": 0.65,
    },
    "rnb": {
        "name": "R&B / Soul",
        "genre": "R&B",
        "description": "Soulful R&B with groove bass and lush chords",
        "tags": ["soulful", "groove", "lush"],
        "instruments": ["drums", "bass", "piano", "guitar", "strings", "pad"],
        "density": 0.80,
    },
    "classical": {
        "name": "Orchestral",
        "genre": "Classical",
        "description": "Full orchestral arrangement with strings, brass, and woodwinds",
        "tags": ["orchestral", "dramatic", "cinematic"],
        "instruments": ["strings", "brass", "piano"],
        "density": 0.85,
    },
    "electronic": {
        "name": "Electronic",
        "genre": "Electronic",
        "description": "Synth-driven electronic production with driving beats",
        "tags": ["electronic", "synth", "driving"],
        "instruments": ["drums", "bass", "pad", "lead_synth"],
        "density": 0.90,
    },
    "rock": {
        "name": "Rock",
        "genre": "Rock",
        "description": "Energetic rock with electric guitars and powerful drums",
        "tags": ["energetic", "powerful", "guitar"],
        "instruments": ["drums", "bass", "guitar", "piano"],
        "density": 0.85,
    },
    "bossa_nova": {
        "name": "Bossa Nova",
        "genre": "Brazilian",
        "description": "Relaxed bossa nova with gentle guitar and subtle percussion",
        "tags": ["relaxed", "brazilian", "elegant"],
        "instruments": ["drums", "bass", "guitar", "piano"],
        "density": 0.55,
    },
    "ambient": {
        "name": "Ambient",
        "genre": "Ambient",
        "description": "Atmospheric ambient textures with evolving pads and minimal rhythm",
        "tags": ["atmospheric", "textural", "minimal"],
        "instruments": ["pad", "strings", "piano"],
        "density": 0.30,
    },
}


def generate_drum_pattern(beat_grid: List[float], time_sig: int, style: str, density: float) -> List[Dict]:
    """Generate drum MIDI notes based on beat grid and style."""
    notes = []

    # Drum MIDI note assignments (General MIDI channel 10)
    KICK = 36
    SNARE = 38
    CLOSED_HH = 42
    OPEN_HH = 46
    CRASH = 49
    RIDE = 51
    HH_PEDAL = 44
    TOM1 = 50
    TOM2 = 47

    for i, beat_time in enumerate(beat_grid):
        beat_in_measure = i % time_sig
        next_time = beat_grid[i + 1] if i + 1 < len(beat_grid) else beat_time + 0.5
        beat_duration = (next_time - beat_time) * 0.95

        # Kick on beat 1 and often beat 3
        if beat_in_measure == 0:
            notes.append({"startTime": round(beat_time, 3), "duration": round(beat_duration * 0.3, 3), "pitch": KICK, "velocity": 100})
        elif beat_in_measure == 2 and random.random() < 0.6:
            notes.append({"startTime": round(beat_time, 3), "duration": round(beat_duration * 0.3, 3), "pitch": KICK, "velocity": 90})

        # Snare on 2 and 4
        if beat_in_measure in [1, 3]:
            notes.append({"startTime": round(beat_time, 3), "duration": round(beat_duration * 0.2, 3), "pitch": SNARE, "velocity": 95})

        # Hi-hat pattern
        if density > 0.5:
            # Eighth note hi-hats
            for sub in range(2):
                hh_time = beat_time + (next_time - beat_time) * sub / 2
                vel = 70 if sub == 0 else 55
                notes.append({"startTime": round(hh_time, 3), "duration": 0.05, "pitch": CLOSED_HH, "velocity": vel})
        else:
            # Quarter note hi-hats
            notes.append({"startTime": round(beat_time, 3), "duration": 0.05, "pitch": CLOSED_HH, "velocity": 65})

        # Occasional crash on downbeat
        if beat_in_measure == 0 and i % (time_sig * 4) == 0:
            notes.append({"startTime": round(beat_time, 3), "duration": round(beat_duration * 0.5, 3), "pitch": CRASH, "velocity": 85})

    return notes


def chord_to_midi_notes(chord: str, octave: int = 4) -> List[int]:
    """Convert chord symbol to list of MIDI pitch numbers."""
    NOTE_MAP = {"C": 60, "C#": 61, "Db": 61, "D": 62, "D#": 63, "Eb": 63,
                "E": 64, "F": 65, "F#": 66, "Gb": 66, "G": 67, "G#": 68,
                "Ab": 68, "A": 69, "A#": 70, "Bb": 70, "B": 71}

    # Parse chord root
    if len(chord) >= 2 and chord[1] in "#b":
        root_name = chord[:2]
        quality = chord[2:]
    else:
        root_name = chord[:1]
        quality = chord[1:]

    root_midi = NOTE_MAP.get(root_name, 60) + (octave - 4) * 0
    root_midi = 48 + (root_midi % 12)  # Normalize to octave 4-5

    # Build chord intervals
    if "maj7" in quality:
        intervals = [0, 4, 7, 11]
    elif "m7" in quality:
        intervals = [0, 3, 7, 10]
    elif "dim7" in quality:
        intervals = [0, 3, 6, 9]
    elif "dim" in quality:
        intervals = [0, 3, 6]
    elif "aug" in quality:
        intervals = [0, 4, 8]
    elif "sus4" in quality:
        intervals = [0, 5, 7]
    elif "sus2" in quality:
        intervals = [0, 2, 7]
    elif "7" in quality:
        intervals = [0, 4, 7, 10]
    elif "m" in quality:
        intervals = [0, 3, 7]
    elif "6" in quality:
        intervals = [0, 4, 7, 9]
    elif "add9" in quality:
        intervals = [0, 2, 4, 7]
    else:
        intervals = [0, 4, 7]  # Major triad

    return [root_midi + i for i in intervals]


def humanize(notes: List[Dict], timing_jitter: float = 0.01, velocity_jitter: int = 8) -> List[Dict]:
    """Apply subtle timing and velocity humanization to MIDI notes."""
    humanized = []
    for note in notes:
        new_note = note.copy()
        new_note["startTime"] = max(0, note["startTime"] + random.gauss(0, timing_jitter))
        new_note["velocity"] = max(20, min(127, note["velocity"] + random.randint(-velocity_jitter, velocity_jitter)))
        humanized.append(new_note)
    return humanized


def generate_bass_line(chord_events: List[Dict], beat_grid: List[float], style: str) -> List[Dict]:
    """Generate bass line following chord roots."""
    notes = []
    for chord_ev in chord_events:
        chord = chord_ev.get("chord", "C")
        start = chord_ev["startTime"]
        end = chord_ev["endTime"]

        # Get root note (2 octaves below middle C area)
        midi_notes = chord_to_midi_notes(chord, octave=3)
        if not midi_notes:
            continue
        root = midi_notes[0] - 12  # Drop an octave

        # Whole note bass hit + optional passing tones
        notes.append({"startTime": round(start, 3), "duration": round((end - start) * 0.45, 3), "pitch": root, "velocity": 88})

        # Add walking bass for jazz
        if style == "jazz" and (end - start) > 0.8:
            mid = start + (end - start) * 0.5
            fifth = root + 7
            notes.append({"startTime": round(mid, 3), "duration": round((end - start) * 0.4, 3), "pitch": fifth, "velocity": 75})

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
            # Block chords
            for pitch in midi_notes:
                notes.append({"startTime": round(start, 3), "duration": round(duration * 0.85, 3), "pitch": pitch, "velocity": 72})
        elif style == "jazz":
            # Comping - syncopated voicings
            offset = random.choice([0.0, 0.1, 0.25])
            for pitch in midi_notes:
                notes.append({"startTime": round(start + offset, 3), "duration": round(duration * 0.5, 3), "pitch": pitch, "velocity": 65})
        elif style in ["rnb", "bossa_nova"]:
            # Arpeggiated
            for j, pitch in enumerate(midi_notes):
                arp_time = start + j * (duration / max(len(midi_notes), 1)) * 0.5
                notes.append({"startTime": round(arp_time, 3), "duration": round(duration * 0.4, 3), "pitch": pitch, "velocity": 68})
        else:
            for pitch in midi_notes:
                notes.append({"startTime": round(start, 3), "duration": round(duration * 0.9, 3), "pitch": pitch, "velocity": 70})

    return notes


def generate_string_pad(chord_events: List[Dict]) -> List[Dict]:
    """Generate lush string/pad voicings."""
    notes = []
    for chord_ev in chord_events:
        chord = chord_ev.get("chord", "C")
        start = chord_ev["startTime"]
        end = chord_ev["endTime"]

        midi_notes = chord_to_midi_notes(chord, octave=5)
        for pitch in midi_notes:
            notes.append({"startTime": round(start, 3), "duration": round((end - start) * 0.98, 3), "pitch": pitch, "velocity": 55})
    return notes


def generate_arrangement(analysis: dict, style_id: str, instruments: Optional[List[str]],
                          density: float, do_humanize: bool, tempo_factor: float) -> Dict[str, Any]:
    """
    Generate full multi-track MIDI arrangement.
    """
    logger.info(f"Generating arrangement: style={style_id}, density={density}")

    style_config = STYLES.get(style_id, STYLES["pop"])
    active_instruments = instruments or style_config["instruments"]

    rhythm = analysis.get("rhythm", {})
    chords_data = analysis.get("chords", {})
    structure = analysis.get("structure", {})

    beat_grid = rhythm.get("beatGrid", [])
    time_sig = rhythm.get("timeSignatureNumerator", 4)
    bpm = rhythm.get("bpm", 120) * tempo_factor
    chord_events = chords_data.get("chords", [])

    if not beat_grid:
        # Generate synthetic beat grid
        beat_duration = 60.0 / bpm
        total_duration = sum(
            s["endTime"] - s["startTime"] for s in structure.get("sections", [])
        ) if structure.get("sections") else 60.0
        beat_grid = [i * beat_duration for i in range(int(total_duration / beat_duration))]

    total_duration = beat_grid[-1] if beat_grid else 60.0

    tracks = []

    # Generate tracks per instrument
    if "drums" in active_instruments:
        drum_notes = generate_drum_pattern(beat_grid, time_sig, style_id, density)
        if do_humanize:
            drum_notes = humanize(drum_notes, timing_jitter=0.008, velocity_jitter=10)
        tracks.append({
            "id": "drums",
            "name": "Drums",
            "instrument": "Drum Kit",
            "channel": 9,
            "color": INSTRUMENTS["drums"]["color"],
            "notes": drum_notes,
            "volume": 0.85,
            "pan": 0.0,
            "muted": False,
            "soloed": False,
        })

    if "bass" in active_instruments and chord_events:
        bass_notes = generate_bass_line(chord_events, beat_grid, style_id)
        if do_humanize:
            bass_notes = humanize(bass_notes, timing_jitter=0.005, velocity_jitter=6)
        tracks.append({
            "id": "bass",
            "name": "Bass",
            "instrument": "Electric Bass",
            "channel": 1,
            "color": INSTRUMENTS["bass"]["color"],
            "notes": bass_notes,
            "volume": 0.80,
            "pan": -0.1,
            "muted": False,
            "soloed": False,
        })

    if "piano" in active_instruments and chord_events:
        piano_notes = generate_piano_voicings(chord_events, style_id, density)
        if do_humanize:
            piano_notes = humanize(piano_notes, timing_jitter=0.012, velocity_jitter=8)
        tracks.append({
            "id": "piano",
            "name": "Piano",
            "instrument": "Grand Piano",
            "channel": 2,
            "color": INSTRUMENTS["piano"]["color"],
            "notes": piano_notes,
            "volume": 0.70,
            "pan": 0.1,
            "muted": False,
            "soloed": False,
        })

    if ("strings" in active_instruments or "pad" in active_instruments) and chord_events:
        pad_notes = generate_string_pad(chord_events)
        if do_humanize:
            pad_notes = humanize(pad_notes, timing_jitter=0.015, velocity_jitter=5)
        tracks.append({
            "id": "strings",
            "name": "Strings / Pad",
            "instrument": "String Ensemble",
            "channel": 4,
            "color": INSTRUMENTS["strings"]["color"],
            "notes": pad_notes,
            "volume": 0.60,
            "pan": 0.0,
            "muted": False,
            "soloed": False,
        })

    logger.info(f"Generated {len(tracks)} tracks with arrangement")

    return {
        "styleId": style_id,
        "tracks": tracks,
        "totalDurationSeconds": round(total_duration, 2),
    }
