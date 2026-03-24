"""
Celery tasks: export pipeline and audio render pipeline.
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


def get_export_task():
    app = _get_celery_app()
    if app is None:
        return None

    @app.task(bind=True, name="workers.tasks.render.run_export")
    def run_export_task(
        self,
        job_id: str,
        project_id: int,
        formats: List[str],
        custom_output_dir: Optional[str],
    ):
        """Celery task: MIDI/MusicXML/PDF export pipeline."""
        from api.routes import run_export_pipeline
        logger.info("Celery export task started — job=%s project=%s formats=%s", job_id, project_id, formats)

        try:
            from api.database import update_job
            update_job(job_id, "running", 1, "Celery worker picked up task",
                       processing_metadata={"celery_task_id": self.request.id})
        except Exception:
            pass

        run_export_pipeline(job_id, project_id, formats, custom_output_dir)

    return run_export_task


def get_render_task():
    app = _get_celery_app()
    if app is None:
        return None

    @app.task(bind=True, name="workers.tasks.render.run_render")
    def run_render_task(
        self,
        job_id: str,
        project_id: int,
        formats: List[str],
        custom_output_dir: Optional[str],
    ):
        """Celery task: audio render pipeline (WAV/FLAC/MP3/Stems)."""
        from api.routes import run_render_pipeline
        logger.info("Celery render task started — job=%s project=%s formats=%s", job_id, project_id, formats)

        try:
            from api.database import update_job
            update_job(job_id, "running", 1, "Celery worker picked up task",
                       processing_metadata={"celery_task_id": self.request.id})
        except Exception:
            pass

        run_render_pipeline(job_id, project_id, formats, custom_output_dir)

    return run_render_task


def dispatch_export(job_id: str, project_id: int, formats: List[str], custom_output_dir: Optional[str]):
    """Dispatch export to Celery if available; returns celery_task_id or None."""
    task_fn = get_export_task()
    if task_fn is None:
        return None
    result = task_fn.apply_async(args=[job_id, project_id, formats, custom_output_dir])
    logger.info("Dispatched Celery export task %s for job %s", result.id, job_id)
    return result.id


def dispatch_render(job_id: str, project_id: int, formats: List[str], custom_output_dir: Optional[str]):
    """Dispatch render to Celery if available; returns celery_task_id or None."""
    task_fn = get_render_task()
    if task_fn is None:
        return None
    result = task_fn.apply_async(args=[job_id, project_id, formats, custom_output_dir])
    logger.info("Dispatched Celery render task %s for job %s", result.id, job_id)
    return result.id
