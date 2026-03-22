"""
Celery application for MusicAI Studio.

Broker: Redis (redis://localhost:6379/0 by default, overridden by REDIS_URL).
Graceful fallback: if Redis is unreachable at startup, CELERY_AVAILABLE is set
to False and all callers fall back to FastAPI BackgroundTasks.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_AVAILABLE: bool = False
celery_app = None  # type: ignore[assignment]


def _try_init_celery() -> bool:
    global celery_app, CELERY_AVAILABLE

    try:
        import redis as redis_lib
        client = redis_lib.from_url(REDIS_URL, socket_connect_timeout=2)
        client.ping()
        client.close()
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — Celery disabled, using in-process workers.", exc)
        return False

    try:
        from celery import Celery

        app = Celery(
            "musicai",
            broker=REDIS_URL,
            backend=REDIS_URL,
        )
        app.conf.update(
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
            task_soft_time_limit=600,   # 10 min soft limit
            task_time_limit=720,        # 12 min hard limit
            result_expires=3600,        # results kept 1 h in Redis
        )
        app.autodiscover_tasks(["workers.tasks"])

        celery_app = app
        CELERY_AVAILABLE = True
        logger.info("Celery initialised — broker: %s", REDIS_URL)
        return True

    except Exception as exc:
        logger.warning("Failed to initialise Celery: %s — using in-process workers.", exc)
        return False


_try_init_celery()


def get_celery_app():
    """Return celery app if available, else None."""
    return celery_app if CELERY_AVAILABLE else None


def revoke_task(celery_task_id: str, terminate: bool = True) -> bool:
    """
    Revoke a Celery task by its task ID.
    Returns True if revoke was sent, False if Celery unavailable.
    """
    app = get_celery_app()
    if app is None or not celery_task_id:
        return False
    try:
        app.control.revoke(celery_task_id, terminate=terminate, signal="SIGTERM")
        logger.info("Revoked Celery task %s", celery_task_id)
        return True
    except Exception as exc:
        logger.warning("Failed to revoke Celery task %s: %s", celery_task_id, exc)
        return False
