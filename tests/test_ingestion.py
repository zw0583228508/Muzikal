"""
STEP 17: Tests for the audio ingestion module.
Run: python3 -m pytest tests/test_ingestion.py -v
"""

import os
import sys
import tempfile
import numpy as np
import pytest

WORKSPACE = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGES = os.path.join(WORKSPACE, "packages")
for p in [WORKSPACE, PACKAGES]:
    if p not in sys.path:
        sys.path.insert(0, p)


def generate_test_wav(duration: float = 3.0, sr: int = 22050, filename: str = None) -> str:
    """Generate a synthetic WAV file for testing."""
    import soundfile as sf
    t = np.linspace(0, duration, int(sr * duration))
    # 440Hz sine wave with some harmonics
    y = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.25 * np.sin(2 * np.pi * 880 * t)
    if filename is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        filename = tmp.name
        tmp.close()
    sf.write(filename, y, sr)
    return filename


class TestValidation:
    def test_file_not_found_raises(self):
        from audio_core.ingestion import validate_file
        with pytest.raises(ValueError, match="not found"):
            validate_file("/nonexistent/path/to/file.wav")

    def test_empty_file_raises(self, tmp_path):
        from audio_core.ingestion import validate_file
        empty = tmp_path / "empty.wav"
        empty.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            validate_file(str(empty))

    def test_unsupported_extension_raises(self, tmp_path):
        from audio_core.ingestion import validate_file
        bad = tmp_path / "test.xyz"
        bad.write_bytes(b"some data")
        with pytest.raises(ValueError, match="Unsupported format"):
            validate_file(str(bad))

    def test_valid_wav_passes(self):
        from audio_core.ingestion import validate_file
        path = generate_test_wav()
        try:
            validate_file(path)  # Should not raise
        finally:
            os.unlink(path)


class TestChecksum:
    def test_same_file_same_hash(self):
        from audio_core.ingestion import compute_checksum
        path = generate_test_wav()
        try:
            h1 = compute_checksum(path)
            h2 = compute_checksum(path)
            assert h1 == h2
        finally:
            os.unlink(path)

    def test_different_files_different_hash(self):
        from audio_core.ingestion import compute_checksum
        path1 = generate_test_wav(duration=2.0)
        path2 = generate_test_wav(duration=3.0)
        try:
            h1 = compute_checksum(path1)
            h2 = compute_checksum(path2)
            assert h1 != h2
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_hash_is_64_chars(self):
        from audio_core.ingestion import compute_checksum
        path = generate_test_wav()
        try:
            h = compute_checksum(path)
            assert len(h) == 64  # SHA-256 hex string
        finally:
            os.unlink(path)


class TestLoadAndNormalize:
    def test_output_is_normalized(self):
        from audio_core.ingestion import load_and_normalize
        path = generate_test_wav()
        try:
            y, sr = load_and_normalize(path)
            assert np.max(np.abs(y)) <= 1.0 + 1e-6
        finally:
            os.unlink(path)

    def test_output_is_mono(self):
        from audio_core.ingestion import load_and_normalize
        path = generate_test_wav()
        try:
            y, sr = load_and_normalize(path, mono=True)
            assert y.ndim == 1
        finally:
            os.unlink(path)

    def test_sample_rate_is_target(self):
        from audio_core.ingestion import load_and_normalize
        path = generate_test_wav(sr=44100)
        try:
            y, sr = load_and_normalize(path, target_sr=22050)
            assert sr == 22050
        finally:
            os.unlink(path)


class TestWaveform:
    def test_waveform_length(self):
        from audio_core.ingestion import generate_waveform
        y = np.random.rand(22050 * 10)
        waveform = generate_waveform(y, num_points=500)
        assert len(waveform) == 500

    def test_waveform_values_in_range(self):
        from audio_core.ingestion import generate_waveform
        y = np.random.rand(22050 * 5) * 2 - 1  # -1 to 1
        waveform = generate_waveform(y)
        for val in waveform:
            assert 0.0 <= val <= 1.0001


class TestFullIngestion:
    def test_ingest_returns_required_keys(self):
        from audio_core.ingestion import ingest_audio
        path = generate_test_wav(duration=5.0)
        try:
            result = ingest_audio(path)
            for key in ["filePath", "fileHash", "metadata", "duration", "sampleRate", "waveform", "warnings"]:
                assert key in result, f"Missing key: {key}"
        finally:
            os.unlink(path)

    def test_ingest_duration_is_positive(self):
        from audio_core.ingestion import ingest_audio
        path = generate_test_wav(duration=5.0)
        try:
            result = ingest_audio(path)
            assert result["duration"] > 0
        finally:
            os.unlink(path)

    def test_ingest_hash_is_consistent(self):
        from audio_core.ingestion import ingest_audio
        path = generate_test_wav(duration=3.0)
        try:
            r1 = ingest_audio(path)
            r2 = ingest_audio(path)
            assert r1["fileHash"] == r2["fileHash"]
        finally:
            os.unlink(path)

    def test_ingest_audio_array_present(self):
        from audio_core.ingestion import ingest_audio
        path = generate_test_wav(duration=3.0)
        try:
            result = ingest_audio(path)
            assert result["audio"] is not None
            assert isinstance(result["audio"], np.ndarray)
            assert len(result["audio"]) > 0
        finally:
            os.unlink(path)
