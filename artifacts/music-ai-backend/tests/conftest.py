"""
pytest configuration / shared fixtures.

Marker taxonomy
---------------
unit        — pure logic test, no I/O, no network
service     — tests one module in isolation (may touch tmp filesystem)
integration — needs a running FastAPI app or real DB
slow        — > 5 s runtime
"""

import os
import sys
import pytest

# ── Path bootstrap ────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Module-level env defaults (override before any import happens) ─────────────
os.environ.setdefault("FEATURE_CACHE_DIR", "/tmp/musicai_test_cache")
# Use SQLite so tests never need a live Postgres instance
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_db.sqlite3")
# Keep storage in tmp so tests never touch /app/storage
os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/musicai_test_storage")


# ── Autouse: fresh isolated directories per test ──────────────────────────────

@pytest.fixture(autouse=True)
def clean_test_cache(tmp_path, monkeypatch):
    """Each test gets its own cache directory — no cross-test pollution."""
    cache_dir = tmp_path / "feature_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FEATURE_CACHE_DIR", str(cache_dir))
    yield str(cache_dir)


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Each test gets its own local storage root — never touches production storage."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(storage_dir))
    yield str(storage_dir)


# ── Integration fixture: FastAPI TestClient ───────────────────────────────────

@pytest.fixture(scope="session")
def test_client():
    """
    Session-scoped FastAPI TestClient.
    Tests marked @pytest.mark.integration use this.
    Unit/service tests should NOT request it.
    """
    try:
        from fastapi.testclient import TestClient
        from main import app
        with TestClient(app) as client:
            yield client
    except Exception:
        pytest.skip("FastAPI app not available for testing")


# ── Data fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_project():
    """Minimal valid project dict (mirrors Node API project shape)."""
    return {
        "id": 1,
        "name": "Test Project",
        "status": "pending",
        "audioFileName": None,
        "audioDurationSeconds": None,
    }


@pytest.fixture
def mock_analysis():
    """Minimal valid analysis result, enough to feed arrangement generation."""
    return {
        "rhythm": {"bpm": 120.0, "timeSignatureNumerator": 4, "timeSignatureDenominator": 4},
        "key": {"globalKey": "C", "mode": "major", "confidence": 0.9},
        "chords": {"chords": [{"chord": "C", "startTime": 0.0, "duration": 2.0}]},
        "melody": {"notes": []},
        "structure": {
            "sections": [
                {"label": "verse", "startTime": 0.0, "endTime": 16.0, "confidence": 0.8},
                {"label": "chorus", "startTime": 16.0, "endTime": 32.0, "confidence": 0.85},
            ]
        },
        "duration": 32.0,
        "sampleRate": 44100,
        "waveformData": [0.0] * 200,
        "isMock": True,
    }


@pytest.fixture
def mock_arrangement():
    """Minimal valid arrangement result."""
    return {
        "styleId": "pop",
        "tracks": [
            {
                "id": "drums",
                "name": "Drums",
                "instrument": "drums",
                "midiProgram": 0,
                "color": "#ff4444",
                "notes": [{"pitch": 36, "startTime": 0.0, "duration": 0.25, "velocity": 100}],
                "volume": 0.8,
                "muted": False,
                "soloed": False,
            }
        ],
        "totalDurationSeconds": 32.0,
        "arrangementPlan": {"harmonicPlan": ["I", "IV", "V", "I"]},
        "generationMetadata": {"bpm": 120, "style": "pop"},
    }
