"""WebSocket broadcaster for real-time binary audio frames and control events."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket
from app.core.logging import get_logger

logger = get_logger("transport.websocket")


class WebSocketBroadcaster:
    """Manages active participant WebSockets and dispatches binary audio frames."""

    def __init__(self):
        # (room_id, participant_id) -> WebSocket
        self._sockets: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, room_id: str, participant_id: str) -> str:
        return f"{room_id}:{participant_id}"

    async def connect(self, room_id: str, participant_id: str, websocket: WebSocket) -> None:
        """Register an active participant WebSocket connection."""
        await websocket.accept()
        key = self._make_key(room_id, participant_id)
        async with self._lock:
            self._sockets[key] = websocket
        logger.info(
            "WebSocket participant connected",
            extra={"room_id": room_id, "participant_id": participant_id}
        )

    async def disconnect(self, room_id: str, participant_id: str) -> None:
        """Unregister a participant WebSocket connection."""
        key = self._make_key(room_id, participant_id)
        async with self._lock:
            if key in self._sockets:
                del self._sockets[key]
        logger.info(
            "WebSocket participant disconnected",
            extra={"room_id": room_id, "participant_id": participant_id}
        )

    async def send_binary(self, room_id: str, participant_id: str, binary_frame: bytes) -> bool:
        """Send a binary frame directly to one participant."""
        key = self._make_key(room_id, participant_id)
        ws = self._sockets.get(key)
        if not ws:
            return False

        try:
            await ws.send_bytes(binary_frame)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to send binary frame to participant",
                extra={"room_id": room_id, "participant_id": participant_id, "error": str(exc)}
            )
            await self.disconnect(room_id, participant_id)
            return False

    async def send_json(self, room_id: str, participant_id: str, event_data: Dict[str, Any]) -> bool:
        """Send a JSON event to one participant."""
        key = self._make_key(room_id, participant_id)
        ws = self._sockets.get(key)
        if not ws:
            return False

        try:
            await ws.send_text(json.dumps(event_data))
            return True
        except Exception as exc:
            logger.warning(
                "Failed to send JSON to participant",
                extra={"room_id": room_id, "participant_id": participant_id, "error": str(exc)}
            )
            await self.disconnect(room_id, participant_id)
            return False

    async def broadcast_binary(
        self, room_id: str, recipient_ids: List[str], binary_frame: bytes
    ) -> int:
        """Broadcast binary frame to multiple participants in a room."""
        success_count = 0
        for pid in recipient_ids:
            if await self.send_binary(room_id, pid, binary_frame):
                success_count += 1
        return success_count

    async def broadcast_json(
        self, room_id: str, recipient_ids: List[str], event_data: Dict[str, Any]
    ) -> int:
        """Broadcast JSON event to multiple participants in a room."""
        success_count = 0
        for pid in recipient_ids:
            if await self.send_json(room_id, pid, event_data):
                success_count += 1
        return success_count

    def get_connected_count(self, room_id: Optional[str] = None) -> int:
        """Count connected WebSockets, optionally filtered by room."""
        if room_id:
            return sum(1 for k in self._sockets.keys() if k.startswith(f"{room_id}:"))
        return len(self._sockets)

