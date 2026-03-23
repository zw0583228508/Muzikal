"""Analysis pipeline endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks

from api.database import update_job, update_project_status, save_analysis_result
from api.schemas import AnalyzeRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze")
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Start audio analysis pipeline in background (Celery if available, else in-process)."""
    from workers.tasks.analysis import dispatch_analysis
    celery_task_id = dispatch_analysis(request.job_id, request.project_id, request.audio_file_path)
    if celery_task_id is None:
        background_tasks.add_task(
            run_analysis_pipeline,
            request.job_id,
            request.project_id,
            request.audio_file_path,
        )
    return {
        "jobId": request.job_id,
        "status": "queued",
        "worker": "celery" if celery_task_id else "inprocess",
    }


def run_analysis_pipeline(job_id: str, project_id: int, audio_file_path: str):
    """Run the full analysis pipeline synchronously in a background thread."""
    from audio.analyzer import run_full_analysis

    try:
        update_job(job_id, "running", 5, "Starting analysis pipeline")
        update_project_status(project_id, "analyzing")

        def progress_callback(step: str, pct: float):
            update_job(job_id, "running", pct, step)

        result = run_full_analysis(audio_file_path, project_id, progress_callback)

        from api.database import update_project_audio_metadata
        update_project_audio_metadata(project_id, {
            "duration_seconds": result.get("duration"),
            "sample_rate": result.get("sampleRate"),
            "channels": 1,
            "codec": None,
        })

        save_analysis_result(project_id, result, pipeline_version="1.0.0")
        update_project_status(project_id, "analyzed")
        update_job(
            job_id, "completed", 100, "Analysis complete",
            result_data={"pipeline_version": "1.0.0", "duration": result.get("duration")},
        )
        logger.info("Analysis complete for project %s", project_id)

    except Exception as e:
        logger.exception("Analysis failed for job %s: %s", job_id, e)
        update_job(job_id, "failed", 0, "Analysis failed", str(e))
        update_project_status(project_id, "error")
