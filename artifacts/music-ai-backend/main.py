"""
MusicAI Studio - Python Audio Processing Backend
Handles: Source separation, MIR analysis, chord detection, melody extraction, arrangement generation
"""

import os
import time
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.agent_routes import router as agent_router
from api.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Artifact Lifecycle Management ─────────────────────────────────────────────

ARTIFACT_MAX_AGE_SECONDS = int(os.environ.get("ARTIFACT_MAX_AGE_DAYS", "7")) * 86_400
ARTIFACT_CLEANUP_DIRS = ["exports", "renders"]   # only ephemeral outputs — NOT uploads/stems


def _cleanup_old_artifacts(storage_path: str) -> None:
    """Delete export/render files older than ARTIFACT_MAX_AGE_SECONDS.

    Runs in a background thread at startup. Leaves uploads and stems intact.
    Does nothing if the storage directory doesn't exist yet.
    """
    now = time.time()
    deleted = 0
    freed_bytes = 0

    for subdir in ARTIFACT_CLEANUP_DIRS:
        dir_path = os.path.join(storage_path, subdir)
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                age = now - os.path.getmtime(fpath)
                if age > ARTIFACT_MAX_AGE_SECONDS:
                    size = os.path.getsize(fpath)
                    os.remove(fpath)
                    deleted += 1
                    freed_bytes += size
            except OSError as exc:
                logger.warning("Lifecycle cleanup: could not process %s — %s", fpath, exc)

    if deleted:
        logger.info(
            "Artifact lifecycle: deleted %d old file(s) (%.1f MB freed) from %s",
            deleted,
            freed_bytes / (1024 * 1024),
            storage_path,
        )
    else:
        logger.info("Artifact lifecycle: no stale artifacts found (max_age=%dd)", ARTIFACT_MAX_AGE_SECONDS // 86400)


def _run_lifecycle_cleanup_async(storage_path: str) -> None:
    """Spawn artifact cleanup in a background thread so it doesn't block startup."""
    t = threading.Thread(
        target=_cleanup_old_artifacts,
        args=(storage_path,),
        daemon=True,
        name="artifact-lifecycle-cleanup",
    )
    t.start()


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MusicAI Backend...")

    # ── Model Registry ────────────────────────────────────────────────────────
    try:
        from model_registry import log_registry_summary, validate_registry
        log_registry_summary()
        errs = validate_registry()
        if errs:
            for err in errs:
                logger.error("MODEL REGISTRY VALIDATION: %s", err)
    except Exception as reg_err:
        logger.error("Model registry load failed: %s", reg_err)

    # ── Startup validation ────────────────────────────────────────────────────
    try:
        from startup_validator import run_and_log
        run_and_log(strict=False)   # strict=False: warn but don't hard-fail in dev
    except Exception as val_err:
        logger.error("Startup validation raised: %s", val_err)

    # ── Storage directories ───────────────────────────────────────────────────
    storage_path = os.environ.get("LOCAL_STORAGE_PATH", "/tmp/musicai_storage")
    for subdir in ["exports", "stems", "renders", "uploads"]:
        os.makedirs(os.path.join(storage_path, subdir), exist_ok=True)
    logger.info("Storage initialized at %s", storage_path)

    # ── Artifact lifecycle cleanup (background) ───────────────────────────────
    _run_lifecycle_cleanup_async(storage_path)

    await init_db()
    yield
    logger.info("Shutting down MusicAI Backend...")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MusicAI Studio API",
    description="AI-powered music intelligence and generation backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/python-api")
app.include_router(agent_router, prefix="/agent")


@app.get("/python-api/health")
async def health():
    return {"status": "ok", "service": "music-ai-backend"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PYTHON_BACKEND_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
