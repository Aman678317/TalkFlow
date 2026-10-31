"""Fan-out engine for 1-to-N translated audio stream dispatching."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger
from app.models.delivery_models import ParticipantRoute
from app.models.events import AudioPublishedEvent
from app.models.schemas import AudioChunkIngestRequest
from app.routing.participant_router import ParticipantRouter

logger = get_logger("routing.fanout")


class FanoutEngine:
    """Dispatches a single generated language audio chunk to multiple eligible listeners."""

    def __init__(self, router: ParticipantRouter):
        self.router = router

    def resolve_fanout_targets(
        self, chunk: AudioChunkIngestRequest
    ) -> List[ParticipantRoute]:
        """Determine all participants who should receive this chunk."""
        recipients = self.router.get_recipients(
            room_id=chunk.session_id,
            target_lang=chunk.target_lang,
            speaker_id=chunk.speaker_id,
        )
        return recipients

    def create_published_event(
        self,
        chunk: AudioChunkIngestRequest,
        recipients: List[ParticipantRoute],
        transport: str = "websocket_binary",
    ) -> AudioPublishedEvent:
        """Create structured event confirming fan-out publication."""
        track_name = f"gt-translated-{chunk.target_lang}"
        return AudioPublishedEvent(
            room_id=chunk.session_id,
            session_id=chunk.session_id,
            speaker_id=chunk.speaker_id,
            segment_id=chunk.segment_id,
            utterance_id=chunk.utterance_id,
            target_lang=chunk.target_lang,
            track=track_name,
            seq=chunk.seq,
            chunk_index=chunk.chunk_index,
            recipients_count=len(recipients),
            recipient_ids=[p.participant_id for p in recipients],
            transport=transport,
        )

