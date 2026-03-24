"""
Instrument Range and Orchestration Constraints — Phase 4.

Provides:
  - Playable MIDI range (lowest/highest note) per instrument
  - Preferred register (comfortable range for normal writing)
  - Articulation options per instrument family
  - Rhythmic role constraints
  - Doubling policy rules
  - Voice-leading helpers (nearest-note voicing, anti-collision)

MIDI note reference:
  C4 = 60 (middle C)
  Range: 0–127

References:
  Adler (1989): The Study of Orchestration
  Blatter (1997): Instrumentation and Orchestration
  Rimsky-Korsakov (1964): Principles of Orchestration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class InstrumentRange:
    """Complete range and articulation spec for one instrument."""
    name: str

    # Absolute playable limits (MIDI)
    min_midi: int
    max_midi: int

    # Preferred (comfortable) register — writing outside this needs justification
    preferred_min: int
    preferred_max: int

    # Orchestration metadata
    family: str          # "strings", "brass", "woodwind", "keyboard", "guitar", "bass", "drums", "synth"
    role: str            # "bass", "inner", "melody", "rhythm", "percussion", "pad"
    clef: str            # "treble", "bass", "alto", "tenor", "percussion", "grand_staff"
    transposition: int   # semitones from concert pitch (0 = concert, -2 = Bb instr, etc.)

    # Articulation options
    articulations: List[str] = field(default_factory=list)

    # Rhythmic role options for arrangement
    rhythm_roles: List[str] = field(default_factory=list)

    # Voice-leading / doubling rules
    can_double_melody: bool = True
    can_double_bass: bool = False
    polyphonic: bool = True         # can play chords
    max_voices: int = 4             # max simultaneous notes

    # Dynamic range (MIDI velocity)
    vel_pp: int = 30   # pianissimo
    vel_p:  int = 45   # piano
    vel_mp: int = 60   # mezzo-piano
    vel_mf: int = 75   # mezzo-forte
    vel_f:  int = 95   # forte
    vel_ff: int = 115  # fortissimo

    # Notes
    notes: str = ""

    @property
    def range_midi(self) -> Tuple[int, int]:
        return (self.min_midi, self.max_midi)

    @property
    def preferred_range(self) -> Tuple[int, int]:
        return (self.preferred_min, self.preferred_max)

    def in_range(self, midi: int) -> bool:
        return self.min_midi <= midi <= self.max_midi

    def in_preferred_range(self, midi: int) -> bool:
        return self.preferred_min <= midi <= self.preferred_max

    def clamp_to_preferred(self, midi: int) -> int:
        return max(self.preferred_min, min(self.preferred_max, midi))

    def clamp_to_range(self, midi: int) -> int:
        return max(self.min_midi, min(self.max_midi, midi))


# ─── Registry ─────────────────────────────────────────────────────────────────

#: Central registry: instrument_key → InstrumentRange
INSTRUMENT_RANGES: Dict[str, InstrumentRange] = {}


def _reg(r: InstrumentRange) -> InstrumentRange:
    INSTRUMENT_RANGES[r.name] = r
    return r


# ─── Keyboards ────────────────────────────────────────────────────────────────

PIANO = _reg(InstrumentRange(
    name="piano",
    min_midi=21, max_midi=108,           # A0–C8
    preferred_min=36, preferred_max=96,  # C2–C7 (comfortable)
    family="keyboard", role="inner",
    clef="grand_staff", transposition=0,
    articulations=["legato", "staccato", "marcato", "tenuto", "accent"],
    rhythm_roles=["comp", "block_chord", "arpeggio", "bass_and_chord", "melody"],
    can_double_melody=True, can_double_bass=True,
    polyphonic=True, max_voices=10,
    vel_pp=25, vel_p=40, vel_mp=58, vel_mf=72, vel_f=92, vel_ff=112,
))

ACCORDION = _reg(InstrumentRange(
    name="accordion",
    min_midi=41, max_midi=89,            # F2–F6
    preferred_min=48, preferred_max=84,  # C3–C6
    family="keyboard", role="inner",
    clef="grand_staff", transposition=0,
    articulations=["legato", "staccato", "marcato", "bellows_shake"],
    rhythm_roles=["comp", "block_chord", "bass_and_chord", "oom_pah"],
    can_double_melody=True, polyphonic=True, max_voices=5,
))

QANUN = _reg(InstrumentRange(
    name="qanun",
    min_midi=48, max_midi=96,            # C3–C7
    preferred_min=55, preferred_max=91,  # G3–G6
    family="keyboard", role="melody",
    clef="treble", transposition=0,
    articulations=["legato", "tremolo", "plucked"],
    rhythm_roles=["melody", "arpeggio", "ornament"],
    can_double_melody=True, polyphonic=True, max_voices=3,
    notes="Middle Eastern plucked zither. Uses microtonal tunings in practice.",
))

# ─── Strings (ensemble) ───────────────────────────────────────────────────────

STRINGS = _reg(InstrumentRange(
    name="strings",
    min_midi=40, max_midi=103,           # E2–G7 (ensemble aggregate)
    preferred_min=48, preferred_max=96,  # C3–C7
    family="strings", role="inner",
    clef="treble", transposition=0,
    articulations=["legato", "staccato", "pizzicato", "tremolo", "sul_ponticello",
                   "harmonics", "col_legno", "arco", "spiccato"],
    rhythm_roles=["pad", "counter_melody", "arpeggiated_comp", "pizz_bass",
                  "sustained_harmony", "melody"],
    can_double_melody=True, polyphonic=True, max_voices=4,
    vel_pp=25, vel_p=40, vel_mp=60, vel_mf=78, vel_f=98, vel_ff=118,
))

VIOLIN = _reg(InstrumentRange(
    name="violin",
    min_midi=55, max_midi=103,           # G3–G7
    preferred_min=60, preferred_max=96,  # C4–C7
    family="strings", role="melody",
    clef="treble", transposition=0,
    articulations=["legato", "staccato", "pizzicato", "tremolo", "harmonics",
                   "sul_ponticello", "arco", "spiccato"],
    rhythm_roles=["melody", "counter_melody", "ornament"],
    can_double_melody=True, polyphonic=False, max_voices=2,
    vel_pp=28, vel_p=42, vel_mp=62, vel_mf=78, vel_f=96, vel_ff=115,
))

# ─── Brass ────────────────────────────────────────────────────────────────────

BRASS = _reg(InstrumentRange(
    name="brass",
    min_midi=40, max_midi=84,            # E2–C6 (ensemble)
    preferred_min=48, preferred_max=79,  # C3–G5
    family="brass", role="inner",
    clef="treble", transposition=0,
    articulations=["legato", "staccato", "marcato", "accent", "sforzando",
                   "flutter_tongue", "stopped", "open"],
    rhythm_roles=["hits", "sustained_harmony", "counter_melody", "melody",
                  "fanfare", "riff"],
    can_double_melody=True, polyphonic=True, max_voices=4,
    vel_pp=40, vel_p=55, vel_mp=70, vel_mf=85, vel_f=105, vel_ff=122,
    notes="Ensemble brass — combine trumpet, trombone, horn.",
))

TRUMPET = _reg(InstrumentRange(
    name="trumpet",
    min_midi=55, max_midi=87,            # G3–Eb6
    preferred_min=58, preferred_max=82,  # Bb3–Bb5
    family="brass", role="melody",
    clef="treble", transposition=-2,     # Bb instrument
    articulations=["legato", "staccato", "marcato", "flutter_tongue", "mute"],
    rhythm_roles=["melody", "counter_melody", "fanfare", "riff"],
    can_double_melody=True, polyphonic=False, max_voices=1,
    vel_pp=40, vel_p=58, vel_mp=72, vel_mf=88, vel_f=108, vel_ff=124,
))

SAXOPHONE = _reg(InstrumentRange(
    name="saxophone",
    min_midi=46, max_midi=84,            # Bb2–C6 (alto)
    preferred_min=49, preferred_max=81,  # Db3–A5
    family="woodwind", role="melody",
    clef="treble", transposition=-9,     # Eb alto sax
    articulations=["legato", "staccato", "growl", "flutter_tongue", "vibrato"],
    rhythm_roles=["melody", "counter_melody", "riff", "ornament"],
    can_double_melody=True, polyphonic=False, max_voices=1,
    vel_pp=35, vel_p=50, vel_mp=65, vel_mf=80, vel_f=100, vel_ff=120,
))

# ─── Bass ─────────────────────────────────────────────────────────────────────

BASS = _reg(InstrumentRange(
    name="bass",
    min_midi=28, max_midi=67,            # E1–G4 (electric/acoustic bass)
    preferred_min=28, preferred_max=60,  # E1–C4
    family="bass", role="bass",
    clef="bass", transposition=0,
    articulations=["legato", "staccato", "slap", "pop", "hammer_on", "ghost_note",
                   "muted", "slide"],
    rhythm_roles=["root_only", "root_fifth", "walking", "syncopated", "pedal_tone"],
    can_double_bass=True, can_double_melody=False,
    polyphonic=False, max_voices=1,
    vel_pp=35, vel_p=50, vel_mp=65, vel_mf=80, vel_f=100, vel_ff=118,
))

DOUBLE_BASS = _reg(InstrumentRange(
    name="double_bass",
    min_midi=28, max_midi=60,            # E1–C4 (orchestra tuning + C ext)
    preferred_min=28, preferred_max=55,  # E1–G3
    family="bass", role="bass",
    clef="bass", transposition=-12,      # written an octave higher
    articulations=["legato", "pizzicato", "arco", "col_legno"],
    rhythm_roles=["root_only", "root_fifth", "walking", "pedal_tone"],
    can_double_bass=True, can_double_melody=False,
    polyphonic=False, max_voices=1,
))

# ─── Guitar family ────────────────────────────────────────────────────────────

GUITAR = _reg(InstrumentRange(
    name="guitar",
    min_midi=40, max_midi=88,            # E2–E7
    preferred_min=40, preferred_max=79,  # E2–G5
    family="guitar", role="inner",
    clef="treble", transposition=-12,    # sounds an octave lower
    articulations=["legato", "staccato", "palm_mute", "hammer_on", "bend",
                   "slide", "vibrato", "harmonics"],
    rhythm_roles=["comp", "power_chords", "arpeggio", "riff", "melody", "strumming"],
    can_double_melody=True, polyphonic=True, max_voices=6,
    vel_pp=30, vel_p=48, vel_mp=65, vel_mf=82, vel_f=102, vel_ff=120,
))

OUD = _reg(InstrumentRange(
    name="oud",
    min_midi=45, max_midi=81,            # A2–A5
    preferred_min=50, preferred_max=77,  # D3–F5
    family="guitar", role="melody",
    clef="treble", transposition=0,
    articulations=["plucked", "tremolo", "slide", "ornament"],
    rhythm_roles=["melody", "arpeggio", "comp", "ornament"],
    can_double_melody=True, polyphonic=True, max_voices=3,
    notes="Middle Eastern lute. No frets — microtonal playing possible.",
))

TSIMBL = _reg(InstrumentRange(
    name="tsimbl",
    min_midi=48, max_midi=88,            # C3–E6
    preferred_min=55, preferred_max=84,  # G3–C6
    family="keyboard", role="melody",
    clef="treble", transposition=0,
    articulations=["plucked", "damped", "tremolo"],
    rhythm_roles=["melody", "ornament", "arpeggio"],
    can_double_melody=True, polyphonic=True, max_voices=4,
    notes="Cimbalom / hammered dulcimer. Eastern European folk and Hasidic music.",
))

# ─── Synths and pads ──────────────────────────────────────────────────────────

PAD = _reg(InstrumentRange(
    name="pad",
    min_midi=36, max_midi=96,
    preferred_min=48, preferred_max=84,
    family="synth", role="pad",
    clef="treble", transposition=0,
    articulations=["sustained", "swell", "fade"],
    rhythm_roles=["sustained_harmony", "pedal_tone", "texture"],
    can_double_melody=False, polyphonic=True, max_voices=4,
    vel_pp=20, vel_p=35, vel_mp=50, vel_mf=65, vel_f=85, vel_ff=105,
))

SYNTH_PAD = _reg(InstrumentRange(
    name="synth_pad",
    min_midi=36, max_midi=96,
    preferred_min=48, preferred_max=84,
    family="synth", role="pad",
    clef="treble", transposition=0,
    articulations=["sustained", "swell", "fade", "sweep"],
    rhythm_roles=["sustained_harmony", "pedal_tone", "texture", "riser"],
    can_double_melody=False, polyphonic=True, max_voices=4,
    vel_pp=20, vel_p=35, vel_mp=50, vel_mf=65, vel_f=85, vel_ff=105,
))

LEAD_SYNTH = _reg(InstrumentRange(
    name="lead_synth",
    min_midi=48, max_midi=96,
    preferred_min=55, preferred_max=91,
    family="synth", role="melody",
    clef="treble", transposition=0,
    articulations=["legato", "portamento", "staccato", "accent"],
    rhythm_roles=["melody", "riff", "counter_melody"],
    can_double_melody=True, polyphonic=False, max_voices=2,
))

CHOIR = _reg(InstrumentRange(
    name="choir",
    min_midi=36, max_midi=84,            # C2–C6
    preferred_min=43, preferred_max=81,  # G2–A5
    family="strings", role="inner",
    clef="grand_staff", transposition=0,
    articulations=["legato", "sustained", "marcato", "sforzando"],
    rhythm_roles=["sustained_harmony", "pad", "counter_melody"],
    can_double_melody=True, polyphonic=True, max_voices=4,
))

# ─── Woodwinds ────────────────────────────────────────────────────────────────

NAY = _reg(InstrumentRange(
    name="nay",
    min_midi=50, max_midi=83,            # D3–B5
    preferred_min=55, preferred_max=79,  # G3–G5
    family="woodwind", role="melody",
    clef="treble", transposition=0,
    articulations=["legato", "staccato", "vibrato", "ornament", "flutter_tongue"],
    rhythm_roles=["melody", "ornament", "counter_melody"],
    can_double_melody=True, polyphonic=False, max_voices=1,
    notes="Middle Eastern reed flute. Breathy tone with microtonal bends.",
))

# ─── Drums/Percussion ─────────────────────────────────────────────────────────

DRUMS = _reg(InstrumentRange(
    name="drums",
    min_midi=35, max_midi=81,            # GM Standard Drum Map
    preferred_min=35, preferred_max=81,
    family="drums", role="percussion",
    clef="percussion", transposition=0,
    articulations=["accent", "ghost_note", "rim_shot", "open_hihat", "closed_hihat",
                   "flam", "drag", "diddle"],
    rhythm_roles=["groove", "fill", "accent", "break"],
    can_double_melody=False, polyphonic=True, max_voices=8,
    vel_pp=25, vel_p=40, vel_mp=60, vel_mf=80, vel_f=100, vel_ff=120,
))

DARBUKA = _reg(InstrumentRange(
    name="darbuka",
    min_midi=35, max_midi=65,
    preferred_min=35, preferred_max=65,
    family="drums", role="percussion",
    clef="percussion", transposition=0,
    articulations=["dum", "tek", "ka", "snap", "slap"],
    rhythm_roles=["groove", "fill", "accent"],
    can_double_melody=False, polyphonic=True, max_voices=4,
    notes="Middle Eastern goblet drum. GM pitches used for mapping.",
))


# ─── Voice-leading utilities ──────────────────────────────────────────────────

def nearest_note_voicing(
    current_notes: List[int],
    target_chord: List[int],
    instrument: str = "piano",
) -> List[int]:
    """
    Voice a target chord to minimize voice movement from the current notes.

    Uses greedy nearest-neighbor assignment. Each current note finds the
    nearest target pitch-class representative. Works in place without
    duplicating pitch classes within an octave.

    Args:
        current_notes: List of MIDI pitches in current chord
        target_chord:  List of MIDI root+intervals (e.g. [60, 64, 67])
        instrument:    Instrument key (for range clamping)

    Returns:
        Re-voiced MIDI pitches list (same length as target_chord)
    """
    spec = INSTRUMENT_RANGES.get(instrument, PIANO)

    if not current_notes or not target_chord:
        return [spec.clamp_to_preferred(n) for n in target_chord]

    # Expand target to chromatic pitch-class octaves
    voiced: List[int] = []
    used: set = set()

    for t_note in sorted(target_chord):
        pitch_class = t_note % 12
        best_midi = t_note
        best_dist = 999

        # Search nearby octaves
        for ref in current_notes:
            if ref in used:
                continue
            for octave_shift in range(-2, 3):
                candidate = pitch_class + 12 * (ref // 12) + 12 * octave_shift
                dist = abs(candidate - ref)
                if dist < best_dist and spec.in_preferred_range(candidate):
                    best_dist = dist
                    best_midi = candidate

        voiced.append(spec.clamp_to_preferred(best_midi))
        used.add(best_midi)

    return voiced


def check_voice_crossing(voices: List[int]) -> List[Tuple[int, int]]:
    """
    Check for voice crossings in a sorted list of MIDI pitches.

    Returns list of (lower_idx, upper_idx) pairs where voice crossing occurred.
    """
    crossings = []
    sorted_voices = sorted(voices)
    for i, v in enumerate(voices):
        if v != sorted_voices[i]:
            crossings.append((i, sorted_voices.index(v)))
    return crossings


def check_parallel_fifths(
    prev_voices: List[int],
    curr_voices: List[int],
) -> List[Tuple[int, int]]:
    """
    Detect parallel fifths between voice pairs.

    Returns list of (voice_a_idx, voice_b_idx) where parallels occur.
    """
    violations = []
    n = min(len(prev_voices), len(curr_voices))
    for i in range(n):
        for j in range(i + 1, n):
            if (abs(prev_voices[i] - prev_voices[j]) % 12 == 7 and
                    abs(curr_voices[i] - curr_voices[j]) % 12 == 7):
                violations.append((i, j))
    return violations


def validate_arrangement_voices(
    tracks: List[Dict],
) -> Dict[str, List[str]]:
    """
    Validate all tracks for range violations and basic orchestration problems.

    Args:
        tracks: List of track dicts with 'instrument' and 'notes' keys.
                Each note has 'pitch' (MIDI int).

    Returns:
        dict mapping instrument → list of issue strings
    """
    issues: Dict[str, List[str]] = {}

    for track in tracks:
        instrument = track.get("instrument", "piano")
        notes = track.get("notes", [])
        spec = INSTRUMENT_RANGES.get(instrument, PIANO)
        track_issues = []

        for note in notes:
            pitch = int(note.get("pitch", note.get("midi", 60)))
            if not spec.in_range(pitch):
                track_issues.append(
                    f"Out of absolute range: pitch {pitch} "
                    f"({_midi_name(pitch)}) — limit [{spec.min_midi}, {spec.max_midi}]"
                )
            elif not spec.in_preferred_range(pitch):
                track_issues.append(
                    f"Outside preferred register: pitch {pitch} "
                    f"({_midi_name(pitch)}) — preferred [{spec.preferred_min}, {spec.preferred_max}]"
                )

        if track_issues:
            issues[instrument] = track_issues

    return issues


def _midi_name(midi: int) -> str:
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    octave = midi // 12 - 1
    name = names[midi % 12]
    return f"{name}{octave}"


def get_instrument_spec(name: str) -> Optional[InstrumentRange]:
    """Look up instrument spec by name. Returns None if not found."""
    return INSTRUMENT_RANGES.get(name)


def list_instruments() -> List[str]:
    """Return all registered instrument names."""
    return list(INSTRUMENT_RANGES.keys())
