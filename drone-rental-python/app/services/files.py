"""Private object-storage naming, ownership validation, and response signing."""

from __future__ import annotations

from typing import Any

from ..common import BusinessException, C, ResultCode
from ..config import Settings
from ..security import CurrentUser
from ..storage import StorageService, access_urls, split_object_keys


USER_CATEGORIES = {
    "avatar": "avatars",
    "qualification": "qualifications",
    "fault": "faults",
    "comment": "comments",
}


def upload_prefix(category: str, current: CurrentUser) -> str:
    """Return a server-controlled prefix; clients cannot provide raw paths."""
    normalized = category.strip().lower()
    if normalized == "drone":
        if current.role != C.ROLE_ADMIN:
            raise BusinessException(ResultCode.FORBIDDEN)
        return "drones"
    directory = USER_CATEGORIES.get(normalized)
    if directory is None:
        raise BusinessException(ResultCode.PARAM_ERROR, "不支持的文件业务类型")
    return f"users/{current.user_id}/{directory}"


def validate_owned_keys(stored_values: str | None, user_id: int, category: str) -> None:
    """Reject URLs and keys outside the current user's business prefix."""
    if not stored_values:
        return
    directory = USER_CATEGORIES.get(category)
    if directory is None:
        raise BusinessException(ResultCode.PARAM_ERROR, "不支持的文件业务类型")
    expected = f"users/{user_id}/{directory}/"
    keys = split_object_keys(stored_values)
    if not keys or any(not key.startswith(expected) for key in keys):
        raise BusinessException(ResultCode.FORBIDDEN, "文件不属于当前用户或业务类型")


def validate_drone_keys(stored_values: str | None) -> None:
    if not stored_values:
        return
    keys = split_object_keys(stored_values)
    if not keys or any(not key.startswith("drones/") for key in keys):
        raise BusinessException(ResultCode.PARAM_ERROR, "无人机图片必须通过设备图片上传接口提交")


def signed_file_data(
    storage: StorageService,
    stored_values: str | None,
    settings: Settings,
) -> dict[str, Any]:
    urls = access_urls(storage, stored_values)
    return {
        "objectKey": stored_values,
        "url": urls[0] if urls else None,
        "urls": urls,
        "expiresIn": settings.minio_presigned_expiry_seconds
        if settings.storage_type.lower() == "minio"
        else None,
    }


def sign_payload_field(
    payload: dict[str, Any],
    field: str,
    key_field: str,
    storage: StorageService,
) -> dict[str, Any]:
    """Keep the stable key separately and expose only temporary URLs to the UI."""
    stored_values = payload.get(field)
    urls = access_urls(storage, stored_values)
    payload[key_field] = stored_values
    payload[field] = ",".join(urls) if urls else None
    return payload
