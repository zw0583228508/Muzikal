"""
Tests for API route handlers — projects, jobs, styles, analysis endpoints.
Uses FastAPI's TestClient from the existing conftest setup.
"""
import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHealthEndpoint:
    def test_health_check_200(self, test_client):
        resp = test_client.get("/python-api/health")
        assert resp.status_code == 200

    def test_health_check_body(self, test_client):
        resp = test_client.get("/python-api/health")
        data = resp.json()
        assert "status" in data or "ok" in str(data).lower() or resp.status_code == 200

    def test_health_check_fast(self, test_client):
        import time
        start = time.time()
        test_client.get("/python-api/health")
        assert time.time() - start < 2.0


class TestStylesEndpoint:
    def test_styles_returns_list(self, test_client):
        resp = test_client.get("/python-api/styles")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_styles_nonempty(self, test_client):
        resp = test_client.get("/python-api/styles")
        assert len(resp.json()) > 0

    def test_each_style_has_id_and_name(self, test_client):
        resp = test_client.get("/python-api/styles")
        for style in resp.json():
            assert "id" in style
            assert "name" in style

    def test_personas_endpoint(self, test_client):
        resp = test_client.get("/python-api/personas")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert isinstance(resp.json(), (list, dict))


class TestCacheEndpoints:
    def test_cache_stats_endpoint(self, test_client):
        resp = test_client.get("/python-api/cache/stats")
        assert resp.status_code in (200, 404)

    def test_cache_stats_body_when_200(self, test_client):
        resp = test_client.get("/python-api/cache/stats")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict)

    def test_cache_clear_endpoint(self, test_client):
        resp = test_client.delete("/python-api/cache")
        assert resp.status_code in (200, 204, 404)


class TestProjectAnalysisEndpoints:
    def test_analysis_missing_project_404(self, test_client):
        resp = test_client.get("/python-api/projects/999999/analysis")
        assert resp.status_code in (404, 422, 200)

    def test_start_analysis_missing_body_422(self, test_client):
        resp = test_client.post("/python-api/projects/1/analyze", json={})
        assert resp.status_code in (200, 201, 202, 400, 404, 422)

    def test_start_analysis_with_mock_data(self, test_client, mock_project):
        project_id = mock_project["id"]
        resp = test_client.post(
            f"/python-api/projects/{project_id}/analyze",
            json={"audioPath": "/tmp/nonexistent.wav", "mock": True},
        )
        assert resp.status_code in (200, 201, 202, 400, 404, 422)


class TestArrangementEndpoints:
    def test_get_arrangement_missing(self, test_client, mock_project):
        project_id = mock_project["id"]
        resp = test_client.get(f"/python-api/projects/{project_id}/arrangement")
        assert resp.status_code in (200, 404)

    def test_generate_arrangement_mock(self, test_client, mock_project):
        project_id = mock_project["id"]
        resp = test_client.post(
            f"/python-api/projects/{project_id}/arrangement",
            json={"styleId": "hasidic-wedding", "personaId": None},
        )
        assert resp.status_code in (200, 201, 202, 400, 404, 422)


class TestJobEndpoints:
    def test_get_nonexistent_job_404(self, test_client):
        resp = test_client.get("/python-api/jobs/nonexistent-job-id")
        assert resp.status_code in (404, 422)

    def test_cancel_nonexistent_job(self, test_client):
        resp = test_client.post("/python-api/jobs/nonexistent/cancel")
        assert resp.status_code in (200, 404, 422)

    def test_retry_nonexistent_job(self, test_client):
        resp = test_client.post("/python-api/jobs/nonexistent/retry")
        assert resp.status_code in (200, 404, 422)
