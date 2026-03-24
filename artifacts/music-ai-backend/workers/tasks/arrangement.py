"""
Celery task: arrangement generation pipeline.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional, List

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _get_celery_app():
    from workers.celery_app import celery_app
    return celery_app


def get_task():
    app = _get_celery_app()
    if app is None:
        return None

    @app.task(bind=True, name="workers.tasks.arrangement.run_arrangement")
    def run_arrangement(
        self,
        job_id: str,
        project_id: int,
        style_id: str,
        instruments: Optional[List[str]],
        density: float,
        do_humanize: bool,
        tempo_factor: float,
        persona_id: Optional[str] = None,
    ):
        """Celery task: arrangement generation pipeline."""
        from api.routes import run_arrangement_pipeline
        logger.info("Celery arrangement task started — job=%s project=%s style=%s", job_id, project_id, style_id)

        try:
            from api.database import update_job
            update_job(job_id, "running", 1, "Celery worker picked up task",
                       processing_metadata={"celery_task_id": self.request.id})
        except Exception:
            pass

        run_arrangement_pipeline(job_id, project_id, style_id, instruments, density, do_humanize, tempo_factor)

    return run_arrangement


def dispatch_arrangement(
    job_id: str,
    project_id: int,
    style_id: str,
    instruments: Optional[List[str]],
    density: float,
    do_humanize: bool,
    tempo_factor: float,
    persona_id: Optional[str] = None,
):
    """Dispatch arrangement to Celery if available; returns celery_task_id or None."""
    task_fn = get_task()
    if task_fn is None:
        return None
    result = task_fn.apply_async(args=[
        job_id, project_id, style_id, instruments, density, do_humanize, tempo_factor, persona_id
    ])
    logger.info("Dispatched Celery arrangement task %s for job %s", result.id, job_id)
    return result.id
