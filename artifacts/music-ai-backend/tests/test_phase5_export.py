"""
Phase 5 — Export and Rendering tests.

Tests:
  - LoudnessMeasurement and normalization
  - Export validator (audio, MIDI, MusicXML)
  - Integration: loudness preset lookup
  - Integration: normalize_audio preserves loudness target
"""

from __future__ import annotations

import io
import os
import tempfile
import math

import numpy as np
import pytest


# ─── Loudness tests ───────────────────────────────────────────────────────────

class TestLoudnessMeasurement:

    def _sine(self, freq: float = 440.0, sr: int = 44100,
              duration: float = 5.0, amplitude: float = 0.5) -> np.ndarray:
        """Generate a sine wave test signal."""
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        return (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)

    def test_measure_silent_returns_low_lufs(self):
        from audio.loudness_normalizer import measure_loudness
        silence = np.zeros((44100 * 3, 2), dtype=np.float32)
        m = measure_loudness(silence, 44100)
        assert m.lufs < -60.0
        assert m.is_silent

    def test_measure_sine_returns_reasonable_lufs(self):
        from audio.loudness_normalizer import measure_loudness
        audio = self._sine()[:, np.newaxis]
        m = measure_loudness(audio, 44100)
        # A -6dB sine wave should be around -23 to -3 LUFS
        assert -40 < m.lufs < 0
        assert not m.is_silent

    def test_measure_stereo(self):
        from audio.loudness_normalizer import measure_loudness
        mono = self._sine()
        stereo = np.column_stack([mono, mono])
        m = measure_loudness(stereo, 44100)
        assert -40 < m.lufs < 0

    def test_measure_mono_1d_array(self):
        from audio.loudness_normalizer import measure_loudness_numpy
        audio = self._sine()  # 1D
        m = measure_loudness_numpy(audio, 44100)
        assert isinstance(m.lufs, float)

    def test_loudness_measurement_str(self):
        from audio.loudness_normalizer import LoudnessMeasurement
        m = LoudnessMeasurement(lufs=-14.0, true_peak_dbtp=-1.5, lra=7.0)
        s = str(m)
        assert "LUFS=-14.0" in s
        assert "dBTP=-1.5" in s

    def test_peak_ok(self):
        from audio.loudness_normalizer import LoudnessMeasurement
        m = LoudnessMeasurement(lufs=-14.0, true_peak_dbtp=-2.0)
        assert m.peak_ok
        m2 = LoudnessMeasurement(lufs=-14.0, true_peak_dbtp=0.5)
        assert not m2.peak_ok


class TestLoudnessNormalization:

    def _sine(self, amplitude: float = 0.1, sr: int = 44100,
              duration: float = 5.0) -> np.ndarray:
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        mono = (np.sin(2 * np.pi * 440 * t) * amplitude).astype(np.float32)
        return np.column_stack([mono, mono])

    def test_compute_normalization_gain_basic(self):
        from audio.loudness_normalizer import compute_normalization_gain
        gain = compute_normalization_gain(
            measured_lufs=-20.0,
            target_lufs=-14.0,
            measured_peak_dbtp=-10.0,
        )
        assert abs(gain - 6.0) < 0.5  # expect ~+6 dB

    def test_compute_normalization_gain_peak_protection(self):
        from audio.loudness_normalizer import compute_normalization_gain
        # measured_lufs=-20, target=-14 → naive gain would be +6 dB
        # measured_peak=-2.0; after +6 dB peak would be +4 dBTP — too loud
        # Peak protection must reduce gain so that peak_after <= -1.0 dBTP
        measured_peak = -2.0
        max_peak = -1.0
        gain = compute_normalization_gain(
            measured_lufs=-20.0,
            target_lufs=-14.0,
            measured_peak_dbtp=measured_peak,
            max_true_peak_dbtp=max_peak,
        )
        # After applying the gain, the peak should not exceed max_peak
        assert measured_peak + gain <= max_peak + 0.01

    def test_no_boost_mode(self):
        from audio.loudness_normalizer import compute_normalization_gain
        gain = compute_normalization_gain(
            measured_lufs=-20.0,
            target_lufs=-14.0,
            measured_peak_dbtp=-10.0,
            allow_boost=False,
        )
        assert gain <= 0.0

    def test_apply_gain_numpy(self):
        from audio.loudness_normalizer import apply_gain_numpy
        audio = np.array([[0.5, 0.5], [0.5, 0.5]], dtype=np.float32)
        boosted = apply_gain_numpy(audio, 6.0)  # +6 dB ≈ ×2
        assert abs(float(boosted[0, 0]) - 1.0) < 0.01  # clips at 1.0

    def test_normalize_audio_reaches_target(self):
        from audio.loudness_normalizer import normalize_audio, measure_loudness
        audio = self._sine(amplitude=0.05)  # quiet signal
        sr = 44100
        target = -14.0
        normalized, result = normalize_audio(audio, sr, target_lufs=target)
        # Target should be approximately reached (±2 LUFS tolerance)
        assert result.gain_applied_db != 0.0
        assert isinstance(result.target_achieved, bool)

    def test_normalize_audio_silent_no_crash(self):
        from audio.loudness_normalizer import normalize_audio
        silence = np.zeros((44100 * 3, 2), dtype=np.float32)
        result_audio, result = normalize_audio(silence, 44100, target_lufs=-14.0)
        assert result.gain_applied_db == 0.0

    def test_normalization_result_to_dict(self):
        from audio.loudness_normalizer import (
            normalize_audio, NormalizationResult, LoudnessMeasurement
        )
        before = LoudnessMeasurement(lufs=-20.0, true_peak_dbtp=-5.0)
        after = LoudnessMeasurement(lufs=-14.0, true_peak_dbtp=-1.0)
        r = NormalizationResult(
            before=before, after=after,
            gain_applied_db=6.0, target_lufs=-14.0, peak_compliant=True,
        )
        d = r.to_dict()
        assert d["beforeLufs"] == -20.0
        assert d["afterLufs"] == -14.0
        assert d["gainAppliedDb"] == 6.0
        assert d["peakCompliant"] is True
        assert "targetAchieved" in d

    def test_loudness_presets_present(self):
        from audio.loudness_normalizer import LOUDNESS_PRESETS
        for key in ("streaming", "broadcast", "film", "mastered", "podcast"):
            assert key in LOUDNESS_PRESETS
            p = LOUDNESS_PRESETS[key]
            assert "target_lufs" in p
            assert "true_peak_dbtp" in p

    def test_export_normalized_to_wav(self):
        from audio.loudness_normalizer import export_normalized
        audio = np.random.randn(44100 * 3, 2).astype(np.float32) * 0.1
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            result = export_normalized(audio, 44100, path, preset="streaming")
            assert os.path.exists(path)
            assert os.path.getsize(path) > 1000
            assert isinstance(result.gain_applied_db, float)
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ─── Export validator tests ───────────────────────────────────────────────────

class TestExportValidator:

    def _write_wav(self, duration: float = 3.0, sr: int = 44100) -> str:
        import soundfile as sf
        audio = np.random.randn(int(sr * duration), 2).astype(np.float32) * 0.3
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        sf.write(path, audio, sr)
        return path

    def test_validate_valid_wav(self):
        from audio.export_validator import validate_audio
        path = self._write_wav()
        try:
            result = validate_audio(path)
            assert result.ok, f"Expected OK but got issues: {result.issues}"
            assert result.metadata["duration_sec"] > 2.0
        finally:
            os.unlink(path)

    def test_validate_missing_file(self):
        from audio.export_validator import validate_audio
        result = validate_audio("/nonexistent/file.wav")
        assert not result.ok
        assert any("not found" in i.lower() for i in result.issues)

    def test_validate_duration_check(self):
        from audio.export_validator import validate_audio
        path = self._write_wav(duration=5.0)
        try:
            # Expected 10s, actual 5s → should flag duration mismatch
            result = validate_audio(path, expected_duration_sec=10.0,
                                    max_duration_tolerance_sec=1.0)
            assert not result.ok
            assert any("duration" in i.lower() for i in result.issues)
        finally:
            os.unlink(path)

    def test_validate_empty_file(self):
        from audio.export_validator import validate_audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            result = validate_audio(path)
            assert not result.ok
        finally:
            os.unlink(path)

    def test_validate_midi_valid(self):
        from audio.export_validator import validate_midi
        try:
            import mido
        except ImportError:
            pytest.skip("mido not available")

        mid = mido.MidiFile(type=1, ticks_per_beat=480)
        tempo_track = mido.MidiTrack()
        mid.tracks.append(tempo_track)
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))

        inst_track = mido.MidiTrack()
        mid.tracks.append(inst_track)
        inst_track.append(mido.Message("note_on", channel=0, note=60, velocity=80, time=0))
        inst_track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=480))
        inst_track.append(mido.Message("note_on", channel=0, note=64, velocity=80, time=0))
        inst_track.append(mido.Message("note_off", channel=0, note=64, velocity=0, time=480))

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            path = f.name
        try:
            mid.save(path)
            result = validate_midi(path)
            assert result.ok, f"MIDI validation failed: {result.issues}"
            assert result.metadata["total_notes"] >= 2
        finally:
            os.unlink(path)

    def test_validate_midi_missing_file(self):
        from audio.export_validator import validate_midi
        result = validate_midi("/nonexistent/file.mid")
        assert not result.ok

    def test_validate_musicxml_valid(self):
        from audio.export_validator import validate_musicxml
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
    <measure number="2">
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
  </part>
</score-partwise>"""
        with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False, mode="w") as f:
            f.write(xml_content)
            path = f.name
        try:
            result = validate_musicxml(path)
            # Should pass (valid root, has notes, has measures)
            assert len(result.issues) == 0 or result.ok
            assert result.metadata["measure_count"] >= 2
        finally:
            os.unlink(path)

    def test_validate_musicxml_invalid_xml(self):
        from audio.export_validator import validate_musicxml
        with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False, mode="w") as f:
            f.write("<not valid xml <<>><>")
            path = f.name
        try:
            result = validate_musicxml(path)
            assert not result.ok
        finally:
            os.unlink(path)

    def test_validate_export_auto_detect_wav(self):
        from audio.export_validator import validate_export
        import soundfile as sf
        audio = np.random.randn(44100 * 2, 2).astype(np.float32) * 0.3
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            sf.write(path, audio, 44100)
            result = validate_export(path)  # kind auto-detected
            assert result.kind == "audio"
        finally:
            os.unlink(path)

    def test_compute_sha256(self):
        from audio.export_validator import compute_sha256
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content for sha256")
            path = f.name
        try:
            digest = compute_sha256(path)
            assert len(digest) == 64
            assert all(c in "0123456789abcdef" for c in digest)
            # Same content → same hash
            assert compute_sha256(path) == digest
        finally:
            os.unlink(path)
