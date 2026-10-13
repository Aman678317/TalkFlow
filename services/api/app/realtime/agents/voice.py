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
                 channels: int = 1) -> None:
        self.bus = bus
        self.tts = tts
        self.meeting_id = meeting_id
        self.channels = channels
        self._seen: set[tuple[str, str, int]] = set()
        self._deliveries: dict[tuple[str, str], _SegmentDelivery] = {}

    # ------------------------------------------------------------------ #
    async def synthesize(self, translation: TranslationSegment, *,
                         recipients: list[str],
                         deliver: DeliveryCallback) -> int:
        """Stream one translated segment to speech. Returns the chunk count."""
        if translation.target_language == translation.source_language:
            return 0
        try:
            stream, _decision = await self.tts.synthesize_stream(
                translation.translated_text, translation.target_language)
        except Exception as exc:
            await self._fail(translation, exc)
            return 0

        index = 0
        try:
            async for chunk in stream:
                await self.publish_chunk(
                    translation, index=index, audio=chunk.data,
                    duration_ms=chunk.duration_ms, sample_rate=chunk.sample_rate,
                    codec=chunk.format, recipients=recipients, deliver=deliver)
                index += 1
        except Exception as exc:
            log.warning("TTS stream aborted for %s: %s",
                        translation.correlation_id, exc)
            await self._fail(translation, exc)

        await self.finish_delivery(translation, recipients=recipients)
        return index

    async def publish_chunk(self, translation: TranslationSegment, *, index: int,
                            audio: bytes, duration_ms: float, recipients: list[str],
                            sample_rate: int = 24000, codec: str = "wav",
                            deliver: DeliveryCallback) -> bool:
        """Declare one chunk, then deliver it — unless we already delivered it."""
        key = (translation.correlation_id, translation.source_segment_id, index)
        duplicate = key in self._seen
        ready = TtsChunkReady(
            correlation_id=translation.correlation_id, meeting_id=self.meeting_id,
            speaker_id=translation.speaker_id, segment_id=translation.source_segment_id,
            target_language=translation.target_language, chunk_index=index,
            codec=codec, sample_rate=sample_rate, channels=self.channels,
            duration_ms=duration_ms, payload_bytes=len(audio),
            recipient_ids=list(recipients))
        await self.bus.publish(ready.to_event(duplicate=duplicate))
        if duplicate:
            # Observed, but never handed to the transport twice.
            return False

        self._seen.add(key)
        state = self._deliveries.setdefault(
            (translation.correlation_id, translation.source_segment_id),
            _SegmentDelivery())
        state.indexes.append(index)
        state.total_bytes += len(audio)
        try:
            await deliver(ready, audio, list(recipients))
        except Exception as exc:
            log.warning("chunk %s delivery failed for %s: %s", index,
                        translation.correlation_id, exc)
            await self.bus.publish(RealtimeEvent(
                type=Stage.STAGE_FAILED, correlation_id=translation.correlation_id,
                meeting_id=self.meeting_id, speaker_id=translation.speaker_id,
                segment_id=translation.source_segment_id,
                payload={"stage": "delivery", "reason": "transport_failed",
                         "recoverable": True, "chunk_index": index,
                         "target_language": translation.target_language,
                         "error_code": type(exc).__name__, "original_audio_available": True}))
            return False
        return True

    async def finish_delivery(self, translation: TranslationSegment, *,
                              recipients: list[str]) -> None:
        state = self._deliveries.get(
            (translation.correlation_id, translation.source_segment_id))
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

    async def _fail(self, translation: TranslationSegment, exc: Exception) -> None:
        await self.bus.publish(RealtimeEvent(
            type=Stage.STAGE_FAILED, correlation_id=translation.correlation_id,
            meeting_id=self.meeting_id, speaker_id=translation.speaker_id,
            segment_id=translation.source_segment_id,
            payload={"stage": "tts", "reason": "provider_unavailable",
                     "target_language": translation.target_language,
                     "error_code": type(exc).__name__, "error": str(exc)[:160],
                     "recoverable": True,
                     # The guide's hard rule: speech synthesis failing must never
                     # take the original conversation down with it.
                     "original_audio_available": True}))

    # ------------------------------------------------------------------ #
    def forget_segment(self, correlation_id: str, segment_id: str) -> None:
        """Interrupted or cancelled: drop dedup state so a fresh attempt is clean."""
        for key in [k for k in self._seen
                    if k[0] == correlation_id and k[1] == segment_id]:
            self._seen.discard(key)
        self._deliveries.pop((correlation_id, segment_id), None)
