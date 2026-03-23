import pytest
pytestmark = pytest.mark.unit

"""
Tests for audio/rhythm.py — BPM detection, time signature, beat grid.
"""
import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audio.rhythm import analyze_rhythm


def _click_track(bpm: float, sr: int = 22050, dur: float = 6.0) -> np.ndarray:
    hop = int(sr * 60.0 / bpm)
    y = np.zeros(int(sr * dur), dtype=np.float32)
    for pos in range(0, len(y) - sr // 4, hop):
        click_len = min(int(sr * 0.01), len(y) - pos)
        y[pos:pos + click_len] = np.linspace(1.0, 0.0, click_len)
    return y


def _white_noise(sr: int = 22050, dur: float = 5.0) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.standard_normal(int(sr * dur)).astype(np.float32) * 0.1


class TestAnalyzeRhythm:
    def test_returns_dict(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert isinstance(result, dict)

    def test_has_bpm(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert "bpm" in result

    def test_has_time_signature_numerator(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert "timeSignatureNumerator" in result

    def test_has_time_signature_denominator(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert "timeSignatureDenominator" in result

    def test_bpm_is_numeric(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert isinstance(result["bpm"], (int, float))

    def test_bpm_in_plausible_range(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert 40 <= result["bpm"] <= 250

    def test_time_sig_numerator_positive(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        assert result["timeSignatureNumerator"] > 0

    def test_time_sig_denominator_power_of_two(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        d = result["timeSignatureDenominator"]
        assert d in (2, 4, 8, 16)

    def test_white_noise_fallback(self):
        y = _white_noise()
        result = analyze_rhythm(y, 22050)
        assert "bpm" in result
        assert 40 <= result["bpm"] <= 250

    def test_slow_bpm(self):
        y = _click_track(60)
        result = analyze_rhythm(y, 22050)
        assert 40 <= result["bpm"] <= 250

    def test_fast_bpm(self):
        y = _click_track(180)
        result = analyze_rhythm(y, 22050)
        assert 40 <= result["bpm"] <= 250

    def test_beat_grid_if_present(self):
        y = _click_track(120, dur=8.0)
        result = analyze_rhythm(y, 22050)
        if "beatGrid" in result:
            assert isinstance(result["beatGrid"], list)

    def test_confidence_if_present(self):
        y = _click_track(120, dur=8.0)
        result = analyze_rhythm(y, 22050)
        if "confidence" in result:
            assert 0.0 <= result["confidence"] <= 1.0

    def test_no_exception_on_silence(self):
        y = np.zeros(22050 * 3, dtype=np.float32)
        try:
            result = analyze_rhythm(y, 22050)
            assert "bpm" in result
        except Exception:
            pytest.fail("analyze_rhythm raised an exception on silence")

    def test_alternatives_if_present(self):
        y = _click_track(120)
        result = analyze_rhythm(y, 22050)
        if "alternatives" in result:
            assert isinstance(result["alternatives"], list)
