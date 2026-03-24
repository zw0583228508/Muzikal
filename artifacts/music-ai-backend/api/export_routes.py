"""Export pipeline endpoints."""

import io
import os
import logging
import tempfile
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.database import update_job
from api.schemas import ExportRequest
from storage.storage_provider import get_storage

logger = logging.getLogger(__name__)

EXPORTS_BASE_DIR = os.environ.get("EXPORTS_DIR", "/tmp/musicai_exports")  # local temp only

router = APIRouter()


def _save_files_to_db(project_id: int, job_id: str, results: dict):
    """Upload generated files to StorageProvider, then record keys in DB."""
    from api.database import get_db_connection
    if not results:
        return

    storage = get_storage()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for fmt, file_path in results.items():
                if not file_path or not os.path.exists(str(file_path)):
                    continue
                file_name = os.path.basename(str(file_path))
                ext = os.path.splitext(file_name)[1].lower().lstrip(".")
                size = os.path.getsize(str(file_path))

                # Upload to storage (S3 or local)
                storage_key = f"exports/project_{project_id}/{job_id}/{file_name}"
                with open(str(file_path), "rb") as f:
                    storage.save(storage_key, f.read())
                logger.debug("Uploaded %s → %s", file_name, storage_key)

                cur.execute(
                    """INSERT INTO project_files
                       (project_id, job_id, file_name, file_path, file_type, file_size_bytes)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (project_id, job_id, file_name, storage_key, ext, size),
                )
        conn.commit()
        logger.info("Uploaded and saved %d file records for project %s", len(results), project_id)
    except Exception as e:
        logger.warning("Could not upload/save file records: %s", e)
    finally:
        conn.close()


@router.post("/export")
async def start_export(request: ExportRequest, background_tasks: BackgroundTasks):
    """Start export pipeline in background (Celery if available, else in-process)."""
    from workers.tasks.render import dispatch_export
    celery_task_id = dispatch_export(
        request.job_id, request.project_id, request.formats, request.output_dir
    )
    if celery_task_id is None:
        background_tasks.add_task(
            run_export_pipeline,
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


def run_export_pipeline(
    job_id: str, project_id: int, formats: List[str],
    custom_output_dir: Optional[str],
):
    """Run export pipeline in a background thread."""
    from api.database import get_db_connection
    import json

    try:
        update_job(job_id, "running", 5, "Preparing export")

        output_dir = custom_output_dir or os.path.join(EXPORTS_BASE_DIR, f"project_{project_id}")
        os.makedirs(output_dir, exist_ok=True)

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rhythm_data, key_data, chords_data, melody_data, structure_data "
                    "FROM analysis_results WHERE project_id=%s",
                    (project_id,),
                )
                analysis_row = cur.fetchone()
                cur.execute(
                    "SELECT tracks_data FROM arrangements WHERE project_id=%s ORDER BY id DESC LIMIT 1",
                    (project_id,),
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

        # ── Validate exported artifacts ──────────────────────────────────────
        update_job(job_id, "running", 90, "Validating exported files")
        validation_summary: dict = {}
        try:
            from audio.export_validator import validate_export, compute_sha256
            for fmt, fpath in results.items():
                if not isinstance(fpath, str) or not fpath:
                    continue
                v = validate_export(fpath)
                checksum = compute_sha256(fpath) if v.ok else None
                validation_summary[fmt] = {
                    "ok":       v.ok,
                    "issues":   v.issues,
                    "warnings": v.warnings,
                    "sha256":   checksum,
                    "metadata": v.metadata,
                }
                if not v.ok:
                    logger.warning(
                        "Export validation FAILED for %s (%s): %s",
                        fmt, fpath, v.issues,
                    )
                else:
                    logger.info("Export validation OK: %s — %s", fmt, v.metadata)
        except Exception as val_err:
            logger.warning("Export validation skipped (non-fatal): %s", val_err)

        _save_files_to_db(project_id, job_id, results)

        update_job(job_id, "completed", 100, "Export complete", result_data={
            "exportedFiles": results,
            "outputDir": output_dir,
            "validation": validation_summary,
        })
        logger.info("Export complete for project %s: %s", project_id, list(results.keys()))

    except Exception as e:
        logger.exception("Export failed for job %s: %s", job_id, e)
        update_job(job_id, "failed", 0, "Export failed", str(e))


@router.post("/projects/{project_id}/export/bundle")
async def export_bundle(project_id: int, formats: List[str] = None):
    """
    Create a ZIP bundle by streaming files from StorageProvider.
    Formats: midi | musicxml | wav | mp3 | flac | stems
    """
    import zipfile as _zipfile
    from fastapi.responses import StreamingResponse
    from api.database import get_db_connection

    if formats is None:
        formats = ["midi", "musicxml", "wav"]

    storage = get_storage()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_name, file_path FROM project_files WHERE project_id=%s",
                (project_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No exports found for this project — export first")

    found_files = [
        (r["file_name"], r["file_path"])
        for r in rows
        if any(r["file_name"].lower().endswith(f".{fmt}") for fmt in formats)
    ]

    if not found_files:
        raise HTTPException(status_code=404, detail="No exported files found for the requested formats")

    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for fname, storage_key in found_files:
            try:
                data = storage.load(storage_key)
                zf.writestr(f"project_{project_id}/{fname}", data)
            except Exception as e:
                logger.warning("Could not load %s from storage: %s", storage_key, e)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=project_{project_id}_bundle.zip"},
    )
