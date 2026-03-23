import pytest
pytestmark = pytest.mark.unit

"""
Tests for audio/key_mode.py — key detection, mode, modulations, and alternatives.
"""
import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audio.key_mode import chroma_to_key, chroma_to_key_top_k, analyze_key


class TestChromaToKey:
    def _make_chroma(self, key_idx: int) -> np.ndarray:
        """Create a synthetic chroma vector dominated by one pitch class."""
        c = np.zeros(12)
        c[key_idx] = 1.0
        c[(key_idx + 7) % 12] = 0.5   # perfect fifth
        c[(key_idx + 4) % 12] = 0.4   # major third
        return c

    def test_returns_tuple_of_three(self):
        chroma = self._make_chroma(0)
        result = chroma_to_key(chroma)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_key_is_string(self):
        key, mode, conf = chroma_to_key(self._make_chroma(0))
        assert isinstance(key, str)
        assert len(key) <= 3

    def test_mode_is_major_or_minor(self):
        _, mode, _ = chroma_to_key(self._make_chroma(0))
        assert mode in ("major", "minor")

    def test_confidence_in_unit_range(self):
        for i in range(12):
            _, _, conf = chroma_to_key(self._make_chroma(i))
            assert 0.0 <= conf <= 1.0, f"Confidence {conf} out of range for key {i}"

    def test_uniform_chroma_low_confidence(self):
        uniform = np.ones(12) / 12
        _, _, conf = chroma_to_key(uniform)
        assert conf < 0.6

    def test_strong_chroma_high_confidence(self):
        c = self._make_chroma(0)
        c = c / c.sum()
        _, _, conf = chroma_to_key(c)
        assert conf > 0.4

    def test_c_major_detection(self):
        """C major chroma: C, E, G dominant."""
        c = np.zeros(12)
        c[0] = 1.0   # C
        c[4] = 0.6   # E
        c[7] = 0.8   # G
        c[2] = 0.3   # D
        c[5] = 0.3   # F
        c[9] = 0.3   # A
        c[11] = 0.2  # B
        key, _, _ = chroma_to_key(c)
        assert key in ("C", "G", "F")

    def test_all_12_keys_return_valid_result(self):
        """Every pitch class dominance produces a valid key/mode/confidence."""
        for i in range(12):
            key, mode, conf = chroma_to_key(self._make_chroma(i))
            assert isinstance(key, str)
            assert mode in ("major", "minor")
            assert 0.0 <= conf <= 1.0


class TestChromaToKeyTopK:
    def _make_chroma(self, key_idx: int) -> np.ndarray:
        c = np.zeros(12)
        c[key_idx] = 1.0
        c[(key_idx + 7) % 12] = 0.4
        return c

    def test_returns_list(self):
        result = chroma_to_key_top_k(self._make_chroma(0), k=3)
        assert isinstance(result, list)

    def test_length_at_most_k(self):
        result = chroma_to_key_top_k(self._make_chroma(0), k=4)
        assert len(result) <= 4

    def test_each_item_has_key_and_score(self):
        result = chroma_to_key_top_k(self._make_chroma(0), k=3)
        for item in result:
            assert "key" in item
            assert "confidence" in item or "score" in item

    def test_sorted_by_score_desc(self):
        result = chroma_to_key_top_k(self._make_chroma(0), k=4)
        confs = [r.get("confidence", r.get("score", 0)) for r in result]
        assert confs == sorted(confs, reverse=True)

    def test_k1_returns_single(self):
        result = chroma_to_key_top_k(self._make_chroma(0), k=1)
        assert len(result) == 1


class TestAnalyzeKey:
    def _make_sine(self, freq: float, sr: int = 22050, dur: float = 4.0) -> np.ndarray:
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        return (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)

    def _make_chord(self, freqs, sr=22050, dur=6.0):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        y = sum(np.sin(2 * np.pi * f * t) * 0.3 for f in freqs)
        return y.astype(np.float32)

    def test_returns_dict(self):
        y = self._make_sine(261.63)  # C4
        result = analyze_key(y, 22050)
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        y = self._make_sine(261.63)
        result = analyze_key(y, 22050)
        for key in ("globalKey", "mode", "confidence", "alternatives", "modulations", "model"):
            assert key in result, f"Missing key: {key}"

    def test_confidence_in_range(self):
        y = self._make_sine(261.63)
        result = analyze_key(y, 22050)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_alternatives_is_list(self):
        y = self._make_sine(261.63)
        result = analyze_key(y, 22050)
        assert isinstance(result["alternatives"], list)

    def test_modulations_is_list(self):
        y = self._make_sine(261.63)
        result = analyze_key(y, 22050)
        assert isinstance(result["modulations"], list)

    def test_modulation_entries_have_required_fields(self):
        """If modulations are detected, they must include timeSeconds, fromKey, toKey, confidence."""
        y = self._make_sine(261.63, dur=10.0)
        result = analyze_key(y, 22050)
        for mod in result["modulations"]:
            assert "timeSeconds" in mod
            assert "fromKey" in mod
            assert "toKey" in mod
            assert "confidence" in mod

    def test_modulation_confidence_in_range(self):
        y = self._make_chord([261.63, 329.63, 392.0], dur=10.0)
        result = analyze_key(y, 22050)
        for mod in result["modulations"]:
            assert 0.0 <= mod["confidence"] <= 1.0

    def test_model_identifier(self):
        y = self._make_sine(261.63)
        result = analyze_key(y, 22050)
        assert result["model"] == "chroma-cqt-ks"

    def test_short_audio_no_modulations(self):
        """Short clips shouldn't have modulation (< 4 s threshold)."""
        y = self._make_sine(261.63, dur=3.0)
        result = analyze_key(y, 22050)
        assert result["modulations"] == []

    def test_warnings_is_list(self):
        y = self._make_sine(261.63)
        result = analyze_key(y, 22050)
        assert isinstance(result.get("warnings", []), list)
