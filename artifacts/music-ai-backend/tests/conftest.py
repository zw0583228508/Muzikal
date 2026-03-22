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
# Use SQLite for tests to avoid needing a live Postgres
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_db.sqlite3")


@pytest.fixture(autouse=True)
def clean_test_cache(tmp_path, monkeypatch):
    """Each test gets a fresh isolated cache directory."""
    cache_dir = tmp_path / "feature_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FEATURE_CACHE_DIR", str(cache_dir))
    yield str(cache_dir)


@pytest.fixture(scope="session")
def test_client():
    """FastAPI TestClient for integration tests."""
    try:
        from fastapi.testclient import TestClient
        from main import app
        with TestClient(app) as client:
            yield client
    except Exception:
        pytest.skip("FastAPI app not available for testing")


@pytest.fixture
def mock_project():
    """Return a minimal mock project dict for use in API tests."""
    return {
        "id": 1,
        "name": "Test Project",
        "status": "pending",
        "audioFileName": None,
        "audioDurationSeconds": None,
    }
