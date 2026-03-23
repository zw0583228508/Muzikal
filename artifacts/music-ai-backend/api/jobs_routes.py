"""Job management endpoints (cancel, status)."""

import logging

from fastapi import APIRouter, HTTPException

from api.database import update_job

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancel a running or queued job.
    If dispatched via Celery, revokes the Celery task.
    Always marks the DB job as 'cancelled'.
    """
    from api.database import get_db_connection
    import json

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, result_data FROM jobs WHERE job_id=%s", (job_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
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
    logger.info("Job %s cancelled (celeryRevoked=%s)", job_id, revoked)
    return {"jobId": job_id, "status": "cancelled", "celeryRevoked": revoked}
