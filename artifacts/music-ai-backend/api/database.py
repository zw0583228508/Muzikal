"""Database connection and session management for Python backend."""

import os
import asyncio
import json
import logging
from typing import Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_conn_pool: Optional[Any] = None


def get_db_connection():
    """Get a database connection."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return conn


async def init_db():
    """Initialize database - tables created by Node.js drizzle migration."""
    logger.info("Python backend connected to PostgreSQL")


def update_job(job_id: str, status: str, progress: float, current_step: str,
               error_message: str = None, extra: dict = None):
    """Update job progress in DB."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Store extra metadata as JSON in error_message field (reuse for now)
            # In the future we'd add a result_data column
            stored_error = error_message
            if extra and not error_message:
                stored_error = json.dumps(extra)
            if stored_error:
                cur.execute(
                    """UPDATE jobs SET status=%s, progress=%s, current_step=%s, error_message=%s,
                       updated_at=NOW() WHERE job_id=%s""",
                    (status, progress, current_step, stored_error, job_id)
                )
            else:
                cur.execute(
                    """UPDATE jobs SET status=%s, progress=%s, current_step=%s,
                       updated_at=NOW() WHERE job_id=%s""",
                    (status, progress, current_step, job_id)
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
                (status, project_id)
            )
        conn.commit()
    finally:
        conn.close()


def save_analysis_result(project_id: int, result: dict):
    """Save analysis result to DB."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Upsert analysis result
            cur.execute("""
                INSERT INTO analysis_results (project_id, rhythm_data, key_data, chords_data, melody_data, structure_data, waveform_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (project_id) DO UPDATE SET
                    rhythm_data=EXCLUDED.rhythm_data,
                    key_data=EXCLUDED.key_data,
                    chords_data=EXCLUDED.chords_data,
                    melody_data=EXCLUDED.melody_data,
                    structure_data=EXCLUDED.structure_data,
                    waveform_data=EXCLUDED.waveform_data
            """, (
                project_id,
                json.dumps(result.get("rhythm")),
                json.dumps(result.get("key")),
                json.dumps(result.get("chords")),
                json.dumps(result.get("melody")),
                json.dumps(result.get("structure")),
                json.dumps(result.get("waveformData")),
            ))
        conn.commit()
    finally:
        conn.close()


def save_arrangement(project_id: int, style_id: str, tracks: list, duration: float):
    """Save arrangement to DB."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO arrangements (project_id, style_id, tracks_data, total_duration_seconds)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (project_id) DO UPDATE SET
                    style_id=EXCLUDED.style_id,
                    tracks_data=EXCLUDED.tracks_data,
                    total_duration_seconds=EXCLUDED.total_duration_seconds
            """, (project_id, style_id, json.dumps(tracks), duration))
        conn.commit()
    finally:
        conn.close()
