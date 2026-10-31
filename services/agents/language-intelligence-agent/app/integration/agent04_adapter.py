"""Adapter for formatting outbound language analysis contracts for Agent 04 (Neural Translation Agent)."""
from __future__ import annotations

import time
from typing import Any, Dict
from app.models.events import InboundTranscriptEvent, LanguageAnalysisFinalEvent
from app.models.schemas import LanguageAnalysisResponse


class Agent04Adapter:
    """Formats and dispatches outbound event contract for Agent 04 (Neural Translation Agent)."""

    AGENT04_URL = "http://127.0.0.1:8004/api/v1/translation/agent03/transcript"

    @staticmethod
    def format_analysis_final_event(
        response: LanguageAnalysisResponse,
        original_event: InboundTranscriptEvent,
    ) -> LanguageAnalysisFinalEvent:
        """Constructs canonical language.analysis.final event payload for Agent 04."""
        targets = getattr(original_event, "target_languages", None) or ["en", "hi", "mr"]
        return LanguageAnalysisFinalEvent(
            type="language.analysis.final",
            session_id=response.session_id,
            conversation_id=response.conversation_id,
            speaker_id=response.speaker_id,
            utterance_id=response.utterance_id or original_event.utterance_id,
            segment_id=response.segment_id or original_event.segment_id,
            seq=response.seq,
            original_text=response.original_text,
            primary_language=response.primary_language,
            primary_language_script=response.primary_language_script,
            secondary_languages=response.secondary_languages,
            is_multilingual=response.is_multilingual,
            detection_status=response.detection_status,
            confidence=response.confidence,
            target_languages=targets,
            language_spans=response.language_spans,
            capability_status=response.capability_status,
            analysis_latency_ms=response.analysis_latency_ms,
            timestamp=time.time(),
        )

    @classmethod
    async def forward_to_agent04(cls, event: LanguageAnalysisFinalEvent) -> bool:
        """Asynchronously dispatches language.analysis.final to Agent 04 on port 8004."""
        import httpx
        payload = event.model_dump()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(cls.AGENT04_URL, json=payload)
                return resp.status_code == 200
        except Exception:
            return False

