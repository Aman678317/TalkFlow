"""Cache backend abstraction: Redis (prod) or in-process memory (dev/test).

Realtime ephemeral state, rate limits and dedup keys live here. The API never
imports redis directly — swapping backends must not touch business logic.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

log = logging.getLogger("app.cache")


class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None: ...
    @abstractmethod
    async def set(self, key: str, value: str, ttl_s: int | None = None) -> None: ...
    @abstractmethod
    async def delete(self, key: str) -> None: ...
    @abstractmethod
    async def incr(self, key: str, ttl_s: int | None = None) -> int: ...
    @abstractmethod
    async def ping(self) -> bool: ...

    async def get_json(self, key: str) -> Any | None:
        raw = await self.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        await self.set(key, json.dumps(value, default=str), ttl_s)


class MemoryCache(CacheBackend):
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    def _expired(self, key: str) -> bool:
        item = self._data.get(key)
        if item and item[1] is not None and item[1] < time.time():
            del self._data[key]
            return True
        return False

    async def get(self, key: str) -> str | None:
        async with self._lock:
            if self._expired(key):
                return None
            item = self._data.get(key)
            return item[0] if item else None

    async def set(self, key: str, value: str, ttl_s: int | None = None) -> None:
        async with self._lock:
            self._data[key] = (value, time.time() + ttl_s if ttl_s else None)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def incr(self, key: str, ttl_s: int | None = None) -> int:
        async with self._lock:
            self._expired(key)
            cur = int(self._data[key][0]) if key in self._data else 0
            cur += 1
            exp = self._data[key][1] if key in self._data and self._data[key][1] else (
                time.time() + ttl_s if ttl_s else None)
            self._data[key] = (str(cur), exp)
            return cur

    async def ping(self) -> bool:
        return True


class RedisCache(CacheBackend):
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis
        self._r = aioredis.from_url(url, decode_responses=True, socket_timeout=3,
                                    socket_connect_timeout=3)

    async def get(self, key: str) -> str | None:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl_s: int | None = None) -> None:
        await self._r.set(key, value, ex=ttl_s)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def incr(self, key: str, ttl_s: int | None = None) -> int:
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            if ttl_s:
                pipe.expire(key, ttl_s, nx=True)
            res = await pipe.execute()
        return int(res[0])

    async def ping(self) -> bool:
        try:
            return bool(await self._r.ping())
        except Exception:
            return False

    @property
    def client(self):
        return self._r


_backend: CacheBackend | None = None


async def init_cache(settings) -> CacheBackend:
    """auto = try redis, fall back to memory with a loud warning (non-prod only)."""
    global _backend
    mode = settings.cache_backend
    if mode in ("auto", "redis") and settings.redis_url:
        try:
            rc = RedisCache(settings.redis_url)
            if await rc.ping():
                _backend = rc
                log.info("cache backend: redis")
                return rc
            raise RuntimeError("redis ping failed")
        except Exception as e:
            if mode == "redis":
                raise
            log.warning("redis unavailable (%s) — falling back to in-memory cache. "
                        "NOT for production: state is per-process.", e)
    if settings.is_production and mode == "redis":
        raise RuntimeError("production requires redis")
    _backend = MemoryCache()
    log.info("cache backend: memory")
    return _backend


def cache() -> CacheBackend:
    global _backend
    if _backend is None:
        _backend = MemoryCache()
    return _backend
