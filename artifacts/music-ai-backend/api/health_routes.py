"""Health, model registry, storage, and style endpoints."""

import os
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from model_registry import get_all_models, get_model_by_task
from audio.style_loader import load_styles

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models")
async def get_models_endpoint():
    """Return the full ML model registry used by the analysis pipeline."""
    return get_all_models()


@router.get("/models/{task}")
async def get_model_by_task_endpoint(task: str):
    """Return the active model for a specific pipeline task."""
    model = get_model_by_task(task)
    if model is None:
        raise HTTPException(status_code=404, detail=f"No active model found for task: {task}")
    return model


@router.get("/storage/serve")
async def serve_storage_file(token: str = Query(...)):
    """
    Serve a LocalStorage file identified by a signed JWT token.
    Validates: signature, expiry. Streams the file from LOCAL_STORAGE_PATH.
    """
    import jwt
    from pathlib import Path

    secret = os.environ.get("STORAGE_SECRET", "dev-local-storage-secret")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Download token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=403, detail=f"Invalid download token: {e}")

    key: str = payload.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="Token missing key claim")

    base = Path(os.environ.get("LOCAL_STORAGE_PATH", "/app/storage"))
    file_path = (base / key).resolve()

    if not str(file_path).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal detected")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on storage")

    logger.info("Serving signed storage file: %s", key)
    return FileResponse(path=str(file_path), filename=file_path.name)


@router.get("/storage/presigned")
async def get_presigned_url(key: str):
    """
    Return a short-lived download URL for any storage key (local or S3).

    For LocalStorage: returns a signed JWT URL served by /storage/serve.
    For S3Storage:    returns a boto3 presigned URL (expires=3600s by default).

    Usage:
        GET /python-api/storage/presigned?key=exports/project_1/job_abc/output.mid
    """
    from storage.storage_provider import get_storage
    storage = get_storage()
    url = storage.generate_presigned_url(key, expires=3600)
    return {"url": url, "key": key, "expires": 3600}


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
