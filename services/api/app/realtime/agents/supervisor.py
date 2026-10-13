"""Agent 4 — supervisor: lifecycle state, ordering, timing, fallback policy.

This agent calls no providers and no LLM. It is deterministic bookkeeping over
the event bus: one record per in-flight utterance, so "did that chunk arrive, in
what order, how late, and should it still be played?" has an answer that does
not require reading five logs.

Cancellation is deliberately scoped. A barge-in from speaker A must not silence
speaker B, and one listener switching target language must not cancel a segment
other listeners are still entitled to hear. So interruptions cancel per
correlation, while a listener's language change marks only that
(recipient, language) pair stale.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage

log = logging.getLogger("app.realtime.agents.supervisor")

_REPORT_ORDER = [Stage.AUDIO_CAPTURED, Stage.TRANSCRIPT_PARTIAL, Stage.TRANSCRIPT_FINAL,
                 Stage.TRANSLATION_READY, Stage.TTS_CHUNK_READY, Stage.AUDIO_DELIVERED]

#: How many utterance chains one meeting keeps ordering state for.
DEFAULT_RECORD_LIMIT = 512


@dataclass
class _ChunkState:
    indexes: set[int] = field(default_factory=set)
    max_index: int = -1
    last_index: int | None = None
    duplicates: int = 0
    late: int = 0
    reordered: int = 0


@dataclass
class _SegmentRecord:
    correlation_id: str
    meeting_id: str = ""
    speaker_id: str | None = None
    source_language: str | None = None
    target_language: str | None = None
    stage_timestamps: dict[Stage, int] = field(default_factory=dict)
    first_of: dict[Stage, int] = field(default_factory=dict)
    stage_order: list[str] = field(default_factory=list)
    chunks: dict[str, _ChunkState] = field(default_factory=dict)
    chunks_delivered: int = 0
    failures: list[str] = field(default_factory=list)


class Supervisor:
    def __init__(self, clock: Callable[[], int] | None = None, *,
                 meeting_id: str = "", record_limit: int = DEFAULT_RECORD_LIMIT) -> None:
        self._clock = clock
        self._meeting_id = meeting_id
        self.record_limit = record_limit
        self._bus: AgentBus | None = None
        self._records: dict[str, _SegmentRecord] = {}
        self._active: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self._stale_recipients: set[tuple[str, str]] = set()
        self._closed = False
        self._metrics = {
            "duplicate_chunks": 0, "late_chunks": 0, "reordered_chunks": 0,
            "missing_chunks": 0, "cancelled_drops": 0, "stage_failures": 0,
            "interrupts": 0, "segments_completed": 0,
        }

    # ------------------------------------------------------------------ #
    def attach(self, bus: AgentBus) -> None:
        self._bus = bus
        bus.subscribe(self._observe)

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def _record(self, correlation_id: str) -> _SegmentRecord:
        rec = self._records.get(correlation_id)
        if rec is None:
            rec = _SegmentRecord(correlation_id=correlation_id)
            self._records[correlation_id] = rec
            # A meeting runs for hours; the observation window is for the recent
            # chain, not for every utterance since the room opened.
            while len(self._records) > self.record_limit:
                self._records.pop(next(iter(self._records)))
        return rec

    # ------------------------------------------------------------------ #
    def _observe(self, event: RealtimeEvent) -> None:
        """Inline bus handler — synchronous, allocation-light, never awaits."""
        rec = self._record(event.correlation_id)
        rec.speaker_id = event.speaker_id or rec.speaker_id
        rec.meeting_id = event.meeting_id or rec.meeting_id
        rec.stage_timestamps.setdefault(event.type, event.timestamp_ms)
        rec.first_of.setdefault(event.type, event.timestamp_ms)
        stage_name = event.type.name.lower()
        if stage_name not in rec.stage_order:
            rec.stage_order.append(stage_name)

        payload = event.payload
        if event.type in (Stage.TRANSCRIPT_PARTIAL, Stage.TRANSCRIPT_FINAL):
            rec.source_language = payload.get("source_language") or rec.source_language
        elif event.type is Stage.TRANSLATION_READY:
            rec.target_language = payload.get("target_language") or rec.target_language
        elif event.type is Stage.TTS_CHUNK_READY:
            self._observe_chunk(rec, event)
        elif event.type is Stage.AUDIO_DELIVERED:
            state = rec.chunks.get((event.segment_id or "",
                                    payload.get("target_language") or ""))
            if state:
                self._metrics["segments_completed"] += 1
                missing = (state.max_index + 1) - len(state.indexes)
                if missing > 0:
                    self._metrics["missing_chunks"] += missing
        elif event.type is Stage.STAGE_FAILED:
            self._metrics["stage_failures"] += 1
            rec.failures.append(str(payload.get("reason") or payload.get("error_code")))

    def _observe_chunk(self, rec: _SegmentRecord, event: RealtimeEvent) -> None:
        payload = event.payload
        index = payload.get("chunk_index")
        if index is None:
            return
        rec.target_language = payload.get("target_language") or rec.target_language
        # Chunk bookkeeping is per language run: one source segment streamed to
        # Hindi and to Tamil has the same indexes, and neither is a duplicate.
        state = rec.chunks.setdefault(
            (event.segment_id or "", payload.get("target_language") or ""),
            _ChunkState())
        if payload.get("duplicate"):
            self._metrics["duplicate_chunks"] += 1
            state.duplicates += 1
            return
        if index in state.indexes:
            self._metrics["duplicate_chunks"] += 1
            state.duplicates += 1
            return
        if index <= state.max_index:
            self._metrics["late_chunks"] += 1
            state.late += 1
        if state.last_index is not None and index != state.last_index + 1:
            self._metrics["reordered_chunks"] += 1
            state.reordered += 1
        state.indexes.add(index)
        state.max_index = max(state.max_index, index)
        state.last_index = index
        rec.chunks_delivered = len(state.indexes)

    # ------------------------------------------------------------------ #
    def segment_report(self, correlation_id: str) -> dict[str, Any]:
        rec = self._record(correlation_id)
        captured = rec.first_of.get(Stage.AUDIO_CAPTURED, 0)
        transcript = rec.first_of.get(Stage.TRANSCRIPT_FINAL, 0)
        translated = rec.first_of.get(Stage.TRANSLATION_READY, 0)
        first_audio = rec.first_of.get(Stage.TTS_CHUNK_READY, 0)
        delivered = rec.first_of.get(Stage.AUDIO_DELIVERED, 0)

        indexes: set[int] = set()
        max_index = -1
        for state in rec.chunks.values():
            indexes |= state.indexes
            max_index = max(max_index, state.max_index)
        expected = max_index + 1 if max_index >= 0 else len(indexes)

        def delta(a: int, b: int) -> int:
            return b - a if a and b else 0

        return {
            "correlation_id": correlation_id,
            "source_language": rec.source_language,
            "target_language": rec.target_language,
            "stages": list(rec.stage_order),
            "stt_ms": delta(captured, transcript),
            "translation_ms": delta(transcript, translated),
            "tts_first_audio_ms": delta(translated, first_audio),
            "delivery_ms": delta(translated, delivered),
            "speech_to_first_translated_audio_ms": delta(captured, first_audio),
            "speech_to_delivery_ms": delta(captured, delivered),
            "chunks_expected": expected,
            "chunks_delivered": len(indexes),
            "missing_chunks": max(0, expected - len(indexes)),
            "duplicates": sum(s.duplicates for s in rec.chunks.values()),
            "late": sum(s.late for s in rec.chunks.values()),
            "reordered": sum(s.reordered for s in rec.chunks.values()),
            "failures": list(rec.failures),
        }

    # ------------------------------------------------------------------ #
    def note_active_segment(self, speaker_id: str, *, correlation_id: str,
                            sequence_number: int,
                            target_languages: list[str]) -> None:
        self._active[correlation_id] = {
            "speaker_id": speaker_id, "sequence_number": sequence_number,
            "target_languages": list(target_languages)}

    def is_cancelled(self, correlation_id: str) -> bool:
        return correlation_id in self._cancelled

    def is_stale_for(self, recipient_id: str, target_language: str) -> bool:
        """A listener who switched language must not receive the old language."""
        return (recipient_id, target_language) in self._stale_recipients

    async def guard(self, correlation_id: str) -> bool:
        """False means: do not deliver this, it is stale. Never raises."""
        if correlation_id in self._cancelled:
            self._metrics["cancelled_drops"] += 1
            return False
        return True

    async def interrupt(self, speaker_id: str, *, reason: str) -> list[str]:
        """Barge-in: cancel this speaker's in-flight output, nobody else's."""
        cancelled = [(cid, meta) for cid, meta in self._active.items()
                     if meta["speaker_id"] == speaker_id]
        for cid, meta in cancelled:
            self._cancelled.add(cid)
            self._active.pop(cid, None)
            self._metrics["interrupts"] += 1
            await self._emit_interrupt(speaker_id, cid, reason,
                                       meta.get("target_languages", []))
        return [cid for cid, _ in cancelled]

    async def recipient_changed(self, recipient_id: str, *, previous_language: str,
                                new_language: str) -> None:
        """One listener changed target language — stale output is stale for them only."""
        self._stale_recipients.add((recipient_id, previous_language))
        if self._bus is not None:
            await self._bus.publish(RealtimeEvent(
                type=Stage.INTERRUPT, correlation_id="", meeting_id="",
                recipient_id=recipient_id,
                payload={"reason": "language_changed", "previous_language": previous_language,
                         "new_language": new_language, "scope": "recipient"}))

    def live_recipients(self, recipients: list[str], target_language: str) -> list[str]:
        return [r for r in recipients
                if (r, target_language) not in self._stale_recipients]

    async def _emit_interrupt(self, speaker_id: str, correlation_id: str, reason: str,
                              target_languages: list[str]) -> None:
        if self._bus is None:
            return
        meeting = self._record(correlation_id).meeting_id or self._meeting_id
        await self._bus.publish(RealtimeEvent(
            type=Stage.INTERRUPT, correlation_id=correlation_id,
            meeting_id=meeting, speaker_id=speaker_id,
            payload={"reason": reason, "correlation_id": correlation_id,
                     "scope": "speaker", "target_languages": list(target_languages)}))

    # ------------------------------------------------------------------ #
    def prune(self, correlation_id: str) -> None:
        """Release a finished utterance's bookkeeping."""
        self._records.pop(correlation_id, None)
        self._active.pop(correlation_id, None)
        self._cancelled.discard(correlation_id)

    def health(self) -> dict[str, Any]:
        return {"closed": self._closed, "active_segments": len(self._active),
                "cancelled_segments": len(self._cancelled),
                "tracked_correlations": len(self._records), **self._metrics}

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._bus is not None:
            await self._bus.publish(RealtimeEvent(
                type=Stage.SESSION_CLOSED, correlation_id="", meeting_id=self._meeting_id,
                payload={"active_segments": len(self._active)}))
        self._active.clear()
