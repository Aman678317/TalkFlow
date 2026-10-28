"""Realtime conversation pipeline (PDD §9-§13).

Human microphone -> audio chunks -> VAD -> streaming STT -> language detect
-> CANONICAL source segment (immutable)
   -> Translation fan-out (ONCE per distinct target language)
      -> TTS (ONCE per target language group)
         -> Listener router (per-participant delivery by hear_lang + mode)

Latency budget target: ~1.5-2.5s for a completed short utterance (measured,
not guaranteed). Every stage records its timing into LatencyTrace.

Failure rule: AI failure NEVER breaks the meeting. Original audio path is
untouched; on translation failure we emit translation.failed +
quality.degraded and keep the conversation running.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select, update

from app import metrics as met
from app.ai import ai
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import db_session
from app.errors import AppError, QuotaExceededError
from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import TtsChunkReady, TranscriptSegment
from app.realtime.agents.listening import (
    MIN_AUDIO_BYTES, ListeningAgent, RealtimeSttProvider,
)
from app.realtime.agents.supervisor import Supervisor
from app.realtime.agents.translation import RealtimeTranslatorProvider, TranslationAgent
from app.realtime.agents.voice import RealtimeTtsProvider, VoiceAgent
from app.realtime.protocol import LatencyTrace, ServerEventType
from app.realtime.session_manager import RtParticipant, RtSession, manager
from app.services import usage_service
from app.realtime.voices import voice_for
from app.services.translation_service import (
    TranslateContext, translate_text, validate_pair,
)
from gt_ai.types import RouteDecision
from gt_ai.vad import EnergyVAD, VadState, create_vad

log = logging.getLogger("app.realtime.pipeline")

AUDIO_QUEUE_MAX = 500          # ~50s of 100ms chunks — backpressure bound

#: Characters that close a clause in the languages this product ships. A live
#: caption ending on one of these has said something a translator can render on
#: its own, so a long speaker does not have to stop for breath before the first
#: words go out. Deliberately excludes ASCII `,` and `;`, and the Devanagari
#: comma `,`: both appear inside a clause, and committing there splits a sentence
#: in half. A tuple because `str.endswith` only accepts one.
_CLAUSE_ENDINGS = ("。", "．", "！", "？", ".", "!", "?", "؟", "।", "॥")


def _ends_at_clause(text: str) -> bool:
    """Whether a partial transcript ends on a clause boundary.

    Trailing quote/bracket characters are skipped because captions frequently
    land as `…plan."` mid-utterance; the sentence still ended.

    Accepts a false positive on a trailing abbreviation ("…the Mr.") in exchange
    for not waiting on breath. It costs one short early segment, the speaker
    keeps talking, and the next clause commits normally — which is the right way
    round, because the alternative failure is a listener hearing nothing for
    fifteen seconds.
    """
    stripped = text.rstrip()
    while stripped and stripped[-1] in '"\'”’」』)]}>':
        stripped = stripped[:-1].rstrip()
    return stripped.endswith(_CLAUSE_ENDINGS)


@dataclass
class UtteranceState:
    """Per-speaker in-flight utterance tracking."""
    participant_id: uuid.UUID
    utterance_id: uuid.UUID = field(default_factory=uuid.uuid4)
    buffer: bytearray = field(default_factory=bytearray)
    started_at_ms: int = 0
    capture_started: float = 0.0
    last_partial_at: float = 0.0
    partial_text: str = ""
    seq: int = 0
    in_speech: bool = False
    locked_language: str | None = None
    last_client_stt_at: float = 0.0


class MeetingPipeline:
    """Session owner for one meeting's speech path.

    The four stages live in ``app.realtime.agents`` and are connected by the
    typed event contract on ``self.bus``; this class keeps what it always owned:
    VAD state, the durable transcript row, the wire protocol, listener routing,
    replay sequencing and staleness. One path, not two — the agents are how this
    class reaches a provider, not an alternative to it.
    """

    def __init__(self, session: RtSession) -> None:
        self.session = session
        self.audio_queues: dict[uuid.UUID, asyncio.Queue] = {}
        self.speaker_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self.vads: dict[uuid.UUID, object] = {}
        self.utterances: dict[uuid.UUID, UtteranceState] = {}
        # Keyed by speaker as well as sequence: ``seq`` is a per-speaker counter,
        # so (seq, target_lang) alone lets one speaker's turn overwrite another's
        # and leaves the overwritten task uncancellable.
        self.translation_tasks: dict[tuple[str, int, str], asyncio.Task] = {}
        self._partial_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._fanout_pending: dict[str, int] = {}
        self._closed = False
        self._latest_final_seq: dict[uuid.UUID, int] = {}
        self._detected: dict[str, dict] = {}
        self._meeting_id = str(session.meeting_id)

        # Agents 1-4 + the supervisor that observes them (Phase 2).
        self.bus = AgentBus()
        self.supervisor = Supervisor(meeting_id=self._meeting_id)
        self.supervisor.attach(self.bus)
        # Tenant-private meeting (issue #109 class 3, finding 8): the STT /
        # TTS / detection calls carry the private intent so a cloud provider
        # is never reachable from a private room.
        meeting_private_only = bool(getattr(self.session, "tenant_private_only", False))
        self.listening = ListeningAgent(
            self.bus,
            RealtimeSttProvider(ai, private_only=meeting_private_only),
            meeting_id=self._meeting_id,
            min_audio_bytes=MIN_AUDIO_BYTES, on_detect=self._on_language_detected)
        self.translating = TranslationAgent(
            self.bus,
            RealtimeTranslatorProvider(db_session, self._translate_context,
                                       translate_fn=lambda *a: translate_text(*a)),
            meeting_id=self._meeting_id)
        self.voice = VoiceAgent(self.bus, RealtimeTtsProvider(ai, private_only=meeting_private_only),
                                meeting_id=self._meeting_id, voice_for=voice_for)

    # ------------------------------------------------------------------ #
    # Agent adapters: room scoping the agents cannot know on their own
    # ------------------------------------------------------------------ #
    def _translate_context(self, segment_id, context, speaker_id=None):
        # The agent speaks in ids as strings; the durable translation, TM and
        # metering rows key on UUIDs, so convert at this boundary.
        try:
            segment_uuid = uuid.UUID(str(segment_id)) if segment_id else None
        except (ValueError, AttributeError, TypeError):
            segment_uuid = None
        speaker = self.session.participants.get(str(speaker_id)) if speaker_id else None
        return TranslateContext(
            org_id=self.session.org_id, user_id=speaker.user_id if speaker else None,
            product="realtime", meeting_id=self.session.meeting_id,
            segment_id=segment_uuid, intent="latency_optimized",
            tenant_private_only=bool(getattr(self.session, "tenant_private_only", False)),
            context=context[-1] if context else None,
            persist=True, meter=True)

    async def _on_language_detected(self, correlation_id: str, detected) -> None:
        """Agent 1 ran detection on our behalf; the meeting's diagnostic stream
        still has to say so, because that banner line is how an operator sees
        which language the path committed to."""
        self._detected[correlation_id] = {
            "provider": detected.provider, "language": detected.language,
            "confidence": detected.confidence}

    def _take_detected_language(self, correlation_id: str) -> dict | None:
        return self._detected.pop(correlation_id, None)

    async def _plan_quotas(self, db) -> dict[str, float]:
        """The org's plan limits, cached for a minute.

        The audio allowance is checked once per utterance, and a realtime
        segment must not pay a subscription read on every turn. A plan
        change taking effect within the minute is fine — the check is an
        allowance guard, not a billing statement.
        """
        now = time.monotonic()
        cached = getattr(self, "_quota_cache", None)
        if cached and now - cached[0] < 60.0:
            return cached[1]
        limits = await usage_service.plan_quotas(db, self.session.org_id)
        self._quota_cache = (now, limits)
        return limits

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def _make_vad(self) -> object:
        """One source of truth for when a turn begins and ends.

        Both providers take the same three settings, so `vad_provider` cannot
        silently change segmentation behaviour. ``vad_min_silence_ms`` is also
        the end-of-speech *latency*: a turn is only declared over after that
        much quiet has actually arrived, and tests/unit/test_vad_cadence.py
        measures it instead of assuming it.
        """
        return create_vad(
            settings.vad_provider,
            sample_rate=16000,
            min_speech_ms=settings.vad_min_speech_ms,
            min_silence_ms=settings.vad_min_silence_ms,
            max_speech_ms=settings.vad_max_speech_ms,
        )

    def start_speaker(self, p: RtParticipant) -> None:
        if p.participant_id in self.speaker_tasks:
            return
        q: asyncio.Queue = asyncio.Queue(maxsize=AUDIO_QUEUE_MAX)
        self.audio_queues[p.participant_id] = q
        self.vads[p.participant_id] = self._make_vad()
        self.utterances[p.participant_id] = UtteranceState(participant_id=p.participant_id)
        task = asyncio.create_task(self._speaker_loop(p),
                                   name=f"pipeline-{p.participant_id}")
        self.speaker_tasks[p.participant_id] = task

    def stop_speaker(self, participant_id: uuid.UUID) -> asyncio.Task | None:
        """Stop capture without discarding a valid in-flight final utterance.

        The browser can send ``audio.stop`` while the VAD still considers the
        speaker to be talking. Preserve the same 50-ms minimum used by normal
        finalization, then let the WebSocket handler await the flush before it
        announces ``audio.stopped``.
        """
        task = self.speaker_tasks.pop(participant_id, None)
        ptask = self._partial_tasks.pop(participant_id, None)
        if ptask and not ptask.done():
            ptask.cancel()
        self.audio_queues.pop(participant_id, None)
        self.vads.pop(participant_id, None)
        utterance = self.utterances.get(participant_id)
        participant = self.session.participants.get(str(participant_id))
        flush_task: asyncio.Task | None = None
        if (
            not self._closed
            and participant is not None
            and utterance is not None
            and utterance.in_speech
            and len(utterance.buffer) >= MIN_AUDIO_BYTES
        ):
            audio = bytes(utterance.buffer)
            utterance.buffer = bytearray()
            utterance.in_speech = False
            flush_task = asyncio.create_task(
                self._finalize_utterance(
                    participant,
                    utterance,
                    forced=True,
                    audio_bytes=audio,
                    start_ms=utterance.started_at_ms,
                    capture_started=utterance.capture_started,
                    utterance_id=utterance.utterance_id,
                    seq=utterance.seq,
                ),
                name=f"stop-finalize-{participant_id}",
            )
        self.utterances.pop(participant_id, None)
        if task:
            task.cancel()
        return flush_task

    async def shutdown(self) -> None:
        self._closed = True
        for pid in list(self.speaker_tasks):
            self.stop_speaker(pid)
        for pt in list(self._partial_tasks.values()):
            pt.cancel()
        self._partial_tasks.clear()
        for t in list(self.translation_tasks.values()):
            t.cancel()
        self.translation_tasks.clear()
        await self.supervisor.close()
        await self.bus.close()

    # ------------------------------------------------------------------ #
    # Audio ingestion
    # ------------------------------------------------------------------ #
    async def feed_audio(self, participant_id: uuid.UUID, pcm16: bytes) -> None:
        q = self.audio_queues.get(participant_id)
        if q is None:
            participant = self.session.participants.get(str(participant_id))
            if participant is not None and not self._closed:
                self.start_speaker(participant)
                q = self.audio_queues.get(participant_id)
        if q is None or not pcm16:
            return
        # PCM16 contract: 16-bit signed integer samples (even number of bytes)
        if len(pcm16) % 2 != 0:
            pcm16 = pcm16[:len(pcm16) - 1]
        # Frame bounds: drop aberrant fragments (<160B) or gigantic bursts (>64KB)
        if len(pcm16) < 160 or len(pcm16) > 64000:
            met.DROPPED_AUDIO_FRAMES.labels(reason="invalid_contract").inc()
            return
        try:
            q.put_nowait(pcm16)
        except asyncio.QueueFull:
            # backpressure: drop oldest audio, warn clients (PDD §10)
            met.DROPPED_AUDIO_FRAMES.labels(reason="audio_backpressure").inc()
            try:
                q.get_nowait()
                q.put_nowait(pcm16)
            except Exception:
                pass
            if not self.session.quality_degraded:
                self.session.quality_degraded = True
                await manager.broadcast(self.session, ServerEventType.QUALITY_DEGRADED, {
                    "reason": "audio_backpressure",
                    "message": "Audio processing is falling behind. Some chunks were "
                               "dropped. The original call is unaffected.",
                    "recoverable": True})

    def _diag(self, stage: str, *, utt: str | None = None, seq: int | None = None,
              speaker: uuid.UUID | None = None, **fields: object) -> dict:
        """Build a structured diagnostic record. Emitted to logs AND broadcast
        to the meeting so frontend can surface "STT: dev_text" / "TTS: dev_tone"
        in the realtime translation status banner — without this, a silent
        empty transcript on the prod Render deploy (faster-whisper not
        installed, dev_text returns empty text) looked like "translation
        active" with zero output to the listener."""
        rec: dict[str, object] = {
            "stage": stage,
            "meeting_id": str(self.session.meeting_id),
        }
        if speaker is not None:
            rec["speaker_id"] = str(speaker)
        if utt is not None:
            rec["utterance_id"] = utt
        if seq is not None:
            rec["seq"] = seq
        rec.update(fields)
        return rec

    def _broadcast_diag(self, record: dict) -> None:
        """Fire-and-forget: push a diagnostic record to every connected
        participant. Never blocks the audio path on a slow socket."""
        try:
            # Served from compose-api.log on CI failure: the loudest question
            # about truth chips is "did the pipeline even emit this?" — answer
            # it at the source instead of guessing from the DOM.
            log.info("room_diag %s %s", record.get("stage"),
                     {k: v for k, v in record.items() if k != "stage"})
            asyncio.create_task(
                manager.broadcast(
                    self.session,
                    "diagnostic",
                    record,
                    sequenced=False,
                ),
                name=f"diag-{record.get('stage')}",
            )
        except RuntimeError:
            # no running loop during shutdown
            pass

    async def _speaker_loop(self, p: RtParticipant) -> None:
        q = self.audio_queues[p.participant_id]
        vad = self.vads[p.participant_id]
        u = self.utterances[p.participant_id]
        try:
            while not self._closed:
                try:
                    chunk = await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if chunk is None:
                    break
                events = vad.process(chunk)  # type: ignore[attr-defined]
                for ev in events:
                    if ev.state == VadState.SPEECH:
                        # Barge-in before this turn opens: whatever is still
                        # queued for this speaker's earlier turns is now stale.
                        await self._handle_barge_in(p)
                        u.in_speech = True
                        u.utterance_id = uuid.uuid4()
                        u.seq += 1
                        u.buffer = bytearray(chunk)
                        u.started_at_ms = ev.timestamp_ms
                        u.capture_started = time.perf_counter()
                        u.last_partial_at = time.perf_counter()
                        u.partial_text = ""
                        now_ms = int(time.time() * 1000)
                        await manager.broadcast(
                            self.session, ServerEventType.SPEECH_STARTED,
                            {"timestamp_ms": ev.timestamp_ms,
                             "utterance_id": str(u.utterance_id),
                             "utteranceId": str(u.utterance_id),
                             "sequence": u.seq,
                             "seq": u.seq,
                             "created_at": now_ms,
                             "createdAt": now_ms},
                            speaker_id=str(p.participant_id))
                        # Agent 1 opens the lifecycle chain, so capture ->
                        # transcript -> translation -> speech -> delivery is one
                        # queryable correlation rather than five separate logs.
                        await self.listening.on_audio_captured(
                            correlation_id=str(u.utterance_id),
                            speaker_id=str(p.participant_id),
                            segment_id=str(u.utterance_id),
                            start_ms=ev.timestamp_ms, sequence_number=u.seq,
                            audio_bytes=len(chunk))
                    else:  # SPEECH ended
                        if u.in_speech:
                            u.buffer.extend(chunk)
                            u.in_speech = False
                            audio_payload = bytes(u.buffer)
                            u.buffer = bytearray()
                            start_ms = u.started_at_ms
                            cap_start = u.capture_started
                            curr_uid = u.utterance_id
                            curr_seq = u.seq
                            asyncio.create_task(
                                self._finalize_utterance(
                                    p, u, forced=False, audio_bytes=audio_payload,
                                    start_ms=start_ms, capture_started=cap_start,
                                    utterance_id=curr_uid, seq=curr_seq
                                ),
                                name=f"finalize-{p.participant_id}-{start_ms}"
                            )
                if u.in_speech:
                    u.buffer.extend(chunk)
                    now = time.perf_counter()
                    # Bounded segment enforcement: a speaker who never pauses is
                    # committed at the same cap the VAD uses, so there is one
                    # turn-length setting and not two that disagree.
                    cap_s = settings.vad_max_speech_ms / 1000.0
                    audio_ms = len(u.buffer) / 32.0  # 16 kHz mono PCM16
                    if (now - u.capture_started) >= cap_s and audio_ms >= cap_s * 1000 * 0.6:
                        self._split_running_utterance(p, u, vad, reason="length_cap")
                    elif (now - u.last_partial_at >= settings.vad_partial_interval_ms / 1000.0
                          and len(u.buffer) > 16000 * 2 * 0.8):
                        u.last_partial_at = now
                        prev_ptask = self._partial_tasks.get(p.participant_id)
                        if prev_ptask and not prev_ptask.done():
                            prev_ptask.cancel()
                        self._partial_tasks[p.participant_id] = asyncio.create_task(
                            self._emit_partial(p, u),
                            name=f"partial-{p.participant_id}-{u.seq}"
                        )
                        # Phrase break: a caption that ends on a clause boundary
                        # after `vad_phrase_commit_ms` of continuous speech is a
                        # complete thought, so commit it now. Waiting for the
                        # speaker's next breath is what made a long turn feel
                        # like nothing had happened for fifteen seconds.
                        if (settings.vad_phrase_commit_ms > 0
                                and (now - u.capture_started) * 1000 >= settings.vad_phrase_commit_ms
                                and _ends_at_clause(u.partial_text)):
                            self._split_running_utterance(p, u, vad, reason="phrase_break")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("speaker loop crashed for %s", p.participant_id)
        finally:
            # flush any in-flight speech on disconnect if session not closed
            if not self._closed and u.in_speech and len(u.buffer) > 3200:
                try:
                    await asyncio.shield(self._finalize_utterance(p, u, forced=True,
                                                                 utterance_id=u.utterance_id,
                                                                 seq=u.seq))
                except Exception:
                    log.exception("flush on disconnect failed")

    # ------------------------------------------------------------------ #
    # Mid-speech commit (Phase 3): the length cap and the phrase break
    # ------------------------------------------------------------------ #
    def _split_running_utterance(self, p: RtParticipant, u: UtteranceState,
                                 vad: object, *, reason: str) -> None:
        """Commit what the speaker has said so far and keep listening.

        Both mid-speech commits do the same thing: hand the audio captured up to
        this instant to the finalization path, then rotate the utterance state so
        the continuation becomes the next segment. The rotation happens *before*
        the task runs, because the speaker is still talking — if the id and seq
        stayed put, late audio would be appended to a segment already on its way
        to translation.
        """
        audio_payload = bytes(u.buffer)
        u.buffer = bytearray()
        start_ms = u.started_at_ms
        cap_start = u.capture_started
        curr_uid = u.utterance_id
        curr_seq = u.seq
        now = time.perf_counter()
        u.utterance_id = uuid.uuid4()
        u.seq += 1
        u.capture_started = now
        u.last_partial_at = now
        u.started_at_ms = getattr(vad, "clock_ms", int(now * 1000))
        u.partial_text = ""
        self._broadcast_diag(self._diag(
            "mid_speech_commit", utt=str(curr_uid), seq=curr_seq,
            speaker=p.participant_id, reason=reason,
            audio_ms=round(len(audio_payload) / 32.0)))
        asyncio.create_task(
            self._finalize_utterance(
                p, u, forced=False, audio_bytes=audio_payload,
                start_ms=start_ms, capture_started=cap_start,
                utterance_id=curr_uid, seq=curr_seq
            ),
            name=f"split-finalize-{p.participant_id}-{start_ms}"
        )

    # ------------------------------------------------------------------ #
    # STT: partial + final
    # ------------------------------------------------------------------ #
    def _lang_hint(self, p: RtParticipant, u: UtteranceState | None = None) -> str | None:
        if p.speak_lang not in ("auto", ""):
            return p.speak_lang
        if u and u.locked_language:
            return u.locked_language
        return None

    # ------------------------------------------------------------------ #
    # Barge-in (Phase 3): cancel one speaker's stale output, nobody else's
    # ------------------------------------------------------------------ #
    async def _handle_barge_in(self, p: RtParticipant) -> list[str]:
        """The speaker started a new turn, so translated audio still in flight
        for their earlier turns would talk over their own voice.

        The scope is deliberate: cancellations are keyed per correlation and only
        this speaker's correlations are touched, so a barge-in cannot silence
        another speaker's audio. Returns the cancelled correlation ids; an empty
        list means nothing was in flight, so nothing is announced — a flush the
        browser cannot attribute to a speaker would only drop live audio.
        """
        pid = str(p.participant_id)
        ptask = self._partial_tasks.pop(p.participant_id, None)
        if ptask and not ptask.done():
            ptask.cancel()
        languages = self.supervisor.active_languages(pid)
        cancelled = await self.supervisor.interrupt(pid, reason="barge_in")
        if not cancelled:
            return []
        for corr in cancelled:
            self._fanout_pending.pop(corr, None)
            self.listening.reset_utterance(corr)
            self.voice.forget_correlation(corr)
            met.STALE_AUDIO_DROPPED.labels(reason="barge_in").inc()
        for (owner, _seq, _lang), task in list(self.translation_tasks.items()):
            if owner == pid:
                task.cancel()
        self._broadcast_diag(self._diag(
            "barge_in", speaker=p.participant_id, cancelled=len(cancelled),
            target_languages=languages))
        await manager.broadcast(
            self.session, ServerEventType.PLAYBACK_FLUSH,
            {"speaker_id": pid, "speakerId": pid, "reason": "barge_in",
             "scope": "speaker", "recoverable": True,
             "target_languages": languages, "correlation_ids": cancelled,
             "message": "Translation of the interrupted turn was dropped."},
            speaker_id=pid)
        return cancelled

    # ------------------------------------------------------------------ #
    # Listener routing (Phase 3): whose audio, in which language, right now
    # ------------------------------------------------------------------ #
    def _audio_recipients(self, target_lang: str,
                          speaker_id: uuid.UUID) -> list[RtParticipant]:
        """Who should get translated audio in this language *at this instant*.

        Recomputed per chunk instead of once per stream: a listener who switches
        language mid-utterance must not keep receiving the old language, while
        everyone else listening in that language is still entitled to every
        chunk of it.

        The speaker is always excluded. Target selection already skips
        self-translation (``required_target_languages``), but a language group
        made for somebody else would otherwise deliver the speaker's own voice
        back to them — duplicated audio, and the one output guaranteed to be
        what their microphone just captured, i.e. the feedback loop.
        """
        listeners = manager.listeners_for_language(self.session, target_lang,
                                                   want_audio=True)
        if len(self.session.participants) > 1:
            listeners = [p for p in listeners if p.participant_id != speaker_id]
        live = set(self.supervisor.live_recipients(
            [str(p.participant_id) for p in listeners], target_lang))
        return [p for p in listeners if str(p.participant_id) in live]

    async def recipient_changed(self, participant_id: uuid.UUID, *,
                                previous_language: str,
                                new_language: str) -> None:
        """A listener changed target language — drop only their stale audio.

        ``sequenced=False`` on purpose: this instruction is addressed to one
        socket about audio that only exists in that socket's queue. Put it in
        the replay buffer and a *different* participant resuming the session
        would be told to stop their live playback.
        """
        pid = str(participant_id)
        await self.supervisor.recipient_changed(
            pid, previous_language=previous_language, new_language=new_language)
        target = [p for p in (self.session.participants.get(pid),) if p is not None]
        await manager.broadcast(
            self.session, ServerEventType.PLAYBACK_FLUSH,
            {"participant_id": pid, "reason": "language_changed", "scope": "recipient",
             "recoverable": True, "previous_language": previous_language,
             "new_language": new_language,
             "message": "Audio in your previous language was dropped."},
            to=target, sequenced=False)

    async def _emit_partial(self, p: RtParticipant, u: UtteranceState) -> None:
        corr = str(u.utterance_id)
        segment = await self.listening.transcribe_partial(
            correlation_id=corr, speaker_id=str(p.participant_id), segment_id=corr,
            sequence_number=u.seq, audio=bytes(u.buffer),
            lang_hint=self._lang_hint(p, u))
        if segment is None:
            # Agent 1 keeps the revision state, so an unchanged or failed partial
            # simply produces no segment. A failed partial is deliberately not a
            # wire event: speech is still in progress.
            self.listening.take_failure(corr)
            return
        u.partial_text = segment.recognized_text
        now_ms = int(time.time() * 1000)
        await manager.broadcast(
            self.session, ServerEventType.TRANSCRIPT_PARTIAL,
            {"speaker_name": p.display_name,
             "display_name": p.display_name,
             "speaker_id": str(p.participant_id),
             "speakerId": str(p.participant_id),
             "session_id": str(self.session.meeting_id),
             "sessionId": str(self.session.meeting_id),
             "language": segment.source_language,
             "text": segment.recognized_text,
             "is_final": False,
             "utterance_started_ms": u.started_at_ms,
             "utterance_id": str(u.utterance_id),
             "utteranceId": str(u.utterance_id),
             "sequence": u.seq,
             "seq": u.seq,
             "created_at": now_ms,
             "createdAt": now_ms},
            speaker_id=str(p.participant_id))

    async def _finalize_utterance(self, p: RtParticipant, u: UtteranceState,
                                  forced: bool = False,
                                  audio_bytes: bytes | None = None,
                                  start_ms: int | None = None,
                                  capture_started: float | None = None,
                                  utterance_id: uuid.UUID | None = None,
                                  seq: int | None = None) -> None:
        audio = audio_bytes if audio_bytes is not None else bytes(u.buffer)
        if audio_bytes is None:
            u.buffer = bytearray()
        # Suppress turn if client STT already finalized this speech and remaining audio is residual
        if (time.time() - getattr(u, "last_client_stt_at", 0.0) < 2.0) or len(audio) < 1600:
            u.locked_language = None
            self._broadcast_diag(self._diag(
                "stt_skipped", utt=str(utterance_id or u.utterance_id),
                seq=seq or u.seq, speaker=p.participant_id,
                reason="client_stt_preempted" if (time.time() - getattr(u, "last_client_stt_at", 0.0) < 2.0) else "below_min_audio",
                audio_bytes=len(audio),
                min_bytes=1600))
            return
        cap_start = capture_started if capture_started is not None else u.capture_started
        capture_ms = (time.perf_counter() - cap_start) * 1000
        # Absolute start of the turn. `started_at_ms` is the VAD's own frame clock,
        # which is per-speaker and restarts with the connection, so it cannot put
        # two speakers' captions on one timeline; capture_ms says how long this
        # turn had been open when STT started, which pins it to wall time.
        start_wall_ms = int(time.time() * 1000 - capture_ms)
        duration_ms = round(len(audio) / 32.0)  # 16 kHz mono PCM16
        started_at_ms = start_ms if start_ms is not None else u.started_at_ms
        ptask = self._partial_tasks.pop(p.participant_id, None)
        if ptask and not ptask.done():
            ptask.cancel()
        corr = str(utterance_id or u.utterance_id)
        seq_num = seq if seq is not None else u.seq
        # Meter the audio, and check the audio allowance BEFORE the expensive
        # work (the STT). The canonical realtime path never recorded audio
        # seconds, so the plan's audio limit had nothing to accrue and could
        # never trip (issue #109 class 4). When the monthly allowance is
        # exhausted the segment is not transcribed and the diagnostic says
        # why — the limit is real, the meeting keeps running.
        if duration_ms > 0 and self.session.org_id:
            try:
                async with db_session() as qdb:
                    await usage_service.check_quota(
                        qdb, self.session.org_id, "audio_seconds",
                        duration_ms / 1000.0,
                        quotas=await self._plan_quotas(qdb))
                    await usage_service.record_usage(
                        qdb, org_id=self.session.org_id, product="realtime",
                        unit_type="audio_seconds", units=duration_ms / 1000.0,
                        metadata={"meeting_id": str(self.session.meeting_id),
                                  "speaker_id": str(p.participant_id)})
                    await qdb.commit()
            except QuotaExceededError as qe:
                self._broadcast_diag(self._diag(
                    "quota_exceeded", utt=corr, seq=seq_num,
                    speaker=p.participant_id, unit="audio_seconds",
                    reason=str(qe)))
                return
            except Exception as exc:
                # Metering must never break a live meeting: a ledger write
                # that fails leaves the usage under-counted for this segment,
                # which is visible; a dropped segment is not recoverable.
                log.warning("realtime audio metering failed (%s); the segment "
                            "continues without this usage record", exc)
        self._broadcast_diag(self._diag(
            "stt_enter", utt=corr, seq=seq_num, speaker=p.participant_id,
            audio_bytes=len(audio), lang_hint=self._lang_hint(p, u) or "auto"))
        segment = await self.listening.finalize(
            correlation_id=corr, speaker_id=str(p.participant_id), segment_id=corr,
            sequence_number=seq_num, audio=audio, start_ms=started_at_ms, end_ms=0,
            lang_hint=self._lang_hint(p, u))
        stt_ms = self.listening.take_provider_ms(corr)
        if segment is None:
            failure = self.listening.take_failure(corr) or {}
            reason = failure.get("reason", "provider_unavailable")
            self._broadcast_diag(self._diag(
                "stt_empty" if reason == "empty_speech" else "stt_failed",
                utt=corr, seq=seq_num, speaker=p.participant_id, reason=reason,
                error_type=failure.get("error_code", ""),
                error=str(failure.get("error", ""))[:160]))
            if reason == "empty_speech":
                # No words recognised is not an outage — the listener only needs
                # to know the speech ended, so no error event is sent. The
                # utterance id rides along so the browser can retire the partial
                # caption that this turn will never complete.
                await manager.broadcast(
                    self.session, ServerEventType.SPEECH_ENDED,
                    {"empty": True, "utterance_id": corr, "utteranceId": corr},
                    speaker_id=str(p.participant_id))
            else:
                await manager.broadcast(
                    self.session, ServerEventType.ERROR,
                    {"code": "stt_unavailable", "message":
                        "Speech recognition is temporarily unavailable. Captions and "
                        "the original audio continue to work.",
                     "recoverable": True}, speaker_id=str(p.participant_id))
            u.locked_language = None
            return
        met.STT_LATENCY.labels(provider=segment.provider or "unknown").observe(stt_ms)
        detected = self._take_detected_language(corr)
        if detected is not None:
            self._broadcast_diag(self._diag("lang_detect", utt=corr, seq=seq_num,
                                            speaker=p.participant_id, **detected))
            await manager.broadcast(
                self.session, ServerEventType.LANGUAGE_DETECTED,
                {"speaker_id": str(p.participant_id),
                 "language": detected.get("language"),
                 "confidence": detected.get("confidence"),
                 "provider": detected.get("provider"),
                 "utterance_id": corr},
                speaker_id=str(p.participant_id)
            )
        self._broadcast_diag(self._diag(
            "stt_exit", utt=corr, seq=seq_num, speaker=p.participant_id,
            provider=segment.provider, model=segment.model,
            stt_ms=round(stt_ms, 1),
            text_len=len(segment.recognized_text),
            text_preview=segment.recognized_text[:80],
            language=segment.source_language, confidence=segment.confidence))
        u.locked_language = None  # Reset locked language for the next speech segment
        await self._commit_segment(
            p, text=segment.recognized_text, source_lang=segment.source_language,
            audio=audio, confidence=segment.confidence,
            stt_model=segment.model or "", stt_provider=segment.provider or "",
            stt_ms=stt_ms, capture_ms=capture_ms, start_ms=started_at_ms,
            start_wall_ms=start_wall_ms, duration_ms=duration_ms,
            utterance_id=utterance_id or u.utterance_id,
            seq_num=seq_num)

    # ------------------------------------------------------------------ #
    # Dev/test text injection (guarded; STT stage marked 'injected')
    # ------------------------------------------------------------------ #
    async def inject_transcript(self, p: RtParticipant, text: str,
                                language: str = "") -> None:
        if not ai.is_dev_mode(__import__("gt_ai.types", fromlist=["Task"]).Task.STT) \
                and not settings.app_env == "test":
            # In production with real STT configured, injection is a host-only
            # debug affordance — disabled entirely by default.
            raise AppError("transcript injection disabled", status=403)
        text = (text or "").strip()
        if not text:
            return
        source_lang = language or (p.speak_lang if p.speak_lang != "auto" else "")
        if not source_lang:
            det = await self.listening.detect_language(text)
            source_lang = det.language
        # The injected line IS the transcript stage's output, so say so: this
        # diag is what turns the room's STT truth chip on for an injected
        # turn. Omitting it left every inject-driven room with an STT chip
        # claiming "no signal yet" while the transcript was already live.
        self._broadcast_diag(self._diag(
            "stt_exit", utt=None, seq=None, speaker=p.participant_id,
            provider="inject", model="host_injected", stt_ms=0.0,
            text_len=len(text), text_preview=text[:80],
            language=source_lang, confidence=1.0))
        await self._commit_segment(p, text=text, source_lang=source_lang,
                                   audio=b"", confidence=1.0,
                                   stt_model="injected", stt_provider="inject",
                                   stt_ms=0.0, capture_ms=0.0, start_ms=0,
                                   start_wall_ms=int(time.time() * 1000))

    async def ingest_client_transcript(self, p: RtParticipant, text: str,
                                       language: str = "", is_final: bool = True) -> None:
        """Ingest live real-time speech recognized by the client's Web Speech engine (Google Meet pattern)."""
        clean_text = (text or "").strip()
        if not clean_text:
            return
        source_lang = language or (p.speak_lang if p.speak_lang not in ("auto", "AUTO", "") else "")
        if not source_lang:
            try:
                det = await self.listening.detect_language(clean_text)
                source_lang = det.language
            except Exception:
                source_lang = "en"

        u = self.utterances.get(p.participant_id)
        if u is None:
            self.start_speaker(p)
            u = self.utterances[p.participant_id]

        now_ms = int(time.time() * 1000)

        if not is_final:
            u.partial_text = clean_text
            await manager.broadcast(
                self.session, ServerEventType.TRANSCRIPT_PARTIAL,
                {
                    "speaker_name": p.display_name,
                    "display_name": p.display_name,
                    "speaker_id": str(p.participant_id),
                    "speakerId": str(p.participant_id),
                    "session_id": str(self.session.meeting_id),
                    "sessionId": str(self.session.meeting_id),
                    "language": source_lang,
                    "text": clean_text,
                    "is_final": False,
                    "utterance_started_ms": u.started_at_ms or now_ms,
                    "utterance_id": str(u.utterance_id),
                    "utteranceId": str(u.utterance_id),
                    "sequence": u.seq,
                    "seq": u.seq,
                    "created_at": now_ms,
                    "createdAt": now_ms,
                },
                speaker_id=str(p.participant_id),
            )
            return

        # Final speech transcript: advance turn and commit segment for MT translation & TTS fanout
        u.seq += 1
        curr_seq = u.seq
        curr_uid = uuid.uuid4()
        u.utterance_id = curr_uid
        u.in_speech = False
        u.partial_text = ""
        u.buffer = bytearray()  # Clear PCM buffer so server VAD does not duplicate this turn
        u.last_client_stt_at = time.time()

        self._broadcast_diag(self._diag(
            "stt_exit", utt=str(curr_uid), seq=curr_seq, speaker=p.participant_id,
            provider="client_speech_api", model="browser_web_speech", stt_ms=0.0,
            text_len=len(clean_text), text_preview=clean_text[:80],
            language=source_lang, confidence=0.98))

        await self._commit_segment(
            p, text=clean_text, source_lang=source_lang,
            audio=b"", confidence=0.98,
            stt_model="browser_web_speech", stt_provider="client_speech_api",
            stt_ms=0.0, capture_ms=0.0, start_ms=now_ms,
            start_wall_ms=now_ms, duration_ms=round(len(clean_text.split()) * 300),
            utterance_id=curr_uid, seq_num=curr_seq
        )

    # ------------------------------------------------------------------ #
    # Canonical segment + fan-out
    # ------------------------------------------------------------------ #
    async def _commit_segment(self, p: RtParticipant, *, text: str,
                              source_lang: str, audio: bytes,
                              confidence: float | None, stt_model: str,
                              stt_provider: str, stt_ms: float,
                              capture_ms: float, start_ms: int,
                              start_wall_ms: int = 0, duration_ms: int = 0,
                              utterance_id: uuid.UUID | None = None,
                              seq_num: int | None = None) -> None:
        session = self.session
        # --- persist canonical source (immutable) ---
        async with db_session() as db:
            scalar_seq = (await db.execute(
                select(func.coalesce(func.max(M.TranscriptSegment.seq), 0))
                .where(M.TranscriptSegment.meeting_id == session.meeting_id)
            )).scalar()
            seq = (scalar_seq or 0) + 1
            segment = M.TranscriptSegment(
                meeting_id=session.meeting_id, seq=seq,
                speaker_id=p.participant_id, speaker_name=p.display_name,
                source_lang=source_lang, source_text=text, is_final=True,
                start_ms=start_ms or None, confidence=confidence,
                stt_model=stt_model, stt_provider=stt_provider,
                latency_json={"audio_capture_ms": capture_ms, "stt_final_ms": stt_ms},
            )
            db.add(segment)
            await db.commit()
            segment_id = segment.id

        # optionally store audio artifact (retention-controlled)
        if audio and settings.retention_audio_days:
            try:
                from app.storage import object_key, sha256_bytes, storage
                from gt_ai.audio_utils import pcm16_to_wav
                key = object_key("audio", str(session.org_id),
                                 f"{segment_id}.wav", sha256_bytes(audio[:64] + str(segment_id).encode()))
                await storage().put(key, pcm16_to_wav(audio, 16000), "audio/wav")
                async with db_session() as db:
                    await db.execute(
                        update(M.TranscriptSegment)
                        .where(M.TranscriptSegment.id == segment_id)
                        .values(audio_object_key=key))
                    await db.commit()
            except Exception:
                log.exception("audio artifact storage failed (non-fatal)")

        now_ms = int(time.time() * 1000)
        u_id = str(utterance_id) if utterance_id is not None else str(segment_id)
        await manager.broadcast(
            session, ServerEventType.SPEECH_ENDED,
            {"timestamp_ms": start_ms, "utterance_id": u_id, "utteranceId": u_id,
             "sequence": seq, "seq": seq},
            speaker_id=str(p.participant_id))
        await manager.broadcast(
            session, ServerEventType.TRANSCRIPT_FINAL,
            {"segment_id": str(segment_id), "utterance_id": u_id,
             "utteranceId": u_id,
             "seq": seq, "sequence": seq,
             "speaker_id": str(p.participant_id), "speakerId": str(p.participant_id),
             "speaker_name": p.display_name, "display_name": p.display_name,
             "session_id": str(session.meeting_id), "sessionId": str(session.meeting_id),
             "language": source_lang, "source_lang": source_lang,
             "source_language": source_lang, "sourceLanguage": source_lang,
             "text": text, "source_text": text, "sourceText": text,
             "is_final": True, "confidence": confidence,
             "stt_model": stt_model,
             # Timeline metadata a caption needs: when this turn started in wall
             # time and how long it ran. A caption's place in the room comes from
             # these, not from arrival order, which translation latency reorders.
             "start_wall_ms": start_wall_ms, "startWallMs": start_wall_ms,
             "duration_ms": duration_ms, "durationMs": duration_ms,
             "latency": {"audio_capture_ms": capture_ms, "stt_final_ms": stt_ms},
             "created_at": now_ms, "createdAt": now_ms,
             "dedup_key": f"{session.meeting_id}:{p.participant_id}:{seq}",
             "dedupKey": f"{session.meeting_id}:{p.participant_id}:{seq}"},
            speaker_id=str(p.participant_id))
        self._latest_final_seq[p.participant_id] = seq
        if session.quality_degraded:
            session.quality_degraded = False

        # --- compute deduplicated target set & fan out ---
        targets = manager.required_target_languages(
            session, source_lang, exclude_speaker=str(p.participant_id))
        # Pin the translation window before queueing the work, then advance it.
        prev_context = self.translating.context_for(str(p.participant_id))
        self.translating.note_source(str(p.participant_id), text)
        if not targets:
            self._broadcast_diag(self._diag(
                "fanout_skipped", utt=str(u_id), seq=seq, speaker=p.participant_id,
                reason="no_targets", source_lang=source_lang,
                connected_participants=sum(
                    1 for x in session.participants.values() if x.connected),
                participant_hear_langs=[
                    x.hear_lang for x in session.participants.values() if x.connected
                ]))
            return
        self._broadcast_diag(self._diag(
            "fanout_start", utt=str(u_id), seq=seq, speaker=p.participant_id,
            source_lang=source_lang, targets=sorted(targets),
            text_preview=text[:80]))
        self._start_fanout(speaker=p, segment_id=segment_id, seq=seq,
                           utterance_id=str(u_id), text=text, source_lang=source_lang,
                           targets=targets, stt_ms=stt_ms, capture_ms=capture_ms,
                           start_wall_ms=start_wall_ms, duration_ms=duration_ms,
                           prev_context=prev_context)

    def _start_fanout(self, *, speaker: RtParticipant, segment_id: uuid.UUID,
                      seq: int, utterance_id: str, text: str, source_lang: str,
                      targets: set[str], stt_ms: float, capture_ms: float,
                      start_wall_ms: int = 0, duration_ms: int = 0,
                      prev_context: tuple[str, ...]) -> None:
        """Launch one language run per distinct target, and declare the turn
        active so a barge-in has something to cancel.

        Without ``note_active_segment`` the supervisor's ``interrupt`` has no
        record of whose output is in flight — which is how barge-in stayed
        unwired for a whole phase.
        """
        self.supervisor.note_active_segment(str(speaker.participant_id),
                                            correlation_id=utterance_id,
                                            sequence_number=seq,
                                            target_languages=sorted(targets))
        self._fanout_pending[utterance_id] = len(targets)
        for target_lang in sorted(targets):
            key = (str(speaker.participant_id), seq, target_lang)
            task = asyncio.create_task(
                self._translate_and_synthesize(
                    segment_id=segment_id, seq=seq, speaker=speaker, text=text,
                    source_lang=source_lang, target_lang=target_lang,
                    stt_ms=stt_ms, capture_ms=capture_ms,
                    start_wall_ms=start_wall_ms, duration_ms=duration_ms,
                    prev_context=prev_context, utterance_id=utterance_id),
                name=f"fanout-{seq}-{target_lang}")
            self.translation_tasks[key] = task
            task.add_done_callback(
                lambda _t, k=key, c=utterance_id: self._finish_fanout_task(k, c))

    def _finish_fanout_task(self, key: tuple[str, int, str], correlation_id: str) -> None:
        """Release one language run, and the whole correlation once they are all
        home. An interrupted run is pruned by ``_handle_barge_in``, which must
        not be second-guessed by a late callback here."""
        self.translation_tasks.pop(key, None)
        remaining = self._fanout_pending.get(correlation_id)
        if remaining is None:
            return
        remaining -= 1
        if remaining > 0:
            self._fanout_pending[correlation_id] = remaining
            return
        self._fanout_pending.pop(correlation_id, None)
        self.supervisor.prune(correlation_id)

    async def _translate_and_synthesize(self, *, segment_id: uuid.UUID, seq: int,
                                        speaker: RtParticipant, text: str,
                                        source_lang: str, target_lang: str,
                                        stt_ms: float, capture_ms: float,
                                        start_wall_ms: int = 0, duration_ms: int = 0,
                                        prev_context: tuple[str, ...] = (),
                                        utterance_id: str | None = None) -> None:
        session = self.session
        trace = LatencyTrace(segment_id=str(segment_id), seq=seq,
                             utterance_id=utterance_id or str(segment_id),
                             start_wall_ms=start_wall_ms, duration_ms=duration_ms,
                             source_lang=source_lang, target_lang=target_lang,
                             audio_capture_ms=capture_ms, stt_final_ms=stt_ms)
        t0 = time.perf_counter()
        u_id = utterance_id or str(segment_id)
        # --- stale check before starting (speaker already moved on?) ---
        if self._is_stale(speaker.participant_id, seq, u_id):
            trace.stale_dropped = True
            met.STALE_AUDIO_DROPPED.labels(reason="pre_translation").inc()
            return
        now_ms = int(time.time() * 1000)
        await manager.broadcast(
            session, ServerEventType.TRANSLATION_STARTED,
            {"segment_id": str(segment_id), "utterance_id": u_id, "utteranceId": u_id,
             "seq": seq, "sequence": seq, "target_lang": target_lang, "target_language": target_lang,
             "created_at": now_ms, "createdAt": now_ms},
            speaker_id=str(speaker.participant_id))
        self._broadcast_diag(self._diag(
            "mt_enter", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
            source_lang=source_lang, target_lang=target_lang,
            text_len=len(text), text_preview=text[:80]))

        # --- Agent 2: one provider call per (segment, target language) ---
        source = TranscriptSegment(
            correlation_id=u_id, meeting_id=self._meeting_id,
            speaker_id=str(speaker.participant_id), segment_id=str(segment_id),
            sequence_number=seq, source_language=source_lang,
            recognized_text=text, is_final=True)
        caption_recipients = [str(x.participant_id) for x in
                              manager.listeners_for_language(session, target_lang,
                                                             want_audio=False)]
        try:
            done = await self.translating.translate_one(
                source, target_lang, caption_recipients, prior_context=prev_context)
        except AppError as e:
            self._broadcast_diag(self._diag(
                "mt_failed", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
                source_lang=source_lang, target_lang=target_lang,
                error_type=type(e).__name__, error=str(e)[:160]))
            await self._translation_failed(segment_id, seq, source_lang,
                                           target_lang, e)
            return
        except Exception as e:
            log.exception("translation crashed")
            await self._translation_failed(segment_id, seq, source_lang,
                                           target_lang, e)
            return
        trace.translation_ms = (time.perf_counter() - t0) * 1000
        translated = done.translated_text
        now_ms = int(time.time() * 1000)
        self._broadcast_diag(self._diag(
            "mt_exit", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
            source_lang=source_lang, target_lang=target_lang,
            provider=done.provider, model=done.model,
            translation_ms=round(trace.translation_ms, 1),
            translated_text_preview=translated[:80]))

        # --- Phase 5 translation.segment.final + translation.final contract ---
        final_translation_event = {
            "type": "translation.segment.final",
            "session_id": str(session.meeting_id),
            "sessionId": str(session.meeting_id),
            "speaker_id": str(speaker.participant_id),
            "speakerId": str(speaker.participant_id),
            "sequence": seq,
            "seq": seq,
            "utterance_id": u_id,
            "utteranceId": u_id,
            "segment_id": str(segment_id),
            "source_lang": source_lang,
            "source_language": source_lang,
            "sourceLanguage": source_lang,
            "target_lang": target_lang,
            "target_language": target_lang,
            "targetLanguage": target_lang,
            "source_text": text,
            "sourceText": text,
            "text": translated,
            "translated_text": translated,
            "translatedText": translated,
            # The translated caption describes the same turn as the source
            # caption, so it carries that turn's timeline, not its own arrival.
            "start_wall_ms": start_wall_ms,
            "startWallMs": start_wall_ms,
            "duration_ms": duration_ms,
            "durationMs": duration_ms,
            "display_name": speaker.display_name,
            "speaker_name": speaker.display_name,
            "model": done.model,
            "quality_flags": done.quality_flags,
            "latency_ms": done.latency_ms,
            "created_at": now_ms,
            "createdAt": now_ms,
            "dedup_key": f"{session.meeting_id}:{speaker.participant_id}:{seq}:{target_lang}",
            "dedupKey": f"{session.meeting_id}:{speaker.participant_id}:{seq}:{target_lang}",
        }
        await manager.broadcast(
            session, ServerEventType.TRANSLATION_FINAL,
            final_translation_event,
            speaker_id=str(speaker.participant_id))
        await manager.broadcast(
            session, ServerEventType.TRANSLATION_SEGMENT_FINAL,
            final_translation_event,
            speaker_id=str(speaker.participant_id))

        if self._is_stale(speaker.participant_id, seq, u_id):
            trace.stale_dropped = True
            met.STALE_AUDIO_DROPPED.labels(reason="pre_tts").inc()
            await self._report_latency(trace)
            return

        # --- TTS: once per (segment, target_lang) group ---
        audio_listeners = self._audio_recipients(target_lang, speaker.participant_id)
        if not audio_listeners:
            self._broadcast_diag(self._diag(
                "tts_skipped", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
                target_lang=target_lang,
                reason="no_audio_listeners",
                participants=[
                    {"id": str(p.participant_id), "hear_lang": p.hear_lang,
                     "audio_mode": p.audio_mode, "connected": p.connected,
                     "is_self": p.participant_id == speaker.participant_id}
                    for p in session.participants.values()
                ]))
            await self._report_latency(trace)
            return
        self._broadcast_diag(self._diag(
            "tts_enter", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
            target_lang=target_lang,
            listener_count=len(audio_listeners),
            listeners=[{"id": str(p.participant_id), "hear_lang": p.hear_lang,
                        "audio_mode": p.audio_mode} for p in audio_listeners]))
        await manager.broadcast(
            session, ServerEventType.TTS_STARTED,
            {"segment_id": str(segment_id), "utterance_id": u_id, "utteranceId": u_id,
             "seq": seq, "sequence": seq, "target_lang": target_lang, "target_language": target_lang,
             "created_at": now_ms, "createdAt": now_ms},
            to=audio_listeners, speaker_id=str(speaker.participant_id))
        t_tts = time.perf_counter()
        decision: RouteDecision | None = None
        # Short id MUST be derived from the same id the JSON `tts.chunk` event
        # carries (`segment_id`), otherwise the two transports produce different
        # queue tags for one chunk and the client cannot dedup the duplicate.
        short_id_bytes = str(segment_id).replace("-", "")[:16].ljust(16, "\x00").encode("utf-8")
        lang_bytes = target_lang.encode("utf-8")
        # TTS header: [T][short id][language length][language][0x01][uint32 chunk index].
        # The marker keeps old clients safe during a rolling deploy; they will
        # treat the extension as part of the WAV payload, while new clients can
        # stop guessing chunk order from binary arrival timing.
        bin_header_prefix = b"\x54" + short_id_bytes + bytes([len(lang_bytes)]) + lang_bytes

        async def deliver(ready: TtsChunkReady, audio: bytes,
                          _recipients: list[str]) -> None:
            """One declared chunk, on both transports, with the same ids."""
            # Both transports get the same recipient list, recomputed here: a
            # listener that only the JSON path skipped would still be played the
            # binary frame, and one that only the binary path skipped would hear
            # the base64 fallback — either way the dedup registry cannot save it.
            recipients = self._audio_recipients(target_lang, speaker.participant_id)
            await manager.broadcast(
                session, ServerEventType.TTS_CHUNK,
                {"segment_id": str(segment_id), "utterance_id": u_id, "utteranceId": u_id,
                 "seq": seq, "sequence": seq, "target_lang": target_lang, "target_language": target_lang,
                 "chunk_index": ready.chunk_index, "chunkIndex": ready.chunk_index,
                 "audio_base64": base64.b64encode(audio).decode(), "format": ready.codec,
                 "sample_rate": ready.sample_rate,
                 "is_dev": ready.is_dev, "model": ready.model,
                 "created_at": now_ms, "createdAt": now_ms},
                to=recipients, speaker_id=str(speaker.participant_id))

            # Binary frame delivery for lowest-latency audio playback.
            # Legacy payload = [tag][shortId][langLen][lang][WAV bytes].
            # Capable clients get [0x01][uint32 chunk index] before the WAV.
            # Frontend decodes via decodeBinaryFrame and routes TTS frames
            # through AudioPlayer.enqueueWav (not enqueuePcm16) — see
            # apps/web/src/lib/audio.ts and MeetingRoom.tsx onBinary.
            for listener in recipients:
                if listener.connected and listener.ws is not None:
                    try:
                        extension = (
                            b"\x01"
                            + int(ready.chunk_index).to_bytes(4, "big", signed=False)
                            if listener.supports_tts_chunk_index
                            else b""
                        )
                        bin_frame = bin_header_prefix + extension + audio
                        await listener.ws.send_bytes(bin_frame)
                    except Exception:
                        pass

        def audio_still_wanted() -> bool:
            """Stop mid-stream if the speaker moved on or barged in, and report
            it once."""
            if not self._is_stale(speaker.participant_id, seq, u_id):
                return True
            if not trace.stale_dropped:
                trace.stale_dropped = True
                met.STALE_AUDIO_DROPPED.labels(reason="mid_tts").inc()
            return False

        async def note_provider(route: RouteDecision) -> None:
            nonlocal decision
            decision = route
            self._broadcast_diag(self._diag(
                "tts_provider", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
                target_lang=target_lang,
                provider=route.provider, model=route.model))

        async def note_first_audio(ready: TtsChunkReady, _elapsed_ms: float) -> None:
            # Measured from before the provider call, as this metric always was;
            # Agent 3's own elapsed starts after the stream opens.
            trace.tts_first_audio_ms = (time.perf_counter() - t_tts) * 1000
            met.TTS_LATENCY.labels(provider=ready.provider).observe(
                trace.tts_first_audio_ms)
            self._broadcast_diag(self._diag(
                "tts_first_audio", utt=str(u_id), seq=seq,
                speaker=speaker.participant_id, target_lang=target_lang,
                provider=ready.provider,
                tts_first_audio_ms=round(trace.tts_first_audio_ms, 1),
                bytes=ready.payload_bytes, sample_rate=ready.sample_rate,
                format=ready.codec, is_dev=ready.is_dev))

        # --- Agent 3: synthesize and deliver, deduplicating chunks ---
        chunk_idx = await self.voice.synthesize(
            done, recipients=[str(x.participant_id) for x in audio_listeners],
            deliver=deliver, should_continue=audio_still_wanted,
            on_provider=note_provider, on_first_audio=note_first_audio)
        failure = self.voice.take_failure(done)
        provider_name = decision.provider if decision else ""
        if failure is None:
            await manager.broadcast(
                session, ServerEventType.TTS_COMPLETED,
                {"segment_id": str(segment_id), "utterance_id": str(segment_id),
                 "seq": seq, "target_lang": target_lang, "target_language": target_lang,
                 "chunks": chunk_idx, "stale_dropped": trace.stale_dropped,
                 "provider": provider_name},
                to=self._audio_recipients(target_lang, speaker.participant_id),
                speaker_id=str(speaker.participant_id))
            self._broadcast_diag(self._diag(
                "tts_exit", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
                target_lang=target_lang, provider=provider_name,
                chunks=chunk_idx, stale_dropped=trace.stale_dropped))
            # LiveKit mode: publish synthetic track (bridge no-ops in ws mode)
            from app.realtime import livekit_bridge
            await livekit_bridge.publish_translated_audio(
                session, target_lang, translated, str(segment_id), seq)
        else:
            log.warning("TTS fan-out failed for target %s: %s", target_lang,
                        failure.get("error", ""))
            self._broadcast_diag(self._diag(
                "tts_failed", utt=str(u_id), seq=seq, speaker=speaker.participant_id,
                target_lang=target_lang,
                error_type=failure.get("error_code", ""),
                error=str(failure.get("error", ""))[:160]))
            await manager.broadcast(
                session, ServerEventType.ERROR,
                {"code": "tts_unavailable",
                 "message": "Translated speech is temporarily unavailable. "
                            "Translated captions remain active.",
                 "recoverable": True, "target_lang": target_lang},
                to=self._audio_recipients(target_lang, speaker.participant_id),
                speaker_id=str(speaker.participant_id))
        trace.delivery_ms = (time.perf_counter() - t0) * 1000
        trace.total_e2e_latency_ms = capture_ms + stt_ms + trace.delivery_ms
        met.E2E_LATENCY.labels(src=source_lang, tgt=target_lang).observe(
            trace.total_e2e_latency_ms)
        await self._report_latency(trace)

    async def _translation_failed(self, segment_id: uuid.UUID, seq: int,
                                  source_lang: str, target_lang: str,
                                  e: Exception) -> None:
        message = ("Translation is taking longer than expected. "
                   "The original audio is still active.")
        code = e.__class__.__name__
        detail = getattr(e, "message", str(e))
        if isinstance(e, AppError):
            code = getattr(e, "code", code)
        await manager.broadcast(
            self.session, ServerEventType.TRANSLATION_FAILED,
            {"segment_id": str(segment_id), "seq": seq,
             "source_lang": source_lang, "target_lang": target_lang,
             "code": code, "message": message, "detail": detail[:200],
             "recoverable": True})
        met.TRANSLATION_FAILURES.labels(src=source_lang or "?", tgt=target_lang,
                                        provider="router", reason=code).inc()

    async def _report_latency(self, trace: LatencyTrace) -> None:
        await manager.broadcast(
            self.session, ServerEventType.LATENCY_REPORT,
            trace.model_dump(), sequenced=False)

    def _is_stale(self, speaker_id: uuid.UUID, seq: int,
                  correlation_id: str | None = None) -> bool:
        """Stale output detection (PDD §10): a newer final segment from the
        same speaker plus an elapsed budget means late audio would talk over
        current speech — drop it instead.

        Cancellation is the other half, and the one barge-in needs: when a
        speaker cuts themselves off, their *next* turn has not been transcribed
        yet, so the sequence comparison still reports the old turn as current.
        """
        if correlation_id is not None and self.supervisor.is_cancelled(correlation_id):
            return True
        latest = self._latest_final_seq.get(speaker_id, seq)
        if seq >= latest:
            return False
        # allow one segment of slack within the staleness window
        return (latest - seq) >= 1 and seq < latest


sessions_pipeline: dict[str, MeetingPipeline] = {}


def get_pipeline(session: RtSession) -> MeetingPipeline:
    if session.pipeline is None:
        session.pipeline = MeetingPipeline(session)
    return session.pipeline
