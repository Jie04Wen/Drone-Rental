"""Password hashing compatible with Java PasswordUtil and legacy MD5 rows."""

from __future__ import annotations

import hashlib
import hmac

import bcrypt


def md5_password(password: str) -> str:
    """Return the legacy Hutool-compatible MD5 value for migration checks."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()  # noqa: S324


def encode_password(password: str) -> str:
    """Create a BCrypt $2a$ hash that Java BCryptPasswordEncoder can read."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10, prefix=b"2a")).decode("ascii")


def is_bcrypt(encoded: str | None) -> bool:
    return bool(encoded and encoded.startswith(("$2a$", "$2b$", "$2y$")))


def verify_password(password: str, encoded: str | None) -> tuple[bool, bool]:
    """Return ``(valid, needs_upgrade)`` for BCrypt or legacy MD5 hashes."""
    if not encoded:
        return False, False
    if is_bcrypt(encoded):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), encoded.encode("ascii")), False
        except ValueError:
            return False, False
    if len(encoded) == 32:
        valid = hmac.compare_digest(md5_password(password), encoded.lower())
        return valid, valid
    return False, False
