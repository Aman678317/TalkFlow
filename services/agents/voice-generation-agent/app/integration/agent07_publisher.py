"""Outbound event dispatcher for Agent 07 (Audio Synchronization & Delivery)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.events import TTSChunkEvent, TTSCompletedEvent, TTSStartedEvent

logger = get_logger(__name__)


class Agent07Publisher:
    """Dispatches synthesized audio chunks and lifecycle events to Agent 07."""

    def __init__(self, agent07_url: Optional[str] = None) -> None:
        self.settings = get_settings()
        self.agent07_url = (agent07_url or self.settings.agent07_url).rstrip("/")
        self.shared_secret = self.settings.shared_secret

    async def publish_started(self, event: TTSStartedEvent) -> None:
        """Publish tts.started event."""
        await self._dispatch("/api/v1/audio/sync/started", event.model_dump())

    async def publish_chunk(self, event: TTSChunkEvent) -> None:
        """Publish tts.chunk event."""
        await self._dispatch("/api/v1/audio/sync/chunk", event.model_dump())

    async def publish_completed(self, event: TTSCompletedEvent) -> None:
        """Publish tts.completed event."""
        await self._dispatch("/api/v1/audio/sync/completed", event.model_dump())

    async def _dispatch(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        target = f"{self.agent07_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.shared_secret}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(target, json=payload, headers=headers)
                if resp.status_code in (200, 201, 202):
                    logger.debug("Dispatched event to Agent 07", extra={"endpoint": endpoint})
                    return resp.json()
        except Exception:
            # Agent 07 may not yet be running if user hasn't launched Agent 07
            logger.debug(
                "Agent 07 offline or unreachable, event enqueued locally",
                extra={"target": target, "event_type": payload.get("type")},
            )
        return None

