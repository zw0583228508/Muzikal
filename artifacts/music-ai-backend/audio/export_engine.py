"""
Export Engine: MIDI, MusicXML, and audio export.
Supports: MIDI (.mid), MusicXML (.musicxml), lead sheet text.
"""

import os
import io
import logging
import json
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def export_midi(tracks: List[Dict], bpm: float = 120.0, output_path: str = None) -> bytes:
    """
    Export arrangement tracks to MIDI format using mido.
    Returns bytes of the MIDI file.
    """
    import mido

    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    tempo = mido.bpm2tempo(bpm)

    # Tempo track
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

    def seconds_to_ticks(seconds: float) -> int:
        return int(seconds * (480 * bpm / 60))

    for track_data in tracks:
        track = mido.MidiTrack()
        mid.tracks.append(track)

        track_name = track_data.get("name", "Track")
        channel = track_data.get("channel", 0)
        if channel > 15:
            channel = 15
        volume = int(track_data.get("volume", 0.8) * 127)

        track.append(mido.MetaMessage("track_name", name=track_name, time=0))

        # Program change (skip for drums channel 9)
        if channel != 9:
            program = track_data.get("program", 0)
            track.append(mido.Message("program_change", channel=channel, program=program, time=0))

        # Volume control change
        track.append(mido.Message("control_change", channel=channel, control=7, value=volume, time=0))

        # Pan
        pan_float = track_data.get("pan", 0.0)
        pan_midi = int((pan_float + 1) / 2 * 127)
        track.append(mido.Message("control_change", channel=channel, control=10, value=pan_midi, time=0))

        # Build events list from notes
        notes_data = track_data.get("notes", [])

        events = []
        for note in notes_data:
            start_ticks = seconds_to_ticks(note["startTime"])
            end_ticks = seconds_to_ticks(note["startTime"] + note.get("duration", 0.25))
            pitch = max(0, min(127, note.get("pitch", 60)))
            velocity = max(1, min(127, note.get("velocity", 80)))

            if track_data.get("muted", False):
                velocity = 0

            events.append(("note_on", start_ticks, pitch, velocity, channel))
            events.append(("note_off", end_ticks, pitch, 0, channel))

        # Sort events by time
        events.sort(key=lambda x: x[1])

        # Convert to delta times
        current_tick = 0
        for event in events:
            evt_type, abs_tick, pitch, vel, ch = event
            delta = max(0, abs_tick - current_tick)
            current_tick = abs_tick
            track.append(mido.Message(evt_type, channel=ch, note=pitch, velocity=vel, time=delta))

        track.append(mido.MetaMessage("end_of_track", time=0))

    # Write to bytes
    buf = io.BytesIO()
    mid.save(file=buf)
    midi_bytes = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(midi_bytes)
        logger.info(f"MIDI exported: {output_path} ({len(midi_bytes)} bytes)")

    return midi_bytes


def export_musicxml(chords: List[Dict], melody_notes: List[Dict],
                    key: str = "C", mode: str = "major", bpm: float = 120.0,
                    time_sig: tuple = (4, 4), output_path: str = None) -> str:
    """
    Export chord progression + melody to MusicXML.
    Returns MusicXML string.
    """
    try:
        import music21.stream as stream
        import music21.note as m21note
        import music21.chord as m21chord
        import music21.tempo as m21tempo
        import music21.meter as m21meter
        import music21.key as m21key
        from music21 import pitch, duration

        # Build score
        score = stream.Score()
        melody_part = stream.Part()
        chord_part = stream.Part()

        melody_part.id = "Melody"
        chord_part.id = "Chords"

        # Set key and time signature
        ks = m21key.Key(key, mode if mode == "major" else "minor")
        ts = m21meter.TimeSignature(f"{time_sig[0]}/{time_sig[1]}")
        mm = m21tempo.MetronomeMark(number=bpm)

        melody_part.append(mm)
        melody_part.append(ks)
        melody_part.append(ts)

        # Chord part
        for chord_ev in chords[:32]:  # Limit for demo
            chord_symbol = chord_ev.get("chord", "C")
            start = chord_ev.get("startTime", 0)
            dur_secs = chord_ev.get("endTime", start + 2) - start
            dur_quarters = max(0.25, dur_secs * (bpm / 60))

            try:
                c = m21chord.Chord(chord_symbol)
                c.duration = duration.Duration(dur_quarters)
                chord_part.append(c)
            except Exception:
                rest = m21note.Rest()
                rest.duration = duration.Duration(max(0.25, dur_quarters))
                chord_part.append(rest)

        # Melody notes
        for note_data in melody_notes[:64]:
            start = note_data.get("startTime", 0)
            dur_secs = note_data.get("endTime", start + 0.25) - start
            dur_quarters = max(0.0625, dur_secs * (bpm / 60))
            midi_pitch = note_data.get("pitch", 60)

            n = m21note.Note()
            n.pitch = pitch.Pitch(midi=midi_pitch)
            n.duration = duration.Duration(dur_quarters)
            n.volume.velocity = note_data.get("velocity", 80)
            melody_part.append(n)

        score.append(melody_part)
        score.append(chord_part)

        # Export to MusicXML
        if output_path:
            score.write("musicxml", fp=output_path)
            logger.info(f"MusicXML exported: {output_path}")
            with open(output_path, "r") as f:
                return f.read()
        else:
            xml_str = score.write("musicxml")
            with open(xml_str, "r") as f:
                content = f.read()
            return content

    except Exception as e:
        logger.warning(f"MusicXML export failed: {e}")
        # Return minimal MusicXML
        return generate_minimal_musicxml(chords, key, bpm, time_sig)


def generate_minimal_musicxml(chords: List[Dict], key: str, bpm: float, time_sig: tuple) -> str:
    """Generate minimal valid MusicXML without music21."""
    measures_xml = []
    for i, chord_ev in enumerate(chords[:16]):
        chord = chord_ev.get("chord", "C")
        measures_xml.append(f"""
        <measure number="{i + 1}">
            <harmony>
                <root><root-step>{chord[0]}</root-step></root>
                <kind>{("minor" if "m" in chord else "major")}</kind>
            </harmony>
            <note>
                <pitch><step>C</step><octave>4</octave></pitch>
                <duration>4</duration>
                <type>whole</type>
            </note>
        </measure>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
    <work><work-title>MusicAI Export</work-title></work>
    <identification>
        <creator type="composer">MusicAI Studio</creator>
        <encoding><software>MusicAI Studio</software></encoding>
    </identification>
    <part-list>
        <score-part id="P1"><part-name>Chords</part-name></score-part>
    </part-list>
    <part id="P1">
        <measure number="1">
            <attributes>
                <divisions>4</divisions>
                <key><fifths>0</fifths></key>
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
            </direction>
        </measure>
        {"".join(measures_xml)}
    </part>
</score-partwise>
"""


def export_lead_sheet(chords: List[Dict], key: str, bpm: float, time_sig: tuple,
                      structure: List[Dict] = None) -> str:
    """
    Generate a text-format lead sheet with chord symbols.
    """
    lines = [
        f"MusicAI Studio - Lead Sheet",
        f"Key: {key}  |  Tempo: {int(bpm)} BPM  |  Time: {time_sig[0]}/{time_sig[1]}",
        "=" * 60,
        "",
    ]

    if structure:
        # Group chords by section
        for section in structure:
            section_label = section.get("label", "section").upper()
            start = section.get("startTime", 0)
            end = section.get("endTime", 0)

            section_chords = [
                c for c in chords
                if c.get("startTime", 0) >= start and c.get("startTime", 0) < end
            ]

            lines.append(f"[{section_label}]")
            chord_line = " | ".join(
                c.get("chord", "C") for c in section_chords[:8]
            )
            lines.append(chord_line if chord_line else "(no chords)")
            lines.append("")
    else:
        # Just list chords
        chord_groups = [chords[i:i+4] for i in range(0, min(len(chords), 32), 4)]
        for group in chord_groups:
            line = " | ".join(c.get("chord", "C") for c in group)
            lines.append(line)

    return "\n".join(lines)


def run_export(project_id: int, analysis: dict, arrangement: dict,
               formats: List[str], output_dir: str,
               progress_callback=None) -> Dict[str, str]:
    """
    Run all requested exports. Returns dict of format → file path.
    Handles: midi, musicxml, pdf, wav, flac, mp3, stems.
    """
    logger.info(f"Exporting project {project_id}: {formats}")
    os.makedirs(output_dir, exist_ok=True)

    results = {}
    rhythm = analysis.get("rhythm", {})
    bpm = rhythm.get("bpm", 120.0)
    key_data = analysis.get("key", {})
    key = key_data.get("globalKey", "C")
    mode = key_data.get("mode", "major")
    time_sig = (rhythm.get("timeSignatureNumerator", 4), rhythm.get("timeSignatureDenominator", 4))
    chords = analysis.get("chords", {}).get("chords", [])
    melody_notes = analysis.get("melody", {}).get("notes", [])
    structure = analysis.get("structure", {}).get("sections", [])
    tracks = arrangement.get("tracks", [])
    total_duration = float(arrangement.get("totalDurationSeconds", 120.0))

    # MIDI
    if "midi" in formats:
        midi_path = os.path.join(output_dir, f"project_{project_id}.mid")
        try:
            if progress_callback:
                progress_callback("Exporting MIDI", 20)
            export_midi(tracks, bpm=bpm, output_path=midi_path)
            results["midi"] = midi_path
            logger.info(f"MIDI exported: {midi_path}")
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

    # Lead Sheet PDF (text fallback)
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

    # Audio formats — delegate to render pipeline
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
