import pytest
pytestmark = pytest.mark.service

"""
Tests for audio/export_engine.py

Actual signatures:
  export_midi(tracks, bpm=120, output_path=None, quantize=True, subdivisions=8) → bytes
  export_musicxml(chords, melody_notes, key="C", mode="major", bpm=120, time_sig=(4,4), output_path=None) → str
  run_export(project_id, analysis, arrangement, formats, output_dir, progress_callback=None) → Dict[str, str]
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MOCK_TRACKS = [
    {
        "id": "track-violin",
        "instrument": "violin",
        "role": "melody",
        "channel": 0,
        "notes": [
            {"time": 0.0, "pitch": 60, "duration": 0.5, "velocity": 80},
            {"time": 0.5, "pitch": 62, "duration": 0.5, "velocity": 75},
            {"time": 1.0, "pitch": 64, "duration": 1.0, "velocity": 85},
        ],
    },
    {
        "id": "track-bass",
        "instrument": "bass",
        "role": "bass",
        "channel": 1,
        "notes": [
            {"time": 0.0, "pitch": 36, "duration": 1.0, "velocity": 90},
            {"time": 1.0, "pitch": 38, "duration": 1.0, "velocity": 85},
        ],
    },
]

MOCK_CHORDS = [
    {"time": 0.0, "chord": "C", "duration": 2.0},
    {"time": 2.0, "chord": "G", "duration": 2.0},
    {"time": 4.0, "chord": "Am", "duration": 2.0},
    {"time": 6.0, "chord": "F", "duration": 2.0},
]

MOCK_MELODY = [
    {"time": 0.0, "pitch": 60, "duration": 0.5},
    {"time": 0.5, "pitch": 62, "duration": 0.5},
    {"time": 1.0, "pitch": 64, "duration": 1.0},
]

MOCK_ANALYSIS = {
    "rhythm": {"bpm": 120, "timeSignatureNumerator": 4, "timeSignatureDenominator": 4},
    "key": {"globalKey": "C", "mode": "major"},
    "chords": {"chords": MOCK_CHORDS},
    "melody": {"notes": MOCK_MELODY},
    "sections": [],
}

MOCK_ARRANGEMENT = {
    "styleId": "hasidic-wedding",
    "bpm": 120,
    "key": "C",
    "mode": "major",
    "tracks": MOCK_TRACKS,
    "sections": [
        {"label": "intro", "start": 0.0, "end": 4.0},
        {"label": "verse", "start": 4.0, "end": 16.0},
    ],
    "chords": MOCK_CHORDS,
}


class TestExportEngineImport:
    def test_import_succeeds(self):
        import audio.export_engine as ee
        assert ee is not None

    def test_has_export_midi(self):
        import audio.export_engine as ee
        assert hasattr(ee, "export_midi") and callable(ee.export_midi)

    def test_has_export_musicxml(self):
        import audio.export_engine as ee
        assert hasattr(ee, "export_musicxml") and callable(ee.export_musicxml)

    def test_has_run_export(self):
        import audio.export_engine as ee
        assert hasattr(ee, "run_export") and callable(ee.run_export)

    def test_has_export_lead_sheet(self):
        import audio.export_engine as ee
        assert hasattr(ee, "export_lead_sheet") and callable(ee.export_lead_sheet)


class TestMidiExport:
    def test_returns_bytes(self):
        from audio.export_engine import export_midi
        result = export_midi(MOCK_TRACKS, bpm=120.0)
        assert isinstance(result, (bytes, bytearray))

    def test_nonempty(self):
        from audio.export_engine import export_midi
        result = export_midi(MOCK_TRACKS, bpm=120.0)
        assert len(result) > 0

    def test_starts_with_mthd(self):
        from audio.export_engine import export_midi
        data = export_midi(MOCK_TRACKS, bpm=120.0)
        assert data[:4] == b"MThd", "Not a valid MIDI file"

    def test_empty_tracks(self):
        from audio.export_engine import export_midi
        result = export_midi([], bpm=120.0)
        assert isinstance(result, (bytes, bytearray))

    def test_single_track(self):
        from audio.export_engine import export_midi
        result = export_midi([MOCK_TRACKS[0]], bpm=120.0)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 0

    def test_quantize_false(self):
        from audio.export_engine import export_midi
        result = export_midi(MOCK_TRACKS, bpm=120.0, quantize=False)
        assert isinstance(result, (bytes, bytearray))

    def test_high_bpm(self):
        from audio.export_engine import export_midi
        result = export_midi(MOCK_TRACKS, bpm=200.0)
        assert isinstance(result, (bytes, bytearray))

    def test_output_path(self, tmp_path):
        from audio.export_engine import export_midi
        outfile = str(tmp_path / "test.mid")
        result = export_midi(MOCK_TRACKS, bpm=120.0, output_path=outfile)
        assert os.path.exists(outfile)


class TestMusicXmlExport:
    def test_returns_string(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml(MOCK_CHORDS, MOCK_MELODY)
        assert isinstance(result, str)

    def test_nonempty(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml(MOCK_CHORDS, MOCK_MELODY)
        assert len(result) > 0

    def test_contains_xml(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml(MOCK_CHORDS, MOCK_MELODY)
        assert "<" in result and ">" in result

    def test_key_param(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml(MOCK_CHORDS, MOCK_MELODY, key="G", mode="major")
        assert isinstance(result, str)

    def test_minor_mode(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml(MOCK_CHORDS, MOCK_MELODY, key="A", mode="minor")
        assert isinstance(result, str)

    def test_empty_chords(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml([], MOCK_MELODY)
        assert isinstance(result, str)

    def test_empty_melody(self):
        from audio.export_engine import export_musicxml
        result = export_musicxml(MOCK_CHORDS, [])
        assert isinstance(result, str)

    def test_output_path(self, tmp_path):
        from audio.export_engine import export_musicxml
        outfile = str(tmp_path / "test.musicxml")
        export_musicxml(MOCK_CHORDS, MOCK_MELODY, output_path=outfile)
        assert os.path.exists(outfile)


class TestRunExport:
    def test_returns_dict(self, tmp_path):
        from audio.export_engine import run_export
        result = run_export(1, MOCK_ANALYSIS, MOCK_ARRANGEMENT, ["midi"], str(tmp_path))
        assert isinstance(result, dict)

    def test_midi_creates_file(self, tmp_path):
        from audio.export_engine import run_export
        run_export(1, MOCK_ANALYSIS, MOCK_ARRANGEMENT, ["midi"], str(tmp_path))
        midi_files = list(tmp_path.glob("*.mid")) + list(tmp_path.glob("*.midi"))
        assert len(midi_files) >= 1

    def test_musicxml_format(self, tmp_path):
        from audio.export_engine import run_export
        result = run_export(1, MOCK_ANALYSIS, MOCK_ARRANGEMENT, ["musicxml"], str(tmp_path))
        assert isinstance(result, dict)

    def test_multiple_formats(self, tmp_path):
        from audio.export_engine import run_export
        result = run_export(1, MOCK_ANALYSIS, MOCK_ARRANGEMENT, ["midi", "musicxml"], str(tmp_path))
        assert isinstance(result, dict)

    def test_empty_formats(self, tmp_path):
        from audio.export_engine import run_export
        result = run_export(1, MOCK_ANALYSIS, MOCK_ARRANGEMENT, [], str(tmp_path))
        assert isinstance(result, dict)


class TestNoteValidation:
    def test_pitches_in_midi_range(self):
        for track in MOCK_TRACKS:
            for note in track["notes"]:
                assert 0 <= note["pitch"] <= 127

    def test_velocities_in_range(self):
        for track in MOCK_TRACKS:
            for note in track["notes"]:
                assert 1 <= note.get("velocity", 64) <= 127

    def test_durations_positive(self):
        for track in MOCK_TRACKS:
            for note in track["notes"]:
                assert note["duration"] > 0

    def test_note_times_non_negative(self):
        for track in MOCK_TRACKS:
            for note in track["notes"]:
                assert note["time"] >= 0
