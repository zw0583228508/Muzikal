import pytest
pytestmark = pytest.mark.integration

"""
Unit tests for job-related API endpoints via FastAPI TestClient.

Tests:
- GET /python-api/health
- GET /python-api/styles
- POST /python-api/jobs/{job_id}/cancel (routing check)
- Celery availability detection (no Redis expected in CI)
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class TestCeleryFallback:
    """Celery should gracefully fall back to in-process when Redis is unavailable."""

    def test_celery_available_flag_is_bool(self):
        from workers.celery_app import CELERY_AVAILABLE
        assert isinstance(CELERY_AVAILABLE, bool)

    def test_get_celery_app_returns_none_without_redis(self):
        """In test environment (no Redis), get_celery_app() returns None."""
        from workers.celery_app import get_celery_app, CELERY_AVAILABLE
        if not CELERY_AVAILABLE:
            assert get_celery_app() is None

    def test_dispatch_analysis_falls_back(self):
        from workers.tasks.analysis import dispatch_analysis
        result = dispatch_analysis("test-job-001", 1, "/nonexistent.wav")
        assert result is None

    def test_dispatch_arrangement_falls_back(self):
        from workers.tasks.arrangement import dispatch_arrangement
        result = dispatch_arrangement("test-job-002", 1, "pop", None, 0.7, True, 1.0)
        assert result is None

    def test_dispatch_export_falls_back(self):
        from workers.tasks.render import dispatch_export
        result = dispatch_export("test-job-003", 1, ["midi"], None)
        assert result is None

    def test_dispatch_render_falls_back(self):
        from workers.tasks.render import dispatch_render
        result = dispatch_render("test-job-004", 1, ["wav"], None)
        assert result is None

    def test_revoke_task_returns_false_without_celery(self):
        from workers.celery_app import revoke_task, CELERY_AVAILABLE
        if not CELERY_AVAILABLE:
            result = revoke_task("fake-task-id-xyz")
            assert result is False


class TestFastApiHealth:
    """Light smoke tests against the FastAPI app using TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_ok(self, client):
        resp = client.get("/python-api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_styles_returns_list(self, client):
        resp = client.get("/python-api/styles")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_cancel_nonexistent_job_returns_404(self, client):
        resp = client.post("/python-api/jobs/nonexistent-job-abc/cancel")
        assert resp.status_code == 404

    def test_analyze_missing_body_returns_422(self, client):
        resp = client.post("/python-api/analyze", json={})
        assert resp.status_code == 422

    def test_arrange_missing_body_returns_422(self, client):
        resp = client.post("/python-api/arrange", json={})
        assert resp.status_code == 422
