"""Adapter matching TalkFlow core repository event models and detection payloads."""
from __future__ import annotations

import time
from typing import Any, Dict
from app.models.schemas import LanguageAnalysisResponse


class TalkFlowAdapter:
    """Provides compatibility with core TalkFlow backend event structures."""

    @staticmethod
    def to_talkflow_detection_dict(resp: LanguageAnalysisResponse) -> Dict[str, Any]:
        """Maps LanguageAnalysisResponse to TalkFlow's legacy DetectionResult schema."""
        return {
            "language": resp.primary_language,
            "confidence": resp.confidence,
            "provider": resp.provider,
            "is_multilingual": resp.is_multilingual,
            "secondary_languages": resp.secondary_languages,
            "spans": [s.model_dump() for s in resp.language_spans],
            "execution_time_ms": resp.analysis_latency_ms,
        }

    @staticmethod
    def to_talkflow_realtime_envelope(resp: LanguageAnalysisResponse) -> Dict[str, Any]:
        """Wraps output in standard TalkFlow realtime event envelope."""
        return {
            "event": "language.detected",
            "session_id": resp.session_id,
            "conversation_id": resp.conversation_id,
            "speaker_id": resp.speaker_id,
            "timestamp": time.time(),
            "data": resp.model_dump(),
        }

