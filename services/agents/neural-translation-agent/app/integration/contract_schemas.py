"""Pipeline contracts and format transformations."""
from __future__ import annotations

from typing import Dict, List, Optional
from app.models.events import Agent03TranscriptEvent, TranslationFinalEvent
from app.models.schemas import BatchTranslationRequestSchema


def adapt_agent03_to_batch_request(event: Agent03TranscriptEvent, target_langs: Optional[List[str]] = None) -> BatchTranslationRequestSchema:
    """Converts inbound Agent 03 transcript analysis event into a multi-target translation batch request."""
    targets = target_langs or event.target_languages or ["en"]
    return BatchTranslationRequestSchema(
        text=event.original_text,
        source_lang=event.primary_language,
        target_langs=targets,
        session_id=event.session_id,
        conversation_id=event.conversation_id,
        speaker_id=event.speaker_id,
        utterance_id=event.utterance_id,
        segment_id=event.segment_id,
    )

