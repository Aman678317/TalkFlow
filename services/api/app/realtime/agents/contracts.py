"""Typed, versioned event contract shared by the four realtime agents.

This is the internal spine of the realtime path — it is *not* the client wire
protocol (`app.realtime.protocol`), which stays unchanged. Agents exchange these
models so a stage can be tested, measured and replayed without a browser, a
database, or a provider call.

Two rules are structural here, not advisory:

* Audio bytes never appear in an event. Chunk events carry `payload_bytes` and
  delivery metadata only; the bytes travel through the transport callback. That
  keeps 50 ms audio frames off the event bus, as the design guide requires.
* Every event carries a correlation id that survives the whole path, so
  capture -> transcript -> translation -> TTS -> delivery is one queryable
  chain rather than five unrelated logs.
"""
from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

AGENT_CONTRACT_VERSION = 1


class Stage(StrEnum):
    """Required lifecycle from the guide (§5)."""

    AUDIO_CAPTURED = "audio.captured"
    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"
    TRANSLATION_READY = "translation.ready"
    TTS_CHUNK_READY = "tts.chunk.ready"
    AUDIO_DELIVERED = "audio.delivered"
    PLAYBACK_STARTED = "playback.started"
    PLAYBACK_ENDED = "playback.ended"
    STAGE_FAILED = "stage.failed"
    INTERRUPT = "interrupt"
    SESSION_CLOSED = "session.closed"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return uuid.uuid4().hex


class RealtimeEvent(BaseModel):
    version: int = AGENT_CONTRACT_VERSION
    event_id: str = Field(default_factory=_new_id)
    type: Stage
    correlation_id: str
    meeting_id: str
    speaker_id: str | None = None
    recipient_id: str | None = None
    segment_id: str | None = None
    sequence: int = 0
    timestamp_ms: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def idempotency_key(self) -> str:
        """Stable key for "have we already acted on this exact event".

        Chunk events key on chunk index; everything else keys on stage, so a
        replayed transport frame is recognisable without suppressing a genuine
        later chunk of the same segment.
        """
        chunk = self.payload.get("chunk_index")
        tail = f"chunk:{chunk}" if chunk is not None else self.type.value
        return f"{self.correlation_id}:{self.segment_id or '-'}:{tail}"


class TranscriptSegment(BaseModel):
    """Agent 1 output (guide §4). One per stable segment, revisioned per partial."""

    version: int = AGENT_CONTRACT_VERSION
    event_id: str = Field(default_factory=_new_id)
    correlation_id: str
    meeting_id: str
    speaker_id: str
    segment_id: str
    sequence_number: int = 0
    transcript_revision: int = 1
    source_language: str
    recognized_text: str
    start_time_ms: int = 0
    end_time_ms: int = 0
    is_final: bool = False
    confidence: float | None = None
    word_timestamps: list[dict[str, Any]] | None = None

    def to_event(self, stage: Stage) -> RealtimeEvent:
        return RealtimeEvent(
            type=stage, correlation_id=self.correlation_id, meeting_id=self.meeting_id,
            speaker_id=self.speaker_id, segment_id=self.segment_id,
            sequence=self.sequence_number, payload=self.model_dump(exclude_defaults=False),
        )


class TranslationSegment(BaseModel):
    """Agent 2 output (guide §4): canonical source -> one recipient's language."""

    version: int = AGENT_CONTRACT_VERSION
    event_id: str = Field(default_factory=_new_id)
    correlation_id: str
    meeting_id: str
    speaker_id: str
    recipient_id: str
    source_segment_id: str
    source_language: str
    target_language: str
    translated_text: str
    translation_revision: int = 1
    is_final: bool = True
    source_start_time_ms: int = 0
    source_end_time_ms: int = 0
    # The canonical source travels with its translation so a listener can always
    # see (and a later stage can always re-translate from) the original words.
    source_text: str = ""
    alignment_metadata: dict[str, Any] | None = None

    def to_event(self) -> RealtimeEvent:
        return RealtimeEvent(
            type=Stage.TRANSLATION_READY, correlation_id=self.correlation_id,
            meeting_id=self.meeting_id, speaker_id=self.speaker_id,
            recipient_id=self.recipient_id, segment_id=self.source_segment_id,
            payload=self.model_dump(exclude_defaults=False),
        )


class TtsChunkReady(BaseModel):
    """Agent 3 declaration (guide §5): everything the browser needs *before* it
    plays a chunk. Deliberately carries no audio."""

    version: int = AGENT_CONTRACT_VERSION
    event_id: str = Field(default_factory=_new_id)
    correlation_id: str
    meeting_id: str
    speaker_id: str
    segment_id: str
    target_language: str
    chunk_index: int
    codec: str = "wav"
    sample_rate: int = 24000
    channels: int = 1
    duration_ms: float = 0.0
    payload_bytes: int = 0
    recipient_ids: list[str] = Field(default_factory=list)

    def to_event(self, *, duplicate: bool = False) -> RealtimeEvent:
        payload = self.model_dump(exclude_defaults=False)
        if duplicate:
            payload["duplicate"] = True
        return RealtimeEvent(
            type=Stage.TTS_CHUNK_READY, correlation_id=self.correlation_id,
            meeting_id=self.meeting_id, speaker_id=self.speaker_id,
            segment_id=self.segment_id, payload=payload,
        )
