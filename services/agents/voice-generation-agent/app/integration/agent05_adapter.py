"""Adapter for incoming Agent 05 quality validation events."""
from __future__ import annotations

import time
from typing import Any, Dict

from app.core.exceptions import QualityGateRejectedError
from app.core.logging import get_logger
from app.integration.agent07_publisher import Agent07Publisher
from app.models.events import (
    Agent05QualityFinalEvent,
    TTSChunkEvent,
    TTSCompletedEvent,
    TTSStartedEvent,
)
from app.models.schemas import SynthesizeResponse
from app.services.synthesis_service import SynthesisService

logger = get_logger(__name__)


class Agent05Adapter:
    """Processes validated translation events from Agent 05."""

    def __init__(
        self,
        service: SynthesisService,
        publisher: Agent07Publisher,
    ) -> None:
        self.service = service
        self.publisher = publisher

    async def process_event(self, payload: Dict[str, Any], tenant_id: str = "org_default") -> SynthesizeResponse:
        """Parse, validate quality gate, synthesize, and dispatch to Agent 07."""
        # Normalize fields if sent with different aliases
        decision = str(payload.get("decision", "REJECT")).upper()
        overall_score = float(payload.get("overall_score", payload.get("score", 0.0)))
        target_text = str(payload.get("target_text", payload.get("text", "")))
        target_lang = str(payload.get("target_lang", payload.get("target_language", "en")))
        segment_id = str(payload.get("segment_id", f"seg_{int(time.time()*1000)}"))
        translation_id = str(payload.get("translation_id", f"trans_{segment_id}"))
        session_id = str(payload.get("session_id", "sess_default"))
        conversation_id = str(payload.get("conversation_id", "conv_default"))
        speaker_id = str(payload.get("speaker_id", "user_001"))
        utterance_id = payload.get("utterance_id") or f"utt_{segment_id}"

        event = Agent05QualityFinalEvent(
            version=1,
            type="quality.assessment.final",
            evaluation_id=str(payload.get("evaluation_id", f"eval_{segment_id}")),
            candidate_hash=str(payload.get("candidate_hash", "")),
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            utterance_id=utterance_id,
            segment_id=segment_id,
            translation_id=translation_id,
            source_lang=str(payload.get("source_lang", "en")),
            target_lang=target_lang,
            source_text=str(payload.get("source_text", "")),
            target_text=target_text,
            decision=decision,
            overall_score=overall_score,
            is_safe_for_voice=bool(payload.get("is_safe_for_voice", True)),
            provider=payload.get("provider"),
            model=payload.get("model"),
            metadata=payload.get("metadata", {}),
            timestamp=float(payload.get("timestamp", time.time())),
        )

        logger.info(
            "Agent 05 inbound translation event received",
            extra={
                "segment_id": segment_id,
                "target_lang": target_lang,
                "decision": decision,
                "score": overall_score,
            },
        )

        # Notify Agent 07 that TTS is starting
        started_event = TTSStartedEvent(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            segment_id=segment_id,
            utterance_id=utterance_id,
            translation_id=translation_id,
            target_lang=target_lang,
            voice_id="auto",
            provider="talkflow",
        )
        await self.publisher.publish_started(started_event)

        # Execute synthesis
        synth_resp = await self.service.handle_agent05_event(event, tenant_id=tenant_id)

        # Forward completion to Agent 07
        chunk_event = TTSChunkEvent(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            segment_id=segment_id,
            utterance_id=synth_resp.utterance_id,
            translation_id=translation_id,
            seq=1,
            target_lang=target_lang,
            voice_id=synth_resp.voice_id,
            provider=synth_resp.provider,
            model=synth_resp.model,
            chunk_index=0,
            is_final_chunk=True,
            sample_rate=synth_resp.sample_rate,
            channels=synth_resp.channels,
            duration_ms=synth_resp.duration_ms,
            audio_base64=synth_resp.audio_base64,
            synthetic=True,
            is_dev=synth_resp.is_dev,
            created_at=time.time(),
        )
        await self.publisher.publish_chunk(chunk_event)

        completed_event = TTSCompletedEvent(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            segment_id=segment_id,
            utterance_id=synth_resp.utterance_id,
            translation_id=translation_id,
            target_lang=target_lang,
            voice_id=synth_resp.voice_id,
            provider=synth_resp.provider,
            total_chunks=1,
            total_duration_ms=synth_resp.duration_ms,
            generation_latency_ms=synth_resp.generation_latency_ms,
            first_chunk_latency_ms=synth_resp.first_audio_chunk_latency_ms,
            created_at=time.time(),
        )
        await self.publisher.publish_completed(completed_event)

        return synth_resp

