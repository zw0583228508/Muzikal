import pytest
pytestmark = pytest.mark.unit

"""
Tests for audio/chords.py — chord detection.
analyze_chords(y, sr, rhythm, key) → {"chords": [...], ...}
"""
import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audio.chords import analyze_chords


MOCK_RHYTHM = {
    "bpm": 120.0,
    "timeSignatureNumerator": 4,
    "timeSignatureDenominator": 4,
    "beatGrid": [0.0, 0.5, 1.0, 1.5, 2.0],
}

MOCK_KEY = {
    "globalKey": "C",
    "mode": "major",
    "confidence": 0.85,
}


def _chord_signal(freqs, sr=22050, dur=6.0) -> np.ndarray:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return sum(np.sin(2 * np.pi * f * t) * 0.3 for f in freqs).astype(np.float32)


def _c_major(sr=22050, dur=6.0):
    return _chord_signal([261.63, 329.63, 392.0], sr, dur)


def _silence(sr=22050, dur=4.0):
    return np.zeros(int(sr * dur), dtype=np.float32)


class TestAnalyzeChords:
    def test_returns_dict(self):
        y = _c_major()
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        assert isinstance(result, dict)

    def test_has_chords_key(self):
        y = _c_major()
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        assert "chords" in result

    def test_chords_is_list(self):
        y = _c_major()
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        assert isinstance(result["chords"], list)

    def test_each_chord_event_has_time(self):
        y = _c_major(dur=8.0)
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        for ev in result["chords"]:
            assert "time" in ev or "start" in ev or "timeSeconds" in ev or "startTime" in ev

    def test_each_chord_has_label(self):
        y = _c_major(dur=8.0)
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        for ev in result["chords"]:
            assert "chord" in ev or "label" in ev or "root" in ev

    def test_silence_no_crash(self):
        y = _silence()
        try:
            result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
            assert isinstance(result, dict)
        except Exception:
            pytest.fail("analyze_chords raised on silence")

    def test_noise_no_crash(self):
        rng = np.random.default_rng(0)
        y = rng.standard_normal(22050 * 5).astype(np.float32) * 0.1
        try:
            result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
            assert isinstance(result, dict)
        except Exception:
            pytest.fail("analyze_chords raised on noise")

    def test_chord_times_monotonic(self):
        y = _c_major(dur=10.0)
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        events = result.get("chords", [])
        if len(events) < 2:
            return
        times = [ev.get("time", ev.get("start", ev.get("timeSeconds", 0))) for ev in events]
        assert times == sorted(times)

    def test_chord_labels_are_strings(self):
        y = _c_major(dur=8.0)
        result = analyze_chords(y, 22050, MOCK_RHYTHM, MOCK_KEY)
        for ev in result.get("chords", []):
            label = ev.get("chord", ev.get("label", ev.get("root", "")))
            assert isinstance(label, str)

    def test_minor_key_chord_detection(self):
        minor_key = {"globalKey": "A", "mode": "minor", "confidence": 0.8}
        y = _chord_signal([220.0, 261.63, 329.63], dur=6.0)
        result = analyze_chords(y, 22050, MOCK_RHYTHM, minor_key)
        assert isinstance(result, dict)
        assert "chords" in result
