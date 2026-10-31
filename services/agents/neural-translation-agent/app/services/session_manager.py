"""Session and participant routing management."""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class ParticipantSeat(BaseModel):
    seat_id: str
    hear_lang: str = "en"
    mode: str = "translated"  # translated | original


class TranslationSession(BaseModel):
    session_id: str
    seats: Dict[str, ParticipantSeat] = Field(default_factory=dict)


class SessionManager:
    """Tracks active sessions and participant target language configurations."""

    def __init__(self) -> None:
        self._sessions: Dict[str, TranslationSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_session(self, session_id: str) -> TranslationSession:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = TranslationSession(session_id=session_id)
            return self._sessions[session_id]

    async def register_seat(self, session_id: str, seat_id: str, hear_lang: str, mode: str = "translated") -> None:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = TranslationSession(session_id=session_id)
            self._sessions[session_id].seats[seat_id] = ParticipantSeat(
                seat_id=seat_id, hear_lang=hear_lang, mode=mode
            )

    async def get_distinct_targets(self, session_id: str, speaker_lang: str) -> List[str]:
        """Returns deduplicated set of target languages needed for active listeners."""
        async with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return []
            targets: Set[str] = set()
            for seat in sess.seats.values():
                if seat.mode == "original":
                    continue  # listeners hearing original audio need no translation
                targets.add(seat.hear_lang.lower())
            return list(targets)

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)


session_manager = SessionManager()

