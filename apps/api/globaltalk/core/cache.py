"""Cache + pub/sub + queue abstraction: Redis in prod, in-process fallback in dev.

The realtime hub and translation dedup cache use this interface so a Redis outage degrades
to single-node behaviour instead of breaking meetings (fallback chain rule).
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Protocol

from globaltalk.core.config import settings
from globaltalk.core.logging import get_logger

log = get_logger("cache")


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: float | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def incr(self, key: str, ttl: float | None = None) -> int: ...
    def publish(self, channel: str, message: dict[str, Any]) -> None: ...
    def subscribe(self, channel: str) -> "Subscription": ...
    def healthy(self) -> bool: ...


class Subscription(Protocol):
    def get(self, timeout: float = 1.0) -> dict[str, Any] | None: ...
    def close(self) -> None: ...


class InProcessBackend:
    """Thread-safe in-memory cache with TTL, counters and pub/sub (single node)."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._subs: dict[str, list[deque]] = defaultdict(list)
        self._lock = threading.Lock()

    def _expired(self, exp: float | None) -> bool:
        return exp is not None and exp < time.time()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            value, exp = item
            if self._expired(exp):
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: str, ttl: float | None = None) -> None:
        with self._lock:
            self._data[key] = (value, time.time() + ttl if ttl else None)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl: float | None = None) -> int:
        with self._lock:
            cur = self._data.get(key)
            n = 0
            if cur and not self._expired(cur[1]):
                n = int(cur[0])
            n += 1
            exp = cur[1] if (cur and cur[1] and not self._expired(cur[1])) else (
                time.time() + ttl if ttl else None)
            self._data[key] = (str(n), exp)
            return n

    def publish(self, channel: str, message: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subs.get(channel, []))
        for q in queues:
            q.append(message)

    def subscribe(self, channel: str) -> "_InProcessSubscription":
        q: deque = deque(maxlen=1000)
        with self._lock:
            self._subs[channel].append(q)
        return _InProcessSubscription(self, channel, q)

    def _unsubscribe(self, channel: str, q: deque) -> None:
        with self._lock:
            subs = self._subs.get(channel, [])
            if q in subs:
                subs.remove(q)

    def healthy(self) -> bool:
        return True


class _InProcessSubscription:
    def __init__(self, backend: InProcessBackend, channel: str, q: deque):
        self._b, self._c, self._q = backend, channel, q

    def get(self, timeout: float = 1.0) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                return self._q.popleft()
            except IndexError:
                time.sleep(0.01)
        return None

    def close(self) -> None:
        self._b._unsubscribe(self._c, self._q)


class RedisBackend:
    def __init__(self, url: str):
        import redis  # lazy
        self._r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2,
                                       socket_connect_timeout=2)
        self._r.ping()

    def get(self, key: str) -> str | None:
        return self._r.get(key)

    def set(self, key: str, value: str, ttl: float | None = None) -> None:
        self._r.set(key, value, ex=int(ttl) if ttl else None)

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def incr(self, key: str, ttl: float | None = None) -> int:
        n = self._r.incr(key)
        if n == 1 and ttl:
            self._r.expire(key, int(ttl))
        return int(n)

    def publish(self, channel: str, message: dict[str, Any]) -> None:
        self._r.publish(channel, json.dumps(message, default=str))

    def subscribe(self, channel: str) -> "_RedisSubscription":
        p = self._r.pubsub()
        p.subscribe(channel)
        return _RedisSubscription(p)

    def healthy(self) -> bool:
        try:
            return bool(self._r.ping())
        except Exception:
            return False


class _RedisSubscription:
    def __init__(self, pubsub):
        self._p = pubsub

    def get(self, timeout: float = 1.0) -> dict[str, Any] | None:
        msg = self._p.get_message(timeout=timeout)
        if msg and msg["type"] == "message":
            return json.loads(msg["data"])
        return None

    def close(self) -> None:
        try:
            self._p.close()
        except Exception:
            pass


_backend: CacheBackend | None = None
_backend_name = "memory"


def get_cache() -> CacheBackend:
    global _backend, _backend_name
    if _backend is not None:
        return _backend
    if os.environ.get("CACHE_BACKEND") == "memory" or not settings.redis_url:
        _backend = InProcessBackend()
        _backend_name = "memory"
        return _backend
    try:
        _backend = RedisBackend(settings.redis_url)
        _backend_name = "redis"
        log.info("cache_backend", extra={"backend": "redis"})
    except Exception as exc:  # Redis optional in dev
        _backend = InProcessBackend()
        _backend_name = "memory"
        log.warning("cache_backend_fallback", extra={"reason": str(exc)})
    return _backend


def cache_backend_name() -> str:
    get_cache()
    return _backend_name


def reset_cache_for_tests() -> None:
    global _backend, _backend_name
    _backend = InProcessBackend()
    _backend_name = "memory"
