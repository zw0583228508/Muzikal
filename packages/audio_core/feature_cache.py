"""
Feature extraction cache — keyed by audio file checksum.
Stores computed audio features to disk as JSON so they can be reused
across analysis jobs on the same audio without recomputing.

Usage:
    from audio_core.feature_cache import FeatureCache

    cache = FeatureCache()
    cached = cache.get(file_hash, "rhythm")
    if cached is None:
        result = analyze_rhythm(y, sr)
        cache.set(file_hash, "rhythm", result)
    else:
        result = cached
"""

import os
import json
import logging
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default cache directory — overridable via environment variable
_DEFAULT_CACHE_DIR = os.environ.get(
    "FEATURE_CACHE_DIR",
    os.path.join(os.path.expanduser("~"), ".musicai_feature_cache"),
)

# Cache TTL: 7 days (features rarely change for the same audio)
_DEFAULT_TTL_SECONDS = int(os.environ.get("FEATURE_CACHE_TTL", str(7 * 24 * 3600)))

# Valid feature keys
FEATURE_KEYS = frozenset([
    "rhythm", "key", "chords", "melody", "structure",
    "vocals", "waveform", "ingestion", "confidence",
    "tonal_timeline", "source_separation",
])


class FeatureCache:
    """
    Disk-based feature cache for audio analysis results.

    Directory layout:
        <cache_dir>/
            <file_hash[:2]>/   (sharded by first 2 chars of hash)
                <file_hash>.json   (all features for this audio)
    """

    def __init__(
        self,
        cache_dir: str = _DEFAULT_CACHE_DIR,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ):
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"FeatureCache initialized at {self.cache_dir}, TTL={ttl_seconds}s")

    def _shard_dir(self, file_hash: str) -> Path:
        return self.cache_dir / file_hash[:2]

    def _cache_path(self, file_hash: str) -> Path:
        return self._shard_dir(file_hash) / f"{file_hash}.json"

    def _load_record(self, file_hash: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(file_hash)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                record = json.load(f)
            age = time.time() - record.get("_cached_at", 0)
            if age > self.ttl_seconds:
                logger.info(f"Cache expired for {file_hash[:8]} (age={age:.0f}s)")
                path.unlink(missing_ok=True)
                return None
            return record
        except Exception as exc:
            logger.warning(f"Failed to read cache for {file_hash[:8]}: {exc}")
            return None

    def _save_record(self, file_hash: str, record: Dict[str, Any]) -> None:
        shard = self._shard_dir(file_hash)
        shard.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(file_hash)
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(record, f, allow_nan=False, separators=(",", ":"))
            tmp.replace(path)
        except Exception as exc:
            logger.warning(f"Failed to write cache for {file_hash[:8]}: {exc}")
            tmp.unlink(missing_ok=True)

    def get(self, file_hash: str, feature_key: str) -> Optional[Any]:
        """
        Retrieve a cached feature for the given audio hash and feature key.
        Returns None if not cached or expired.
        """
        if not file_hash or feature_key not in FEATURE_KEYS:
            return None
        record = self._load_record(file_hash)
        if record is None:
            return None
        value = record.get(feature_key)
        if value is not None:
            logger.info(f"Cache HIT: {file_hash[:8]} / {feature_key}")
        return value

    def set(self, file_hash: str, feature_key: str, value: Any) -> None:
        """
        Store a computed feature in the cache.
        """
        if not file_hash or feature_key not in FEATURE_KEYS:
            return
        record = self._load_record(file_hash) or {}
        record["_file_hash"] = file_hash
        record["_cached_at"] = time.time()
        record[feature_key] = value
        self._save_record(file_hash, record)
        logger.info(f"Cache SET: {file_hash[:8]} / {feature_key}")

    def get_all(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Return all cached features for the given audio hash."""
        if not file_hash:
            return None
        record = self._load_record(file_hash)
        if not record:
            return None
        return {k: v for k, v in record.items() if k in FEATURE_KEYS}

    def has(self, file_hash: str, feature_key: str) -> bool:
        """Check if a feature is cached without loading it."""
        if not file_hash or feature_key not in FEATURE_KEYS:
            return False
        record = self._load_record(file_hash)
        return record is not None and feature_key in record

    def invalidate(self, file_hash: str) -> None:
        """Remove all cached features for a given audio hash."""
        path = self._cache_path(file_hash)
        path.unlink(missing_ok=True)
        logger.info(f"Cache INVALIDATED: {file_hash[:8]}")

    def clear_all(self) -> int:
        """Remove all cached entries. Returns count of removed files."""
        count = 0
        for json_file in self.cache_dir.glob("**/*.json"):
            json_file.unlink(missing_ok=True)
            count += 1
        logger.info(f"Cache CLEARED: {count} entries removed")
        return count

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        files = list(self.cache_dir.glob("**/*.json"))
        total_bytes = sum(f.stat().st_size for f in files if f.exists())
        return {
            "cache_dir": str(self.cache_dir),
            "entry_count": len(files),
            "total_size_mb": round(total_bytes / 1024 / 1024, 2),
            "ttl_seconds": self.ttl_seconds,
        }


def hash_file(file_path: str) -> str:
    """Compute SHA-256 checksum of a file for use as cache key."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# Module-level singleton — shared across all callers in the same process
_default_cache: Optional[FeatureCache] = None


def get_default_cache() -> FeatureCache:
    """Return the process-level singleton FeatureCache."""
    global _default_cache
    if _default_cache is None:
        _default_cache = FeatureCache()
    return _default_cache
