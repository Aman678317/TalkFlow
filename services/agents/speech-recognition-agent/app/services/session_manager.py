"""Session management and bounded concurrency for Speech Recognition Agent."""
from __future__ import annotations

import asyncio
from typing import Dict, Optional, Set
from app.core.config import settings
from app.core.exceptions import SessionCapacityExceededError
from app.core.logging import get_logger

log = get_logger("services.session_manager")


class STTSession:
    """Stateful session tracking for a participant stream."""

    def __init__(self, session_id: str, speaker_id: str = "user_001"):
        self.session_id = session_id
        self.speaker_id = speaker_id
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=settings.concurrency.queue_capacity)
        self.created_at = asyncio.get_event_loop().time()
        self.total_frames_processed = 0
        self.total_audio_seconds = 0.0
        self.active_utterance_id: Optional[str] = None
        self.active_segment_id: Optional[str] = None


class STTSessionManager:
    """Thread-safe manager for concurrent STT sessions."""

    def __init__(self, max_sessions: int = 50):
        self.max_sessions = max_sessions
        self._sessions: Dict[str, STTSession] = {}
        self._lock = asyncio.Lock()

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)

    async def get_or_create_session(self, session_id: str, speaker_id: str = "user_001") -> STTSession:
        """Retrieves an existing session or registers a new one under capacity limits."""
        async with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]

            if len(self._sessions) >= self.max_sessions:
                raise SessionCapacityExceededError(
                    f"Session limit reached ({self.max_sessions} concurrent sessions)"
                )

            session = STTSession(session_id=session_id, speaker_id=speaker_id)
            self._sessions[session_id] = session
            log.info(f"STT Session registered: {session_id} (Active: {len(self._sessions)})")
            return session

    async def remove_session(self, session_id: str) -> None:
        """Removes and cleans up an active session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                log.info(f"STT Session terminated: {session_id} (Active: {len(self._sessions)})")

