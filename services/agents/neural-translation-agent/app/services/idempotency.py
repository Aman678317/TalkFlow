"""In-flight deduplication and idempotency lock for concurrent identical translation jobs."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple


class IdempotencyCoordinator:
    """Ensures identical in-flight translation jobs share a single future instead of duplicating inference."""

    def __init__(self) -> None:
        self._in_flight: Dict[Tuple[str, str], asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_job(
        self,
        segment_id: str,
        target_lang: str,
    ) -> Tuple[Optional[asyncio.Future[Any]], bool]:
        """Returns (future, is_creator). If is_creator is True, caller must execute and resolve the future."""
        async with self._lock:
            key = (segment_id, target_lang)
            if key in self._in_flight:
                return self._in_flight[key], False

            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            self._in_flight[key] = fut
            return fut, True

    async def complete_job(self, segment_id: str, target_lang: str, result: Any, error: Optional[Exception] = None) -> None:
        async with self._lock:
            key = (segment_id, target_lang)
            fut = self._in_flight.pop(key, None)
            if fut and not fut.done():
                if error:
                    fut.set_exception(error)
                else:
                    fut.set_result(result)


idempotency_coordinator = IdempotencyCoordinator()

