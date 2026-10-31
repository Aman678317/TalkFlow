"""Final transcription and text integrity engine."""
from __future__ import annotations

import time
from typing import Dict, Optional, Set
from app.audio.timestamps import TimelineConverter
from app.core.logging import get_logger
from app.models.events import TranscriptFinalEvent
from app.models.schemas import STTResult, TranscribeResponse
from app.providers.base import STTProvider
from app.stt.confidence import ConfidenceEvaluator

log = get_logger("stt.finalizer")


class FinalizerEngine:
    """Produces immutable finalized transcripts with idempotency protection and anti-hallucination."""

    def __init__(self, provider: STTProvider, evaluator: Optional[ConfidenceEvaluator] = None):
        self.provider = provider
        self.evaluator = evaluator or ConfidenceEvaluator()
        self._finalized_segment_ids: Set[str] = set()

    def is_finalized(self, segment_id: str) -> bool:
        """Idempotency check: returns True if segment was already finalized."""
        return segment_id in self._finalized_segment_ids

    def finalize(
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
        """Executes final transcription for an utterance segment."""
        # Idempotency guard
        if segment_id in self._finalized_segment_ids:
            log.warning(f"Segment {segment_id} already finalized. Ignoring duplicate submission.")

        started = time.perf_counter()

        # 1. Execute transcription
        raw_result: STTResult = self.provider.transcribe(
            audio_pcm16=audio_pcm16,
            sample_rate=sample_rate,
            language_hint=language_hint,
            word_timestamps=word_timestamps,
        )

        # 2. Evaluate confidence and filter hallucinations
        clean_text, quality_flags = self.evaluator.evaluate(raw_result)

        # 3. Align timestamps relative to conversation timeline
        aligned_segments = TimelineConverter.align_segment_timings(
            raw_result.segments,
            base_start_ms=start_ms,
        )

        all_words = []
        for s in aligned_segments:
            all_words.extend(s.words)

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        duration_ms = round(len(audio_pcm16) / 32.0, 2)  # 32 bytes/ms at 16kHz PCM16 mono

        self._finalized_segment_ids.add(segment_id)

        return TranscribeResponse(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            utterance_id=utterance_id,
            segment_id=segment_id,
            text=clean_text,
            language_hint=raw_result.language,
            language_probability=raw_result.language_probability,
            confidence=raw_result.confidence,
            is_final=True,
            provider=self.provider.name,
            model=self.provider.model_name,
            duration_ms=duration_ms,
            recognition_latency_ms=latency_ms,
            segments=aligned_segments,
            words=all_words,
            quality_flags=quality_flags,
        )

    def to_event(self, resp: TranscribeResponse, seq: int = 1) -> TranscriptFinalEvent:
        """Converts TranscribeResponse to TalkFlow TranscriptFinalEvent envelope."""
        return TranscriptFinalEvent(
            session_id=resp.session_id,
            conversation_id=resp.conversation_id,
            speaker_id=resp.speaker_id,
            utterance_id=resp.utterance_id,
            segment_id=resp.segment_id,
            seq=seq,
            duration_ms=resp.duration_ms,
            text=resp.text,
            language_hint=resp.language_hint,
            language_probability=resp.language_probability,
            confidence=resp.confidence,
            is_final=True,
            provider=resp.provider,
            model=resp.model,
            recognition_latency_ms=resp.recognition_latency_ms,
            quality_flags=resp.quality_flags,
            segments=[s.model_dump() for s in resp.segments],
            words=[w.model_dump() for w in resp.words],
        )

