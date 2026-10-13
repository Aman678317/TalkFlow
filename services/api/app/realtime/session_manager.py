"""Realtime session manager (PDD §9, §13, §38).

Keeps live state for meetings: participants, preferences, per-session
sequence counters, event replay buffers for reconnect-resume, and the
listener routing table.

Routing keys (PDD §12):
    translation fan-out: (segment_seq, target_lang)  — computed ONCE per pair
    listener route:      (participant_id) -> hear_lang -> WS connection

Durable state (transcript, preferences) lives in PostgreSQL; this manager is
the fast in-process control layer. On multi-node deployments, Redis pub/sub
bridges sessions across API instances (bridge hooks included).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app import metrics as met
from app.config import settings
from app.realtime.protocol import ServerEvent

log = logging.getLogger("app.realtime.sessions")


@dataclass
class RtParticipant:
    participant_id: uuid.UUID
    user_id: uuid.UUID | None
    display_name: str
    speak_lang: str = "auto"
    hear_lang: str = "en"
    audio_mode: str = "translated"   # original|translated|mixed|captions_only
    captions_enabled: bool = True
    ws: WebSocket | None = None
    ws_task: asyncio.Task | None = None
    connected: bool = False
    last_seq_seen: int = 0
    joined_at: float = field(default_factory=time.time)
    is_bot: bool = False             # agent bridge participants
    # ---- bounded outbound queue ------------------------------------------- #
    # Every frame this connection is owed goes through `outbox` and one writer
    # task, never through the caller's `await`. See SessionManager._offer.
    outbox: asyncio.Queue | None = field(default=None, repr=False)
    sender: asyncio.Task | None = field(default=None, repr=False)
    sent: int = 0
    dropped_events: int = 0
    dropped_audio: int = 0
    send_slow: bool = False


@dataclass
class RtSession:
    session_id: str
    meeting_id: uuid.UUID
    org_id: uuid.UUID
    room_name: str
    mode: str                        # ws | livekit
    participants: dict[str, RtParticipant] = field(default_factory=dict)  # key=participant_id hex
    sequence: int = 0                # server event sequence
    replay_buffer: deque = field(default_factory=lambda: deque(maxlen=settings.rt_resume_buffer_size))
    created_at: float = field(default_factory=time.time)
    closed: bool = False
    pipeline: Any = None             # MeetingPipeline instance
    db_seq: int = 0                  # transcript seq counter (mirrored from DB)
    active_speakers: set[str] = field(default_factory=set)
    quality_degraded: bool = False
    # This room's audio window, resolved at connect by retention_service.policy_for.
    # None means no policy was read for this session, so the deployment default
    # still governs whether a turn's WAV is stored at all.
    retention_audio_days: int | None = None

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RtSession] = {}
        self._by_meeting: dict[uuid.UUID, str] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    async def create_session(self, meeting_id: uuid.UUID, org_id: uuid.UUID,
                             room_name: str, mode: str,
                             db_seq_start: int = 0,
                             retention_audio_days: int | None = None) -> RtSession:
        async with self._lock:
            existing = self._by_meeting.get(meeting_id)
            if existing and existing in self._sessions:
                return self._sessions[existing]
            session = RtSession(session_id=uuid.uuid4().hex, meeting_id=meeting_id,
                                org_id=org_id, room_name=room_name, mode=mode,
                                db_seq=db_seq_start,
                                retention_audio_days=retention_audio_days)
            self._sessions[session.session_id] = session
            self._by_meeting[meeting_id] = session.session_id
            met.ACTIVE_MEETINGS.inc()
            log.info("rt session %s created for meeting %s", session.session_id, meeting_id)
            return session

    def get_session(self, session_id: str) -> RtSession | None:
        return self._sessions.get(session_id)

    def get_session_for_meeting(self, meeting_id: uuid.UUID) -> RtSession | None:
        sid = self._by_meeting.get(meeting_id)
        return self._sessions.get(sid) if sid else None

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.closed = True
                self._by_meeting.pop(session.meeting_id, None)
                met.ACTIVE_MEETINGS.dec()
                for p in session.participants.values():
                    self._stop_sender(p)
                if session.pipeline:
                    await session.pipeline.shutdown()
                log.info("rt session %s closed", session_id)

    # ------------------------------------------------------------------ #
    # Participants & routing
    # ------------------------------------------------------------------ #
    def add_participant(self, session: RtSession, p: RtParticipant) -> None:
        previous = session.participants.get(str(p.participant_id))
        if previous is not None and previous is not p:
            # A reconnect builds a fresh participant for the same id. The object
            # being replaced still owns a writer task pointed at a socket nobody
            # will read from again.
            self._stop_sender(previous)
        else:
            met.ACTIVE_PARTICIPANTS.inc()
        session.participants[str(p.participant_id)] = p

    def remove_participant(self, session: RtSession, participant_id: uuid.UUID) -> None:
        key = str(participant_id)
        p = session.participants.pop(key, None)
        if p is not None:
            self._stop_sender(p)
            met.ACTIVE_PARTICIPANTS.dec()

    def attach_ws(self, session: RtSession, participant_id: uuid.UUID,
                  ws: WebSocket) -> tuple[RtParticipant | None, WebSocket | None]:
        p = session.participants.get(str(participant_id))
        old_ws = None
        if p:
            if p.connected and p.ws is not None and p.ws != ws:
                old_ws = p.ws
            if p.ws is not None and p.ws != ws:
                # A new socket is a new connection, not a continuation of the old
                # one: its writer and whatever that writer had not managed to push
                # out belong to a turn nobody will play.
                self._stop_sender(p)
            p.ws = ws
            p.connected = True
        return p, old_ws

    def detach_ws(self, session: RtSession, participant_id: uuid.UUID,
                  ws: WebSocket | None = None) -> None:
        p = session.participants.get(str(participant_id))
        if p:
            if ws is not None and p.ws != ws:
                return  # do not detach a newer superseded socket
            p.connected = False
            p.ws = None
            p.ws_task = None
            self._stop_sender(p)

    @staticmethod
    def _stop_sender(p: RtParticipant) -> None:
        """Drop the writer with the socket it was writing to.

        The backlog goes with it: frames for a dead connection are not
        replayable through a queue, and the resume buffer is what a reconnecting
        client reads.
        """
        if p.sender is not None and not p.sender.done():
            p.sender.cancel()
        p.sender = None
        p.outbox = None

    # ------------------------------------------------------------------ #
    # Outbound queue: one writer per connection, bounded backlog
    # ------------------------------------------------------------------ #
    def _outbox_for(self, session: RtSession, p: RtParticipant) -> asyncio.Queue:
        if p.outbox is None or p.sender is None or p.sender.done():
            p.outbox = asyncio.Queue(maxsize=max(1, settings.rt_send_queue_size))
            p.sender = asyncio.create_task(self._drain(session, p),
                                           name=f"rt-send-{p.participant_id}")
        return p.outbox

    def _offer(self, session: RtSession, p: RtParticipant, kind: str,
               payload) -> None:
        """Hand one frame to the connection's writer, without waiting for it.

        This is the whole of the backpressure decision, so it is worth stating
        plainly. `broadcast` used to `await ws.send_text(...)` for every
        listener in turn, which means the meeting's fan-out task — the one that
        produces captions and audio for *everyone* — was only as fast as the
        slowest browser in the room. A backgrounded tab stops reading its socket,
        the TCP window closes, and that one listener holds the pipeline.

        So the write is handed to a per-connection writer instead, and the
        backlog is bounded. When it is full the *oldest* queued frame is dropped,
        because a live meeting only has one useful direction: the frame a
        listener would receive 4 seconds late describes a turn they have already
        moved past, and the newest one describes the turn they are on. Nothing
        here pretends the drop is free — it is counted, and it is reported.
        """
        q = self._outbox_for(session, p)
        dropped: tuple[str, object] | None = None
        try:
            q.put_nowait((kind, payload))
        except asyncio.QueueFull:
            try:
                dropped = q.get_nowait()
            except asyncio.QueueEmpty:
                return  # the writer took it between the two calls
            try:
                q.put_nowait((kind, payload))
            except asyncio.QueueFull:
                return
        if dropped is not None:
            lost = dropped[0]
            if lost == "audio":
                p.dropped_audio += 1
            else:
                p.dropped_events += 1
            p.send_slow = True
            session.quality_degraded = True
            met.SEND_DROPPED.labels(kind=lost, reason="queue_full").inc()

    async def _drain(self, session: RtSession, p: RtParticipant) -> None:
        """The only task that writes to this participant's socket."""
        q = p.outbox
        assert q is not None
        while True:
            kind, payload = await q.get()
            ws = p.ws
            if ws is None:
                continue
            send = ws.send_bytes if kind == "audio" else ws.send_text
            try:
                # `asyncio.timeout` rather than `wait_for`: it bounds the write
                # without wrapping it in another task, so the frame is still
                # written by *this* task and a caller that yields once after
                # offering it can rely on it having been handed to the socket.
                async with asyncio.timeout(settings.rt_send_timeout_s):
                    await send(payload)
                p.sent += 1
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                met.SEND_DROPPED.labels(kind=kind, reason="send_timeout").inc()
                log.warning("closing %s: socket did not accept a frame in %.1fs "
                            "(queue was %d deep)", p.participant_id,
                            settings.rt_send_timeout_s, q.qsize())
                self._drop_connection(session, p, ws)
                return
            except Exception as e:
                log.debug("ws send failed to %s: %s", p.participant_id, e)
                self._drop_connection(session, p, ws)
                return

    def _drop_connection(self, session: RtSession, p: RtParticipant,
                         ws: WebSocket) -> None:
        """A socket that will not take a frame is not a slow listener, it is a
        dead one. Mark it as the receive loop would and let that loop run its
        own teardown — including the resume buffer this client will read when it
        reconnects.

        Deliberately not `detach_ws`: that cancels this task, and a task cannot
        cancel itself on its way out.
        """
        if p.ws is not ws:
            return
        p.connected = False
        p.ws = None
        p.send_slow = True

    def send_stats(self, session: RtSession) -> dict[str, Any]:
        """What the room's connections could not take.

        Health that cannot say "a listener lost frames" is how a meeting where
        half the room heard nothing gets reported as healthy.
        """
        return {
            "sent": sum(p.sent for p in session.participants.values()),
            "dropped_events": sum(p.dropped_events for p in session.participants.values()),
            "dropped_audio": sum(p.dropped_audio for p in session.participants.values()),
            "queued": sum(p.outbox.qsize() for p in session.participants.values()
                          if p.outbox is not None),
            "slow": [str(pid) for pid, p in session.participants.items()
                     if p.send_slow],
            "queue_size": max(1, settings.rt_send_queue_size),
        }


    def audio_listener(self, p: RtParticipant) -> bool:
        """Whether this participant is owed translated speech at all.

        One definition of "wants audio", shared by the fan-out below and by the
        stage health report: a captions-only room legitimately delivers no
        synthesized speech, and calling that broken is how a warning stops being
        read.
        """
        return p.connected and p.audio_mode in ("translated", "mixed")

    def listeners_for_language(self, session: RtSession, target_lang: str,
                               *, want_audio: bool) -> list[RtParticipant]:
        """Fan-out: participants whose hear_lang == target_lang.

        want_audio=True -> only translated/mixed modes.
        want_audio=False -> anyone with captions enabled (caption fan-out).
        """
        out = []
        for p in session.participants.values():
            if not p.connected or p.hear_lang != target_lang:
                continue
            if want_audio:
                if self.audio_listener(p):
                    out.append(p)
            else:
                if p.captions_enabled or p.audio_mode != "original":
                    out.append(p)
        return out

    def required_target_languages(self, session: RtSession,
                                  source_lang: str,
                                  exclude_speaker: str | None = None) -> set[str]:
        """Deduplicated target set: translate each language ONCE (PDD §13)."""
        langs: set[str] = set()
        for key, p in session.participants.items():
            if key == exclude_speaker:
                # speakers still get captions of their own speech? No —
                # they see their own source transcript; skip self-translation.
                continue
            if not p.connected:
                continue
            if p.hear_lang and p.hear_lang != source_lang:
                if p.audio_mode in ("translated", "mixed") or p.captions_enabled:
                    langs.add(p.hear_lang)
        return langs

    # ------------------------------------------------------------------ #
    # Event broadcast + replay buffer (reconnect resume, PDD §38)
    # ------------------------------------------------------------------ #
    async def broadcast(self, session: RtSession, event_type: str,
                        data: dict | None = None, *,
                        to: list[RtParticipant] | None = None,
                        speaker_id: str | None = None,
                        sequenced: bool = True) -> ServerEvent:
        seq = session.next_sequence() if sequenced else 0
        event = ServerEvent(
            type=event_type,
            session_id=session.session_id,
            conversation_id=str(session.meeting_id),
            speaker_id=speaker_id,
            sequence=seq,
            data=data or {},
        )
        payload = event.to_json()
        if sequenced:
            session.replay_buffer.append(payload)
        targets = to if to is not None else list(session.participants.values())
        for p in targets:
            if p.ws is None or not p.connected:
                continue
            self._offer(session, p, "event", payload)
        # One scheduling turn, so that a caller which awaits this — the fan-out
        # task, a test that asserts on what a listener received — sees the frames
        # it just handed off. It is a yield, not a wait: a writer that is blocked
        # on a stalled socket is not runnable, so this returns immediately and the
        # slow listener holds nobody up.
        await asyncio.sleep(0)
        return event

    async def send_to(self, p: RtParticipant, session: RtSession,
                      event_type: str, data: dict, *,
                      sequenced: bool = True) -> ServerEvent:
        return await self.broadcast(session, event_type, data, to=[p],
                                    sequenced=sequenced)

    def replay_since(self, session: RtSession, last_seq: int) -> list[str]:
        """Return buffered raw events with sequence > last_seq (dedupe-safe)."""
        out = []
        for raw in session.replay_buffer:
            try:
                import json
                ev = json.loads(raw)
                if ev.get("sequence", 0) > last_seq:
                    out.append(raw)
            except Exception:
                continue
        return out

    async def relay_audio(self, session: RtSession, from_pid, pcm: bytes) -> None:
        """Original-audio relay (WS transport): listeners in original/mixed
        mode hear the real speaker. Binary frame = [0x4F][16B shortId][PCM16].
        In LiveKit mode the SFU handles this and relay is skipped."""
        if session.mode == "livekit":
            return
        short_id = str(from_pid).replace("-", "")[:16].ljust(16, "\x00").encode("utf-8")
        payload = b"\x4f" + short_id + pcm
        for p in session.participants.values():
            if (p.connected and p.ws is not None and p.participant_id != from_pid
                    and p.audio_mode in ("original", "mixed")):
                self.send_audio(session, p, payload)
        await asyncio.sleep(0)

    def send_audio(self, session: RtSession, p: RtParticipant,
                   payload: bytes) -> None:
        """Queue one media frame for one listener.

        Both kinds of audio the room sends (relay of the speaker's own voice, and
        a synthesized chunk) go through the same writer as the JSON events, in the
        same queue, so the order the pipeline produced them in is the order the
        browser reads them — which is what its dedup registry keys on.
        """
        if p.ws is None or not p.connected:
            return
        self._offer(session, p, "audio", payload)

    def send_event(self, session: RtSession, p: RtParticipant, payload: str) -> None:
        """Queue one raw JSON frame for one listener.

        Direct socket writes from a *third* task — a signalling relay, say — race
        the connection's own writer, so anything addressed to a participant goes
        through their queue even when it is not a session broadcast.
        """
        if p.ws is None or not p.connected:
            return
        self._offer(session, p, "event", payload)


manager = SessionManager()
