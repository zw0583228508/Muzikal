"""Arrangement generation endpoints."""

import logging
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks

from api.database import update_job, update_project_status, save_arrangement
from api.schemas import ArrangeRequest
from orchestration.arrangement_planner import generate_arrangement_two_stage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/arrange")
async def start_arrangement(request: ArrangeRequest, background_tasks: BackgroundTasks):
    """Start arrangement generation in background (Celery if available, else in-process)."""
    from workers.tasks.arrangement import dispatch_arrangement

    style_id = request.style_id
    instruments = request.instruments
    density = request.density
    persona_id = request.persona_id

    if request.style_profile:
        try:
            from orchestration.style_profile_adapter import adapt_profile_to_arranger_args
            adapted = adapt_profile_to_arranger_args(request.style_profile, {}, persona_id)
            style_id = adapted.get("style_id", style_id)
            instruments = adapted.get("instruments", instruments)
            density = adapted.get("density", density)
            persona_id = adapted.get("persona_id", persona_id)
        except Exception as e:
            logger.warning("StyleProfile adapter error, using defaults: %s", e)

    celery_task_id = dispatch_arrangement(
        request.job_id, request.project_id, style_id,
        instruments, density, request.humanize,
        request.tempo_factor, persona_id,
    )
    if celery_task_id is None:
        background_tasks.add_task(
            run_arrangement_pipeline,
            request.job_id,
            request.project_id,
            style_id,
            instruments,
            density,
            request.humanize,
            request.tempo_factor,
            persona_id,
            request.style_profile,
        )
    return {
        "jobId": request.job_id,
        "status": "queued",
        "worker": "celery" if celery_task_id else "inprocess",
    }


def run_arrangement_pipeline(
    job_id: str, project_id: int, style_id: str,
    instruments: Optional[List[str]], density: float,
    do_humanize: bool, tempo_factor: float,
    persona_id: Optional[str] = None,
    style_profile: Optional[dict] = None,
):
    """Run arrangement generation in a background thread."""
    from api.database import get_db_connection
    import json

    try:
        update_job(job_id, "running", 10, "Loading analysis data")
        update_project_status(project_id, "arranging")

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rhythm_data, key_data, chords_data, melody_data, structure_data "
                    "FROM analysis_results WHERE project_id=%s",
                    (project_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            raise ValueError(f"No analysis found for project {project_id}")

        analysis = {
            "rhythm": row["rhythm_data"],
            "key": row["key_data"],
            "chords": row["chords_data"],
            "melody": row["melody_data"],
            "structure": row["structure_data"],
        }

        update_job(job_id, "running", 30, "Generating arrangement structure")

        if style_profile:
            try:
                from orchestration.style_profile_adapter import adapt_profile_to_arranger_args
                adapted = adapt_profile_to_arranger_args(style_profile, analysis, persona_id)
                analysis = adapted["analysis"]
                if not instruments:
                    instruments = adapted.get("instruments", instruments)
            except Exception as adapter_err:
                logger.warning("StyleProfile adapter error in pipeline: %s", adapter_err)

        arrangement = generate_arrangement_two_stage(
            analysis, style_id=style_id, density=density,
            instruments=instruments or [], do_humanize=do_humanize,
            tempo_factor=tempo_factor, persona_id=persona_id,
            style_profile=style_profile,
        )

        update_job(job_id, "running", 80, "Saving arrangement")
        arrangement_plan = {
            "harmonicPlan": arrangement.get("harmonicPlan"),
            "sections": arrangement.get("sections"),
            "blueprintSummary": arrangement.get("blueprintSummary"),
            "source": arrangement.get("source"),
        }
        generation_metadata = {
            "bpm": arrangement.get("bpm"),
            "style": style_id,
            "density": density,
            "humanize": do_humanize,
            "tempoFactor": tempo_factor,
            "plannerVersion": "two_stage_v1",
        }
        save_arrangement(
            project_id,
            style_id,
            arrangement.get("tracks", []),
            arrangement.get("totalDurationSeconds", 0),
            arrangement_plan=arrangement_plan,
            generation_metadata=generation_metadata,
        )

        update_project_status(project_id, "arranged")
        update_job(job_id, "completed", 100, "Arrangement complete")
        logger.info("Arrangement complete for project %s", project_id)

    except Exception as e:
        logger.exception("Arrangement failed for job %s: %s", job_id, e)
        update_job(job_id, "failed", 0, "Arrangement failed", str(e))
        update_project_status(project_id, "error")
