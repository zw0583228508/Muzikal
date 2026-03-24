"""Database connection and operations for Python backend.

All DB writes go through explicit columns — never store metadata in error_message.
"""

import os
import json
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

# psycopg2 is lazily imported inside functions so that the module can be
# imported safely in environments where psycopg2 is not installed (e.g.
# unit-test runners that use SQLite or a DB-free mode).
try:
    import psycopg2 as _psycopg2
    from psycopg2.extras import RealDictCursor as _RealDictCursor
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _psycopg2 = None  # type: ignore[assignment]
    _RealDictCursor = None  # type: ignore[assignment,misc]
    _PSYCOPG2_AVAILABLE = False


def get_db_connection():
    """Get a database connection (caller must close it).

    Raises RuntimeError if DATABASE_URL is not set or psycopg2 is unavailable.
    """
    if not _PSYCOPG2_AVAILABLE:
        raise RuntimeError(
            "psycopg2 is not installed — cannot connect to PostgreSQL. "
            "Install it with: pip install psycopg2-binary"
        )
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")
    return _psycopg2.connect(database_url, cursor_factory=_RealDictCursor)


async def init_db():
    """Called at startup — tables are managed by Node.js Drizzle migrations."""
    logger.info("Python backend connected to PostgreSQL")


def update_job(
    job_id: str,
    status: str,
    progress: float,
    current_step: str,
    error_message: str = None,
    result_data: dict = None,
    warnings: list = None,
    is_mock: bool = False,
    processing_metadata: dict = None,
):
    """Update job progress in DB.

    - error_message: only for real errors, never for result payloads
    - result_data: structured result payload (replaces old error_message hack)
    - warnings: list of non-fatal warning strings
    - is_mock: True if this job ran in simulation mode
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE jobs SET
                    status=%s,
                    progress=%s,
                    current_step=%s,
                    error_message=%s,
                    result_data=%s,
                    warnings=%s,
                    is_mock=%s,
                    processing_metadata=%s,
                    updated_at=NOW()
                WHERE job_id=%s""",
                (
                    status,
                    progress,
                    current_step,
                    error_message,
                    json.dumps(result_data) if result_data else None,
                    json.dumps(warnings) if warnings else None,
                    is_mock,
                    json.dumps(processing_metadata) if processing_metadata else None,
                    job_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def update_project_status(project_id: int, status: str):
    """Update project status in DB."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE projects SET status=%s, updated_at=NOW() WHERE id=%s",
                (status, project_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_project_audio_metadata(project_id: int, metadata: dict):
    """Persist audio file metadata (duration, sample rate, channels, etc.)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE projects SET
                    audio_duration_seconds=%s,
                    audio_sample_rate=%s,
                    audio_channels=%s,
                    audio_codec=%s,
                    updated_at=NOW()
                WHERE id=%s""",
                (
                    metadata.get("duration_seconds"),
                    metadata.get("sample_rate"),
                    metadata.get("channels"),
                    metadata.get("codec"),
                    project_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def save_analysis_result(project_id: int, result: dict, pipeline_version: str = "1.0.0"):
    """Save full analysis result to DB.

    Stores all computed data including vocals, source separation,
    pipeline version, and model metadata.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analysis_results (
                    project_id,
                    rhythm_data, key_data, chords_data,
                    melody_data, structure_data, waveform_data,
                    vocals_data, source_separation_data,
                    tonal_timeline_data, confidence_data,
                    pipeline_version, model_versions, processing_metadata,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (project_id) DO UPDATE SET
                    rhythm_data = EXCLUDED.rhythm_data,
                    key_data = EXCLUDED.key_data,
                    chords_data = EXCLUDED.chords_data,
                    melody_data = EXCLUDED.melody_data,
                    structure_data = EXCLUDED.structure_data,
                    waveform_data = EXCLUDED.waveform_data,
                    vocals_data = EXCLUDED.vocals_data,
                    source_separation_data = EXCLUDED.source_separation_data,
                    tonal_timeline_data = EXCLUDED.tonal_timeline_data,
                    confidence_data = EXCLUDED.confidence_data,
                    pipeline_version = EXCLUDED.pipeline_version,
                    model_versions = EXCLUDED.model_versions,
                    processing_metadata = EXCLUDED.processing_metadata,
                    updated_at = NOW()
                """,
                (
                    project_id,
                    json.dumps(result.get("rhythm")),
                    json.dumps(result.get("key")),
                    json.dumps(result.get("chords")),
                    json.dumps(result.get("melody")),
                    json.dumps(result.get("structure")),
                    json.dumps(result.get("waveformData")),
                    json.dumps(result.get("vocals")),
                    json.dumps(result.get("sourceSeparation")),
                    json.dumps(result.get("tonalTimeline")),
                    json.dumps(result.get("confidenceData")),
                    pipeline_version,
                    json.dumps(result.get("modelVersions")),
                    json.dumps({
                        **(result.get("processingMetadata") or {}),
                        "canonical":        result.get("canonical"),
                        "cadences":         result.get("cadences"),
                        "harmonicRhythm":   result.get("harmonicRhythm"),
                        "diatonicRatio":    result.get("diatonicRatio"),
                        "qualityFlags":     result.get("qualityFlags"),
                    }),
                ),
            )
        conn.commit()
        logger.info(f"Saved analysis result for project {project_id}")
    finally:
        conn.close()


def get_active_job_for_project(project_id: int, job_type: str) -> Optional[dict]:
    """Return an active (queued/running) job for this project+type, or None.

    Used for idempotency: if a job is already in flight, return it instead
    of creating a duplicate.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT job_id, status, progress, current_step
                   FROM jobs
                   WHERE project_id = %s
                     AND type = %s
                     AND status IN ('queued', 'running')
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (project_id, job_type),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "jobId":       row["job_id"],
            "status":      row["status"],
            "progress":    row["progress"],
            "currentStep": row["current_step"],
        }
    finally:
        conn.close()


def increment_job_retry(job_id: str) -> int:
    """Atomically increment retry_count inside processing_metadata JSONB; returns new count."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Read current metadata
            cur.execute(
                "SELECT processing_metadata FROM jobs WHERE job_id = %s",
                (job_id,),
            )
            row = cur.fetchone()
            current_meta = {}
            if row and row["processing_metadata"]:
                current_meta = row["processing_metadata"] if isinstance(row["processing_metadata"], dict) else json.loads(row["processing_metadata"])
            retry_count = current_meta.get("retryCount", 0) + 1
            current_meta["retryCount"] = retry_count

            cur.execute(
                "UPDATE jobs SET processing_metadata = %s::jsonb, updated_at = NOW() WHERE job_id = %s",
                (json.dumps(current_meta), job_id),
            )
        conn.commit()
        return retry_count
    except Exception as e:
        logger.warning("increment_job_retry failed for %s: %s", job_id, e)
        conn.rollback()
        return 1
    finally:
        conn.close()


def get_analysis_result(project_id: int) -> Optional[dict]:
    """Retrieve the latest analysis result for a project.

    Returns None if no result exists yet.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    rhythm_data, key_data, chords_data,
                    melody_data, structure_data,
                    pipeline_version, model_versions, processing_metadata
                FROM analysis_results
                WHERE project_id = %s
                """,
                (project_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None

        def _load(v):
            if v is None:
                return None
            return json.loads(v) if isinstance(v, str) else v

        processing_meta = _load(row[7]) or {}
        return {
            "rhythm":           _load(row[0]),
            "key":              _load(row[1]),
            "chords":           _load(row[2]),
            "melody":           _load(row[3]),
            "structure":        _load(row[4]),
            "pipelineVersion":  row[5],
            "modelVersions":    _load(row[6]),
            "canonical":        processing_meta.get("canonical"),
            "cadences":         processing_meta.get("cadences"),
            "harmonicRhythm":   processing_meta.get("harmonicRhythm"),
            "diatonicRatio":    processing_meta.get("diatonicRatio"),
            "qualityFlags":     processing_meta.get("qualityFlags", []),
        }
    finally:
        conn.close()


def save_arrangement(
    project_id: int,
    style_id: str,
    tracks: list,
    duration: float,
    arrangement_plan: dict = None,
    generation_metadata: dict = None,
):
    """Save arrangement to DB with versioning.

    Each call creates a new arrangement version and marks all previous
    versions for this project as is_current=False.
    This supports multiple arrangement revisions per project.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Get next version number
            cur.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_ver FROM arrangements WHERE project_id=%s",
                (project_id,),
            )
            row = cur.fetchone()
            next_ver = int(row["next_ver"]) if row else 1

            # Mark all existing as not current
            cur.execute(
                "UPDATE arrangements SET is_current=FALSE, updated_at=NOW() WHERE project_id=%s",
                (project_id,),
            )

            # Insert new current version
            cur.execute(
                """INSERT INTO arrangements (
                    project_id, version_number, is_current,
                    style_id, tracks_data, total_duration_seconds,
                    arrangement_plan, generation_metadata
                ) VALUES (%s, %s, TRUE, %s, %s, %s, %s, %s)""",
                (
                    project_id,
                    next_ver,
                    style_id,
                    json.dumps(tracks),
                    duration,
                    json.dumps(arrangement_plan) if arrangement_plan else None,
                    json.dumps(generation_metadata) if generation_metadata else None,
                ),
            )
        conn.commit()
        logger.info(f"Saved arrangement v{next_ver} for project {project_id} (style={style_id})")
    finally:
        conn.close()
