"""
Celery task: audio analysis pipeline.

Wraps the same `run_analysis_pipeline` logic from api/routes.py so that
the real work is identical whether invoked via Celery or in-process.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Ensure the project root (where 'api', 'audio', etc. live) is on the path
# when the worker is launched from a different cwd.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _get_celery_app():
    from workers.celery_app import celery_app
    return celery_app


def get_task():
    """Return the Celery task (lazily bound so import works without Redis)."""
    app = _get_celery_app()
    if app is None:
        return None

    @app.task(bind=True, name="workers.tasks.analysis.run_analysis")
    def run_analysis(self, job_id: str, project_id: int, audio_file_path: str):
        """Celery task: full MIR analysis pipeline."""
        from api.routes import run_analysis_pipeline
        logger.info("Celery analysis task started — job=%s project=%s", job_id, project_id)

        # Store Celery task ID in job result_data so cancel can revoke it
        try:
            from api.database import update_job
            update_job(job_id, "running", 1, "Celery worker picked up task",
                       processing_metadata={"celery_task_id": self.request.id})
        except Exception:
            pass

        run_analysis_pipeline(job_id, project_id, audio_file_path)

    return run_analysis


def dispatch_analysis(job_id: str, project_id: int, audio_file_path: str):
    """
    Dispatch analysis to Celery if available; returns (celery_task_id | None).
    Callers should fall back to BackgroundTasks when this returns None.
    """
    task_fn = get_task()
    if task_fn is None:
        return None
    result = task_fn.apply_async(args=[job_id, project_id, audio_file_path])
    logger.info("Dispatched Celery analysis task %s for job %s", result.id, job_id)
    return result.id
