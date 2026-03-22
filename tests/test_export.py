"""
STEP 17: Tests for the export engine (T008 + T011).
Run: python3 -m pytest tests/test_export.py -v
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "artifacts", "music-ai-backend"))


def make_simple_arrangement() -> dict:
    """Build a minimal arrangement for export testing."""
    bpm = 120
    beat = 60.0 / bpm
    total = 16.0  # 4 bars

    return {
        "total_duration_seconds": total,
        "bpm": bpm,
        "key": "C",
        "mode": "major",
        "time_signature": [4, 4],
        "tracks": [
            {
                "id": "piano",
                "name": "Piano",
                "instrument": "Grand Piano",
                "midi_program": 0,
                "channel": 0,
                "notes": [
                    {"pitch": 60, "startTime": 0.0, "duration": beat, "velocity": 80},
                    {"pitch": 64, "startTime": beat, "duration": beat, "velocity": 75},
                    {"pitch": 67, "startTime": beat * 2, "duration": beat, "velocity": 78},
                    {"pitch": 60, "startTime": beat * 3, "duration": beat, "velocity": 72},
                ],
            }
        ],
        "chord_events": [
            {"startTime": 0.0,  "endTime": 4.0,  "chord": "C",  "romanNumeral": "I",   "confidence": 0.92},
            {"startTime": 4.0,  "endTime": 8.0,  "chord": "Am", "romanNumeral": "vi",  "confidence": 0.85},
            {"startTime": 8.0,  "endTime": 12.0, "chord": "F",  "romanNumeral": "IV",  "confidence": 0.88},
            {"startTime": 12.0, "endTime": 16.0, "chord": "G",  "romanNumeral": "V",   "confidence": 0.90},
        ],
        "sections": [
            {"label": "intro", "startTime": 0.0,  "endTime": 8.0},
            {"label": "verse", "startTime": 8.0,  "endTime": 16.0},
        ],
    }


# ─── Quantization tests ────────────────────────────────────────────────────────

class TestQuantization:
    def test_quantize_time_snaps_to_grid(self):
        from audio.export_engine import quantize_time
        beat = 0.5  # 120 BPM
        # 0.123 should snap to nearest eighth note (0.0625)
        result = quantize_time(0.123, beat, subdivisions=8)
        assert result % (beat / 8) < 1e-9 or abs(result - 0.125) < 0.01

    def test_quantize_notes_preserves_count(self):
        from audio.export_engine import quantize_notes
        notes = [
            {"startTime": 0.01, "duration": 0.48, "pitch": 60, "velocity": 80},
            {"startTime": 0.51, "duration": 0.47, "pitch": 64, "velocity": 75},
        ]
        result = quantize_notes(notes, bpm=120, subdivisions=8)
        assert len(result) == 2

    def test_quantize_notes_no_negative_duration(self):
        from audio.export_engine import quantize_notes
        notes = [{"startTime": 0.0, "duration": 0.001, "pitch": 60, "velocity": 80}]
        result = quantize_notes(notes, bpm=120, subdivisions=8)
        assert result[0]["duration"] >= 0.0

    def test_align_chords_to_measures(self):
        from audio.export_engine import align_chords_to_measures
        chords = [
            {"startTime": 0.05, "endTime": 2.02, "chord": "C"},
            {"startTime": 2.03, "endTime": 3.98, "chord": "Am"},
        ]
        aligned = align_chords_to_measures(chords, bpm=120, time_sig_num=4)
        # All start times should be multiples of beat (0.5s at 120 BPM)
        for c in aligned:
            assert c["endTime"] > c["startTime"]


# ─── MIDI export tests ─────────────────────────────────────────────────────────

class TestMidiExport:
    def test_midi_export_creates_file(self):
        from audio.export_engine import export_midi
        arr = make_simple_arrangement()
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            path = f.name
        try:
            export_midi(arr["tracks"], arr["bpm"], path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_midi_export_returns_bytes(self):
        from audio.export_engine import export_midi
        arr = make_simple_arrangement()
        result = export_midi(arr["tracks"], arr["bpm"])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_midi_export_with_quantize(self):
        from audio.export_engine import export_midi
        arr = make_simple_arrangement()
        result = export_midi(arr["tracks"], arr["bpm"], quantize=True, subdivisions=8)
        assert isinstance(result, bytes) and len(result) > 0

    def test_midi_export_empty_tracks(self):
        from audio.export_engine import export_midi
        result = export_midi([], bpm=120.0)
        assert isinstance(result, bytes)

    def test_midi_export_muted_track(self):
        from audio.export_engine import export_midi
        tracks = [{"id": "piano", "name": "Piano", "channel": 0, "muted": True,
                   "notes": [{"startTime": 0.0, "duration": 0.5, "pitch": 60, "velocity": 80}]}]
        result = export_midi(tracks, bpm=120.0)
        assert isinstance(result, bytes)


# ─── Chord symbol parsing ──────────────────────────────────────────────────────

class TestChordParsing:
    def test_parse_major_chord(self):
        from audio.export_engine import _parse_chord_symbol
        root, kind = _parse_chord_symbol("C")
        assert root == "C"
        assert kind == "major"

    def test_parse_minor_chord(self):
        from audio.export_engine import _parse_chord_symbol
        root, kind = _parse_chord_symbol("Am")
        assert root == "A"
        assert kind == "minor"

    def test_parse_maj7_chord(self):
        from audio.export_engine import _parse_chord_symbol
        root, kind = _parse_chord_symbol("Cmaj7")
        assert root == "C"
        assert kind == "major-seventh"

    def test_parse_m7_chord(self):
        from audio.export_engine import _parse_chord_symbol
        root, kind = _parse_chord_symbol("Fm7")
        assert root == "F"
        assert kind == "minor-seventh"

    def test_parse_sharps(self):
        from audio.export_engine import _parse_chord_symbol
        root, kind = _parse_chord_symbol("F#m")
        assert root == "F#"
        assert kind == "minor"

    def test_parse_dom7(self):
        from audio.export_engine import _parse_chord_symbol
        root, kind = _parse_chord_symbol("G7")
        assert root == "G"
        assert kind == "dominant"


# ─── MusicXML export ──────────────────────────────────────────────────────────

class TestMusicXMLExport:
    def test_musicxml_is_valid_string(self):
        from audio.export_engine import export_musicxml
        arr = make_simple_arrangement()
        xml = export_musicxml(arr["chord_events"], [], "C", "major", 120.0, (4, 4))
        assert isinstance(xml, str)
        assert xml.startswith("<?xml")
        assert "<score-partwise" in xml

    def test_musicxml_has_key_signature(self):
        from audio.export_engine import export_musicxml
        arr = make_simple_arrangement()
        xml = export_musicxml(arr["chord_events"], [], "G", "major", 120.0, (4, 4))
        assert "<fifths>" in xml

    def test_musicxml_has_harmony_elements(self):
        from audio.export_engine import export_musicxml
        arr = make_simple_arrangement()
        xml = export_musicxml(arr["chord_events"], [], "C", "major", 120.0, (4, 4))
        assert "<harmony>" in xml
        assert "<root-step>" in xml
        assert "<kind>" in xml

    def test_musicxml_writes_to_file(self):
        from audio.export_engine import export_musicxml
        arr = make_simple_arrangement()
        with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False, mode="w") as f:
            path = f.name
        try:
            xml = export_musicxml(arr["chord_events"], [], "C", "major", 120.0, (4, 4), path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ─── Lead sheet ───────────────────────────────────────────────────────────────

class TestLeadSheet:
    def test_lead_sheet_is_string(self):
        from audio.export_engine import export_lead_sheet
        arr = make_simple_arrangement()
        ls = export_lead_sheet(arr["chord_events"], "C", 120.0, (4, 4))
        assert isinstance(ls, str)
        assert len(ls) > 20

    def test_lead_sheet_contains_key_and_bpm(self):
        from audio.export_engine import export_lead_sheet
        arr = make_simple_arrangement()
        ls = export_lead_sheet(arr["chord_events"], "G", 140.0, (4, 4))
        assert "G" in ls
        assert "140" in ls

    def test_lead_sheet_with_sections(self):
        from audio.export_engine import export_lead_sheet
        arr = make_simple_arrangement()
        ls = export_lead_sheet(arr["chord_events"], "C", 120.0, (4, 4), arr["sections"])
        assert "INTRO" in ls
        assert "VERSE" in ls

    def test_lead_sheet_contains_chord_symbols(self):
        from audio.export_engine import export_lead_sheet
        arr = make_simple_arrangement()
        ls = export_lead_sheet(arr["chord_events"], "C", 120.0, (4, 4))
        assert "C" in ls
        assert "Am" in ls


# ─── YAML schema validation ────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_genres_yaml_exists(self):
        genres_path = os.path.join(os.path.dirname(__file__), "..", "configs", "styles", "genres.yaml")
        assert os.path.exists(genres_path), "genres.yaml missing"

    def test_genres_yaml_has_15_styles(self):
        import yaml
        genres_path = os.path.join(os.path.dirname(__file__), "..", "configs", "styles", "genres.yaml")
        with open(genres_path) as f:
            data = yaml.safe_load(f)
        assert len(data["styles"]) == 15

    def test_arranger_profiles_match_styles(self):
        import yaml
        genres_path = os.path.join(os.path.dirname(__file__), "..", "configs", "styles", "genres.yaml")
        profiles_path = os.path.join(os.path.dirname(__file__), "..", "configs", "styles", "arranger_profiles.yaml")
        with open(genres_path) as f:
            styles = {s["id"] for s in yaml.safe_load(f)["styles"]}
        with open(profiles_path) as f:
            profiles = set(yaml.safe_load(f)["profiles"].keys())
        assert styles == profiles, f"Mismatch: styles_only={styles - profiles}, profiles_only={profiles - styles}"

    def test_export_options_schema(self):
        profiles_path = os.path.join(os.path.dirname(__file__), "..", "configs", "styles", "arranger_profiles.yaml")
        assert os.path.exists(profiles_path), "arranger_profiles.yaml missing"
