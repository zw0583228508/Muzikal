"""
Export Engine: MIDI, MusicXML, and audio export.
Supports: MIDI (.mid), MusicXML (.musicxml), lead sheet text.

Improvements (T008):
- Note quantization to beat grid
- Measure-aligned chord progression
- Proper MusicXML chord symbols with root/kind
- Lead sheet with bar lines, measure numbers, and section labels
"""

import os
import io
import logging
import json
import math
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Quantization ─────────────────────────────────────────────────────────────

def quantize_time(t: float, beat_duration: float, subdivisions: int = 8) -> float:
    """Snap t to the nearest rhythmic subdivision (default: 32nd note)."""
    grid = beat_duration / subdivisions
    if grid <= 0:
        return t
    return round(round(t / grid) * grid, 5)


def quantize_notes(
    notes: List[Dict], bpm: float, subdivisions: int = 8, min_duration: float = 0.0
) -> List[Dict]:
    """
    Quantize all note start times and durations to the beat grid.
    subdivisions=8 → eighth-note grid (e.g. 16th notes at BPM=120 → 0.125s)
    """
    if bpm <= 0:
        return notes
    beat_dur = 60.0 / bpm
    quantized = []
    for note in notes:
        n = note.copy()
        q_start = quantize_time(float(note.get("startTime", 0)), beat_dur, subdivisions)
        raw_dur = float(note.get("duration", beat_dur / 2))
        q_end = quantize_time(float(note.get("startTime", 0)) + raw_dur, beat_dur, subdivisions)
        q_dur = max(min_duration if min_duration > 0 else beat_dur / subdivisions, q_end - q_start)
        n["startTime"] = q_start
        n["duration"] = round(q_dur, 5)
        quantized.append(n)
    return quantized


def align_chords_to_measures(
    chords: List[Dict], bpm: float, time_sig_num: int = 4, time_sig_den: int = 4
) -> List[Dict]:
    """
    Snap chord start/end times to measure boundaries.
    Chords shorter than half a beat are extended.
    """
    if bpm <= 0 or not chords:
        return chords
    beat_dur = 60.0 / bpm
    measure_dur = beat_dur * time_sig_num

    aligned = []
    for chord in chords:
        c = chord.copy()
        start = float(chord.get("startTime", 0))
        end = float(chord.get("endTime", start + measure_dur))

        q_start = quantize_time(start, beat_dur, time_sig_num)  # align to beats
        q_end = quantize_time(end, beat_dur, time_sig_num)
        if q_end <= q_start:
            q_end = q_start + beat_dur  # at least one beat

        c["startTime"] = round(q_start, 4)
        c["endTime"] = round(q_end, 4)
        aligned.append(c)
    return aligned


# ─── MIDI export ──────────────────────────────────────────────────────────────

def export_midi(
    tracks: List[Dict],
    bpm: float = 120.0,
    output_path: str = None,
    quantize: bool = True,
    subdivisions: int = 8,
) -> bytes:
    """
    Export arrangement tracks to MIDI format using mido.
    Supports note quantization before export.
    Returns bytes of the MIDI file.
    """
    try:
        import mido
    except ImportError as exc:
        raise RuntimeError(
            "MIDI export dependency missing: 'mido' is not installed. "
            "Install it with: pip install mido"
        ) from exc

    bpm = float(bpm) if bpm else 120.0
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    tempo = mido.bpm2tempo(bpm)

    # Tempo track
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4,
                                         clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))

    def seconds_to_ticks(seconds: float) -> int:
        return max(0, int(seconds * (480 * bpm / 60)))

    for track_data in tracks:
        track = mido.MidiTrack()
        mid.tracks.append(track)

        track_name = track_data.get("name", "Track")
        channel = int(track_data.get("channel", 0))
        if channel > 15:
            channel = 15
        volume = int(float(track_data.get("volume", 0.8)) * 127)
        program = int(track_data.get("program", 0))

        track.append(mido.MetaMessage("track_name", name=track_name, time=0))

        if channel != 9:
            track.append(mido.Message("program_change", channel=channel, program=program, time=0))

        track.append(mido.Message("control_change", channel=channel, control=7, value=volume, time=0))

        pan_float = float(track_data.get("pan", 0.0))
        pan_midi = int((pan_float + 1) / 2 * 127)
        track.append(mido.Message("control_change", channel=channel, control=10, value=pan_midi, time=0))

        # Quantize notes
        notes_data = list(track_data.get("notes", []))
        if quantize:
            notes_data = quantize_notes(notes_data, bpm, subdivisions=subdivisions)

        # Build events
        events = []
        is_muted = bool(track_data.get("muted", False))
        for note in notes_data:
            start_ticks = seconds_to_ticks(float(note.get("startTime", 0)))
            dur = float(note.get("duration", 60.0 / bpm / 2))
            end_ticks = seconds_to_ticks(float(note.get("startTime", 0)) + dur)
            pitch = max(0, min(127, int(note.get("pitch", 60))))
            velocity = 0 if is_muted else max(1, min(127, int(note.get("velocity", 80))))

            events.append(("note_on",  start_ticks, pitch, velocity, channel))
            events.append(("note_off", end_ticks,   pitch, 0,        channel))

        events.sort(key=lambda x: (x[1], 0 if x[0] == "note_off" else 1))

        current_tick = 0
        for evt_type, abs_tick, pitch, vel, ch in events:
            delta = max(0, abs_tick - current_tick)
            current_tick = abs_tick
            track.append(mido.Message(evt_type, channel=ch, note=pitch, velocity=vel, time=delta))

        track.append(mido.MetaMessage("end_of_track", time=0))

    buf = io.BytesIO()
    mid.save(file=buf)
    midi_bytes = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(midi_bytes)
        logger.info(f"MIDI exported: {output_path} ({len(midi_bytes)} bytes)")

    return midi_bytes


# ─── Chord symbol utilities ───────────────────────────────────────────────────

_CHORD_KIND_MAP = {
    "maj7": "major-seventh",  "M7": "major-seventh",
    "m7":   "minor-seventh",  "min7": "minor-seventh",
    "7":    "dominant",
    "m":    "minor",          "min": "minor",
    "dim7": "diminished-seventh", "dim": "diminished",
    "aug":  "augmented",
    "sus4": "suspended-fourth", "sus2": "suspended-second",
    "6":    "major-sixth",    "m6": "minor-sixth",
    "m7b5": "half-diminished", "ø7": "half-diminished",
    "maj":  "major",          "":   "major",
}

def _parse_chord_symbol(symbol: str) -> Tuple[str, str]:
    """Return (root_step, quality) for a chord symbol like 'Am7', 'Cmaj7', 'F#m'."""
    if not symbol:
        return "C", "major"
    if len(symbol) >= 2 and symbol[1] in "#b":
        root = symbol[:2]
        quality_raw = symbol[2:]
    else:
        root = symbol[:1]
        quality_raw = symbol[1:]

    # Remove slash bass note
    if "/" in quality_raw:
        quality_raw = quality_raw.split("/")[0]

    # Map to MusicXML kind
    kind = "major"
    for suffix in sorted(_CHORD_KIND_MAP, key=lambda k: -len(k)):
        if quality_raw.endswith(suffix) or quality_raw == suffix:
            kind = _CHORD_KIND_MAP[suffix]
            break

    return root, kind


def _chord_to_musicxml_harmony(chord_ev: Dict, bpm: float, time_sig: Tuple[int, int]) -> str:
    """Generate <harmony> element XML for a chord event."""
    symbol = chord_ev.get("chord", "C")
    root, kind = _parse_chord_symbol(symbol)

    # Root step / alter
    step = root[0].upper()
    alter_map = {"#": "1", "b": "-1"}
    alter_str = ""
    if len(root) > 1 and root[1] in alter_map:
        alter_str = f"<alter>{alter_map[root[1]]}</alter>"

    return f"""    <harmony>
      <root><root-step>{step}</root-step>{alter_str}</root>
      <kind>{kind}</kind>
    </harmony>"""


# ─── MusicXML export ──────────────────────────────────────────────────────────

def export_musicxml(
    chords: List[Dict],
    melody_notes: List[Dict],
    key: str = "C",
    mode: str = "major",
    bpm: float = 120.0,
    time_sig: Tuple[int, int] = (4, 4),
    output_path: str = None,
) -> str:
    """
    Export chord progression + melody to MusicXML.
    Uses minimal native XML generation with correct chord symbols.
    """
    bpm = float(bpm) if bpm else 120.0
    beat_dur = 60.0 / bpm
    measure_dur = beat_dur * time_sig[0]
    divisions = 4  # quarter note = 4 divisions

    # Align chords to measures
    aligned_chords = align_chords_to_measures(chords, bpm, time_sig[0], time_sig[1])

    # Fifths lookup for key signature
    FIFTHS_MAP = {
        "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6,
        "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6,
        "Am": 0, "Em": -3, "Dm": -1, "Cm": -3,
    }
    key_root = key.split("/")[0].strip()
    fifths = FIFTHS_MAP.get(key_root, 0)
    key_mode = "minor" if mode == "minor" else "major"

    # Group melody notes into measures
    def dur_type(quarters: float) -> str:
        if quarters >= 4:   return "whole"
        if quarters >= 2:   return "half"
        if quarters >= 1:   return "quarter"
        if quarters >= 0.5: return "eighth"
        return "16th"

    # Build measures
    total_dur = max(
        (aligned_chords[-1]["endTime"] if aligned_chords else 0),
        (melody_notes[-1].get("endTime", 0) if melody_notes else 0),
        measure_dur,
    )
    num_measures = max(1, math.ceil(total_dur / measure_dur))

    # Pitch name from MIDI
    PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    def midi_to_pitch_xml(midi: int) -> str:
        octave = midi // 12 - 1
        step_idx = midi % 12
        step = PITCH_NAMES[step_idx]
        alter = ""
        if "#" in step:
            step = step[0]
            alter = "<alter>1</alter>"
        return f"<pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch>"

    measures_xml = []
    chord_idx = 0

    for measure_num in range(1, num_measures + 1):
        m_start = (measure_num - 1) * measure_dur
        m_end = measure_num * measure_dur

        measure_parts = []

        # Attributes on first measure
        if measure_num == 1:
            measure_parts.append(f"""      <attributes>
        <divisions>{divisions}</divisions>
        <key><fifths>{fifths}</fifths><mode>{key_mode}</mode></key>
        <time><beats>{time_sig[0]}</beats><beat-type>{time_sig[1]}</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <direction placement="above">
        <direction-type>
          <metronome parentheses="no">
            <beat-unit>quarter</beat-unit>
            <per-minute>{int(bpm)}</per-minute>
          </metronome>
        </direction-type>
      </direction>""")

        # Chord harmonies in this measure
        while chord_idx < len(aligned_chords):
            c = aligned_chords[chord_idx]
            if c["startTime"] >= m_end:
                break
            if c["startTime"] >= m_start:
                measure_parts.append(_chord_to_musicxml_harmony(c, bpm, time_sig))
            chord_idx += 1

        # Melody notes in this measure
        m_notes = [n for n in melody_notes if m_start <= float(n.get("startTime", 0)) < m_end]
        if m_notes:
            for n in m_notes[:8]:  # cap per measure
                dur_secs = float(n.get("endTime", n.get("startTime", 0) + 0.5)) - float(n.get("startTime", 0))
                dur_quarters = max(0.125, dur_secs * bpm / 60)
                dur_divs = max(1, round(dur_quarters * divisions))
                dtype = dur_type(dur_quarters)
                pitch_xml = midi_to_pitch_xml(int(n.get("pitch", 60)))
                vel = int(n.get("velocity", 80))
                measure_parts.append(f"""      <note>
        {pitch_xml}
        <duration>{dur_divs}</duration>
        <type>{dtype}</type>
        <dynamics><p>{vel}</p></dynamics>
      </note>""")
        else:
            # Whole rest
            measure_parts.append(f"""      <note>
        <rest measure="yes"/>
        <duration>{divisions * time_sig[0]}</duration>
        <type>whole</type>
      </note>""")

        measures_xml.append(f"""    <measure number="{measure_num}">
{chr(10).join(measure_parts)}
    </measure>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <work><work-title>MusicAI Export — {key} {mode}</work-title></work>
  <identification>
    <creator type="composer">MusicAI Studio</creator>
    <encoding>
      <software>MusicAI Studio v1.1</software>
      <encoding-date>{__import__("datetime").date.today().isoformat()}</encoding-date>
    </encoding>
  </identification>
  <part-list>
    <score-part id="P1"><part-name>Lead Sheet</part-name></score-part>
  </part-list>
  <part id="P1">
{chr(10).join(measures_xml)}
  </part>
</score-partwise>
"""

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml)
        logger.info(f"MusicXML exported: {output_path}")

    return xml


# ─── Lead sheet ───────────────────────────────────────────────────────────────

def export_lead_sheet(
    chords: List[Dict],
    key: str,
    bpm: float,
    time_sig: Tuple[int, int],
    structure: List[Dict] = None,
) -> str:
    """
    Generate a text-format lead sheet with measure numbers, bar lines, and sections.
    """
    bpm = float(bpm) if bpm else 120.0
    beat_dur = 60.0 / bpm
    measure_dur = beat_dur * time_sig[0]

    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        f"║  MusicAI Studio — Lead Sheet                            ║",
        f"║  Key: {key:<6}  Tempo: {int(bpm)} BPM  Time: {time_sig[0]}/{time_sig[1]:<20}║",
        "╚══════════════════════════════════════════════════════════╝",
        "",
    ]

    # Align chords to measures
    aligned = align_chords_to_measures(chords, bpm, time_sig[0], time_sig[1])

    def measure_number(t: float) -> int:
        return max(1, int(t / measure_dur) + 1) if measure_dur > 0 else 1

    if structure:
        for section in structure:
            label = section.get("label", "section").upper()
            s_start = section.get("startTime", 0)
            s_end = section.get("endTime", 0)
            m_start = measure_number(s_start)
            m_end = measure_number(s_end)

            section_chords = [c for c in aligned if c.get("startTime", 0) >= s_start and c.get("startTime", 0) < s_end]

            lines.append(f"┌─ [{label}]  mm. {m_start}–{m_end - 1} {'─' * max(1, 40 - len(label) - len(str(m_start)) - len(str(m_end)))}┐")

            # Group into rows of 4 chords
            row = []
            prev_measure = None
            for chord in section_chords[:32]:
                m = measure_number(chord.get("startTime", 0))
                symbol = chord.get("chord", "C")
                roman = chord.get("romanNumeral", "")
                conf_str = f"({int(chord.get('confidence', 0.8) * 100)}%)" if chord.get("confidence") else ""
                cell = f"{m}|{symbol:<5}{conf_str}"
                row.append(cell)
                if len(row) == 4:
                    lines.append("  " + "  ".join(row))
                    row = []
            if row:
                lines.append("  " + "  ".join(row))
            lines.append(f"└{'─' * 55}┘")
            lines.append("")
    else:
        # No structure — flat measure list
        row = []
        for chord in aligned[:64]:
            m = measure_number(chord.get("startTime", 0))
            symbol = chord.get("chord", "C")
            row.append(f"{m}|{symbol:<5}")
            if len(row) == 4:
                lines.append("  " + " │ ".join(row))
                row = []
        if row:
            lines.append("  " + " │ ".join(row))
        lines.append("")

    lines.append("── Generated by MusicAI Studio ──")
    return "\n".join(lines)


# ─── music21 MusicXML export (primary) ───────────────────────────────────────

def export_musicxml_music21(
    chords: List[Dict],
    melody_notes: List[Dict],
    key_name: str = "C",
    mode: str = "major",
    bpm: float = 120.0,
    time_sig: Tuple[int, int] = (4, 4),
    section_labels: Optional[List[Dict]] = None,
    output_path: Optional[str] = None,
    title: str = "Untitled",
) -> str:
    """
    Export chord progression + melody to MusicXML using music21 v9.

    Produces a proper 2-staff score (treble + chord symbols) with:
      - Key signature (correct accidentals via music21.key.Key)
      - Time signature
      - Tempo marking (MetronomeMark)
      - Melody line in treble clef (quantized to 16th notes)
      - Chord symbols above the staff (ChordSymbol objects, editable in Sibelius/MuseScore)
      - Section rehearsal marks (Verse, Chorus, etc.)
      - Rest filling for incomplete measures

    Falls back to the native XML export if music21 is unavailable.

    Returns the output file path.
    """
    try:
        import music21 as m21
        from music21 import stream, note, chord as m21chord
        from music21 import key as m21key, meter, tempo as m21tempo
        from music21 import harmony, expressions, clef as m21clef
        from music21 import duration as m21duration, interval
    except ImportError:
        logger.warning("music21 not available — falling back to native XML export")
        return export_musicxml(chords, melody_notes, key_name, mode, bpm, time_sig, output_path)

    bpm = float(bpm) if bpm and bpm > 0 else 120.0
    num_beats, beat_unit = int(time_sig[0]), int(time_sig[1])
    beat_sec = 60.0 / bpm
    measure_sec = beat_sec * num_beats

    # ── Build score ─────────────────────────────────────────────────────────
    score = stream.Score()
    score.metadata = m21.metadata.Metadata()
    score.metadata.title = title

    part = stream.Part(id="P1")

    # ── Key signature ─────────────────────────────────────────────────────
    _ENHARMONIC_M21 = {
        "C#": "C#", "Db": "D-", "D#": "D#", "Eb": "E-",
        "F#": "F#", "Gb": "G-", "G#": "G#", "Ab": "A-",
        "A#": "A#", "Bb": "B-", "Cb": "C-", "B#": "B#",
    }
    m21_key_name = _ENHARMONIC_M21.get(key_name, key_name)
    key_mode = "minor" if mode in ("minor", "harmonic_minor") else "major"
    try:
        k = m21key.Key(m21_key_name, key_mode)
    except Exception:
        k = m21key.Key("C", "major")

    # ── Time signature ─────────────────────────────────────────────────────
    ts = meter.TimeSignature(f"{num_beats}/{beat_unit}")

    # ── Tempo mark ─────────────────────────────────────────────────────────
    mm = m21tempo.MetronomeMark(number=round(bpm), referent=m21duration.Duration("quarter"))

    # ── Compute total measures ─────────────────────────────────────────────
    total_dur_sec = 0.0
    if chords:
        total_dur_sec = max(total_dur_sec, max(float(c.get("end", c.get("endTime", 0))) for c in chords))
    if melody_notes:
        total_dur_sec = max(total_dur_sec, max(float(n.get("endTime", n.get("end", 0))) for n in melody_notes))
    if total_dur_sec < measure_sec:
        total_dur_sec = measure_sec

    num_measures = max(1, math.ceil(total_dur_sec / measure_sec))

    # ── Map chord symbols to beat positions ───────────────────────────────
    def seconds_to_offset(t_sec: float) -> float:
        """Convert seconds to score offset in quarter notes."""
        return t_sec / beat_sec

    def _quality_to_m21(quality: str) -> str:
        """Map our quality codes to music21 chord kind strings."""
        MAP = {
            "maj": "major", "min": "minor",
            "dom7": "dominant-seventh", "maj7": "major-seventh",
            "min7": "minor-seventh", "dim7": "diminished-seventh",
            "dim": "diminished", "aug": "augmented",
            "sus2": "suspended-second", "sus4": "suspended-fourth",
            "add9": "major-ninth", "min9": "minor-ninth",
        }
        return MAP.get(quality, "major")

    def _parse_chord_for_m21(chord_str: str) -> Optional[harmony.ChordSymbol]:
        """Parse 'Cmin7', 'Gmaj', etc. to music21 ChordSymbol."""
        if not chord_str or chord_str in ("N", "N.C.", "NC", "None"):
            return None
        _EN = {"Db": "D-", "Eb": "E-", "Gb": "G-", "Ab": "A-", "Bb": "B-", "Cb": "C-"}
        _QUALITIES = {
            "maj": "major", "min": "minor", "dim": "diminished", "aug": "augmented",
            "maj7": "major-seventh", "min7": "minor-seventh", "dom7": "dominant-seventh",
            "dim7": "diminished-seventh", "sus2": "suspended-second", "sus4": "suspended-fourth",
            "add9": "major-ninth", "min9": "minor-ninth",
        }
        for root_len in (2, 1):
            root_raw = chord_str[:root_len]
            root = _EN.get(root_raw, root_raw)
            if root in ["C", "C#", "D-", "D", "D#", "E-", "E", "F", "F#", "G-", "G", "G#", "A-", "A", "A#", "B-", "B"]:
                quality_str = chord_str[root_len:]
                kind = _QUALITIES.get(quality_str, "major")
                try:
                    cs = harmony.ChordSymbol(root=root, kind=kind)
                    return cs
                except Exception:
                    try:
                        return harmony.ChordSymbol(chord_str)
                    except Exception:
                        return None
        return None

    # ── Build measures ─────────────────────────────────────────────────────
    melody_idx = 0
    chord_idx = 0

    for m_num in range(num_measures):
        m_start_sec = m_num * measure_sec
        m_end_sec   = (m_num + 1) * measure_sec
        m_offset = m_num * num_beats   # offset in quarter notes (assuming 4/4)

        measure = stream.Measure(number=m_num + 1)

        # Header elements in first measure
        if m_num == 0:
            measure.insert(0, k)
            measure.insert(0, ts)
            measure.insert(0, mm)
            measure.insert(0, m21clef.TrebleClef())

        # Section label as rehearsal mark
        if section_labels:
            for sec in section_labels:
                sec_start = float(sec.get("start", 0))
                if abs(sec_start - m_start_sec) < measure_sec / 2:
                    label = str(sec.get("label", "")).capitalize()
                    rh = expressions.RehearsalMark(label)
                    measure.insert(0, rh)
                    break

        # Chord symbols at their beat positions within the measure
        while chord_idx < len(chords):
            c = chords[chord_idx]
            c_start = float(c.get("start", c.get("startTime", 0)))
            if c_start >= m_end_sec:
                break
            if c_start >= m_start_sec:
                cs = _parse_chord_for_m21(c.get("chord", ""))
                if cs is not None:
                    # Position within measure in quarter notes
                    pos_in_measure = (c_start - m_start_sec) / beat_sec
                    measure.insert(pos_in_measure, cs)
            chord_idx += 1

        # Melody notes in this measure
        measure_notes = []
        while melody_idx < len(melody_notes):
            n = melody_notes[melody_idx]
            n_start = float(n.get("startTime", n.get("start", 0)))
            if n_start >= m_end_sec:
                break
            if n_start >= m_start_sec:
                measure_notes.append(n)
                melody_idx += 1
            else:
                melody_idx += 1

        if measure_notes:
            measure_filled_ql = 0.0
            for n in measure_notes:
                n_start = float(n.get("startTime", n.get("start", 0)))
                n_dur_sec = float(n.get("duration", beat_sec / 2))
                midi_pitch = int(n.get("pitch", n.get("midiPitch", 60)))

                pos_in_measure_ql = (n_start - m_start_sec) / beat_sec

                # Fill gap with rest if needed
                if pos_in_measure_ql > measure_filled_ql + 0.01:
                    rest_ql = pos_in_measure_ql - measure_filled_ql
                    try:
                        r = note.Rest(quarterLength=_quantize_ql(rest_ql))
                        measure.append(r)
                        measure_filled_ql += float(r.quarterLength)
                    except Exception:
                        pass

                # Add note
                ql = _quantize_ql(n_dur_sec / beat_sec)
                try:
                    m21_note = note.Note(midi=midi_pitch)
                    m21_note.quarterLength = ql
                    vel = int(n.get("velocity", 80))
                    m21_note.volume.velocity = max(1, min(127, vel))
                    measure.append(m21_note)
                    measure_filled_ql = pos_in_measure_ql + ql
                except Exception as e:
                    logger.debug("Note error at pitch=%d: %s", midi_pitch, e)
                    continue

            # Fill rest of measure
            remaining_ql = num_beats - measure_filled_ql
            if remaining_ql > 0.1:
                try:
                    r = note.Rest(quarterLength=_quantize_ql(remaining_ql))
                    measure.append(r)
                except Exception:
                    pass
        else:
            # Full measure rest
            r = note.Rest()
            r.quarterLength = num_beats
            measure.append(r)

        part.append(measure)

    score.append(part)

    # ── Write output ──────────────────────────────────────────────────────
    if output_path is None:
        import tempfile
        output_path = tempfile.mktemp(suffix=".musicxml")

    try:
        score.write("musicxml", fp=output_path)
        logger.info("[export_music21] MusicXML written to %s (%d measures)", output_path, num_measures)
        return output_path
    except Exception as e:
        logger.error("[export_music21] music21 write failed: %s — falling back to native", e)
        return export_musicxml(chords, melody_notes, key_name, mode, bpm, time_sig, output_path)


def _quantize_ql(ql: float, min_ql: float = 0.0625) -> float:
    """Quantize quarter-length to nearest 16th note grid."""
    grid = 0.25  # 16th note
    q = max(min_ql, round(ql / grid) * grid)
    return round(q, 4)


def _lead_sheet_to_html(text: str, title: str = "Lead Sheet") -> str:
    """
    Wrap a plain-text lead sheet in styled HTML.
    Uses monospace font and print-optimized CSS.
    The resulting .html file can be opened in any browser and printed as PDF
    (File → Print → Save as PDF).
    """
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = escaped.split("\n")
    # Make chord lines bold
    def _style_line(line: str) -> str:
        stripped = line.strip()
        if stripped.startswith("│") or stripped.startswith("||") or stripped.startswith("|"):
            return f"<span class='chords'>{line}</span>"
        if stripped.startswith("═") or stripped.startswith("──") or stripped.startswith("="):
            return f"<span class='rule'>{line}</span>"
        if any(kw in stripped for kw in ("Verse", "Chorus", "Bridge", "Intro", "Outro")):
            return f"<strong class='section'>{line}</strong>"
        return line

    body_lines = "\n".join(_style_line(l) for l in lines)

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Courier New', Courier, monospace;
      font-size: 11pt;
      line-height: 1.55;
      max-width: 900px;
      margin: 2cm auto;
      padding: 0 1cm;
      color: #1a1a1a;
      background: #fff;
    }}
    h1 {{
      font-family: Georgia, serif;
      font-size: 18pt;
      text-align: center;
      margin-bottom: 0.5em;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .chords {{ color: #003399; font-weight: bold; }}
    .rule   {{ color: #999; }}
    .section {{ color: #006600; font-size: 12pt; }}
    @media print {{
      body {{ margin: 1cm; }}
      @page {{ size: A4; margin: 2cm; }}
    }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <pre>{body_lines}</pre>
</body>
</html>"""


# ─── Main export orchestrator ─────────────────────────────────────────────────

def run_export(
    project_id: int,
    analysis: dict,
    arrangement: dict,
    formats: List[str],
    output_dir: str,
    progress_callback=None,
) -> Dict[str, str]:
    """
    Run all requested exports. Returns dict of format → file path.
    Handles: midi, musicxml, pdf, wav, flac, mp3, stems.
    """
    logger.info(f"Exporting project {project_id}: {formats}")
    os.makedirs(output_dir, exist_ok=True)

    results = {}
    rhythm = analysis.get("rhythm", {})
    bpm = float(rhythm.get("bpm", 120.0))
    key_data = analysis.get("key", {})
    key = str(key_data.get("globalKey", "C"))
    mode = str(key_data.get("mode", "major"))
    time_sig = (int(rhythm.get("timeSignatureNumerator", 4)), int(rhythm.get("timeSignatureDenominator", 4)))
    chords = list(analysis.get("chords", {}).get("chords", []))
    melody_notes = list(analysis.get("melody", {}).get("notes", []))
    structure = list(analysis.get("structure", {}).get("sections", []))
    tracks = list(arrangement.get("tracks", []))
    total_duration = float(arrangement.get("totalDurationSeconds", 120.0))

    # MIDI
    if "midi" in formats:
        midi_path = os.path.join(output_dir, f"project_{project_id}.mid")
        try:
            if progress_callback:
                progress_callback("Exporting MIDI", 20)
            export_midi(tracks, bpm=bpm, output_path=midi_path, quantize=True)
            results["midi"] = midi_path
        except Exception as e:
            logger.error(f"MIDI export failed: {e}")

    # MusicXML — primary: music21 v9; fallback: native XML
    if "musicxml" in formats:
        xml_path = os.path.join(output_dir, f"project_{project_id}.musicxml")
        try:
            if progress_callback:
                progress_callback("Exporting MusicXML (music21)", 35)
            export_musicxml_music21(
                chords=chords,
                melody_notes=melody_notes,
                key_name=key,
                mode=mode,
                bpm=bpm,
                time_sig=time_sig,
                section_labels=structure,
                output_path=xml_path,
                title=f"Project {project_id}",
            )
            results["musicxml"] = xml_path
            logger.info("MusicXML exported via music21: %s", xml_path)
        except Exception as e:
            logger.error(f"MusicXML export (music21) failed: {e} — trying native fallback")
            try:
                export_musicxml(chords, melody_notes, key, mode, bpm, time_sig, xml_path)
                results["musicxml"] = xml_path
            except Exception as e2:
                logger.error(f"MusicXML native fallback also failed: {e2}")

    # Lead Sheet — HTML+text with inline CSS (viewable in browser, printable as PDF)
    if "pdf" in formats:
        pdf_path = os.path.join(output_dir, f"project_{project_id}_lead_sheet.html")
        try:
            if progress_callback:
                progress_callback("Generating lead sheet", 45)
            lead_sheet_text = export_lead_sheet(chords, key, bpm, time_sig, structure)
            html_content = _lead_sheet_to_html(lead_sheet_text, title=f"Project {project_id} — Lead Sheet")
            with open(pdf_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            results["pdf"] = pdf_path
            logger.info("Lead sheet HTML written: %s", pdf_path)
        except Exception as e:
            logger.error(f"Lead sheet export failed: {e}")

    # Audio formats
    audio_formats = [f for f in formats if f in ("wav", "flac", "mp3", "stems")]
    if audio_formats and tracks:
        try:
            from audio.render_pipeline import run_audio_render
            if progress_callback:
                progress_callback("Rendering audio", 50)
            audio_results = run_audio_render(
                project_id, tracks, total_duration, audio_formats, output_dir, progress_callback
            )
            results.update(audio_results)
        except Exception as e:
            logger.error(f"Audio render failed: {e}")

    logger.info(f"Export complete: {list(results.keys())}")
    return results
