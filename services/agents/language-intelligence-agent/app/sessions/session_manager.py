"""Session and speaker context coordinator with bounded memory management."""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional
from app.core.config import settings
from app.core.exceptions import SessionCapacityExceededError
from app.core.logging import get_logger
from app.sessions.speaker_context import SpeakerLanguageContext

log = get_logger("sessions.session_manager")


class SessionLanguageContext:
    """Stateful context for a multi-participant communication session."""

    def __init__(self, session_id: str, conversation_id: str):
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.speakers: Dict[str, SpeakerLanguageContext] = {}
        self.created_at = time.time()
        self.last_active_at = time.time()

    def get_or_create_speaker(self, speaker_id: str) -> SpeakerLanguageContext:
        self.last_active_at = time.time()
        if speaker_id not in self.speakers:
            self.speakers[speaker_id] = SpeakerLanguageContext(
                speaker_id=speaker_id,
                window_size=settings.sessions.speaker_history_window,
            )
        return self.speakers[speaker_id]


class LanguageSessionManager:
    """Thread-safe manager for concurrent active conversation sessions."""

    def __init__(self, max_sessions: int = 64):
        self.max_sessions = max_sessions
        self._sessions: Dict[str, SessionLanguageContext] = {}
        self._lock = threading.Lock()

    @property
    def active_session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def get_or_create_session(self, session_id: str, conversation_id: Optional[str] = None) -> SessionLanguageContext:
        with self._lock:
            if session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.last_active_at = time.time()
                return sess

            # Capacity check
            if len(self._sessions) >= self.max_sessions:
                # Evict oldest session
                oldest_id = min(self._sessions.keys(), key=lambda k: self._sessions[k].last_active_at)
                log.warning(f"Evicting oldest inactive session '{oldest_id}' due to capacity limit ({self.max_sessions})")
                del self._sessions[oldest_id]

            conv_id = conversation_id or session_id
            sess = SessionLanguageContext(session_id=session_id, conversation_id=conv_id)
            self._sessions[session_id] = sess
            log.info(f"Language session registered: {session_id} (Active: {len(self._sessions)})")
            return sess

    def get_speaker_dominant_language(self, session_id: str, speaker_id: str) -> Optional[str]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            spk = sess.speakers.get(speaker_id)
            return spk.dominant_language if spk else None

    def record_speaker_utterance(
        self,
        session_id: str,
        speaker_id: str,
        utterance_id: str,
        detected_language: str,
        confidence: float,
        is_multilingual: bool = False,
        conversation_id: Optional[str] = None,
    ) -> str:
        sess = self.get_or_create_session(session_id, conversation_id)
        spk = sess.get_or_create_speaker(speaker_id)
        return spk.record_utterance(
            utterance_id=utterance_id,
            detected_language=detected_language,
            confidence=confidence,
            is_multilingual=is_multilingual,
        )

    def terminate_session(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                log.info(f"Language session terminated: {session_id} (Active: {len(self._sessions)})")

