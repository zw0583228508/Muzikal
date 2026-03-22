"""
Tests for the vocal analysis module.
Covers: confidence, warnings, alternatives, vocal range (T004, T011).
Run: python3 -m pytest tests/test_vocal.py -v
"""

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "artifacts", "music-ai-backend"))


def make_sine(freq: float = 440.0, duration: float = 3.0, sr: int = 22050, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration))
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def make_silence(duration: float = 2.0, sr: int = 22050) -> np.ndarray:
    return np.zeros(int(sr * duration), dtype=np.float32)


class TestAnalyzeVocals:
    def test_returns_required_keys(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        for key in ("notes", "vibrato", "phrases", "vocal_range", "voiced_ratio",
                    "confidence", "warnings", "alternatives", "model"):
            assert key in result, f"Missing key: {key}"

    def test_confidence_is_float_between_0_and_1(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_warnings_is_list(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        assert isinstance(result["warnings"], list)

    def test_no_vocal_path_adds_warning(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        has_mix_warning = any("mix" in w.lower() or "stem" in w.lower() for w in result["warnings"])
        assert has_mix_warning, f"Expected 'no vocal stem' warning, got: {result['warnings']}"

    def test_model_field_is_pyin(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        assert "pyin" in result["model"].lower()

    def test_alternatives_is_list(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        assert isinstance(result["alternatives"], list)

    def test_silence_gives_low_confidence(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_silence(duration=2.0)
        result = analyze_vocals(None, y, 22050)
        assert result["confidence"] <= 0.5, f"Expected low confidence on silence, got {result['confidence']}"

    def test_vibrato_has_detected_flag(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        assert "detected" in result["vibrato"]
        assert isinstance(result["vibrato"]["detected"], bool)

    def test_voiced_ratio_between_0_and_1(self):
        from audio.vocal_analysis import analyze_vocals
        y = make_sine(freq=440.0, duration=3.0)
        result = analyze_vocals(None, y, 22050)
        assert 0.0 <= result["voiced_ratio"] <= 1.0
