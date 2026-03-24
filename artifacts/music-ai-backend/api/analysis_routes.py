"""Analysis pipeline endpoints — v2 (high-accuracy multi-stage pipeline)."""

import logging
import os

from fastapi import APIRouter, BackgroundTasks

from api.database import update_job, update_project_status, save_analysis_result
from api.schemas import AnalyzeRequest

logger = logging.getLogger(__name__)

router = APIRouter()

PIPELINE_VERSION = "2.0.0"


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
            request.mode,
        )
    return {
        "jobId": request.job_id,
        "status": "queued",
        "worker": "celery" if celery_task_id else "inprocess",
        "mode": request.mode,
        "pipelineVersion": PIPELINE_VERSION,
    }


def run_analysis_pipeline(job_id: str, project_id: int, audio_file_path: str, mode: str = "balanced"):
    """
    Run the full analysis pipeline synchronously in a background thread.
    Uses the new high-accuracy multi-stage pipeline (analysis.pipeline).
    Falls back to the legacy audio.analyzer if the new pipeline fails.
    """
    try:
        update_job(job_id, "running", 3, "Preprocessing audio")
        update_project_status(project_id, "analyzing")

        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        # ─── Primary: new high-accuracy pipeline ──────────────────────────────
        update_job(job_id, "running", 8, f"Starting {mode} analysis pipeline")
        result = _run_new_pipeline(audio_file_path, mode, job_id)

        # ─── Update project audio metadata from result ─────────────────────────
        from api.database import update_project_audio_metadata
        meta = result.get("stems", {})
        audio_meta_raw = result.get("audioMeta", result.get("audio_meta", {}))
        update_project_audio_metadata(project_id, {
            "duration_seconds": audio_meta_raw.get("duration") or result.get("duration"),
            "sample_rate": audio_meta_raw.get("sample_rate") or result.get("sampleRate"),
            "channels": audio_meta_raw.get("channels", 1),
            "codec": None,
        })

        save_analysis_result(project_id, result, pipeline_version=PIPELINE_VERSION)
        update_project_status(project_id, "analyzed")
        update_job(
            job_id, "completed", 100, "Analysis complete",
            result_data={
                "pipeline_version": PIPELINE_VERSION,
                "mode": mode,
                "duration": audio_meta_raw.get("duration"),
                "global_confidence": result.get("globalConfidence", 0),
            },
        )
        logger.info("Analysis complete for project %s (mode=%s)", project_id, mode)

    except Exception as e:
        logger.exception("Analysis failed for job %s: %s", job_id, e)
        # ─── Fallback to legacy pipeline on failure ────────────────────────────
        try:
            logger.warning("Trying legacy pipeline fallback for job %s", job_id)
            update_job(job_id, "running", 5, "Falling back to legacy pipeline")
            _run_legacy_pipeline(job_id, project_id, audio_file_path)
        except Exception as legacy_err:
            logger.exception("Legacy pipeline also failed: %s", legacy_err)
            update_job(job_id, "failed", 0, "Analysis failed", str(e))
            update_project_status(project_id, "error")


def _run_new_pipeline(audio_file_path: str, mode: str, job_id: str) -> dict:
    """Run the new analysis.pipeline and return legacy-format dict."""
    from analysis.pipeline import analyze_to_dict
    return analyze_to_dict(audio_file_path, mode=mode)


def _run_legacy_pipeline(job_id: str, project_id: int, audio_file_path: str) -> None:
    """Fallback to the original audio.analyzer pipeline."""
    from audio.analyzer import run_full_analysis
    from api.database import update_project_audio_metadata

    def progress_callback(step: str, pct: float):
        update_job(job_id, "running", pct, step)

    result = run_full_analysis(audio_file_path, project_id, progress_callback)

    update_project_audio_metadata(project_id, {
        "duration_seconds": result.get("duration"),
        "sample_rate": result.get("sampleRate"),
        "channels": 1,
        "codec": None,
    })

    save_analysis_result(project_id, result, pipeline_version="1.0.0-legacy")
    update_project_status(project_id, "analyzed")
    update_job(
        job_id, "completed", 100, "Analysis complete (legacy)",
        result_data={"pipeline_version": "1.0.0-legacy", "duration": result.get("duration")},
    )
    logger.info("Legacy analysis complete for project %s", project_id)
