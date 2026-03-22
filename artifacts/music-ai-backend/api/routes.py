"""
Python Backend API Routes.
Handles heavy processing: audio analysis, arrangement generation.
"""

import os
import uuid
import asyncio
import logging
import threading
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from api.schemas import AnalyzeRequest, ArrangeRequest
from api.database import update_job, update_project_status, save_analysis_result, save_arrangement
from orchestration.arranger import generate_arrangement, STYLES

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/styles")
async def get_styles():
    """Return available musical styles."""
    return [
        {
            "id": style_id,
            "name": config["name"],
            "genre": config["genre"],
            "description": config["description"],
            "tags": config["tags"],
        }
        for style_id, config in STYLES.items()
    ]


@router.post("/analyze")
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Start audio analysis pipeline in background."""
    background_tasks.add_task(
        run_analysis_pipeline,
        request.job_id,
        request.project_id,
        request.audio_file_path,
    )
    return {"jobId": request.job_id, "status": "queued"}


@router.post("/arrange")
async def start_arrangement(request: ArrangeRequest, background_tasks: BackgroundTasks):
    """Start arrangement generation in background."""
    background_tasks.add_task(
        run_arrangement_pipeline,
        request.job_id,
        request.project_id,
        request.style_id,
        request.instruments,
        request.density,
        request.humanize,
        request.tempo_factor,
    )
    return {"jobId": request.job_id, "status": "queued"}


def run_analysis_pipeline(job_id: str, project_id: int, audio_file_path: str):
    """Run the full analysis pipeline synchronously in background thread."""
    from audio.analyzer import run_full_analysis

    try:
        update_job(job_id, "running", 5, "Starting analysis pipeline")
        update_project_status(project_id, "analyzing")

        steps = [
            ("Loading audio", 5),
            ("Generating waveform", 10),
            ("Analyzing rhythm and tempo", 20),
            ("Detecting key and mode", 40),
            ("Analyzing chord progressions", 55),
            ("Extracting melody", 70),
            ("Detecting song structure", 85),
            ("Finalizing results", 95),
        ]

        def progress_callback(step: str, pct: float):
            update_job(job_id, "running", pct, step)

        result = run_full_analysis(audio_file_path, project_id, progress_callback)

        save_analysis_result(project_id, result)
        update_project_status(project_id, "analyzed")
        update_job(job_id, "completed", 100, "Analysis complete")
        logger.info(f"Analysis complete for project {project_id}")

    except Exception as e:
        logger.exception(f"Analysis failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Analysis failed", str(e))
        update_project_status(project_id, "error")


def run_arrangement_pipeline(job_id: str, project_id: int, style_id: str,
                              instruments: Optional[List[str]], density: float,
                              do_humanize: bool, tempo_factor: float):
    """Run arrangement generation in background."""
    from api.database import get_db_connection
    import json

    try:
        update_job(job_id, "running", 10, "Loading analysis data")
        update_project_status(project_id, "arranging")

        # Load analysis from DB
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rhythm_data, key_data, chords_data, melody_data, structure_data FROM analysis_results WHERE project_id=%s",
                    (project_id,)
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

        arrangement = generate_arrangement(
            analysis, style_id, instruments, density, do_humanize, tempo_factor
        )

        update_job(job_id, "running", 80, "Saving arrangement")
        save_arrangement(project_id, style_id, arrangement["tracks"], arrangement["totalDurationSeconds"])

        update_project_status(project_id, "arranged")
        update_job(job_id, "completed", 100, "Arrangement complete")
        logger.info(f"Arrangement complete for project {project_id}")

    except Exception as e:
        logger.exception(f"Arrangement failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Arrangement failed", str(e))
        update_project_status(project_id, "error")
