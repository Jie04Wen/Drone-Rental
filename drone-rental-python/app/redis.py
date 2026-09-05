from __future__ import annotations

import atexit
import hashlib
import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import redis
from functools import lru_cache
from redis import Redis
from redis.exceptions import RedisError

from .config import Settings, get_settings

LOGGER = logging.getLogger(__name__)
DRONE_CACHE_NAMESPACE = "drone"

# RATE_LIMIT_LUA：分布式令牌桶限流，实现多进程、多实例共享的接口限流。
RATE_LIMIT_LUA = """
local current = redis.call('HMGET', KEYS[1], 'tokens', 'timestamp')
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local tokens = tonumber(current[1]) or capacity
local previous = tonumber(current[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - previous) * refill)
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'timestamp', now)
redis.call('EXPIRE', KEYS[1], math.max(1, math.ceil(capacity / refill * 2)))
return allowed
"""

# RELEASE_LUA：按所有者安全释放幂等租约
RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class RedisSupport:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Redis[str] | None = None
        self._last_error_log = 0.0
        self._log_lock = threading.Lock()
        if settings.redis_enabled:
            self.client = redis.Redis.from_url(
                settings.redis_url,
                password=settings.redis_password or None,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout_seconds,
                socket_connect_timeout=settings.redis_connect_timeout_seconds,
                health_check_interval=30,
            )

    def key(self, suffix: str) -> str:
        prefix = self.settings.redis_key_prefix.strip(':')
        return f"{prefix}:{suffix}" if prefix else suffix

    def _warn(self, operation: str, exc: Exception) -> None:
        # 防止Redis故障时请求刷屏 30s记录一次
        now = time.monotonic()
        with self._log_lock:
            if now - self._last_error_log >= 30:
                LOGGER.warning("Redis %s 失败，已执行降级: %s", operation, exc)
                self._last_error_log = now

    def ping(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self.client.ping())
        except RedisError as exc:
            self._warn("Ping", exc)
            return False

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except RedisError as exc:
                self._warn("关闭连接池", exc)

    def get_json(self, suffix: str) -> Any | None:
        if self.client is None:
            return None
        try:
            raw = self.client.get(self.key(suffix))
            return json.loads(raw) if raw is not None else None
        except (RedisError, json.JSONDecodeError) as exc:
            self._warn("GET", exc)
            return None

    def set_json(self, suffix: str, value: Any, ttl_seconds: int) -> None:
        if self.client is None:
            return
        try:
            self.client.set(
                self.key(suffix),
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
            )
        except (RedisError, TypeError, ValueError) as exc:
            self._warn("SET", exc)

    def namespace_version(self, namespace: str) -> int | None:
        if self.client is None:
            return None
        try:
            version_key = self.key(f"cache:{namespace}:version")
            value = self.client.get(version_key)
            if value is None:
                self.client.set(version_key, "1", nx=True)
                value = self.client.get(version_key)
            return int(value or 1)
        except (RedisError, TypeError, ValueError) as exc:
            self._warn("读取缓存版本", exc)
            return None

    def invalidate_namespace(self, namespace: str) -> None:
        if self.client is None:
            return
        try:
            self.client.incr(self.key(f"cache:{namespace}:version"))
        except RedisError as exc:
            self._warn("缓存失效", exc)

    @staticmethod
    def params_digest(params: dict[str, Any]) -> str:
        canonical = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record_session(self, jti: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        self.set_json(f"auth:session:{jti}", payload, ttl_seconds)

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        if self.client is None or ttl_seconds <= 0:
            return
        try:
            pipe = self.client.pipeline(transaction=True)
            pipe.set(self.key(f"auth:revoked:{jti}"), "1", ex=ttl_seconds)
            pipe.delete(self.key(f"auth:session:{jti}"))
            pipe.execute()
        except RedisError as exc:
            self._warn("JWT 撤销", exc)

    def is_revoked(self, jti: str) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self.client.exists(self.key(f"auth:revoked:{jti}")))
        except RedisError as exc:
            self._warn("JWT 黑名单检查", exc)
            return False

    def distributed_rate_limit(self, suffix: str, permits: int, burst: int) -> bool | None:
        if self.client is None:
            return None
        try:
            return bool(self.client.eval(
                RATE_LIMIT_LUA, 1, self.key(f"rate:{suffix}"), burst, permits
            ))
        except RedisError as exc:
            self._warn("限流", exc)
            return None

    def acquire_once(self, suffix: str, ttl_seconds: int) -> str | None | bool:
        """返回 token=成功、None=重复、False=Redis 不可用。"""
        if self.client is None:
            return False
        token = uuid.uuid4().hex
        try:
            acquired = self.client.set(self.key(f"idem:{suffix}"), token, nx=True, ex=ttl_seconds)
            return token if acquired else None
        except RedisError as exc:
            self._warn("幂等", exc)
            return False

    def release_once(self, suffix: str, token: str) -> None:
        if self.client is None:
            return
        try:
            self.client.eval(RELEASE_LUA, 1, self.key(f"idem:{suffix}"), token)
        except RedisError as exc:
            self._warn("释放幂等租约", exc)

    @contextmanager
    def optional_lock(self, suffix: str) -> Iterator[bool]:
        if self.client is None:
            yield True
            return
        lock = self.client.lock(
            self.key(f"lock:{suffix}"),
            timeout=self.settings.redis_lock_ttl_seconds,
            blocking_timeout=self.settings.redis_lock_wait_seconds,
        )
        try:
            acquired = bool(lock.acquire(blocking=True))
        except RedisError as exc:
            self._warn("分布式锁", exc)
            yield True  # 降级后由 MySQL 保证最终正确性
            return

        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            try:
                lock.release()
            except RedisError as exc:
                self._warn("释放分布式锁", exc)


@lru_cache
def get_redis_support() -> RedisSupport:
    support = RedisSupport(get_settings())
    atexit.register(support.close)
    return support


def invalidate_drone_cache() -> None:
    get_redis_support().invalidate_namespace(DRONE_CACHE_NAMESPACE)
