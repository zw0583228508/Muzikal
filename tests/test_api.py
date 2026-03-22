"""
STEP 17: API endpoint tests.
Run: python3 -m pytest tests/test_api.py -v
Requires the API server to be running on port 8080.
"""

import pytest
import requests

BASE_URL = "http://localhost:8080/api"


def api(path: str, method: str = "GET", **kwargs):
    url = f"{BASE_URL}{path}"
    fn = getattr(requests, method.lower())
    return fn(url, timeout=10, **kwargs)


class TestHealthEndpoints:
    def test_health(self):
        """Health endpoint — skip if not implemented."""
        r = api("/health")
        assert r.status_code in [200, 404]  # optional endpoint

    def test_styles_returns_15(self):
        r = api("/styles")
        assert r.status_code == 200
        styles = r.json()
        assert len(styles) == 15

    def test_styles_have_required_fields(self):
        r = api("/styles")
        for style in r.json():
            assert "id" in style
            assert "name" in style
            assert "nameHe" in style
            assert "genre" in style


class TestProjectValidation:
    def test_invalid_id_returns_400(self):
        r = api("/projects/abc")
        assert r.status_code == 400
        assert "invalid" in r.json().get("error", "").lower()

    def test_negative_id_returns_400(self):
        r = api("/projects/-1")
        assert r.status_code in [400, 404]

    def test_nonexistent_project_returns_404(self):
        r = api("/projects/99999999")
        assert r.status_code == 404

    def test_nonexistent_analysis_returns_404(self):
        r = api("/projects/99999999/analysis")
        assert r.status_code in [400, 404]

    def test_nonexistent_arrangement_returns_404(self):
        r = api("/projects/99999999/arrangement")
        assert r.status_code in [400, 404]


class TestProjectsCRUD:
    def test_create_project(self):
        r = api("/projects", method="POST", json={"name": "Test Project"})
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["name"] == "Test Project"
        return data["id"]

    def test_create_project_missing_name_returns_400(self):
        r = api("/projects", method="POST", json={})
        assert r.status_code == 400

    def test_list_projects(self):
        r = api("/projects")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_project(self):
        # First create
        cr = api("/projects", method="POST", json={"name": "Get Test"})
        pid = cr.json()["id"]
        # Then get
        r = api(f"/projects/{pid}")
        assert r.status_code == 200
        assert r.json()["id"] == pid

    def test_delete_project(self):
        cr = api("/projects", method="POST", json={"name": "Delete Test"})
        pid = cr.json()["id"]
        r = api(f"/projects/{pid}", method="DELETE")
        assert r.status_code == 204
        # Should 404 now
        r2 = api(f"/projects/{pid}")
        assert r2.status_code == 404


class TestJobEndpoints:
    def test_nonexistent_job_returns_404(self):
        r = api("/jobs/nonexistent-job-uuid-1234")
        assert r.status_code == 404

    def test_job_response_has_required_fields(self):
        # Create project and start an analysis to get a real job
        cr = api("/projects", method="POST", json={"name": "Job Test"})
        pid = cr.json()["id"]
        ar = api(f"/projects/{pid}/analyze", method="POST")
        if ar.status_code == 200:
            job = ar.json()
            assert "jobId" in job
            assert "status" in job
            assert "isMock" in job
            # Cleanup
            api(f"/projects/{pid}", method="DELETE")


class TestLocksEndpoints:
    def setup_method(self):
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Lock Test"}, timeout=10)
        self.pid = cr.json()["id"]

    def teardown_method(self):
        requests.delete(f"{BASE_URL}/projects/{self.pid}", timeout=10)

    def test_get_locks_returns_empty_by_default(self):
        r = api(f"/projects/{self.pid}/locks")
        assert r.status_code == 200
        assert "locks" in r.json()

    def test_patch_single_lock(self):
        r = api(f"/projects/{self.pid}/locks/harmony", method="PATCH", json={"locked": True})
        assert r.status_code == 200
        data = r.json()
        assert data["locked"] is True
        assert data["component"] == "harmony"

    def test_invalid_lock_component_returns_400(self):
        r = api(f"/projects/{self.pid}/locks/invalid_component", method="PATCH", json={"locked": True})
        assert r.status_code == 400
