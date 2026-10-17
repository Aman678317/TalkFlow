"""Bounded concurrency for blocking AI inference (remediation plan P1).

STT/MT/TTS providers run blocking model work (CTranslate2, ONNX, Piper) inside
``asyncio.to_thread``. Without a cap, one busy room can saturate the thread
pool and inflate *every other meeting's* stage latency. This gate bounds the
number of in-flight provider calls per process; streaming delivery stays
outside the gate so a slow consumer cannot hold an inference slot.

The default gate is process-wide (one semaphore per running event loop) so all
three realtime agents share the same budget. Agents may construct their own
``InferenceGate`` for tests or dedicated capacity.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator


class InferenceGate:
    """An async semaphore wrapper; ``await gate.slot()`` before provider calls."""

    def __init__(self, limit: int = 4) -> None:
        self._sem = asyncio.Semaphore(max(1, limit))

    @contextlib.asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._sem:
            yield None


class StageDeadlineExpired(TimeoutError):
    """A stage blew its configured deadline.

    Raised instead of a bare ``TimeoutError`` (which other layers map to a
    generic provider outage) so agents can report the *right* recoverable
    reason on the wire: the provider may be healthy, it was just too slow.
    """

    def __init__(self, stage: str, deadline_ms: float) -> None:
        self.stage = stage
        self.deadline_ms = deadline_ms
        super().__init__(f"{stage} exceeded its {deadline_ms:.0f} ms deadline")


_default_gate: InferenceGate | None = None


def reset_default_gate() -> None:
    """Drop the singleton so the next call re-reads the configured limit."""
    global _default_gate
    _default_gate = None


def default_gate() -> InferenceGate:
    """The shared process-wide gate, sized from settings on first use."""
    global _default_gate
    if _default_gate is None:
        from app.config import settings
        _default_gate = InferenceGate(settings.rt_inference_concurrency)
    return _default_gate
