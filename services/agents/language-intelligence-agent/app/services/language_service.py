"""High-level Language Intelligence Service coordinating engine, sessions, and telemetry."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.logging import get_logger
from app.detection.engine import LanguageIntelligenceEngine
from app.models.events import InboundTranscriptEvent, LanguageAnalysisFinalEvent, WordTiming
from app.models.schemas import LanguageAnalysisResponse
from app.monitoring.metrics import metrics
from app.sessions.session_manager import LanguageSessionManager

log = get_logger("services.language_service")


class LanguageIntelligenceService:
    """Service coordinator for language identification batch and streaming requests."""

    def __init__(
        self,
        engine: Optional[LanguageIntelligenceEngine] = None,
        session_manager: Optional[LanguageSessionManager] = None,
    ):
        self.engine = engine or LanguageIntelligenceEngine()
        self.session_manager = session_manager or LanguageSessionManager(
            max_sessions=settings.sessions.max_concurrent_sessions,
        )

    async def analyze_text(
        self,
        text: str,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        speaker_id: str = "user_001",
        utterance_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        seq: int = 1,
        language_hint: Optional[str] = None,
        stt_probability: Optional[float] = None,
        word_timings: Optional[List[WordTiming]] = None,
    ) -> LanguageAnalysisResponse:
        """Processes raw text and returns comprehensive language analysis response."""
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        conv_id = conversation_id or sess_id
        utt_id = utterance_id or f"utt_{uuid.uuid4().hex[:12]}"
        seg_id = segment_id or f"seg_{uuid.uuid4().hex[:12]}"

        # Retrieve speaker dominant language for hysteresis
        speaker_dominant = self.session_manager.get_speaker_dominant_language(sess_id, speaker_id)

        # Run multi-signal engine
        resp = self.engine.analyze_text(
            text=text,
            session_id=sess_id,
            conversation_id=conv_id,
            speaker_id=speaker_id,
            utterance_id=utt_id,
            segment_id=seg_id,
            seq=seq,
            language_hint=language_hint,
            stt_probability=stt_probability,
            word_timings=word_timings,
            speaker_dominant_lang=speaker_dominant,
        )

        # Update speaker stateful history
        self.session_manager.record_speaker_utterance(
            session_id=sess_id,
            speaker_id=speaker_id,
            utterance_id=utt_id,
            detected_language=resp.primary_language,
            confidence=resp.confidence,
            is_multilingual=resp.is_multilingual,
            conversation_id=conv_id,
        )

        # Record telemetry metrics
        sec_str = ",".join(resp.secondary_languages)
        metrics.record_detection(
            language=resp.primary_language,
            script=resp.primary_language_script,
            provider=resp.provider,
            latency_sec=resp.analysis_latency_ms / 1000.0,
            is_multilingual=resp.is_multilingual,
            secondary_langs=sec_str,
            status=resp.detection_status,
            reason=resp.evidence.get("reason_code") or "none",
        )
        metrics.set_active_sessions(self.session_manager.active_session_count)

        return resp

    async def handle_agent02_transcript_event(self, event: InboundTranscriptEvent) -> LanguageAnalysisFinalEvent:
        """Consumes a finalized transcript event from Agent 02 and produces an Agent 04 analysis event."""
        from app.integration.agent04_adapter import Agent04Adapter

        analysis_resp = await self.analyze_text(
            text=event.text,
            session_id=event.session_id,
            conversation_id=event.conversation_id,
            speaker_id=event.speaker_id,
            utterance_id=event.utterance_id,
            segment_id=event.segment_id,
            seq=event.seq,
            language_hint=event.language_hint,
            stt_probability=event.language_probability,
            word_timings=event.words,
        )

        final_event = Agent04Adapter.format_analysis_final_event(analysis_resp, event)
        import asyncio
        asyncio.create_task(Agent04Adapter.forward_to_agent04(final_event))
        return final_event


language_service = LanguageIntelligenceService()

