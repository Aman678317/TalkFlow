"""Agent 1 — listening: audio ingestion, VAD boundaries, speech recognition.

Owns turning captured audio into a trustworthy, timestamped source transcript.
It does not translate and it does not synthesize speech.

The one job that makes the rest of the path debuggable: a segment id stays
stable across partial revisions and is finalized exactly once, and every way
this stage can fail produces an explicit event instead of silence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage, TranscriptSegment
from gt_ai.types import DetectionResult, RouteDecision, TranscriptChunk

log = logging.getLogger("app.realtime.agents.listening")

# 50 ms at 16 kHz mono s16le. Shorter than this is a mic blip, not speech —
# the same bound the live pipeline has always applied.
MIN_AUDIO_BYTES = 1600

# A detected language this weak is not worth speaking a translation for.
LANGUAGE_LOCK_CONFIDENCE = 0.70


class SttProvider(Protocol):
    """The slice of ``app.ai.AIFacade`` that Agent 1 needs."""

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None,
                         ) -> tuple[TranscriptChunk, RouteDecision]: ...

    async def detect_language(self, text: str) -> DetectionResult: ...


class RealtimeSttProvider:
    """Production adapter: delegates to the configured AI facade."""

    def __init__(self, facade) -> None:
        self._facade = facade

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return await self._facade.transcribe(audio, sample_rate, lang_hint=lang_hint)

    async def detect_language(self, text: str) -> DetectionResult:
        return await self._facade.detect_language(text)


@dataclass
class _SegmentState:
    revision: int = 0
    finalized: bool = False
    last_text: str = ""
    locked_language: str | None = None


class ListeningAgent:
    def __init__(self, bus: AgentBus, stt: SttProvider, *, meeting_id: str,
                 sample_rate: int = 16000,
                 min_audio_bytes: int = MIN_AUDIO_BYTES) -> None:
        self.bus = bus
        self.stt = stt
        self.meeting_id = meeting_id
        self.sample_rate = sample_rate
        self.min_audio_bytes = min_audio_bytes
        self._segments: dict[tuple[str, str], _SegmentState] = {}

    # ------------------------------------------------------------------ #
    def _state(self, correlation_id: str, segment_id: str) -> _SegmentState:
        return self._segments.setdefault((correlation_id, segment_id), _SegmentState())

    async def _fail(self, *, correlation_id: str, speaker_id: str, segment_id: str,
                    sequence_number: int, reason: str, **extra) -> None:
        payload = {"stage": "stt", "reason": reason, "recoverable": True}
        payload.update(extra)
        await self.bus.publish(RealtimeEvent(
            type=Stage.STAGE_FAILED, correlation_id=correlation_id,
            meeting_id=self.meeting_id, speaker_id=speaker_id, segment_id=segment_id,
            sequence=sequence_number, payload=payload))

    # ------------------------------------------------------------------ #
    async def on_audio_captured(self, *, correlation_id: str, speaker_id: str,
                                segment_id: str, start_ms: int, sequence_number: int,
                                audio_bytes: int) -> None:
        """VAD reported speech start. Record the boundary, touch no provider."""
        self._state(correlation_id, segment_id)
        await self.bus.publish(RealtimeEvent(
            type=Stage.AUDIO_CAPTURED, correlation_id=correlation_id,
            meeting_id=self.meeting_id, speaker_id=speaker_id, segment_id=segment_id,
            sequence=sequence_number,
            payload={"start_time_ms": start_ms, "audio_bytes": audio_bytes,
                     "sample_rate": self.sample_rate,
                     "sequence_number": sequence_number}))

    async def transcribe_partial(self, *, correlation_id: str, speaker_id: str,
                                 segment_id: str, sequence_number: int, audio: bytes,
                                 lang_hint: str | None = None) -> TranscriptSegment | None:
        state = self._state(correlation_id, segment_id)
        if state.finalized:
            return None
        try:
            chunk, _decision = await self.stt.transcribe(audio, self.sample_rate,
                                                         lang_hint=lang_hint)
        except Exception as exc:
            await self._fail(correlation_id=correlation_id, speaker_id=speaker_id,
                             segment_id=segment_id, sequence_number=sequence_number,
                             reason="provider_unavailable", phase="partial",
                             error_code=type(exc).__name__)
            return None

        text = (chunk.text or "").strip()
        if not text or text == state.last_text:
            return None
        if (not state.locked_language and chunk.language
                and (chunk.confidence or 0.0) >= LANGUAGE_LOCK_CONFIDENCE):
            state.locked_language = chunk.language
        state.last_text = text
        state.revision += 1
        segment = TranscriptSegment(
            correlation_id=correlation_id, meeting_id=self.meeting_id,
            speaker_id=speaker_id, segment_id=segment_id,
            sequence_number=sequence_number, transcript_revision=state.revision,
            source_language=state.locked_language or chunk.language or lang_hint or "auto",
            recognized_text=text, start_time_ms=chunk.start_ms, end_time_ms=chunk.end_ms,
            is_final=False, confidence=chunk.confidence)
        await self.bus.publish(segment.to_event(Stage.TRANSCRIPT_PARTIAL))
        return segment

    async def finalize(self, *, correlation_id: str, speaker_id: str, segment_id: str,
                       sequence_number: int, audio: bytes, start_ms: int, end_ms: int,
                       lang_hint: str | None = None) -> TranscriptSegment | None:
        """Recognize the closed segment and emit exactly one final transcript."""
        state = self._state(correlation_id, segment_id)
        if state.finalized:
            return None
        if len(audio) < self.min_audio_bytes:
            # Not speech — deliberately no transcript event, and no provider call.
            return None
        try:
            chunk, _decision = await self.stt.transcribe(audio, self.sample_rate,
                                                         lang_hint=lang_hint)
        except Exception as exc:
            await self._fail(correlation_id=correlation_id, speaker_id=speaker_id,
                             segment_id=segment_id, sequence_number=sequence_number,
                             reason="provider_unavailable",
                             error_code=type(exc).__name__, error=str(exc)[:160])
            return None

        text = (chunk.text or "").strip()
        if not text:
            await self._fail(correlation_id=correlation_id, speaker_id=speaker_id,
                             segment_id=segment_id, sequence_number=sequence_number,
                             reason="empty_speech", audio_bytes=len(audio))
            return None

        language = state.locked_language or chunk.language or lang_hint
        if not language or language == "auto":
            try:
                detected = await self.stt.detect_language(text)
                language = detected.language
            except Exception as exc:
                await self._fail(correlation_id=correlation_id, speaker_id=speaker_id,
                                 segment_id=segment_id, sequence_number=sequence_number,
                                 reason="provider_unavailable", phase="language_detect",
                                 error_code=type(exc).__name__)
                return None
        if not language or language == "auto":
            await self._fail(correlation_id=correlation_id, speaker_id=speaker_id,
                             segment_id=segment_id, sequence_number=sequence_number,
                             reason="unsupported_language", recognized_chars=len(text))
            return None

        state.finalized = True
        state.last_text = text
        state.revision += 1
        segment = TranscriptSegment(
            correlation_id=correlation_id, meeting_id=self.meeting_id,
            speaker_id=speaker_id, segment_id=segment_id,
            sequence_number=sequence_number, transcript_revision=state.revision,
            source_language=language, recognized_text=text,
            start_time_ms=start_ms, end_time_ms=end_ms or chunk.end_ms,
            is_final=True, confidence=chunk.confidence)
        await self.bus.publish(segment.to_event(Stage.TRANSCRIPT_FINAL))
        self._prune()
        return segment

    # ------------------------------------------------------------------ #
    def _prune(self) -> None:
        """Drop closed segments once the bookkeeping grows, never live speech."""
        if len(self._segments) <= 32:
            return
        for key, st in list(self._segments.items()):
            if st.finalized:
                self._segments.pop(key, None)

    def reset_utterance(self, correlation_id: str) -> None:
        """Barge-in: forget revision state for one in-flight utterance."""
        for key in [k for k in self._segments if k[0] == correlation_id]:
            self._segments.pop(key, None)
