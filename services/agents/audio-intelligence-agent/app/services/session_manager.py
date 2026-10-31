"""Session manager managing concurrent streaming sessions and backpressure queues."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple
from app.core.config import settings
from app.core.exceptions import SessionCapacityExceededError, SessionNotFoundError
from app.core.logging import get_logger
from app.monitoring.metrics import metrics
from app.services.pipeline import AudioPipeline

log = get_logger("session_manager")


@dataclass
class SessionState:
    session_id: str
    conversation_id: str
    speaker_id: str
    pipeline: AudioPipeline
    queue: asyncio.Queue[Tuple[bytes, int, int, int, str]]  # (pcm, seq, sr, ch, enc)
    worker_task: Optional[asyncio.Task] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    is_active: bool = True


class SessionManager:
    """Manages active streaming sessions with bounded queues and worker tasks."""

    def __init__(self, max_concurrent_sessions: int = 64, queue_capacity: int = 100):
        self.max_concurrent_sessions = max_concurrent_sessions
        self.queue_capacity = queue_capacity
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)

    async def create_session(
        self,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        on_event_callback: Optional[Callable[[Dict[str, Any], Optional[bytes]], Any]] = None,
    ) -> SessionState:
        """Registers a new streaming session with bounded worker queue."""
        async with self._lock:
            if session_id in self._sessions:
                # Existing session: update timestamp and return
                self._sessions[session_id].last_activity = time.time()
                return self._sessions[session_id]

            if len(self._sessions) >= self.max_concurrent_sessions:
                raise SessionCapacityExceededError(
                    f"Maximum concurrent sessions ({self.max_concurrent_sessions}) reached"
                )

            pipeline = AudioPipeline(
                session_id=session_id,
                conversation_id=conversation_id,
                speaker_id=speaker_id,
                on_event_callback=on_event_callback,
            )

            queue: asyncio.Queue[Tuple[bytes, int, int, int, str]] = asyncio.Queue(
                maxsize=self.queue_capacity
            )

            state = SessionState(
                session_id=session_id,
                conversation_id=conversation_id,
                speaker_id=speaker_id,
                pipeline=pipeline,
                queue=queue,
            )

            # Start asynchronous queue consumer task
            state.worker_task = asyncio.create_task(self._process_queue_worker(state))
            self._sessions[session_id] = state
            metrics.set_active_sessions(len(self._sessions))
            log.info(f"Session created: {session_id} for speaker {speaker_id} (active: {len(self._sessions)})")
            return state

    def get_session(self, session_id: str) -> SessionState:
        """Retrieves existing session or raises SessionNotFoundError."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session '{session_id}' not found or has expired")
        sess = self._sessions[session_id]
        sess.last_activity = time.time()
        return sess

    async def enqueue_frame(
        self,
        session_id: str,
        raw_bytes: bytes,
        sequence: int = -1,
        sample_rate: int = 16000,
        channels: int = 1,
        encoding: str = "pcm_s16le",
    ) -> bool:
        """Pushes audio frame to session's bounded queue with backpressure handling."""
        state = self.get_session(session_id)

        try:
            # Try non-blocking put
            state.queue.put_nowait((raw_bytes, sequence, sample_rate, channels, encoding))
            return True
        except asyncio.QueueFull:
            # Backpressure handling: drop oldest partial frame if allowed
            if settings.streaming.backpressure_drop_stale_partials:
                try:
                    _ = state.queue.get_nowait()
                    state.queue.task_done()
                    state.queue.put_nowait((raw_bytes, sequence, sample_rate, channels, encoding))
                    metrics.record_dropped_frame("queue_overflow_dropped_oldest")
                    log.warning(f"Backpressure: dropped oldest frame for session {session_id}")
                    return True
                except Exception:
                    pass
            metrics.record_dropped_frame("queue_overflow_rejected")
            log.warning(f"Backpressure: frame rejected for session {session_id} (queue full)")
            return False

    async def terminate_session(self, session_id: str) -> None:
        """Flushes remaining audio and cleans up session resources."""
        async with self._lock:
            if session_id not in self._sessions:
                return

            state = self._sessions.pop(session_id)
            state.is_active = False

            # Cancel worker task
            if state.worker_task and not state.worker_task.done():
                state.worker_task.cancel()
                try:
                    await asyncio.wait_for(state.worker_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            # Final flush of pipeline
            state.pipeline.flush()
            state.pipeline.chunk_manager.cleanup_session(session_id)
            metrics.set_active_sessions(len(self._sessions))
            log.info(f"Session terminated: {session_id} (active remaining: {len(self._sessions)})")

    async def _process_queue_worker(self, state: SessionState) -> None:
        """Continuous consumer loop executing audio pipeline frames."""
        try:
            while state.is_active:
                try:
                    item = await state.queue.get()
                except asyncio.CancelledError:
                    break

                raw_bytes, sequence, sample_rate, channels, encoding = item
                try:
                    await state.pipeline.process_frame(
                        raw_bytes=raw_bytes,
                        sequence=sequence,
                        sample_rate=sample_rate,
                        channels=channels,
                        encoding=encoding,
                    )
                except Exception as exc:
                    log.error(f"Error processing frame in session {state.session_id}: {exc}")
                finally:
                    state.queue.task_done()
        except asyncio.CancelledError:
            pass

