"""Rate limiting (fixed-window counters over the cache backend).

Keyed by (bucket, identity) where identity = api_key_id | user_id | IP.
Returns structured 429s with Retry-After per PDD §37.
"""
from __future__ import annotations

import time

from app.cache import cache
from app.errors import RateLimitError


def _parse(spec: str) -> tuple[int, int]:
    """'60/minute' -> (60, 60)."""
    count, _, period = spec.partition("/")
    seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}.get(period, 60)
    return int(count), seconds


async def check_rate_limit(bucket: str, identity: str, spec: str) -> None:
    limit, window_s = _parse(spec)
    window = int(time.time() // window_s)
    key = f"rl:{bucket}:{identity}:{window}"
    count = await cache().incr(key, ttl_s=window_s + 1)
    if count > limit:
        retry_after = max(1, window_s - int(time.time() % window_s))
        raise RateLimitError(
            "Rate limit exceeded. Please retry later.",
            details={"limit": limit, "window_seconds": window_s,
                     "retry_after": retry_after},
        )
