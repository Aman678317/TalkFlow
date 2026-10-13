"""Agent 4 — supervisor: lifecycle state, ordering, timing, fallback policy.

This agent calls no providers and no LLM. It is deterministic bookkeeping over
the event bus: one record per in-flight utterance, so "did that chunk arrive, in
what order, how late, and should it still be played?" has an answer that does
not require reading five logs. The same observation answers a second question —
"has each stage actually produced anything yet?" — which is what a health
indicator has to be built from, since anything else is a claim.

Cancellation is deliberately scoped. A barge-in from speaker A must not silence
speaker B, and one listener switching target language must not cancel a segment
other listeners are still entitled to hear. So interruptions cancel per
correlation, while a listener's language change marks only that
(recipient, language) pair stale.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage

log = logging.getLogger("app.realtime.agents.supervisor")


def _wall_ms() -> int:
    return int(time.time() * 1000)

_REPORT_ORDER = [Stage.AUDIO_CAPTURED, Stage.TRANSCRIPT_PARTIAL, Stage.TRANSCRIPT_FINAL,
                 Stage.TRANSLATION_READY, Stage.TTS_CHUNK_READY, Stage.AUDIO_DELIVERED]

#: How many utterance chains one meeting keeps ordering state for.
DEFAULT_RECORD_LIMIT = 512

#: The four stages a listener depends on, in pipeline order. Health is reported
#: per stage because "the pipeline is up" is not a claim anybody can act on.
STAGE_CHAIN: tuple[str, ...] = ("listening", "translation", "voice", "delivery")

#: Which lifecycle event hands work to which stage, and which stage's promise it
#: settles. A stage's producer cannot report that it has stalled — a stalled
#: producer reports nothing — so outstanding work is tracked here, from the
#: upstream event, and released only by the stage's own output.
#: `None` as the language field means "the turn itself, before a target exists".
_REQUEST: dict[Stage, tuple[str, str | None]] = {
    Stage.AUDIO_CAPTURED: ("listening", None),
    Stage.TRANSLATION_READY: ("voice", "target_language"),
    Stage.TTS_CHUNK_READY: ("delivery", "target_language"),
}

_ARRIVAL: dict[Stage, tuple[str, str | None]] = {
    Stage.TRANSCRIPT_FINAL: ("listening", None),
    Stage.TRANSLATION_READY: ("translation", "target_language"),
    Stage.TTS_CHUNK_READY: ("voice", "target_language"),
    Stage.AUDIO_DELIVERED: ("delivery", "target_language"),
}

#: A stage names itself the way its provider does, not the way the chain does.
#: Without this, Agent 1's "stt" failure would land in a bucket nobody reads.
_FAILURE_STAGE: dict[str, str] = {
    "stt": "listening", "listening": "listening",
    "translation": "translation",
    "tts": "voice", "voice": "voice",
    "delivery": "delivery",
}

#: Which payload field names the language a failure settles a promise for.
_FAILURE_LANG: dict[str, str | None] = {
    "listening": None, "translation": "target_language",
    "voice": "target_language", "delivery": "target_language",
}

#: How many speech-end -> first-audio measurements one meeting keeps per language
#: pair for the percentile report. A rolling window, not the whole meeting: a
#: p95 computed over eight hours of audio describes a deployment that no longer
#: exists, and an unbounded list is a memory leak with a report attached.
LATENCY_WINDOW = 200


def _percentile(sorted_vals: list[int], q: float) -> int:
    """Nearest-rank percentile. `sorted_vals` must be non-empty and sorted."""
    rank = max(0, min(len(sorted_vals) - 1,
                      int(-(-q * len(sorted_vals) // 1)) - 1))
    return sorted_vals[rank]


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
    #: Wall ms at which the speaker stopped producing audio for this turn, when
    #: the pipeline could say so. Every "how long did the listener wait" number
    #: hangs off this instant; the stage durations below hang off event arrivals,
    #: which start the clock at the first audio frame and so flatter the pause a
    #: listener actually experiences.
    speech_end_wall_ms: int = 0


class Supervisor:
    #: The only statuses this class emits. Kept as a named set because a health
    #: reader has to be able to tell "broken" from "nothing to do", and an
    #: open-ended vocabulary turns that into guesswork.
    STATUSES = frozenset({"not_yet_ran", "waiting", "ok", "degraded", "failing"})

    def __init__(self, clock: Callable[[], int] | None = None, *,
                 meeting_id: str = "", record_limit: int = DEFAULT_RECORD_LIMIT,
                 latency_window: int = LATENCY_WINDOW) -> None:
        self._clock = clock
        self._meeting_id = meeting_id
        self.record_limit = record_limit
        self.latency_window = latency_window
        self._bus: AgentBus | None = None
        self._records: dict[str, _SegmentRecord] = {}
        self._active: dict[str, dict[str, Any]] = {}
        # Insertion-ordered rather than a set: an id lands here when a run is
        # cancelled and only leaves when that turn is pruned, which a barge-in
        # does by hand. Bound it like every other per-turn table in here.
        self._cancelled: dict[str, None] = {}
        self._stale_recipients: set[tuple[str, str]] = set()
        self._closed = False
        self._metrics = {
            "duplicate_chunks": 0, "late_chunks": 0, "reordered_chunks": 0,
            "missing_chunks": 0, "cancelled_drops": 0, "stage_failures": 0,
            "interrupts": 0, "segments_completed": 0,
        }
        self._stage_counts = {key: {"events": 0, "expected": 0}
                              for key in STAGE_CHAIN}
        #: Outstanding work per stage: {(correlation, language): first_seen_ms}.
        self._pending: dict[str, dict[tuple[str, str], int]] = {
            key: {} for key in STAGE_CHAIN}
        self._stage_failures: dict[str, int] = dict.fromkeys(STAGE_CHAIN, 0)
        self._stage_event_ms: dict[str, int] = dict.fromkeys(STAGE_CHAIN, 0)
        self._stage_failure_ms: dict[str, int] = dict.fromkeys(STAGE_CHAIN, 0)
        #: speech-end -> first translated audio, ms, per "src->tgt" pair.
        self._latency: dict[str, deque[int]] = {}

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
        self._observe_stage(event)

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
        if len(state.indexes) == 1:
            self._note_first_audio(rec, event)

    def _note_first_audio(self, rec: _SegmentRecord, event: RealtimeEvent) -> None:
        """Record one sample of the wait a listener actually experienced.

        Measured from the pipeline's speech-end anchor rather than from the
        first audio frame of the turn, because the two differ by how long the
        speaker talked: the frame clock answers "how fast is our pipeline", the
        anchor answers "how long after I stopped talking did they hear me".
        """
        if not rec.speech_end_wall_ms:
            return
        sample = event.timestamp_ms - rec.speech_end_wall_ms
        if sample < 0:
            # The chunk is older than the moment the speaker stopped. A clock jump
            # or a turn the pipeline never declared ended — either way it is not a
            # wait anybody experienced, and averaging it would pull the p50 down.
            return
        pair = f"{rec.source_language or 'unknown'}->{rec.target_language or 'unknown'}"
        window = self._latency.get(pair)
        if window is None:
            window = self._latency[pair] = deque(maxlen=self.latency_window)
        window.append(sample)

    def latency_summary(self) -> dict[str, Any]:
        """p50/p95 of speech-end -> first translated audio, per language pair.

        A pair with no samples is absent rather than zero: "0 ms" would read as a
        meeting that was fast, when the truth is that nothing was measured.
        """
        out: dict[str, Any] = {"window": self.latency_window, "pairs": {}}
        everything: list[int] = []
        for pair, window in self._latency.items():
            values = sorted(window)
            if not values:
                continue
            everything += values
            out["pairs"][pair] = {"n": len(values),
                                  "p50_ms": _percentile(values, 0.50),
                                  "p95_ms": _percentile(values, 0.95),
                                  "max_ms": values[-1]}
        if everything:
            everything.sort()
            out["overall"] = {"n": len(everything),
                              "p50_ms": _percentile(everything, 0.50),
                              "p95_ms": _percentile(everything, 0.95),
                              "max_ms": everything[-1]}
        return out

    def _observe_stage(self, event: RealtimeEvent) -> None:
        """Per-stage ledger: what was handed over, and what came back."""
        if event.type is Stage.STAGE_FAILED:
            key = _FAILURE_STAGE.get(str(event.payload.get("stage") or ""))
            if key is not None:
                self._stage_failures[key] += 1
                self._stage_failure_ms[key] = event.timestamp_ms
                # The stage answered, even if the answer was no. Leaving it in the
                # ledger would report an error as a stall.
                self._pending[key].pop(self._pending_key(event, _FAILURE_LANG.get(key,
                                                                                   None)), None)
            return
        if event.payload.get("duplicate"):
            return
        request = _REQUEST.get(event.type)
        if request is not None:
            self._note_expected(*request, event=event)
        arrival = _ARRIVAL.get(event.type)
        if arrival is not None:
            self._note_arrived(*arrival, event=event)

    @staticmethod
    def _pending_key(event: RealtimeEvent, lang_field: str | None) -> tuple[str, str]:
        """One unit of outstanding work: a turn in a target language.

        Language-parted because a turn translated into Hindi and into Tamil is
        two promises, and keeping the third one silent while the first two are
        delivered is exactly the failure a health report has to show.
        """
        lang = "" if lang_field is None else str(event.payload.get(lang_field) or "")
        return (event.correlation_id, lang)

    def _note_expected(self, key: str, lang_field: str | None, *,
                       event: RealtimeEvent, when_ms: int | None = None) -> None:
        """Work entered a stage; remember it until the stage answers."""
        self._stage_counts[key]["expected"] += 1
        self._pending[key].setdefault(
            self._pending_key(event, lang_field),
            event.timestamp_ms if when_ms is None else when_ms)

    def _note_arrived(self, key: str, lang_field: str | None, *,
                      event: RealtimeEvent) -> None:
        self._stage_counts[key]["events"] += 1
        self._stage_event_ms[key] = event.timestamp_ms
        self._pending[key].pop(self._pending_key(event, lang_field), None)

    def _drop_pending(self, correlation_id: str) -> None:
        """Stop owing a turn: cancellation releases every stage's claim on it."""
        for ledger in self._pending.values():
            for unit in [k for k in ledger if k[0] == correlation_id]:
                del ledger[unit]

    def stage_status(self) -> dict[str, dict[str, Any]]:
        """What each stage has actually proved it did, from observed events only.

        Deliberately room-blind: this answers "did the code run, and is anything
        still owed to it", not "should anything have been produced here" — whether
        anybody in the meeting asked for translated audio is routing, and the
        session owner holds that. `waiting` is the honest answer to "work arrived
        and nothing has come back", which is what a stalled provider looks like
        from in here; a hardcoded "active" reported that state as healthy.
        """
        out: dict[str, dict[str, Any]] = {}
        now = self._clock() if self._clock is not None else _wall_ms()
        for key in STAGE_CHAIN:
            counts = self._stage_counts[key]
            events, expected = counts["events"], counts["expected"]
            failures = self._stage_failures[key]
            ledger = self._pending[key]
            # The oldest promise this stage has not answered.
            owed_since = min(ledger.values(), default=0)
            if events and failures:
                status = "degraded"
            elif events:
                status = "ok"
            elif failures:
                status = "failing"
            elif ledger:
                status = "waiting"
            else:
                status = "not_yet_ran"
            out[key] = {"status": status, "events": events, "expected": expected,
                        "pending": len(ledger), "failures": failures,
                        "last_event_ms": self._stage_event_ms[key],
                        "last_failure_ms": self._stage_failure_ms[key],
                        # "waiting" alone cannot tell a provider that stalled an
                        # hour ago from a stage the pipeline reached 40 ms ago,
                        # and neither can a reader. This can.
                        "pending_ms": max(0, now - owed_since) if ledger else 0}
        return out

    # ------------------------------------------------------------------ #
    def segment_report(self, correlation_id: str) -> dict[str, Any]:
        rec = self._record(correlation_id)
        captured = rec.first_of.get(Stage.AUDIO_CAPTURED, 0)
        transcript = rec.first_of.get(Stage.TRANSCRIPT_FINAL, 0)
        translated = rec.first_of.get(Stage.TRANSLATION_READY, 0)
        first_audio = rec.first_of.get(Stage.TTS_CHUNK_READY, 0)
        delivered = rec.first_of.get(Stage.AUDIO_DELIVERED, 0)
        speech_end = rec.speech_end_wall_ms

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
            "speech_end_wall_ms": rec.speech_end_wall_ms,
            "stages": list(rec.stage_order),
            "stt_ms": delta(captured, transcript),
            "translation_ms": delta(transcript, translated),
            "tts_first_audio_ms": delta(translated, first_audio),
            "delivery_ms": delta(translated, delivered),
            "speech_to_first_translated_audio_ms": delta(captured, first_audio),
            "speech_to_delivery_ms": delta(captured, delivered),
            # What the listener waited after they stopped hearing the speaker.
            # 0 when the pipeline had no anchor for this turn.
            "speech_end_to_first_audio_ms": delta(speech_end, first_audio),
            "speech_end_to_delivery_ms": delta(speech_end, delivered),
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
                            target_languages: list[str],
                            speech_end_wall_ms: int = 0) -> None:
        self._active[correlation_id] = {
            "speaker_id": speaker_id, "sequence_number": sequence_number,
            "target_languages": list(target_languages)}
        if speech_end_wall_ms:
            self._record(correlation_id).speech_end_wall_ms = speech_end_wall_ms
        # Recorded here rather than derived from `_active`, which a barge-in
        # releases: the pipeline has now promised one provider call per language,
        # and translation is the only stage that can be owed work without an
        # upstream event naming it.
        now = self._clock() if self._clock is not None else _wall_ms()
        for lang in {language for language in target_languages if language}:
            self._stage_counts["translation"]["expected"] += 1
            self._pending["translation"].setdefault((correlation_id, lang), now)

    def is_cancelled(self, correlation_id: str) -> bool:
        return correlation_id in self._cancelled

    def _mark_cancelled(self, correlation_id: str) -> None:
        """Remember that this turn's output is stale, for as long as it takes the
        cancelled runs to report home — and no longer than the observation window
        of any other per-turn table."""
        self._cancelled[correlation_id] = None
        while len(self._cancelled) > self.record_limit:
            self._cancelled.pop(next(iter(self._cancelled)))

    def active_languages(self, speaker_id: str) -> list[str]:
        """Target languages still in flight for one speaker.

        Asked *before* an interruption, because the answer is what the browser
        has to drop — after ``interrupt`` the bookkeeping is gone.
        """
        return sorted({lang
                       for cid, meta in self._active.items()
                       if meta["speaker_id"] == speaker_id
                       for lang in meta.get("target_languages", [])})

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
            self._mark_cancelled(cid)
            self._active.pop(cid, None)
            self._drop_pending(cid)
            self._metrics["interrupts"] += 1
            await self._emit_interrupt(speaker_id, cid, reason,
                                       meta.get("target_languages", []))
        return [cid for cid, _ in cancelled]

    def forget_participant(self, participant_id: str) -> list[str]:
        """A participant left: release everything this meeting holds for them.

        The synchronous twin of ``interrupt``, for a path that cannot await —
        the WebSocket handler runs it inside a ``finally`` of a task being
        cancelled. So it publishes nothing (the room learns who went away from
        ``participant.left``) and simply stops owing their turn: the output is
        marked stale, their language-switch marks go with them, and whatever was
        still in flight is the caller's to cancel.

        Returns the correlations it abandoned.
        """
        abandoned = [cid for cid, meta in self._active.items()
                     if meta["speaker_id"] == participant_id]
        for cid in abandoned:
            self._mark_cancelled(cid)
            self._active.pop(cid, None)
            self._drop_pending(cid)
        for key in [k for k in self._stale_recipients
                    if k[0] == participant_id]:
            self._stale_recipients.discard(key)
        return abandoned

    async def recipient_changed(self, recipient_id: str, *, previous_language: str,
                                new_language: str) -> None:
        """One listener changed target language — stale output is stale for them only."""
        # Un-stale the language they just switched *to*. Without this, en→hi→en
        # leaves (recipient, "en") stale forever and they never hear English
        # again, because the first switch marked it and nothing ever cleared it.
        self._stale_recipients.discard((recipient_id, new_language))
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
        self._cancelled.pop(correlation_id, None)
        self._drop_pending(correlation_id)

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
