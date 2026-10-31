"""Core Voice Synthesis Orchestration Service for Agent 06.

Unites quality gating, translation identity validation, voice selection,
provider routing, audio normalization, TalkFlow wire framing, streaming,
and cancellation management.
"""
from __future__ import annotations

import base64
import time
from typing import AsyncIterator, Optional, Tuple

from app.audio.binary_framing import build_binary_tts_frame
from app.audio.chunker import chunk_pcm, split_sentences
from app.audio.normalizer import AudioNormalizer
from app.core.config import get_settings
from app.core.exceptions import (
    AudioFramingError,
    ConsentRequiredError,
    ConsentRevokedError,
    QualityGateRejectedError,
    SpeechSynthesisError,
    TranslationIdentityMismatchError,
    VoiceUnavailableError,
)
from app.core.logging import get_logger
from app.gate.identity_validator import IdentityValidator
from app.gate.quality_gate import QualityGateValidator
from app.models.events import (
    Agent05QualityFinalEvent,
    TTSCancelledEvent,
    TTSChunkEvent,
    TTSCompletedEvent,
    TTSFailedEvent,
    TTSStartedEvent,
)
from app.models.schemas import (
    CancellationResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.providers.router import ProviderRouter
from app.services.cancellation import CancellationManager
from app.services.idempotency import IdempotencyManager
from app.voices.consent_manager import VoiceConsentManager
from app.voices.registry import VoiceRegistry
from app.voices.selector import VoiceSelector

logger = get_logger(__name__)


class SynthesisService:
    """Central synthesis orchestrator."""

    def __init__(
        self,
        registry: Optional[VoiceRegistry] = None,
        consent_manager: Optional[VoiceConsentManager] = None,
        router: Optional[ProviderRouter] = None,
    ) -> None:
        self.settings = get_settings()
        self.registry = registry or VoiceRegistry()
        self.consent_manager = consent_manager or VoiceConsentManager()
        self.selector = VoiceSelector(self.registry, self.consent_manager)
        self.router = router or ProviderRouter()
        self.normalizer = AudioNormalizer(default_sample_rate=self.settings.audio_sample_rate)
        self.quality_gate = QualityGateValidator(min_score=self.settings.min_quality_score)
        self.identity_validator = IdentityValidator()
        self.idempotency = IdempotencyManager(max_size=500, ttl_seconds=300.0)
        self.cancellation = CancellationManager()

    async def synthesize(
        self,
        request: SynthesizeRequest,
        tenant_id: str = "org_default",
    ) -> SynthesizeResponse:
        """Execute full synthesis with quality gate, identity verification, and caching."""
        t0 = time.perf_counter()

        # 1. Quality Gate Check
        self.quality_gate.validate_decision(
            decision=request.quality_decision,
            score=request.quality_score,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
        )

        # 2. Identity Verification
        self.identity_validator.validate_identity(
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
            target_language=request.target_language,
            text=request.text,
        )

        # 3. Check Cancellation
        if self.cancellation.is_cancelled(request.conversation_id, request.segment_id):
            raise SpeechSynthesisError(
                f"Utterance segment '{request.segment_id}' in conversation '{request.conversation_id}' was cancelled."
            )

        # 4. Check Idempotency Cache
        cached = self.idempotency.get(
            tenant_id=tenant_id,
            conversation_id=request.conversation_id,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
            target_language=request.target_language,
            text=request.text,
        )
        if cached is not None:
            logger.info("Serving synthesis response from idempotency cache", extra={"segment_id": request.segment_id})
            return cached

        # 5. Voice Selection with Fail-Closed Fallback (Rules 1, 2, 5)
        try:
            voice = self.selector.select_voice(
                target_language=request.target_language,
                preferred_voice_id=request.requested_voice_id,
                speaker_id=request.speaker_id,
                tenant_id=tenant_id,
                offline_only=request.offline_only or self.settings.offline_only,
                private_only=(request.privacy_mode == "private_only") or self.settings.private_only,
            )
        except (ConsentRequiredError, ConsentRevokedError) as e:
            # Rule 5: If consent is missing, expired, or revoked, automatically use standard expressive voice
            logger.warning(
                f"Voice similarity requested without valid consent for speaker '{request.speaker_id}' in tenant '{tenant_id}': {e}. "
                f"Fail-Closed: Automatically falling back to standard expressive synthetic voice."
            )
            voice = self.selector.select_voice(
                target_language=request.target_language,
                preferred_voice_id=None,
                speaker_id=None,
                tenant_id=tenant_id,
                offline_only=request.offline_only or self.settings.offline_only,
                private_only=(request.privacy_mode == "private_only") or self.settings.private_only,
            )

        # 6. Synthesize Audio
        try:
            tts_res = await self.router.synthesize(
                voice=voice,
                text=request.text,
                language=request.target_language,
                sample_rate=self.settings.audio_sample_rate,
            )
        except Exception as e:
            logger.error("Synthesis provider error", extra={"voice": voice.voice_id, "error": str(e)})
            raise SpeechSynthesisError(f"Speech synthesis failed with voice '{voice.voice_id}': {e}") from e

        # 7. Normalize Audio (PCM16 mono target sample rate)
        norm_pcm, norm_sr = self.normalizer.normalize_pcm(
            pcm_bytes=tts_res.pcm_data,
            source_sr=tts_res.sample_rate,
            target_sr=self.settings.audio_sample_rate,
            channels=1,
        )
        norm_wav = self.normalizer.pcm_to_wav(norm_pcm, sample_rate=norm_sr)

        duration_ms = (len(norm_pcm) / (norm_sr * 2)) * 1000.0
        total_latency_ms = (time.perf_counter() - t0) * 1000.0

        # Encode audio payload to base64
        audio_b64 = base64.b64encode(norm_wav).decode("ascii")
        utterance_id = request.utterance_id or f"utt_{request.segment_id}_{int(time.time()*1000)}"

        response = SynthesizeResponse(
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
            utterance_id=utterance_id,
            speaker_id=request.speaker_id,
            target_language=request.target_language,
            target_locale=voice.locale,
            provider=tts_res.provider,
            model=tts_res.model,
            voice_id=voice.voice_id,
            audio_format="pcm_s16le",
            sample_rate=norm_sr,
            channels=1,
            duration_ms=duration_ms,
            chunk_count=1,
            audio_base64=audio_b64,
            synthetic=True,
            is_dev=tts_res.is_dev,
            generation_latency_ms=total_latency_ms,
            first_audio_chunk_latency_ms=tts_res.latency_ms,
            timestamp=time.time(),
        )

        # Cache response
        self.idempotency.put(
            tenant_id=tenant_id,
            conversation_id=request.conversation_id,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
            target_language=request.target_language,
            text=request.text,
            result=response,
        )

        return response

    async def synthesize_stream(
        self,
        request: SynthesizeRequest,
        tenant_id: str = "org_default",
    ) -> AsyncIterator[Tuple[TTSChunkEvent, bytes]]:
        """Stream synthesized audio chunks and binary TalkFlow wire frames."""
        t0 = time.perf_counter()

        # 1. Quality Gate Check
        self.quality_gate.validate_decision(
            decision=request.quality_decision,
            score=request.quality_score,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
        )

        # 2. Identity Verification
        self.identity_validator.validate_identity(
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
            target_language=request.target_language,
            text=request.text,
        )

        # 3. Voice Selection
        voice = self.selector.select_voice(
            target_language=request.target_language,
            preferred_voice_id=request.requested_voice_id,
            speaker_id=request.speaker_id,
            tenant_id=tenant_id,
            offline_only=request.offline_only or self.settings.offline_only,
            private_only=(request.privacy_mode == "private_only") or self.settings.private_only,
        )

        utterance_id = request.utterance_id or f"utt_{request.segment_id}_{int(time.time()*1000)}"

        # 4. Stream provider chunks
        seq = 0
        first_chunk_sent = False

        async for chunk in self.router.synthesize_stream(
            voice=voice,
            text=request.text,
            language=request.target_language,
            sample_rate=self.settings.audio_sample_rate,
        ):
            # Check cancellation between chunks
            if self.cancellation.is_cancelled(request.conversation_id, request.segment_id):
                logger.warning(
                    "Streaming TTS aborted mid-stream due to cancellation",
                    extra={"conversation_id": request.conversation_id, "segment_id": request.segment_id},
                )
                break

            seq += 1
            norm_pcm, norm_sr = self.normalizer.normalize_pcm(
                pcm_bytes=chunk.data,
                source_sr=chunk.sample_rate,
                target_sr=self.settings.audio_sample_rate,
                channels=1,
            )
            norm_wav = self.normalizer.pcm_to_wav(norm_pcm, sample_rate=norm_sr)

            # TalkFlow binary frame with 0x54 magic prefix and uint32 sequence index
            binary_frame = build_binary_tts_frame(
                segment_id=request.segment_id,
                target_lang=request.target_language,
                chunk_index=chunk.chunk_index,
                audio_pcm_bytes=norm_pcm,
                include_chunk_index=True,
            )

            b64_audio = base64.b64encode(norm_wav).decode("ascii")

            chunk_event = TTSChunkEvent(
                version=1,
                type="tts.chunk",
                session_id=request.session_id,
                conversation_id=request.conversation_id,
                speaker_id=request.speaker_id,
                segment_id=request.segment_id,
                utterance_id=utterance_id,
                translation_id=request.translation_id,
                seq=seq,
                target_lang=request.target_language,
                voice_id=voice.voice_id,
                provider=chunk.provider,
                model=chunk.model,
                chunk_index=chunk.chunk_index,
                is_final_chunk=chunk.is_last,
                sample_rate=norm_sr,
                channels=1,
                encoding="pcm_s16le",
                format="wav",
                duration_ms=chunk.duration_ms,
                audio_base64=b64_audio,
                synthetic=True,
                is_dev=chunk.is_dev,
                created_at=time.time(),
            )

            yield chunk_event, binary_frame

    async def handle_agent05_event(
        self,
        event: Agent05QualityFinalEvent,
        tenant_id: str = "org_default",
    ) -> SynthesizeResponse:
        """Handle incoming Agent 05 quality approval webhook event."""
        # Validate that Agent 05 declared this translation safe for voice
        if not event.is_safe_for_voice:
            raise QualityGateRejectedError(
                f"Agent 05 marked evaluation {event.evaluation_id} as not safe for voice (is_safe_for_voice=False)."
            )

        synth_req = SynthesizeRequest(
            text=event.target_text,
            target_language=event.target_lang,
            session_id=event.session_id,
            conversation_id=event.conversation_id,
            segment_id=event.segment_id,
            translation_id=event.translation_id or f"trans_{event.segment_id}",
            speaker_id=event.speaker_id,
            utterance_id=event.utterance_id,
            quality_decision=event.decision,
            quality_score=event.overall_score,
            privacy_mode="standard",
            offline_only=self.settings.offline_only,
        )

        return await self.synthesize(synth_req, tenant_id=tenant_id)

    def cancel(
        self,
        session_id: str,
        conversation_id: str = "conv_default",
        segment_id: Optional[str] = None,
        utterance_id: Optional[str] = None,
        reason: str = "barge_in_interruption",
    ) -> CancellationResponse:
        """Cancel pending or active utterance synthesis."""
        if segment_id:
            self.cancellation.cancel_segment(conversation_id, segment_id)
            return CancellationResponse(
                cancelled=True,
                segment_id=segment_id,
                utterance_id=utterance_id,
                message=f"Synthesis for segment '{segment_id}' successfully cancelled ({reason}).",
            )
        else:
            self.cancellation.cancel_conversation(conversation_id)
            return CancellationResponse(
                cancelled=True,
                segment_id=None,
                utterance_id=utterance_id,
                message=f"All synthesis in conversation '{conversation_id}' successfully cancelled ({reason}).",
            )
