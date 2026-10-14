"""Agent 3 — voice: target-language speech, chunk declaration, delivery.

Owns generating audio for a translated segment and handing each chunk to the
transport *with* everything the receiving browser needs to play it in order:
codec, sample rate, channel count, chunk index, segment id, duration and the
recipients it is meant for.

Raw audio never enters the event bus. Chunks travel to the transport through the
`deliver` callback the session owns; the bus only sees byte counts and metadata.
That is what keeps 20-40 ms audio frames off the control plane, and it is why a
slow consumer cannot backpressure synthesis.

Duplicate chunks are suppressed here, at the point of delivery, and still
published as observable events — so the transport plays a chunk once while the
supervisor can still count and report the duplication.
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import (
    RealtimeEvent,
    Stage,
    TranslationSegment,
    TtsChunkReady,
)
from gt_ai.types import AudioChunk, RouteDecision

log = logging.getLogger("app.realtime.agents.voice")

#: How many delivered chunk keys one meeting remembers for replay detection.
DEFAULT_SEEN_LIMIT = 4096

# Delivery hand-off: (declared chunk, raw audio, intended recipients) -> transport.
DeliveryCallback = Callable[[TtsChunkReady, bytes, list[str]], Awaitable[None]]


class TtsStreamProvider(Protocol):
    """The slice of ``app.ai.AIFacade`` that Agent 3 needs."""

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None,
                                ) -> tuple[AsyncIterator[AudioChunk], RouteDecision]: ...


class RealtimeTtsProvider:
    """Production adapter: delegates to the configured AI facade."""

    def __init__(self, facade) -> None:
        self._facade = facade

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        return await self._facade.synthesize_stream(text, lang, voice)


@dataclass
class _SegmentDelivery:
    indexes: list[int] = field(default_factory=list)
    total_bytes: int = 0


class VoiceAgent:
    def __init__(self, bus: AgentBus, tts: TtsStreamProvider, *, meeting_id: str,
                 channels: int = 1, seen_limit: int = DEFAULT_SEEN_LIMIT,
                 voice_for: Callable[[str], str | None] | None = None) -> None:
        self.bus = bus
        self.tts = tts
        self.meeting_id = meeting_id
        self.channels = channels
        self.seen_limit = seen_limit
        #: target language -> voice name. None means "ask the provider for its
        #: default", which is what the pipeline did until a voice per language
        #: could be chosen at all.
        self.voice_for = voice_for
        # Insertion-ordered set: one long meeting must not accumulate a chunk key
        # per 40 ms frame forever, and the recent window is what a replay needs.
        self._seen: dict[tuple[str, str, str, int], None] = {}
        self._deliveries: dict[tuple[str, str, str], _SegmentDelivery] = {}
        self._failures: dict[tuple[str, str, str], dict] = {}

    # ------------------------------------------------------------------ #
    async def synthesize(self, translation: TranslationSegment, *,
                         recipients: list[str],
                         deliver: DeliveryCallback,
                         should_continue: Callable[[], bool] | None = None,
                         on_provider: Callable[[RouteDecision], Awaitable[None]] | None = None,
                         on_first_audio: Callable[[TtsChunkReady, float],
                                                   Awaitable[None]] | None = None,
                         ) -> int:
        """Stream one translated segment to speech. Returns the chunk count.

        ``should_continue`` is the session owner's staleness question — the
        speaker may have started a new utterance mid-stream, and audio for the
        old one must stop arriving rather than talk over the current speech.
        """
        if translation.target_language == translation.source_language:
            return 0
        voice = self.voice_for(translation.target_language) if self.voice_for else None
        try:
            stream, decision = await self.tts.synthesize_stream(
                translation.translated_text, translation.target_language, voice)
        except Exception as exc:
            await self._fail(translation, exc)
            return 0
        if on_provider is not None:
            await on_provider(decision)

        t0 = time.perf_counter()
        index = 0
        try:
            async for chunk in stream:
                if should_continue is not None and not should_continue():
                    break
                if index == 0 and on_first_audio is not None:
                    await on_first_audio(
                        TtsChunkReady(
                            correlation_id=translation.correlation_id,
                            meeting_id=self.meeting_id, speaker_id=translation.speaker_id,
                            segment_id=translation.source_segment_id,
                            target_language=translation.target_language, chunk_index=0,
                            sequence_number=translation.source_sequence_number,
                            codec=chunk.format, sample_rate=chunk.sample_rate,
                            channels=self.channels, duration_ms=chunk.duration_ms,
                            payload_bytes=len(chunk.data), recipient_ids=list(recipients),
                            provider=decision.provider, model=chunk.model,
                            is_dev=chunk.is_dev),
                        (time.perf_counter() - t0) * 1000)
                await self.publish_chunk(
                    translation, index=index, audio=chunk.data,
                    duration_ms=chunk.duration_ms, sample_rate=chunk.sample_rate,
                    codec=chunk.format, recipients=recipients, deliver=deliver,
                    provider=decision.provider, model=chunk.model, is_dev=chunk.is_dev)
                index += 1
        except Exception as exc:
            log.warning("TTS stream aborted for %s: %s",
                        translation.correlation_id, exc)
            await self._fail(translation, exc)

        await self.finish_delivery(translation, recipients=recipients)
        return index

    # ------------------------------------------------------------------ #
    @staticmethod
    def _delivery_key(translation: TranslationSegment) -> tuple[str, str, str]:
        """One language's run of one segment. Two target languages of the same
        source segment are separate deliveries."""
        return (translation.correlation_id, translation.source_segment_id,
                translation.target_language)

    async def publish_chunk(self, translation: TranslationSegment, *, index: int,
                            audio: bytes, duration_ms: float, recipients: list[str],
                            sample_rate: int = 24000, codec: str = "wav",
                            deliver: DeliveryCallback, provider: str = "",
                            model: str = "", is_dev: bool = False) -> bool:
        """Declare one chunk, then deliver it — unless we already delivered it.

        The key includes the target language: one source segment fans out to
        several languages at once, and chunk 0 of each is a different chunk.
        """
        key = (translation.correlation_id, translation.source_segment_id,
               translation.target_language, index)
        duplicate = key in self._seen
        ready = TtsChunkReady(
            correlation_id=translation.correlation_id, meeting_id=self.meeting_id,
            speaker_id=translation.speaker_id, segment_id=translation.source_segment_id,
            target_language=translation.target_language, chunk_index=index,
            sequence_number=translation.source_sequence_number,
            codec=codec, sample_rate=sample_rate, channels=self.channels,
            duration_ms=duration_ms, payload_bytes=len(audio),
            recipient_ids=list(recipients), provider=provider, model=model,
            is_dev=is_dev)
        await self.bus.publish(ready.to_event(duplicate=duplicate))
        if duplicate:
            # Observed, but never handed to the transport twice.
            return False

        self._seen[key] = None
        while len(self._seen) > self.seen_limit:
            self._seen.pop(next(iter(self._seen)))
        state = self._deliveries.setdefault(
            self._delivery_key(translation), _SegmentDelivery())
        state.indexes.append(index)
        state.total_bytes += len(audio)
        try:
            await deliver(ready, audio, list(recipients))
        except Exception as exc:
            log.warning("chunk %s delivery failed for %s: %s", index,
                        translation.correlation_id, exc)
            await self._fail(translation, exc, stage="delivery",
                             reason="transport_failed", chunk_index=index)
            return False
        return True

    async def finish_delivery(self, translation: TranslationSegment, *,
                              recipients: list[str]) -> None:
        state = self._deliveries.get(self._delivery_key(translation))
        indexes = list(state.indexes) if state else []
        total = state.total_bytes if state else 0
        await self.bus.publish(RealtimeEvent(
            type=Stage.AUDIO_DELIVERED, correlation_id=translation.correlation_id,
            meeting_id=self.meeting_id, speaker_id=translation.speaker_id,
            segment_id=translation.source_segment_id,
            payload={"chunks_delivered": len(indexes), "total_bytes": total,
                     "chunk_indexes": indexes, "target_language": translation.target_language,
                     "recipient_ids": list(recipients),
                     "duration_ms": 0.0}))
        # Closed: the running totals were for this declaration only.
        self._deliveries.pop(self._delivery_key(translation), None)

    async def _fail(self, translation: TranslationSegment, exc: Exception,
                    *, stage: str = "tts", reason: str = "provider_unavailable",
                    **extra) -> None:
        payload = {"stage": stage, "reason": reason,
                   "target_language": translation.target_language,
                   "error_code": type(exc).__name__, "error": str(exc)[:160],
                   "recoverable": True,
                   # The guide's hard rule: speech synthesis failing must never
                   # take the original conversation down with it.
                   "original_audio_available": True}
        payload.update(extra)
        self._failures[self._delivery_key(translation)] = payload
        await self.bus.publish(RealtimeEvent(
            type=Stage.STAGE_FAILED, correlation_id=translation.correlation_id,
            meeting_id=self.meeting_id, speaker_id=translation.speaker_id,
            segment_id=translation.source_segment_id,
            sequence=translation.source_sequence_number,
            # The message stays in the record above, which the session owner
            # reads and logs. `take_failure` hands it out; the trace does not.
            payload={k: v for k, v in payload.items() if k != "error"}))

    def take_failure(self, translation: TranslationSegment) -> dict | None:
        """Pop the failure this stage recorded for one language run, so the
        session owner can put the right recoverable error on the wire. Silence
        is not an option here: a listener must be told translated speech
        stopped working."""
        return self._failures.pop(self._delivery_key(translation), None)

    # ------------------------------------------------------------------ #
    def forget_segment(self, correlation_id: str, segment_id: str) -> None:
        """Interrupted or cancelled: drop that run's dedup and failure state, in
        every target language, so a retry is not judged a duplicate of audio
        that never finished playing."""
        for key in [k for k in self._seen
                    if k[0] == correlation_id and k[1] == segment_id]:
            self._seen.pop(key, None)
        for table in (self._deliveries, self._failures):
            for key in [k for k in table
                        if k[0] == correlation_id and k[1] == segment_id]:
                table.pop(key, None)

    def forget_correlation(self, correlation_id: str) -> None:
        """Barge-in: drop every language run of one utterance.

        ``forget_segment`` needs the durable segment id, but an interruption can
        land before the transcript row exists, and a cancelled task never runs
        ``finish_delivery``, so that run's totals would otherwise be kept for
        the life of the meeting — and a retried chunk 0 would be judged a
        duplicate of audio that never finished playing.
        """
        for key in [k for k in self._seen if k[0] == correlation_id]:
            self._seen.pop(key, None)
        for table in (self._deliveries, self._failures):
            for key in [k for k in table if k[0] == correlation_id]:
                table.pop(key, None)
