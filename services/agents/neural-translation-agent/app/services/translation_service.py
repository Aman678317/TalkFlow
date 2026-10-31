"""High-level translation service orchestrating single, batch, and event workflows."""
from __future__ import annotations

import asyncio
import logging
from typing import List
from app.integration.event_publisher import publisher as agent05_publisher
from app.models.events import Agent03TranscriptEvent, TranslationFinalEvent, TranslationFailedEvent
from app.models.schemas import BatchTranslationRequestSchema, BatchTranslationResponseSchema, TranslationRequestSchema, TranslationResponseSchema
from app.services.fanout_adapter import fanout_coordinator
from app.services.session_manager import session_manager
from app.translation.engine import translation_engine

log = logging.getLogger("agent04.services.translation")


class TranslationService:
    """Service facade for REST endpoints, streaming pipelines, and multi-agent coordination."""

    def __init__(self) -> None:
        self.engine = translation_engine
        self.fanout = fanout_coordinator
        self.session_manager = session_manager

    async def translate_single(self, req: TranslationRequestSchema) -> TranslationResponseSchema:
        return await self.engine.translate_single(req)

    async def translate_batch(self, req: BatchTranslationRequestSchema) -> BatchTranslationResponseSchema:
        return await self.fanout.execute_fanout(req)

    async def handle_agent03_event(self, event: Agent03TranscriptEvent) -> List[TranslationFinalEvent]:
        """Consumes a finalized transcript event from Agent 03 and dispatches multi-target translations."""
        targets = event.target_languages or ["en"]
        batch_req = BatchTranslationRequestSchema(
            text=event.original_text,
            source_lang=event.primary_language,
            target_langs=targets,
            session_id=event.session_id,
            conversation_id=event.conversation_id,
            speaker_id=event.speaker_id,
            utterance_id=event.utterance_id,
            segment_id=event.segment_id,
        )

        batch_resp = await self.fanout.execute_fanout(batch_req)
        final_events: List[TranslationFinalEvent] = []

        for tgt, res in batch_resp.results.items():
            if res.status in ("success", "identity"):
                final_events.append(
                    TranslationFinalEvent(
                        session_id=event.session_id,
                        conversation_id=event.conversation_id,
                        speaker_id=event.speaker_id,
                        utterance_id=event.utterance_id,
                        segment_id=event.segment_id,
                        seq=event.seq,
                        source_lang=event.primary_language,
                        target_lang=tgt,
                        source_text=event.original_text,
                        text=res.text,
                        is_final=True,
                        provider=res.provider,
                        model=res.model,
                        latency_ms=res.latency_ms,
                        quality_flags=res.quality_flags,
                        pivoted=res.pivoted,
                        source_equals_target=(res.status == "identity"),
                    )
                )

        for ev in final_events:
            asyncio.create_task(agent05_publisher.forward_to_agent05(ev))

        return final_events


translation_service = TranslationService()

