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

    # MusicXML
    if "musicxml" in formats:
        xml_path = os.path.join(output_dir, f"project_{project_id}.musicxml")
        try:
            if progress_callback:
                progress_callback("Exporting MusicXML", 35)
            export_musicxml(chords, melody_notes, key, mode, bpm, time_sig, xml_path)
            results["musicxml"] = xml_path
        except Exception as e:
            logger.error(f"MusicXML export failed: {e}")

    # Lead Sheet (PDF text fallback)
    if "pdf" in formats:
        pdf_path = os.path.join(output_dir, f"project_{project_id}_lead_sheet.txt")
        try:
            if progress_callback:
                progress_callback("Generating lead sheet", 45)
            lead_sheet = export_lead_sheet(chords, key, bpm, time_sig, structure)
            with open(pdf_path, "w", encoding="utf-8") as f:
                f.write(lead_sheet)
            results["pdf"] = pdf_path
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
