"""Sliding-window rate limiting (Redis-backed; in-memory fallback). Keyed by subject+route."""
from __future__ import annotations

import time
from dataclasses import dataclass

from globaltalk.core.cache import get_cache
from globaltalk.core.errors import RateLimitedError


@dataclass(frozen=True)
class Limit:
    max_requests: int
    window_seconds: int

    @classmethod
    def parse(cls, spec: str) -> "Limit":
        n, _, unit = spec.partition("/")
        secs = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[unit]
        return cls(int(n), secs)


def check_rate_limit(key: str, limit: Limit) -> None:
    bucket = f"rl:{key}:{int(time.time()) // limit.window_seconds}"
    n = get_cache().incr(bucket, ttl=limit.window_seconds + 1)
    if n > limit.max_requests:
        raise RateLimitedError(
            "Rate limit exceeded. Please slow down.",
            details={"limit": limit.max_requests, "window_seconds": limit.window_seconds,
                     "retry_after_seconds": limit.window_seconds})
