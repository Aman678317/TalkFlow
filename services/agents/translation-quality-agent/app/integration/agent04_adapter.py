"""Inbound adapter for Agent 04 (Neural Translation Agent) translation.final events."""
from __future__ import annotations

from typing import Any, Dict
from app.models.events import Agent04TranslationFinalEvent
from app.models.schemas import EvaluationRequestSchema


class Agent04Adapter:
    """Adapts Agent 04 translation.final event envelopes into Agent 05 EvaluationRequestSchema."""

    @staticmethod
    def to_evaluation_request(event: Agent04TranslationFinalEvent) -> EvaluationRequestSchema:
        return EvaluationRequestSchema(
            source_text=event.source_text,
            target_text=event.text,
            source_lang=event.source_lang,
            target_lang=event.target_lang,
            session_id=event.session_id,
            conversation_id=event.conversation_id,
            speaker_id=event.speaker_id,
            utterance_id=event.utterance_id,
            segment_id=event.segment_id,
            translation_id=f"tx_{event.segment_id}_{event.target_lang}",
            provider=event.provider or "agent04",
            model=event.model or "unknown",
            glossary=event.glossary_terms,
            protected_spans=event.protected_spans,
            mode="final",
        )

