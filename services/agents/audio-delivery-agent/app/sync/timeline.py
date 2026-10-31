"""Turn timeline tracker ensuring proper chronological playback across speakers."""
from __future__ import annotations

import time
from typing import Dict, Optional
from app.core.logging import get_logger

logger = get_logger("sync.timeline")


class TurnTimelineTracker:
    """Tracks chronological wall-clock conversation progression per room."""

    def __init__(self):
        # room_id -> highest observed start_wall_ms
        self._room_latest_turn_wall_ms: Dict[str, float] = {}
        # room_id -> active speaking speaker_id
        self._room_active_speaker: Dict[str, str] = {}
        # (room_id, speaker_id) -> latest_seq
        self._speaker_latest_seq: Dict[str, int] = {}

    def record_turn_start(self, room_id: str, speaker_id: str, seq: int, start_wall_ms: Optional[float] = None) -> float:
        """Register the start of an utterance turn."""
        wall_ms = start_wall_ms if start_wall_ms is not None else (time.time() * 1000.0)

        current_latest = self._room_latest_turn_wall_ms.get(room_id, 0.0)
        if wall_ms > current_latest:
            self._room_latest_turn_wall_ms[room_id] = wall_ms

        self._room_active_speaker[room_id] = speaker_id
        key = f"{room_id}:{speaker_id}"
        self._speaker_latest_seq[key] = max(self._speaker_latest_seq.get(key, 0), seq)
        return wall_ms

    def get_latest_wall_ms(self, room_id: str) -> float:
        return self._room_latest_turn_wall_ms.get(room_id, 0.0)

    def is_superseded_by_newer_turn(self, room_id: str, speaker_id: str, seq: int) -> bool:
        """Check if a newer sequence from the same speaker has already begun."""
        key = f"{room_id}:{speaker_id}"
        latest_seq = self._speaker_latest_seq.get(key, 0)
        return seq < latest_seq

    def clear_room(self, room_id: str) -> None:
        """Clear timeline state for a room."""
        self._room_latest_turn_wall_ms.pop(room_id, None)
        self._room_active_speaker.pop(room_id, None)
        keys_to_del = [k for k in self._speaker_latest_seq.keys() if k.startswith(f"{room_id}:")]
        for k in keys_to_del:
            self._speaker_latest_seq.pop(k, None)

