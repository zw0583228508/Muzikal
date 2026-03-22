"""
pytest configuration / shared fixtures.
"""

import os
import sys
import pytest

# Ensure backend root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Point to a test-only temp cache dir so production cache isn't touched
os.environ.setdefault("FEATURE_CACHE_DIR", "/tmp/musicai_test_cache")


@pytest.fixture(autouse=True)
def clean_test_cache(tmp_path, monkeypatch):
    """Each test gets a fresh isolated cache directory."""
    import tempfile
    cache_dir = tmp_path / "feature_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FEATURE_CACHE_DIR", str(cache_dir))
    yield str(cache_dir)
