"""Audio render pipeline endpoints."""

import os
import logging
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks

from api.database import update_job
from api.schemas import RenderRequest
from api.export_routes import _save_files_to_db

logger = logging.getLogger(__name__)

RENDERS_BASE_DIR = os.environ.get("RENDERS_DIR", "/tmp/musicai_renders")

router = APIRouter()


@router.post("/render")
async def start_render(request: RenderRequest, background_tasks: BackgroundTasks):
    """Start audio rendering pipeline in background (Celery if available, else in-process)."""
    from workers.tasks.render import dispatch_render
    celery_task_id = dispatch_render(
        request.job_id, request.project_id, request.formats, request.output_dir
    )
    if celery_task_id is None:
        background_tasks.add_task(
            run_render_pipeline,
            request.job_id,
            request.project_id,
            request.formats,
            request.output_dir,
        )
    return {
        "jobId": request.job_id,
        "status": "queued",
        "worker": "celery" if celery_task_id else "inprocess",
    }


def run_render_pipeline(
    job_id: str, project_id: int, formats: List[str],
    custom_output_dir: Optional[str],
):
    """Render audio from arrangement tracks in a background thread."""
    from api.database import get_db_connection
    import json

    try:
        update_job(job_id, "running", 5, "Loading arrangement data")

        output_dir = custom_output_dir or os.path.join(RENDERS_BASE_DIR, f"project_{project_id}")
        os.makedirs(output_dir, exist_ok=True)

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tracks_data, total_duration_seconds FROM arrangements "
                    "WHERE project_id=%s ORDER BY id DESC LIMIT 1",
                    (project_id,),
                )
                arr_row = cur.fetchone()
        finally:
            conn.close()

        if not arr_row:
            raise ValueError(f"No arrangement found for project {project_id}")

        tracks = arr_row["tracks_data"]
        if isinstance(tracks, str):
            tracks = json.loads(tracks)
        total_duration = float(arr_row["total_duration_seconds"] or 120.0)

        def progress_callback(step: str, pct: float):
            update_job(job_id, "running", pct, step)

        update_job(job_id, "running", 10, "Starting audio synthesis")

        from audio.render_pipeline import run_audio_render
        results = run_audio_render(
            project_id, tracks, total_duration, formats, output_dir, progress_callback
        )

        _save_files_to_db(project_id, job_id, results)

        update_job(job_id, "completed", 100, "Render complete", result_data={
            "renderedFiles": results,
            "outputDir": output_dir,
        })
        logger.info("Render complete for project %s: %s", project_id, list(results.keys()))

    except Exception as e:
        logger.exception("Render failed for job %s: %s", job_id, e)
        update_job(job_id, "failed", 0, "Render failed", str(e))
