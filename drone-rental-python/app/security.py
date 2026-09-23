import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header

from .common import BusinessException, C, ResultCode
from .config import Settings, get_settings
from .redis import get_redis_support

@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    username: str
    role: int
    token_id: str
    expires_at: int


def create_token(user_id: int, username: str, role: int, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "userId": user_id,
        "username": username,
        "role": role,
        "sub": username,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_expiration_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS512")


def decode_token(token: str, settings: Settings) -> CurrentUser:
    """Decode a JWT for HTTP dependencies and WebSocket authentication."""
    prefix = settings.jwt_prefix + " "
    if token.startswith(prefix):
        token = token[len(prefix):]
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS512"])
        user_id, username, role, token_id, expires_at = claims.get("userId"), claims.get("sub"), claims.get("role",0), claims.get("jti"), claims.get("exp")
        if user_id is None or username is None or token_id is None or expires_at is None:
            raise ValueError("missing claims")
        current = CurrentUser(
            int(user_id), str(username), int(role), str(token_id), int(expires_at),
        )
        if get_redis_support().is_revoked(current.token_id):
            raise BusinessException(ResultCode.UNAUTHORIZED)
        return current
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise BusinessException(ResultCode.UNAUTHORIZED) from exc


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if not authorization:
        raise BusinessException(ResultCode.UNAUTHORIZED)
    return decode_token(authorization, settings)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != C.ROLE_ADMIN:
        raise BusinessException(ResultCode.FORBIDDEN)
    return user
