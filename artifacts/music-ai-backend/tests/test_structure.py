"""
Tests for audio/structure.py — segment/section detection.
analyze_structure(y, sr, rhythm) → {"sections": [...] or similar}
"""
import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audio.structure import analyze_structure


MOCK_RHYTHM = {
    "bpm": 120.0,
    "timeSignatureNumerator": 4,
    "timeSignatureDenominator": 4,
    "beatGrid": [float(i) * 0.5 for i in range(40)],
}


def _repeating_audio(sr=22050, dur=20.0) -> np.ndarray:
    y = np.zeros(int(sr * dur), dtype=np.float32)
    block = int(sr * 4)
    freqs = [261.63, 329.63, 261.63, 392.0, 261.63]
    for i, f in enumerate(freqs):
        start = i * block
        end = min(start + block, len(y))
        t = np.linspace(0, (end - start) / sr, end - start, endpoint=False)
        y[start:end] = np.sin(2 * np.pi * f * t).astype(np.float32) * 0.3
    return y


def _silence(sr=22050, dur=10.0):
    return np.zeros(int(sr * dur), dtype=np.float32)


class TestAnalyzeStructure:
    def test_returns_dict(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        assert isinstance(result, dict)

    def test_has_sections_key(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        assert "sections" in result or "segments" in result or "labels" in result

    def test_sections_is_list(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        assert isinstance(sections, list)

    def test_at_least_one_section(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        assert len(sections) >= 1

    def test_each_section_has_label(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        for seg in sections:
            assert "label" in seg or "type" in seg or "name" in seg

    def test_each_section_has_start(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        for seg in sections:
            assert "start" in seg or "startTime" in seg or "timeSeconds" in seg

    def test_silence_no_crash(self):
        y = _silence()
        try:
            result = analyze_structure(y, 22050, MOCK_RHYTHM)
            assert isinstance(result, dict)
        except Exception:
            pytest.fail("analyze_structure raised on silence")

    def test_short_audio_single_section(self):
        y = np.sin(np.linspace(0, 3 * 2 * np.pi * 261, 22050 * 5)).astype(np.float32)
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        assert len(sections) >= 1

    def test_section_labels_are_strings(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        for seg in sections:
            label = seg.get("label", seg.get("type", seg.get("name", "")))
            assert isinstance(label, str)

    def test_start_times_monotonic(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        if len(sections) < 2:
            return
        times = [seg.get("start", seg.get("startTime", seg.get("timeSeconds", 0))) for seg in sections]
        assert times == sorted(times)

    def test_first_section_starts_near_zero(self):
        y = _repeating_audio()
        result = analyze_structure(y, 22050, MOCK_RHYTHM)
        sections = result.get("sections", result.get("segments", result.get("labels", [])))
        if not sections:
            return
        first = sections[0].get("start", sections[0].get("startTime", sections[0].get("timeSeconds", 0)))
        assert first <= 2.0

    def test_noise_no_crash(self):
        rng = np.random.default_rng(7)
        y = rng.standard_normal(22050 * 10).astype(np.float32) * 0.1
        try:
            result = analyze_structure(y, 22050, MOCK_RHYTHM)
            assert isinstance(result, dict)
        except Exception:
            pytest.fail("analyze_structure raised on noise")
