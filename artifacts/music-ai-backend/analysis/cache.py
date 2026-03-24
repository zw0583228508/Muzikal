"""
Disk-backed cache for analysis stages.
Each cache entry is keyed by (file_hash, stage_name).
Stores JSON-serializable results to avoid re-running expensive computations.
"""

from __future__ import annotations

import os
import json
import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_DIR = os.environ.get("ANALYSIS_CACHE_DIR", "/tmp/musicai_analysis_cache")
_TTL_SECONDS = int(os.environ.get("ANALYSIS_CACHE_TTL", str(7 * 24 * 3600)))  # 7 days


def _cache_path(file_hash: str, stage: str) -> Path:
    return Path(_CACHE_DIR) / file_hash[:2] / f"{file_hash}_{stage}.json"


def compute_file_hash(file_path: str) -> str:
    """SHA-256 of the first 2MB + last 2MB + file size (fast, stable)."""
    h = hashlib.sha256()
    size = os.path.getsize(file_path)
    h.update(str(size).encode())
    chunk = 2 * 1024 * 1024
    with open(file_path, "rb") as f:
        h.update(f.read(chunk))
        if size > chunk:
            f.seek(max(0, size - chunk))
            h.update(f.read(chunk))
    return h.hexdigest()


def cache_get(file_hash: str, stage: str) -> Optional[Any]:
    path = _cache_path(file_hash, stage)
    if not path.exists():
        return None
    try:
        if time.time() - path.stat().st_mtime > _TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug("Cache hit: %s/%s", file_hash[:8], stage)
        return data
    except Exception as e:
        logger.debug("Cache read error %s/%s: %s", file_hash[:8], stage, e)
        return None


def cache_set(file_hash: str, stage: str, data: Any) -> None:
    path = _cache_path(file_hash, stage)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), default=str)
        logger.debug("Cache write: %s/%s", file_hash[:8], stage)
    except Exception as e:
        logger.warning("Cache write error %s/%s: %s", file_hash[:8], stage, e)


def cache_invalidate(file_hash: str, stage: str | None = None) -> None:
    """Remove cache entries for a file. If stage is None, removes all stages."""
    cache_dir = Path(_CACHE_DIR) / file_hash[:2]
    prefix = f"{file_hash}_{stage}.json" if stage else file_hash
    for p in cache_dir.glob(f"{file_hash}_*.json"):
        if stage is None or p.name == prefix:
            p.unlink(missing_ok=True)
