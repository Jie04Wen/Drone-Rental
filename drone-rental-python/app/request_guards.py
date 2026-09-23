"""Single-process rate limiting and idempotency guards from the Java project."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from fastapi import Request

from .config import get_settings
from .redis import get_redis_support


@dataclass
class _Bucket:
    capacity: int
    refill_per_second: float
    tokens: float
    last_refill: float


class RateLimiter:
    # 优先使用 Redis 分布式令牌桶，失败时回退单进程令牌桶。
    def __init__(self) -> None:
        self._redis = get_redis_support()
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, permits: int, burst: int) -> bool:
        distributed = self._redis.distributed_rate_limit(key, permits, burst)
        # True/False 表示 Redis 命令成功，采用分布式结果
        # None 表示 Redis 关闭或异常，回退本地限流
        if distributed is not None:
            return distributed
        return self.acquire_local(key, permits, burst)

    def acquire_local(self, key: str, permits: int, burst: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = _Bucket(burst, float(permits), float(burst - 1), now)
                return True
            elapsed = now - bucket.last_refill
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_second)
            bucket.last_refill = now
            if bucket.tokens < 1:
                return False
            bucket.tokens -= 1
            return True


class IdempotencyStore:
    # 优先使用 Redis 幂等租约，失败时回退单进程字典
    def __init__(self) -> None:
        self._redis = get_redis_support()
        self._ttl_seconds = get_settings().redis_idempotency_ttl_seconds
        self._values: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str) -> str | None:
        if not key:
            return uuid4().hex

        distributed = self._redis.acquire_once(key, self._ttl_seconds)
        if isinstance(distributed, str):
            return distributed
        if distributed is None:
            return None
        return self.acquire_local(key)

    def acquire_local(self, key: str) -> str | None:
        now = time.monotonic()
        with self._lock:
            self._values = {
                item: value
                for item, value in self._values.items()
                if value[0] >= now
            }

            if key in self._values:
                return None

            token = uuid4().hex
            self._values[key] = (now + self._ttl_seconds, token)
            return token

    def release(self, key: str, token: str) -> None:
        if not key or not token:
            return
        self._redis.release_once(key, token)

        with self._lock:
            current = self._values.get(key)

            if current is not None and current[1] == token:
                self._values.pop(key, None)


class RateLimitExceeded(Exception):
    pass


def rate_limit(permits: int, burst: int):
    """Create a FastAPI dependency matching Java's IP-based @RateLimit."""

    async def dependency(request: Request):
        forwarded = request.headers.get("X-Forwarded-For")
        identity = forwarded.split(",", 1)[0].strip() if forwarded else (
            request.client.host if request.client else "unknown")
        key = f"{request.url.path}:{identity}"
        if not request.app.state.rate_limiter.acquire(key, permits, burst):
            raise RateLimitExceeded

    return dependency
