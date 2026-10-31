"""Event publisher dispatching translation.final to Agent 05 (Translation Quality Agent)."""
from __future__ import annotations

import logging
import httpx
from app.core.config import settings
from app.models.events import TranslationFinalEvent

log = logging.getLogger("agent04.integration.publisher")


class EventPublisher:
    """Dispatches final translation events to Agent 05 and TalkFlow core."""

    def __init__(self, agent05_url: str = settings.integration.agent05_url) -> None:
        self.agent05_url = agent05_url.rstrip("/")

    async def forward_to_agent05(self, event: TranslationFinalEvent) -> bool:
        """Posts translated output to Agent 05 for semantic quality validation."""
        url = f"{self.agent05_url}/api/v1/quality/agent04/transcript"
        payload = event.model_dump()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code in (200, 201, 202):
                    log.info(f"Published segment {event.segment_id} ({event.source_lang}->{event.target_lang}) to Agent 05")
                    return True
                log.warning(f"Agent 05 responded with status {resp.status_code}")
                return False
        except Exception as e:
            log.debug(f"Agent 05 endpoint offline ({url}): {e}")
            return False


publisher = EventPublisher()

