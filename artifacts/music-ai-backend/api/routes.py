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
from orchestration.arranger import generate_arrangement
from audio.style_loader import load_styles, get_style

EXPORTS_BASE_DIR = os.environ.get("EXPORTS_DIR", "/tmp/musicai_exports")
RENDERS_BASE_DIR = os.environ.get("RENDERS_DIR", "/tmp/musicai_renders")

logger = logging.getLogger(__name__)

router = APIRouter()


def _save_files_to_db(project_id: int, job_id: str, results: dict):
    """Save generated file records to project_files table."""
    from api.database import get_db_connection
    if not results:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for fmt, file_path in results.items():
                if not file_path or not os.path.exists(str(file_path)):
                    continue
                file_name = os.path.basename(str(file_path))
                ext = os.path.splitext(file_name)[1].lower().lstrip(".")
                size = os.path.getsize(str(file_path))
                cur.execute(
                    """INSERT INTO project_files (project_id, job_id, file_name, file_path, file_type, file_size_bytes)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (project_id, job_id, file_name, str(file_path), ext, size)
                )
        conn.commit()
        logger.info(f"Saved {len(results)} file records for project {project_id}")
    except Exception as e:
        logger.warning(f"Could not save file records: {e}")
    finally:
        conn.close()


@router.get("/styles")
async def get_styles_endpoint():
    """Return available musical styles from canonical YAML config."""
    styles = load_styles()
    return [
        {
            "id": s["id"],
            "name": s.get("name", s["id"]),
            "nameHe": s.get("nameHe", s.get("name", s["id"])),
            "genre": s.get("genre", ""),
            "genreHe": s.get("genreHe", s.get("genre", "")),
            "description": s.get("description", ""),
            "density_default": s.get("density_default", 0.7),
            "instrumentation": s.get("instrumentation", []),
        }
        for s in styles
    ]


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
    return {"jobId": request.job_id, "status": "queued", "worker": "celery" if celery_task_id else "inprocess"}


@router.post("/arrange")
async def start_arrangement(request: ArrangeRequest, background_tasks: BackgroundTasks):
    """Start arrangement generation in background (Celery if available, else in-process).
    When style_profile is provided, the adapter translates it to arranger args automatically.
    """
    from workers.tasks.arrangement import dispatch_arrangement

    style_id = request.style_id
    instruments = request.instruments
    density = request.density
    persona_id = request.persona_id

    # If StyleProfile provided, derive style args from it via adapter
    if request.style_profile:
        try:
            from orchestration.style_profile_adapter import adapt_profile_to_arranger_args
            placeholder_analysis: dict = {}
            adapted = adapt_profile_to_arranger_args(
                request.style_profile, placeholder_analysis, persona_id
            )
            style_id = adapted.get("style_id", style_id)
            instruments = adapted.get("instruments", instruments)
            density = adapted.get("density", density)
            persona_id = adapted.get("persona_id", persona_id)
        except Exception as e:
            logger.warning(f"StyleProfile adapter error, using defaults: {e}")

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
    return {"jobId": request.job_id, "status": "queued", "worker": "celery" if celery_task_id else "inprocess"}


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

        # Persist audio metadata (duration, sample rate, etc.)
        from api.database import update_project_audio_metadata
        update_project_audio_metadata(project_id, {
            "duration_seconds": result.get("duration"),
            "sample_rate": result.get("sampleRate"),
            "channels": 1,  # loaded as mono
            "codec": None,
        })

        save_analysis_result(project_id, result, pipeline_version="1.0.0")
        update_project_status(project_id, "analyzed")
        update_job(job_id, "completed", 100, "Analysis complete",
                   result_data={"pipeline_version": "1.0.0", "duration": result.get("duration")})
        logger.info(f"Analysis complete for project {project_id}")

    except Exception as e:
        logger.exception(f"Analysis failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Analysis failed", str(e))
        update_project_status(project_id, "error")


def run_arrangement_pipeline(job_id: str, project_id: int, style_id: str,
                              instruments: Optional[List[str]], density: float,
                              do_humanize: bool, tempo_factor: float,
                              persona_id: Optional[str] = None,
                              style_profile: Optional[dict] = None):
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

        # If StyleProfile provided, re-derive analysis patches via adapter
        if style_profile:
            try:
                from orchestration.style_profile_adapter import adapt_profile_to_arranger_args
                adapted = adapt_profile_to_arranger_args(style_profile, analysis, persona_id)
                analysis = adapted["analysis"]
                if not instruments:
                    instruments = adapted.get("instruments", instruments)
            except Exception as adapter_err:
                logger.warning(f"StyleProfile adapter error in pipeline: {adapter_err}")

        arrangement = generate_arrangement(
            analysis, style_id, instruments, density, do_humanize, tempo_factor,
            persona_id=persona_id, style_profile=style_profile,
        )

        update_job(job_id, "running", 80, "Saving arrangement")
        arrangement_plan = {
            "harmonicPlan": arrangement.get("harmonicPlan"),
            "sections": arrangement.get("sections"),
            "profileUsed": arrangement.get("profileUsed"),
        }
        generation_metadata = {
            "bpm": arrangement.get("bpm"),
            "style": style_id,
            "density": density,
            "humanize": do_humanize,
            "tempoFactor": tempo_factor,
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
        logger.info(f"Arrangement complete for project {project_id}")

    except Exception as e:
        logger.exception(f"Arrangement failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Arrangement failed", str(e))
        update_project_status(project_id, "error")


# ── Export Endpoint ──────────────────────────────────────────────────────────

@router.post("/export")
async def start_export(request: ExportRequest, background_tasks: BackgroundTasks):
    """Start export pipeline in background (Celery if available, else in-process)."""
    from workers.tasks.render import dispatch_export
    celery_task_id = dispatch_export(request.job_id, request.project_id, request.formats, request.output_dir)
    if celery_task_id is None:
        background_tasks.add_task(
            run_export_pipeline,
            request.job_id,
            request.project_id,
            request.formats,
            request.output_dir,
        )
    return {"jobId": request.job_id, "status": "queued", "worker": "celery" if celery_task_id else "inprocess"}


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

        _save_files_to_db(project_id, job_id, results)

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
    """Start audio rendering pipeline in background (Celery if available, else in-process)."""
    from workers.tasks.render import dispatch_render
    celery_task_id = dispatch_render(request.job_id, request.project_id, request.formats, request.output_dir)
    if celery_task_id is None:
        background_tasks.add_task(
            run_render_pipeline,
            request.job_id,
            request.project_id,
            request.formats,
            request.output_dir,
        )
    return {"jobId": request.job_id, "status": "queued", "worker": "celery" if celery_task_id else "inprocess"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancel a running or queued job.
    If the job was dispatched via Celery, revoke the Celery task.
    Always marks the DB job as 'cancelled'.
    """
    from api.database import get_db_connection, update_job
    import json

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, result_data FROM jobs WHERE job_id=%s", (job_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")

    status = row["status"]
    if status in ("completed", "failed", "cancelled"):
        return {"jobId": job_id, "status": status, "message": "Already finished"}

    result_data = row["result_data"] or {}
    if isinstance(result_data, str):
        try:
            result_data = json.loads(result_data)
        except Exception:
            result_data = {}

    celery_task_id = result_data.get("celery_task_id")
    revoked = False
    if celery_task_id:
        from workers.celery_app import revoke_task
        revoked = revoke_task(celery_task_id)

    update_job(job_id, "cancelled", None, "Cancelled by user")
    return {"jobId": job_id, "status": "cancelled", "celeryRevoked": revoked}


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

        _save_files_to_db(project_id, job_id, results)

        update_job(job_id, "completed", 100, "Render complete", extra={
            "renderedFiles": results,
            "outputDir": output_dir,
        })
        logger.info(f"Render complete for project {project_id}: {list(results.keys())}")

    except Exception as e:
        logger.exception(f"Render failed for job {job_id}: {e}")
        update_job(job_id, "failed", 0, "Render failed", str(e))
