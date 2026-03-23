"""
Integration-style tests for the Node.js regen endpoints via HTTP.

These tests call the running api-server at http://localhost:8080 — they run only
when the server is live (skipped otherwise).
"""

import os
import pytest

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

BASE_URL = "http://localhost:8080/api"


def _server_available():
    if not HAS_HTTPX:
        return False
    try:
        r = httpx.get(f"{BASE_URL}/projects", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_available(),
    reason="api-server not running at localhost:8080"
)


@pytest.fixture(scope="module")
def project_with_arrangement():
    """Return a project ID that has an existing arrangement, or skip."""
    r = httpx.get(f"{BASE_URL}/projects", timeout=5)
    raw = r.json() if r.status_code == 200 else []
    # Handle both paginated {"projects": [...]} and plain list responses
    if isinstance(raw, dict):
        projects = raw.get("projects", [])
    else:
        projects = raw if isinstance(raw, list) else []
    arranged = [p for p in projects if isinstance(p, dict) and p.get("status") in ("arranged", "analyzed")]
    if not arranged:
        pytest.skip("No analysed/arranged project available for regen tests")
    pid = arranged[0]["id"]
    # Ensure arrangement exists
    arr_resp = httpx.get(f"{BASE_URL}/projects/{pid}/arrangement", timeout=5)
    if arr_resp.status_code != 200:
        # Trigger arrangement
        job_resp = httpx.post(
            f"{BASE_URL}/projects/{pid}/arrangement",
            json={"styleId": "pop"},
            timeout=5,
        )
        import time; time.sleep(16)
    return pid


class TestRegenSectionEndpoint:
    def test_regen_section_returns_job_id(self, project_with_arrangement):
        pid = project_with_arrangement
        resp = httpx.post(
            f"{BASE_URL}/projects/{pid}/arrangement/section/verse/regenerate",
            json={"styleId": "pop"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "jobId" in data
        assert data["jobId"].startswith("regen-section-")
        assert data.get("status") in ("queued", "running", "completed")

    def test_regen_section_with_persona(self, project_with_arrangement):
        pid = project_with_arrangement
        resp = httpx.post(
            f"{BASE_URL}/projects/{pid}/arrangement/section/chorus/regenerate",
            json={"styleId": "hasidic", "personaId": "hasidic-wedding"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "jobId" in data

    def test_regen_section_unknown_project(self):
        resp = httpx.post(
            f"{BASE_URL}/projects/999999/arrangement/section/verse/regenerate",
            json={"styleId": "pop"},
            timeout=5,
        )
        assert resp.status_code in (404, 400)

    def test_regen_section_no_arrangement(self):
        r = httpx.get(f"{BASE_URL}/projects", timeout=5)
        raw = r.json() if r.status_code == 200 else []
        if isinstance(raw, dict):
            projects = raw.get("projects", [])
        else:
            projects = raw if isinstance(raw, list) else []
        fresh = [p for p in projects if isinstance(p, dict) and p.get("status") == "created"]
        if not fresh:
            pytest.skip("No fresh project available")
        pid = fresh[0]["id"]
        resp = httpx.post(
            f"{BASE_URL}/projects/{pid}/arrangement/section/verse/regenerate",
            json={"styleId": "pop"},
            timeout=5,
        )
        data = resp.json()
        assert "error" in data or resp.status_code in (400, 404)


class TestRegenTrackEndpoint:
    def test_regen_track_returns_job_id(self, project_with_arrangement):
        pid = project_with_arrangement
        resp = httpx.post(
            f"{BASE_URL}/projects/{pid}/arrangement/track/drums/regenerate",
            json={"styleId": "pop"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "jobId" in data
        assert data["jobId"].startswith("regen-track-")
        assert data.get("status") in ("queued", "running", "completed")

    def test_regen_track_stores_input_payload(self, project_with_arrangement):
        pid = project_with_arrangement
        resp = httpx.post(
            f"{BASE_URL}/projects/{pid}/arrangement/track/bass/regenerate",
            json={"styleId": "jazz"},
            timeout=10,
        )
        assert resp.status_code == 200
        job_id = resp.json().get("jobId")
        assert job_id is not None

        job_resp = httpx.get(f"{BASE_URL}/jobs/{job_id}", timeout=5)
        assert job_resp.status_code == 200
        job = job_resp.json()
        payload = job.get("inputPayload") or {}
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        assert payload.get("trackId") == "bass"


class TestPersonasEndpoint:
    def test_personas_endpoint_returns_all_six(self):
        resp = httpx.get(f"{BASE_URL}/styles/personas", timeout=5)
        assert resp.status_code == 200
        personas = resp.json()
        assert isinstance(personas, list)
        assert len(personas) >= 6

    def test_persona_fields(self):
        resp = httpx.get(f"{BASE_URL}/styles/personas", timeout=5)
        personas = resp.json()
        for p in personas:
            assert "id" in p
            assert "name" in p
            assert "nameEn" in p
            assert "tags" in p

    def test_hasidic_wedding_persona_present(self):
        resp = httpx.get(f"{BASE_URL}/styles/personas", timeout=5)
        ids = [p["id"] for p in resp.json()]
        assert "hasidic-wedding" in ids
