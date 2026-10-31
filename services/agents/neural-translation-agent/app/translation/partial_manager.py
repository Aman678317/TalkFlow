"""Provisional partial revision tracking and stale event cancellation."""
from __future__ import annotations

import asyncio
from typing import Dict, Optional, Tuple


class PartialManager:
    """Tracks active streaming revisions per (session_id, speaker_id, target_lang)."""

    def __init__(self) -> None:
        # key: (session_id, speaker_id, target_lang) -> latest revision int
        self._revisions: Dict[Tuple[str, str, str], int] = {}
        self._lock = asyncio.Lock()

    async def get_next_revision(self, session_id: str, speaker_id: str, target_lang: str) -> int:
        async with self._lock:
            key = (session_id, speaker_id, target_lang)
            rev = self._revisions.get(key, 0) + 1
            self._revisions[key] = rev
            return rev

    async def is_stale(self, session_id: str, speaker_id: str, target_lang: str, revision: int) -> bool:
        async with self._lock:
            key = (session_id, speaker_id, target_lang)
            current = self._revisions.get(key, 0)
            return revision < current

    async def reset(self, session_id: str, speaker_id: str, target_lang: str) -> None:
        async with self._lock:
            self._revisions.pop((session_id, speaker_id, target_lang), None)


partial_manager = PartialManager()

