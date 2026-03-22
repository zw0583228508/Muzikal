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

from api.schemas import AnalyzeRequest, ArrangeRequest, ExportRequest, RenderRequest
from api.database import update_job, update_project_status, save_analysis_result, save_arrangement
from orchestration.arranger import generate_arrangement, STYLES

EXPORTS_BASE_DIR = os.environ.get("EXPORTS_DIR", "/tmp/musicai_exports")
RENDERS_BASE_DIR = os.environ.get("RENDERS_DIR", "/tmp/musicai_renders")

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


# ── Export Endpoint ──────────────────────────────────────────────────────────

@router.post("/export")
async def start_export(request: ExportRequest, background_tasks: BackgroundTasks):
    """Start export pipeline in background."""
    background_tasks.add_task(
        run_export_pipeline,
        request.job_id,
        request.project_id,
        request.formats,
        request.output_dir,
    )
    return {"jobId": request.job_id, "status": "queued"}


def run_export_pipeline(job_id: str, project_id: int, formats: List[str],
                         custom_output_dir: Optional[str]):
    """Run export pipeline in background."""
    from api.database import get_db_connection
    import json

    try:
        update_job(job_id, "running", 5, "Preparing export")

        output_dir = custom_output_dir or os.path.join(EXPORTS_BASE_DIR, f"project_{project_id}")
        os.makedirs(output_dir, exist_ok=True)

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Load analysis
                cur.execute(
                    "SELECT rhythm_data, key_data, chords_data, melody_data, structure_data FROM analysis_results WHERE project_id=%s",
                    (project_id,)
                )
                analysis_row = cur.fetchone()

                # Load arrangement
                cur.execute(
                    "SELECT tracks_data FROM arrangements WHERE project_id=%s ORDER BY id DESC LIMIT 1",
                    (project_id,)
                )
                arr_row = cur.fetchone()
        finally:
            conn.close()

        if not analysis_row:
            raise ValueError(f"No analysis found for project {project_id}")

        analysis = {
            "rhythm": analysis_row["rhythm_data"],
            "key": analysis_row["key_data"],
            "chords": analysis_row["chords_data"],
            "melody": analysis_row["melody_data"],
            "structure": analysis_row["structure_data"],
        }

        arrangement = {}
        if arr_row:
            tracks = arr_row["tracks_data"]
            if isinstance(tracks, str):
                tracks = json.loads(tracks)
            arrangement = {"tracks": tracks}

        update_job(job_id, "running", 20, "Exporting files")

        from audio.export_engine import run_export
        results = run_export(project_id, analysis, arrangement, formats, output_dir)

        update_job(job_id, "completed", 100, "Export complete", extra={
            "exportedFiles": results,
            "outputDir": output_dir,
        })
        logger.info(f"Export complete for project {project_id}: {list(results.keys())}")

    except Exception as e:
        logger.exception(f"Export failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Export failed", str(e))


# ── Render Endpoint (Audio Synthesis) ────────────────────────────────────────

@router.post("/render")
async def start_render(request: RenderRequest, background_tasks: BackgroundTasks):
    """Start audio rendering pipeline in background."""
    background_tasks.add_task(
        run_render_pipeline,
        request.job_id,
        request.project_id,
        request.formats,
        request.output_dir,
    )
    return {"jobId": request.job_id, "status": "queued"}


def run_render_pipeline(job_id: str, project_id: int, formats: List[str],
                         custom_output_dir: Optional[str]):
    """Render audio from arrangement tracks."""
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
                    "SELECT tracks_data, total_duration_seconds FROM arrangements WHERE project_id=%s ORDER BY id DESC LIMIT 1",
                    (project_id,)
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

        update_job(job_id, "completed", 100, "Render complete", extra={
            "renderedFiles": results,
            "outputDir": output_dir,
        })
        logger.info(f"Render complete for project {project_id}: {list(results.keys())}")

    except Exception as e:
        logger.exception(f"Render failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Render failed", str(e))
