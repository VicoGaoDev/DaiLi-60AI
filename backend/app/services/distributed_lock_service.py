from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import redis

from app.config import settings

logger = logging.getLogger(__name__)

LockStatus = Literal["acquired", "contended", "unavailable"]


@dataclass
class RedisLockHandle:
    status: LockStatus
    lock: redis.lock.Lock | None = None


def acquire_redis_lock(
    name: str,
    *,
    timeout_seconds: int,
    blocking_timeout_seconds: int = 0,
) -> RedisLockHandle:
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        lock = client.lock(name, timeout=max(int(timeout_seconds or 0), 1))
        acquired = lock.acquire(
            blocking=blocking_timeout_seconds > 0,
            blocking_timeout=max(float(blocking_timeout_seconds), 0.0) or None,
        )
        if not acquired:
            return RedisLockHandle(status="contended")
        return RedisLockHandle(status="acquired", lock=lock)
    except Exception:
        logger.warning("Redis lock unavailable: %s", name, exc_info=True)
        return RedisLockHandle(status="unavailable")


def release_redis_lock(handle: RedisLockHandle) -> None:
    if handle.status != "acquired" or not handle.lock:
        return
    try:
        handle.lock.release()
    except Exception:
        logger.warning("Failed to release Redis lock", exc_info=True)
