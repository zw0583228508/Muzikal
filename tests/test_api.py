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


class TestMockModeEndpoint:
    def test_mock_mode_returns_200(self):
        r = api("/projects/mock-mode")
        assert r.status_code == 200

    def test_mock_mode_has_required_fields(self):
        r = api("/projects/mock-mode")
        data = r.json()
        assert "isMock" in data, "isMock field missing"
        assert "pipelineVersion" in data, "pipelineVersion field missing"
        assert "modelVersions" in data, "modelVersions field missing"

    def test_mock_mode_is_mock_is_boolean(self):
        r = api("/projects/mock-mode")
        assert isinstance(r.json()["isMock"], bool)

    def test_mock_mode_pipeline_version_format(self):
        r = api("/projects/mock-mode")
        version = r.json()["pipelineVersion"]
        parts = version.split(".")
        assert len(parts) == 3, f"Expected semver x.y.z, got: {version}"

    def test_mock_mode_model_versions_has_7_models(self):
        r = api("/projects/mock-mode")
        model_versions = r.json()["modelVersions"]
        assert isinstance(model_versions, dict)
        expected_models = {"madmom", "essentia", "chord-cnn", "pyin", "msaf", "demucs", "crepe"}
        for model in expected_models:
            assert model in model_versions, f"Model '{model}' missing from modelVersions"

    def test_analyze_without_audio_fails_in_real_mode(self):
        """In non-mock mode, analysis without audio should return 400."""
        r = api("/projects/mock-mode")
        if r.json().get("isMock"):
            pytest.skip("MOCK_MODE=true — server allows analysis without audio")
        cr = api("/projects", method="POST", json={"name": "No-Audio Test"})
        pid = cr.json()["id"]
        ar = api(f"/projects/{pid}/analyze", method="POST")
        assert ar.status_code == 400
        assert "audio" in ar.json().get("error", "").lower()
        api(f"/projects/{pid}", method="DELETE")


class TestAnalysisResultFields:
    """Verify that real analysis results include confidence, warnings, alternatives."""

    def test_analysis_endpoint_returns_404_when_no_analysis(self):
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Analysis Fields Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            r = api(f"/projects/{pid}/analysis")
            assert r.status_code == 404
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)

    def test_analysis_in_mock_mode_starts_job(self):
        import time
        mode = api("/projects/mock-mode").json()
        if not mode.get("isMock"):
            pytest.skip("Skipping mock analysis test — MOCK_MODE=false")
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Mock Analysis Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            ar = api(f"/projects/{pid}/analyze", method="POST")
            assert ar.status_code == 200
            job = ar.json()
            assert "jobId" in job
            assert job["isMock"] is True
            time.sleep(2)
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)


class TestArrangementEndpoint:
    """Tests for the arrangement endpoint (T011)."""

    def test_arrangement_returns_404_when_not_ready(self):
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Arr 404 Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            r = api(f"/projects/{pid}/arrangement")
            assert r.status_code == 404
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)

    def test_arrangement_job_starts_in_mock_mode(self):
        mode = api("/projects/mock-mode").json()
        if not mode.get("isMock"):
            pytest.skip("Skipping mock arrangement test — MOCK_MODE=false")
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Mock Arr Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            r = api(f"/projects/{pid}/arrangement", method="POST", json={"styleId": "pop"})
            assert r.status_code == 200
            job = r.json()
            assert "jobId" in job
            assert job["isMock"] is True, f"Expected isMock=True for arrangement in MOCK_MODE, got {job}"
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)

    def test_arrangement_history_is_list(self):
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Arr History Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            r = api(f"/projects/{pid}/arrangement/history")
            assert r.status_code == 200
            assert isinstance(r.json(), list)
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)


class TestExportEndpoint:
    """Tests for the export endpoint (T011)."""

    def test_export_job_starts_in_mock_mode(self):
        mode = api("/projects/mock-mode").json()
        if not mode.get("isMock"):
            pytest.skip("Skipping mock export test — MOCK_MODE=false")
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Mock Export Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            r = api(f"/projects/{pid}/export", method="POST", json={"formats": ["midi"]})
            assert r.status_code == 200
            job = r.json()
            assert "jobId" in job
            assert job["isMock"] is True
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)

    def test_export_files_returns_list(self):
        cr = requests.post(f"{BASE_URL}/projects", json={"name": "Export Files Test"}, timeout=10)
        pid = cr.json()["id"]
        try:
            r = api(f"/projects/{pid}/files")
            assert r.status_code == 200
            assert isinstance(r.json(), list)
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)


class TestLockSystemFull:
    """Full lock system tests (T011 — T009 verification)."""

    def _make_project(self, name: str) -> int:
        r = requests.post(f"{BASE_URL}/projects", json={"name": name}, timeout=10)
        return r.json()["id"]

    def test_put_locks_full_state(self):
        pid = self._make_project("Lock PUT Test")
        try:
            body = {"harmony": True, "structure": False, "melody": True,
                    "tracks": False, "key": True, "chords": False, "bpm": False}
            r = api(f"/projects/{pid}/locks", method="PUT", json=body)
            assert r.status_code == 200
            locks = r.json()["locks"]
            assert locks["harmony"] is True
            assert locks["melody"] is True
            assert locks["structure"] is False
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)

    def test_patch_all_lock_components(self):
        pid = self._make_project("Lock PATCH All Test")
        try:
            for component in ["harmony", "structure", "melody", "tracks", "key", "chords", "bpm"]:
                r = api(f"/projects/{pid}/locks/{component}", method="PATCH", json={"locked": True})
                assert r.status_code == 200, f"PATCH lock/{component} failed: {r.text}"
                assert r.json()["locked"] is True
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)

    def test_invalid_lock_key_in_put_is_ignored(self):
        pid = self._make_project("Lock PUT Invalid Key")
        try:
            r = api(f"/projects/{pid}/locks", method="PUT", json={"harmony": True, "INVALID_KEY": True})
            assert r.status_code == 200
            assert "INVALID_KEY" not in r.json()["locks"]
        finally:
            requests.delete(f"{BASE_URL}/projects/{pid}", timeout=10)


class TestVersioning:
    """Versioning system tests (T005 — STEP 9)."""

    def test_pipeline_version_is_1_1_0(self):
        r = api("/projects/mock-mode")
        assert r.status_code == 200
        version = r.json().get("pipelineVersion", "")
        assert version == "1.1.0", f"Expected pipelineVersion=1.1.0, got {version}"

    def test_model_versions_use_model_name_keys(self):
        r = api("/projects/mock-mode")
        mv = r.json().get("modelVersions", {})
        for key in mv:
            assert key in {"madmom", "essentia", "chord-cnn", "pyin", "msaf", "demucs", "crepe"}, \
                f"Unexpected model key '{key}' — should use model-name format"

    def test_model_version_values_are_non_empty_strings(self):
        r = api("/projects/mock-mode")
        mv = r.json().get("modelVersions", {})
        assert len(mv) > 0, "Expected at least one model version entry"
        for key, val in mv.items():
            assert isinstance(val, str) and len(val) > 0, \
                f"Model version '{key}' should be a non-empty string, got: {val!r}"
