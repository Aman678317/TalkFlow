"""Bounded, non-blocking event bus connecting the four realtime agents.

The whole point of this file is what it refuses to do: it never applies
backpressure to the audio path. A producer that finds the consumer queue full
counts the drop and returns immediately, so a stalled metrics exporter or a slow
WS consumer cannot slow down transcription or synthesis.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from app.realtime.agents.contracts import RealtimeEvent

log = logging.getLogger("app.realtime.agents.bus")

DEFAULT_MAXSIZE = 256
DEFAULT_TRACE_LIMIT = 4096

SyncHandler = Callable[[RealtimeEvent], Any]
AsyncHandler = Callable[[RealtimeEvent], Awaitable[Any]]


def _wall_ms() -> int:
    return int(time.time() * 1000)


class AgentBus:
    def __init__(self, *, maxsize: int = DEFAULT_MAXSIZE,
                 trace_limit: int = DEFAULT_TRACE_LIMIT,
                 clock: Callable[[], int] | None = None) -> None:
        self._queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=maxsize)
        self._trace: deque[RealtimeEvent] = deque(maxlen=trace_limit)
        self._handlers: list[tuple[bool, Callable[[RealtimeEvent], Any]]] = []
        self._clock = clock or _wall_ms
        self.maxsize = maxsize
        self.dropped = 0
        self.published = 0
        self.dispatched = 0
        self.closed = False
        #: Position in this bus's own event stream, stamped on publish.
        self._sequence = 0

    # ------------------------------------------------------------------ #
    @property
    def trace(self) -> list[RealtimeEvent]:
        """Every event that entered the bus, oldest first."""
        return list(self._trace)

    def subscribe(self, handler: Callable[[RealtimeEvent], Any]) -> None:
        """Sync handlers run inline; async handlers go through the bounded queue."""
        self._handlers.append((inspect.iscoroutinefunction(handler), handler))

    async def publish(self, event: RealtimeEvent) -> bool:
        """Enqueue an event. Returns False when the consumer queue was full.

        Never awaits on a consumer, so the calling stage keeps moving at audio
        speed even if nobody is reading.
        """
        if self.closed:
            self.dropped += 1
            return False
        # Both stamps are unconditional. The clock may already have been supplied
        # by a test or a replay, but the position in this stream belongs to the
        # bus, and an event that skipped numbering left a hole no reader could
        # tell apart from a drop.
        self._sequence += 1
        stamped = event.model_copy(update={
            "bus_sequence": self._sequence,
            "timestamp_ms": event.timestamp_ms or self._clock()})
        self._trace.append(stamped)
        self.published += 1
        try:
            self._queue.put_nowait(stamped)
        except asyncio.QueueFull:
            self.dropped += 1
            log.debug("agent bus full, dropped %s", stamped.type)
            return False
        for is_async, handler in self._handlers:
            if not is_async:
                handler(stamped)
        return True

    async def drain(self) -> list[RealtimeEvent]:
        """Hand everything currently queued to the async subscribers."""
        out: list[RealtimeEvent] = []
        while not self._queue.empty():
            event = self._queue.get_nowait()
            out.append(event)
            for is_async, handler in self._handlers:
                if is_async:
                    await handler(event)
        self.dispatched += len(out)
        return out

    def health(self) -> dict[str, Any]:
        return {
            "queue_depth": self._queue.qsize(),
            "queue_bound": self.maxsize,
            "dropped_events": self.dropped,
            "published": self.published,
            "dispatched": self.dispatched,
            "last_event_sequence": self._sequence,
            "trace_events": len(self._trace),
            "closed": self.closed,
        }

    async def close(self) -> None:
        self.closed = True
