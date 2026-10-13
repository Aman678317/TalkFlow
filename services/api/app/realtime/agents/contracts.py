"""Typed, versioned event contract shared by the four realtime agents.

This is the internal spine of the realtime path — it is *not* the client wire
protocol (`app.realtime.protocol`), which stays unchanged. Agents exchange these
models so a stage can be tested, measured and replayed without a browser, a
database, or a provider call.

Two rules are structural here, not advisory:

* Audio bytes never appear in an event. Chunk events carry `payload_bytes` and
  delivery metadata only; the bytes travel through the transport callback. That
  keeps 50 ms audio frames off the event bus, as the design guide requires.
* **Words never appear in an event either.** A stage event says how much was
  said, in which language, by which engine, and how long it took — never what
  was said. `observation()` is the only thing a stage may publish, precisely
  because a 4 096-event trace of a meeting is a second, unretained transcript
  the moment it stores sentences. Text travels on the client wire protocol and
  into the durable transcript row, which are governed elsewhere.
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


def failure_reason(exc: BaseException) -> str:
    """Why a stage stopped, from what the failure itself said.

    An outage and a refused language pair are different answers, and a room that
    reports them with one word cannot tell an operator whether to add capacity or
    to fix a capability row. `AppError` subclasses already name themselves, the
    meeting's own deadline is a `TimeoutError`, and only what is left gets the
    outage label — so the label is earned rather than assumed.

    Both producers of a failure — the internal ``stage.failed`` event and the
    client-facing ``translation.failed`` code — call this one function, which is
    the only reason the two can be trusted to agree.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    if isinstance(exc, TimeoutError):
        # `asyncio.wait_for`, `httpx` and the socket layer all raise a timeout
        # that is this type, so the meeting's own deadline and a provider that
        # never answers are the same honest answer.
        return "timeout"
    return "provider_unavailable"


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
    #: The speaker's turn number, carried so a stage event can be placed on the
    #: same timeline the captions use. Not the bus's own order — see `bus_sequence`.
    sequence: int = 0
    #: This event's position in the single stream of events this meeting's bus
    #: published, stamped by the bus and never by the producer. `sequence` restarts
    #: per speaker and `event_id` is random, so neither can answer "what happened
    #: between the translation event and this chunk, and in what order?" — an
    #: event log you cannot sort is not evidence.
    bus_sequence: int = 0
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
    # Provenance. The durable transcript row records which engine produced it,
    # so a later "why is this caption wrong" question has an answer.
    provider: str | None = None
    model: str | None = None

    def observation(self) -> dict[str, Any]:
        """Everything about this transcript that is not the words.

        `word_timestamps` is left out on purpose: they are the recognised words
        again, in a finer form than the sentence itself.
        """
        return {
            "version": self.version,
            "sequence_number": self.sequence_number,
            "transcript_revision": self.transcript_revision,
            "source_language": self.source_language,
            "is_final": self.is_final,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
            "text_chars": len(self.recognized_text or ""),
            "word_count": len((self.recognized_text or "").split()),
        }

    def to_event(self, stage: Stage) -> RealtimeEvent:
        return RealtimeEvent(
            type=stage, correlation_id=self.correlation_id, meeting_id=self.meeting_id,
            speaker_id=self.speaker_id, segment_id=self.segment_id,
            sequence=self.sequence_number, payload=self.observation(),
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
    #: The speaker's turn number this translation came from. Without it every
    #: stage after Agent 1 published `sequence=0`, so the two stages a listener
    #: actually waits on — translation and speech — had no place in the turn.
    source_sequence_number: int = 0
    source_start_time_ms: int = 0
    source_end_time_ms: int = 0
    # The canonical source travels with its translation so a listener can always
    # see (and a later stage can always re-translate from) the original words.
    source_text: str = ""
    alignment_metadata: dict[str, Any] | None = None
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    quality_flags: list[str] = Field(default_factory=list)

    def observation(self) -> dict[str, Any]:
        """Sizes and provenance for both sides of the transfer, never the text.

        `source_text` stays on the model — a later stage must be able to
        re-translate from the original words — it simply does not travel into
        the event spine.
        """
        return {
            "version": self.version,
            "sequence_number": self.source_sequence_number,
            "translation_revision": self.translation_revision,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "is_final": self.is_final,
            "source_start_time_ms": self.source_start_time_ms,
            "source_end_time_ms": self.source_end_time_ms,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 1),
            "quality_flags": list(self.quality_flags),
            "source_chars": len(self.source_text or ""),
            "translated_chars": len(self.translated_text or ""),
        }

    def to_event(self) -> RealtimeEvent:
        return RealtimeEvent(
            type=Stage.TRANSLATION_READY, correlation_id=self.correlation_id,
            meeting_id=self.meeting_id, speaker_id=self.speaker_id,
            recipient_id=self.recipient_id, segment_id=self.source_segment_id,
            sequence=self.source_sequence_number, payload=self.observation(),
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
    #: The speaker's turn number, so a chunk can be placed in the turn it belongs
    #: to rather than only in the segment it came from.
    sequence_number: int = 0
    codec: str = "wav"
    sample_rate: int = 24000
    channels: int = 1
    duration_ms: float = 0.0
    payload_bytes: int = 0
    recipient_ids: list[str] = Field(default_factory=list)
    # Which engine produced this audio and whether it is a synthetic stand-in.
    # The browser shows both, and the deployed wire events carry both, so the
    # declaration has to hold them or the transport cannot reproduce the frame.
    provider: str = ""
    model: str = ""
    is_dev: bool = False

    def to_event(self, *, duplicate: bool = False) -> RealtimeEvent:
        # No `observation()` here: every field of a chunk declaration is already
        # transport metadata — codec, rate, index, byte count — there is no
        # content on this model to leave out.
        payload = self.model_dump(exclude_defaults=False)
        if duplicate:
            payload["duplicate"] = True
        return RealtimeEvent(
            type=Stage.TTS_CHUNK_READY, correlation_id=self.correlation_id,
            meeting_id=self.meeting_id, speaker_id=self.speaker_id,
            segment_id=self.segment_id, sequence=self.sequence_number,
            payload=payload,
        )
