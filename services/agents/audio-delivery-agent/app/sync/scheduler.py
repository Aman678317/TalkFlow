"""Adaptive audio playback scheduler for pacing chunk emissions."""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional
from app.core.logging import get_logger
from app.models.schemas import AudioChunkIngestRequest

logger = get_logger("sync.scheduler")


class PlaybackScheduler:
    """Calculates scheduling targets and paces chunk emissions."""

    def __init__(self, catchup_factor: float = 1.15):
        self.catchup_factor = catchup_factor
        # (room_id, segment_id, target_lang) -> expected_next_playout_wall_ms
        self._next_playout_ms: Dict[str, float] = {}

    def _make_key(self, room_id: str, segment_id: str, target_lang: str) -> str:
        return f"{room_id}:{segment_id}:{target_lang}"

    def schedule_chunk(self, chunk: AudioChunkIngestRequest) -> float:
        """Calculate playout wall clock time in ms for this chunk.
        
        Returns:
            scheduled_wall_ms
        """
        key = self._make_key(chunk.session_id, chunk.segment_id, chunk.target_lang)
        now_ms = time.time() * 1000.0

        current_scheduled = self._next_playout_ms.get(key, now_ms)
        scheduled_at = max(now_ms, current_scheduled)

        # Estimate duration if not provided
        chunk_dur_ms = chunk.duration_ms
        if chunk_dur_ms <= 0:
            chunk_dur_ms = 250.0  # standard default chunk size

        # If behind real-time, apply catchup factor to accelerate slightly
        if scheduled_at > now_ms + 1000.0:
            effective_dur = chunk_dur_ms / self.catchup_factor
        else:
            effective_dur = chunk_dur_ms

        self._next_playout_ms[key] = scheduled_at + effective_dur
        return scheduled_at

    def reset_utterance(self, room_id: str, segment_id: str, target_lang: str) -> None:
        """Reset playout timeline for an utterance."""
        key = self._make_key(room_id, segment_id, target_lang)
        self._next_playout_ms.pop(key, None)

    def clear_room(self, room_id: str) -> None:
        """Clear all playout state for a room."""
        keys = [k for k in self._next_playout_ms.keys() if k.startswith(f"{room_id}:")]
        for k in keys:
            self._next_playout_ms.pop(k, None)

