import pytest
pytestmark = pytest.mark.service

"""
Unit tests for packages/audio_core/feature_cache.py
"""

import json
import os
import time

import pytest


def _make_cache(cache_dir: str):
    """Import and instantiate FeatureCache pointing at the temp dir."""
    import importlib.util, types

    spec_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "packages", "audio_core", "feature_cache.py"
    )
    spec_path = os.path.abspath(spec_path)
    spec = importlib.util.spec_from_file_location("feature_cache", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cache = mod.FeatureCache(cache_dir=cache_dir, ttl_seconds=3600)
    return cache


class TestFeatureCache:
    def test_miss_returns_none(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        assert cache.get("abc123", "rhythm") is None

    def test_set_then_get(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        data = {"bpm": 120, "beats": [0.5, 1.0, 1.5]}
        cache.set("abc123", "rhythm", data)
        result = cache.get("abc123", "rhythm")
        assert result is not None
        assert result["bpm"] == 120
        assert result["beats"] == [0.5, 1.0, 1.5]

    def test_different_steps_are_independent(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        cache.set("abc123", "rhythm", {"bpm": 90})
        cache.set("abc123", "key", {"key": "Am"})
        assert cache.get("abc123", "rhythm")["bpm"] == 90
        assert cache.get("abc123", "key")["key"] == "Am"
        assert cache.get("abc123", "chords") is None

    def test_different_checksums_are_independent(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        cache.set("hash1", "rhythm", {"bpm": 100})
        cache.set("hash2", "rhythm", {"bpm": 200})
        assert cache.get("hash1", "rhythm")["bpm"] == 100
        assert cache.get("hash2", "rhythm")["bpm"] == 200

    def test_overwrite(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        cache.set("abc123", "rhythm", {"bpm": 120})
        cache.set("abc123", "rhythm", {"bpm": 140})
        assert cache.get("abc123", "rhythm")["bpm"] == 140

    def test_ttl_expiry(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        cache.ttl_seconds = 0  # expire immediately
        cache.set("abc123", "rhythm", {"bpm": 120})
        time.sleep(0.05)
        result = cache.get("abc123", "rhythm")
        assert result is None

    def test_stats(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        cache.set("h1", "rhythm", {"bpm": 120})
        cache.set("h2", "key", {"key": "C"})
        stats = cache.stats()
        assert isinstance(stats, dict)
        count = stats.get("entry_count") or stats.get("total_entries") or 0
        assert count >= 2

    def test_clear(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        cache.set("abc123", "rhythm", {"bpm": 120})
        # support both clear() and clear_all()
        if hasattr(cache, "clear"):
            cache.clear()
        else:
            cache.clear_all()
        assert cache.get("abc123", "rhythm") is None

    def test_handles_complex_json_data(self, tmp_path):
        cache = _make_cache(str(tmp_path))
        data = {
            "chords": [
                {"start": 0.0, "end": 2.0, "chord": "Am", "confidence": 0.92},
                {"start": 2.0, "end": 4.0, "chord": "F", "confidence": 0.88},
            ],
            "lead_sheet": "Am F C G",
        }
        cache.set("deadbeef", "chords", data)
        result = cache.get("deadbeef", "chords")
        assert result["lead_sheet"] == "Am F C G"
        assert len(result["chords"]) == 2
        assert result["chords"][0]["chord"] == "Am"
