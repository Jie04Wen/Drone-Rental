"""Local and MinIO storage implementations from Java StorageService."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .config import Settings

LOGGER = logging.getLogger(__name__)


class StorageService(ABC):
    @abstractmethod
    def upload(
        self,
        filename: str,
        content: bytes,
        content_type: str | None,
        object_prefix: str,
    ) -> str: ...

    @abstractmethod
    def delete(self, object_key: str) -> bool: ...

    @abstractmethod
    def get_access_url(self, stored_value: str) -> str | None: ...


def split_object_keys(stored_values: str | None) -> list[str]:
    """Split comma-separated object keys without accepting empty entries."""
    if not stored_values:
        return []
    return [item.strip() for item in stored_values.split(",") if item.strip()]


def _safe_object_key(value: str) -> str | None:
    key = value.strip().lstrip("/")
    if not key or "\\" in key or any(part in ("", ".", "..") for part in key.split("/")):
        return None
    return key


class LocalStorageService(StorageService):
    """对应 Java：LocalStorageService.java。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.upload_dir = settings.upload_path.resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def upload(
        self,
        filename: str,
        content: bytes,
        content_type: str | None,
        object_prefix: str,
    ) -> str:
        extension = Path(filename).suffix
        object_key = f"{object_prefix.strip('/')}/{uuid4().hex}{extension}"
        target = (self.upload_dir / Path(object_key)).resolve()
        if self.upload_dir not in target.parents:
            raise ValueError("Invalid storage object prefix")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return object_key

    def delete(self, object_key: str) -> bool:
        key = object_key.removeprefix(self.settings.upload_access_url)
        candidate = (self.upload_dir / key).resolve()
        if self.upload_dir not in candidate.parents:
            return False
        try:
            candidate.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            LOGGER.warning("Local storage delete failed: %s", object_key, exc_info=True)
            return False

    def get_access_url(self, stored_value: str) -> str | None:
        value = stored_value.strip()
        if not value:
            return None
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith(self.settings.upload_access_url):
            return value
        key = _safe_object_key(value)
        return self.settings.upload_access_url.rstrip("/") + "/" + key if key else None


class MinioStorageService(StorageService):
    """对应 Java：MinioStorageService.java。"""

    def __init__(self, settings: Settings):
        from minio import Minio

        self.settings = settings
        endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")
        self.secure = settings.minio_endpoint.startswith("https://")
        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=self.secure,
            region=settings.minio_region or None,
        )
        try:
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
        except Exception:
            LOGGER.error("MinIO bucket initialization failed", exc_info=True)

    def upload(
        self,
        filename: str,
        content: bytes,
        content_type: str | None,
        object_prefix: str,
    ) -> str:
        object_name = f"{object_prefix.strip('/')}/{uuid4().hex}{Path(filename).suffix}"
        self.client.put_object(
            self.settings.minio_bucket,
            object_name,
            BytesIO(content),
            len(content),
            content_type=content_type or "application/octet-stream",
        )
        # 数据库仅保存稳定对象键，绝不保存会过期的预签名 URL。
        return object_name

    def delete(self, object_key: str) -> bool:
        object_name = self._extract_object_name(object_key)
        if object_name is None:
            return False
        try:
            self.client.remove_object(self.settings.minio_bucket, object_name)
            return True
        except Exception:
            LOGGER.warning("MinIO delete failed: %s", object_key, exc_info=True)
            return False

    def get_presigned_url(self, object_name: str) -> str | None:
        """Generate a short-lived private download URL."""
        try:
            return self.client.presigned_get_object(
                self.settings.minio_bucket,
                object_name,
                expires=timedelta(
                    seconds=max(60, min(self.settings.minio_presigned_expiry_seconds, 604800))
                ),
            )
        except Exception:
            LOGGER.error("MinIO presigned URL failed", exc_info=True)
            return None

    def get_access_url(self, stored_value: str) -> str | None:
        value = stored_value.strip()
        if not value:
            return None
        object_name = self._extract_object_name(value)
        if object_name is not None:
            return self.get_presigned_url(object_name)
        # 保留外部 CDN URL 和迁移前仍由本地 /uploads 提供的资源。
        if value.startswith(("http://", "https://", self.settings.upload_access_url)):
            return value
        return None

    def _extract_object_name(self, stored_value: str) -> str | None:
        value = stored_value.strip()
        marker = f"/{self.settings.minio_bucket}/"
        if marker in value:
            return _safe_object_key(value.split(marker, 1)[1])
        if value.startswith(("http://", "https://")):
            return None
        if value.startswith(self.settings.upload_access_url):
            return None
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc:
            return None
        return _safe_object_key(value)


def access_urls(storage: StorageService, stored_values: str | None) -> list[str]:
    """Resolve stored object keys while remaining compatible with legacy URLs."""
    return [url for value in split_object_keys(stored_values) if (url := storage.get_access_url(value))]


def get_storage(settings: Settings) -> StorageService:
    if settings.storage_type.lower() == "minio":
        return MinioStorageService(settings)
    return LocalStorageService(settings)
