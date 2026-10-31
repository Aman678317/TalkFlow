"""Barge-in interruption manager for instant playback cancellation."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from app.core.logging import get_logger
from app.jitter.jitter_buffer import JitterBufferManager
from app.models.events import AudioCancelledEvent
from app.transport.websocket_broadcaster import WebSocketBroadcaster

logger = get_logger("cancellation.barge_in")


class BargeInManager:
    """Coordinates immediate cancellation of pending translated audio playback."""

    def __init__(
        self,
        jitter_buffer: JitterBufferManager,
        broadcaster: WebSocketBroadcaster,
    ):
        self.jitter_buffer = jitter_buffer
        self.broadcaster = broadcaster
        # room_id -> last_interruption_timestamp
        self._last_interruptions: Dict[str, float] = {}

    async def handle_interruption(
        self,
        room_id: str,
        session_id: Optional[str] = None,
        speaker_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        reason: str = "barge_in_interruption",
    ) -> Dict[str, Any]:
        """Abort playback, flush jitter buffers, and notify clients to clear audio players."""
        now = time.time()
        self._last_interruption = now

        # 1. Flush queued chunks in jitter buffer
        flushed_count = await self.jitter_buffer.cancel_utterance(
            room_id=room_id,
            segment_id=segment_id,
            speaker_id=speaker_id,
        )

        # 2. Prepare cancellation event
        cancelled_event = AudioCancelledEvent(
            room_id=room_id,
            session_id=session_id or room_id,
            speaker_id=speaker_id,
            segment_id=segment_id,
            reason=reason,
            flushed_chunks_count=flushed_count,
        )

        # 3. Broadcast flush command to clients in the room
        flush_msg = {
            "type": "playback.flush",
            "room_id": room_id,
            "session_id": session_id or room_id,
            "speaker_id": speaker_id,
            "segment_id": segment_id,
            "reason": reason,
            "timestamp": now,
        }

        # Send to all connected participants in room
        p_count = self.broadcaster.get_connected_count(room_id)
        if p_count > 0:
            # We broadcast to all room websockets
            keys = [
                k.split(":", 1)[1]
                for k in self.broadcaster._sockets.keys()
                if k.startswith(f"{room_id}:")
            ]
            await self.broadcaster.broadcast_json(room_id, keys, flush_msg)

        logger.info(
            "Barge-in cancellation processed",
            extra={
                "room_id": room_id,
                "segment_id": segment_id,
                "speaker_id": speaker_id,
                "flushed_chunks": flushed_count,
                "notified_clients": len(keys) if p_count > 0 else 0,
            }
        )

        return {
            "status": "cancelled",
            "room_id": room_id,
            "segment_id": segment_id,
            "flushed_chunks": flushed_count,
            "event": cancelled_event.model_dump(),
        }

