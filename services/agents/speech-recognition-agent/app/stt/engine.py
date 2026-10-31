"""High-level STT Engine coordinating speech recognition pipeline."""
from __future__ import annotations

import asyncio
from typing import Optional, Tuple
from app.core.config import settings
from app.core.logging import get_logger
from app.models.events import TranscriptFinalEvent, TranscriptPartialEvent
from app.models.schemas import TranscribeResponse
from app.providers import get_stt_provider
from app.providers.base import STTProvider
from app.stt.confidence import ConfidenceEvaluator
from app.stt.finalizer import FinalizerEngine
from app.stt.partial_manager import PartialManager

log = get_logger("stt.engine")


class STTEngine:
    """Core Speech Recognition Engine handling file, segment, and streaming recognition."""

    def __init__(self, provider: Optional[STTProvider] = None):
        self.provider = provider or get_stt_provider()
        self.evaluator = ConfidenceEvaluator(
            no_speech_threshold=settings.anti_hallucination.no_speech_threshold,
            min_confidence=settings.anti_hallucination.min_confidence,
            max_repetition_count=settings.anti_hallucination.max_repetition_count,
            suppress_silence_loops=settings.anti_hallucination.suppress_silence_loops,
        )
        self.finalizer = FinalizerEngine(self.provider, self.evaluator)
        self.partial_manager = PartialManager(
            self.provider,
            partial_interval_ms=settings.streaming.partial_interval_ms,
            min_duration_ms=settings.streaming.min_audio_duration_ms,
            max_duration_ms=settings.streaming.max_audio_duration_ms,
        )

    def transcribe_segment(
        self,
        audio_pcm16: bytes,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        utterance_id: str,
        segment_id: str,
        seq: int = 1,
        start_ms: int = 0,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None,
        word_timestamps: bool = True,
    ) -> TranscribeResponse:
        """Synchronously transcribes an audio segment from Agent 01."""
        return self.finalizer.finalize(
            audio_pcm16=audio_pcm16,
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            utterance_id=utterance_id,
            segment_id=segment_id,
            seq=seq,
            start_ms=start_ms,
            sample_rate=sample_rate,
            language_hint=language_hint,
            word_timestamps=word_timestamps,
        )

    async def transcribe_segment_async(
        self,
        audio_pcm16: bytes,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        utterance_id: str,
        segment_id: str,
        seq: int = 1,
        start_ms: int = 0,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None,
        word_timestamps: bool = True,
    ) -> TranscribeResponse:
        """Asynchronously transcribes an audio segment in threadpool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.transcribe_segment(
                audio_pcm16=audio_pcm16,
                session_id=session_id,
                conversation_id=conversation_id,
                speaker_id=speaker_id,
                utterance_id=utterance_id,
                segment_id=segment_id,
                seq=seq,
                start_ms=start_ms,
                sample_rate=sample_rate,
                language_hint=language_hint,
                word_timestamps=word_timestamps,
            ),
        )

    def detect_language(self, audio_pcm16: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
        """Detects language hint without overriding Agent 03."""
        return self.provider.detect_language(audio_pcm16, sample_rate)

