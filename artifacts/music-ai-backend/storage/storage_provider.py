"""
Storage abstraction layer — Phase 5.4.

Supports:
  - LocalStorage  : writes files under /tmp/muzikal (default dev/CI)
  - S3Storage     : writes to an S3-compatible bucket when S3_ENDPOINT is set

Usage:
    from storage.storage_provider import get_storage
    storage = get_storage()
    path = storage.save("project_1/stems/drums.wav", audio_bytes)
    url  = storage.get_url("project_1/stems/drums.wav")
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageProvider(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """Persist data under key. Returns a local path or remote URI."""

    @abstractmethod
    def load(self, key: str) -> bytes:
        """Load raw bytes for the given key."""

    @abstractmethod
    def get_url(self, key: str, expires: int = 3600) -> str:
        """Return a URL (presigned or direct) for the given key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the key exists in storage."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a stored object."""


class LocalStorage(StorageProvider):
    """File-system storage — suitable for development and single-node deployments."""

    def __init__(self, base_path: str | None = None):
        self.base = Path(base_path or os.environ.get("LOCAL_STORAGE_PATH", "/tmp/muzikal"))
        self.base.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorage initialised at %s", self.base)

    def _path(self, key: str) -> Path:
        return self.base / key

    def save(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        logger.debug("LocalStorage.save: %s (%d bytes)", key, len(data))
        return str(p)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def get_url(self, key: str, expires: int = 3600) -> str:
        return f"/api/storage/{key}"

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3Storage(StorageProvider):
    """S3-compatible object storage (AWS S3, MinIO, Cloudflare R2, etc.)."""

    def __init__(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3Storage. Run: pip install boto3") from exc

        self._boto3 = boto3
        endpoint = os.environ.get("S3_ENDPOINT")
        access_key = os.environ.get("S3_ACCESS_KEY")
        secret_key = os.environ.get("S3_SECRET_KEY")
        self.bucket = os.environ.get("S3_BUCKET", "muzikal")

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        logger.info("S3Storage initialised — bucket=%s endpoint=%s", self.bucket, endpoint)

    def save(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        logger.debug("S3Storage.save: s3://%s/%s (%d bytes)", self.bucket, key, len(data))
        return f"s3://{self.bucket}/{key}"

    def load(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def get_url(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_instance: StorageProvider | None = None


def get_storage() -> StorageProvider:
    """
    Factory — returns the appropriate storage backend based on environment.
    S3Storage is used when S3_ENDPOINT is set; otherwise LocalStorage.
    Result is cached as a module-level singleton.
    """
    global _instance
    if _instance is not None:
        return _instance

    if os.environ.get("S3_ENDPOINT"):
        _instance = S3Storage()
    else:
        _instance = LocalStorage()

    return _instance
