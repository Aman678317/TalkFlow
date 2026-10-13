"""Agent 1 — listening: audio ingestion, VAD boundaries, speech recognition.

Owns turning captured audio into a trustworthy, timestamped source transcript.
It does not translate and it does not synthesize speech.

The one job that makes the rest of the path debuggable: a segment id stays
stable across partial revisions and is finalized exactly once, and every way
this stage can fail produces an explicit event instead of silence.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
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
                 min_audio_bytes: int = MIN_AUDIO_BYTES,
                 on_detect: Callable[[str, DetectionResult], Awaitable[None]] | None = None,
                 ) -> None:
        self.bus = bus
        self.stt = stt
        self.meeting_id = meeting_id
        self.sample_rate = sample_rate
        self.min_audio_bytes = min_audio_bytes
        self.on_detect = on_detect
        self._segments: dict[tuple[str, str], _SegmentState] = {}
        self._failures: dict[str, dict] = {}
        self._provider_ms: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    def _state(self, correlation_id: str, segment_id: str) -> _SegmentState:
        return self._segments.setdefault((correlation_id, segment_id), _SegmentState())

    def take_failure(self, correlation_id: str) -> dict | None:
        """Pop the failure this stage last recorded for one utterance.

        The session owner needs the *reason* to pick the right wire event: an
        empty transcript is a normal outcome, an unavailable provider is a
        recoverable error, and both look like `None` from here.
        """
        return self._failures.pop(correlation_id, None)

    def take_provider_ms(self, correlation_id: str) -> float:
        """Milliseconds the recognition call itself took, excluding detection."""
        return self._provider_ms.pop(correlation_id, 0.0)

    async def detect_language(self, text: str) -> DetectionResult:
        """Recognise a language for text the pipeline already has.

        The injected-transcript path needs detection without audio, and the
        provider stays behind this stage: the session owner never calls an STT
        provider directly.
        """
        return await self.stt.detect_language(text)

    def _effective_hint(self, state: _SegmentState,
                        lang_hint: str | None) -> str | None:
        """A declared speak language wins over a lock inferred from audio."""
        return lang_hint or state.locked_language

    async def _fail(self, *, correlation_id: str, speaker_id: str, segment_id: str,
                    sequence_number: int, reason: str, **extra) -> None:
        payload = {"stage": "stt", "reason": reason, "recoverable": True}
        payload.update(extra)
        # Kept for the session owner so it can map a stage failure to the exact
        # wire event the client expects ("speech.ended empty" vs "stt
        # unavailable") without re-deriving it from a None return. The raw cause
        # stays in this record — a provider's message quotes the audio it failed
        # on often enough that it has no business in the meeting's trace.
        self._failures[correlation_id] = payload
        await self.bus.publish(RealtimeEvent(
            type=Stage.STAGE_FAILED, correlation_id=correlation_id,
            meeting_id=self.meeting_id, speaker_id=speaker_id, segment_id=segment_id,
            sequence=sequence_number,
            payload={k: v for k, v in payload.items() if k != "error"}))

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
        # Once a language is locked it is fed back as the hint: recognising Hindi
        # text without saying "Hindi" costs accuracy on every later partial.
        hint = self._effective_hint(state, lang_hint)
        try:
            chunk, decision = await self.stt.transcribe(audio, self.sample_rate,
                                                        lang_hint=hint)
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
            is_final=False, confidence=chunk.confidence,
            provider=chunk.provider or decision.provider,
            model=chunk.model or decision.model)
        await self.bus.publish(segment.to_event(Stage.TRANSCRIPT_PARTIAL))
        return segment

    async def finalize(self, *, correlation_id: str, speaker_id: str, segment_id: str,
                       sequence_number: int, audio: bytes, start_ms: int, end_ms: int,
                       lang_hint: str | None = None) -> TranscriptSegment | None:
        """Recognize the closed segment and emit exactly one final transcript."""
        state = self._state(correlation_id, segment_id)
        if state.finalized:
            return None
        self._failures.pop(correlation_id, None)
        if len(audio) < self.min_audio_bytes:
            # Not speech — deliberately no transcript event, and no provider call.
            return None
        t0 = time.perf_counter()
        hint = self._effective_hint(state, lang_hint)
        try:
            chunk, decision = await self.stt.transcribe(audio, self.sample_rate,
                                                        lang_hint=hint)
        except Exception as exc:
            await self._fail(correlation_id=correlation_id, speaker_id=speaker_id,
                             segment_id=segment_id, sequence_number=sequence_number,
                             reason="provider_unavailable",
                             error_code=type(exc).__name__, error=str(exc)[:160])
            return None
        self._provider_ms[correlation_id] = (time.perf_counter() - t0) * 1000

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
                if self.on_detect is not None:
                    await self.on_detect(correlation_id, detected)
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
            is_final=True, confidence=chunk.confidence,
            provider=chunk.provider or decision.provider,
            model=chunk.model or decision.model)
        await self.bus.publish(segment.to_event(Stage.TRANSCRIPT_FINAL))
        self._prune()
        return segment

    # ------------------------------------------------------------------ #
    async def note_injected_segment(self, *, correlation_id: str, speaker_id: str,
                                    segment_id: str, sequence_number: int,
                                    language: str, text: str, provider: str,
                                    model: str) -> None:
        """Publish the transcript stage event for a turn that arrived as text.

        `transcript.inject` stands in for this agent's provider call, so the
        stage event it would have emitted has to come from here: the supervisor
        reads the source language of its latency rollup, its ordering ledger and
        the listening stage's health off this one event.
        """
        segment = TranscriptSegment(
            correlation_id=correlation_id, meeting_id=self.meeting_id,
            speaker_id=speaker_id, segment_id=segment_id,
            sequence_number=sequence_number, source_language=language,
            recognized_text=text, is_final=True, confidence=1.0,
            provider=provider, model=model)
        await self.bus.publish(segment.to_event(Stage.TRANSCRIPT_FINAL))

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
