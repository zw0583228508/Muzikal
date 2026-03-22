"""
STEP 17: Tests for the rhythm analysis module.
Run: python3 -m pytest tests/test_rhythm.py -v
"""

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "artifacts", "music-ai-backend"))


def make_click_track(bpm: float = 120.0, duration: float = 10.0, sr: int = 22050) -> np.ndarray:
    """Generate a simple click track at a known BPM."""
    beat_period = sr * 60.0 / bpm
    y = np.zeros(int(sr * duration))
    beat_idx = 0
    while beat_idx < len(y):
        # Short click burst
        end = min(beat_idx + 441, len(y))  # 20ms click
        y[beat_idx:end] = np.sin(np.linspace(0, np.pi * 10, end - beat_idx))
        beat_idx += int(beat_period)
    return y


class TestAnalyzeRhythm:
    def test_returns_required_keys(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        for key in ["bpm", "timeSignatureNumerator", "timeSignatureDenominator", "beatGrid", "downbeats", "confidence", "warnings"]:
            assert key in result, f"Missing: {key}"

    def test_bpm_in_range(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        assert 40 <= result["bpm"] <= 220

    def test_confidence_in_range(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_beat_grid_is_sorted(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        bg = result["beatGrid"]
        assert bg == sorted(bg)

    def test_warnings_is_list(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        assert isinstance(result["warnings"], list)

    def test_time_signature_common_values(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        assert result["timeSignatureNumerator"] in [2, 3, 4, 6, 8]
        assert result["timeSignatureDenominator"] in [4, 8]

    def test_alternatives_present(self):
        from audio.rhythm import analyze_rhythm
        y = make_click_track(bpm=120.0, duration=15.0)
        result = analyze_rhythm(y, sr=22050)
        assert "alternatives" in result
        assert len(result["alternatives"]) >= 1
