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
    connected: bool = False
    last_seq_seen: int = 0
    joined_at: float = field(default_factory=time.time)
    is_bot: bool = False             # agent bridge participants


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
                             db_seq_start: int = 0) -> RtSession:
        async with self._lock:
            existing = self._by_meeting.get(meeting_id)
            if existing and existing in self._sessions:
                return self._sessions[existing]
            session = RtSession(session_id=uuid.uuid4().hex, meeting_id=meeting_id,
                                org_id=org_id, room_name=room_name, mode=mode,
                                db_seq=db_seq_start)
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
                if session.pipeline:
                    await session.pipeline.shutdown()
                log.info("rt session %s closed", session_id)

    # ------------------------------------------------------------------ #
    # Participants & routing
    # ------------------------------------------------------------------ #
    def add_participant(self, session: RtSession, p: RtParticipant) -> None:
        session.participants[str(p.participant_id)] = p
        met.ACTIVE_PARTICIPANTS.inc()

    def remove_participant(self, session: RtSession, participant_id: uuid.UUID) -> None:
        key = str(participant_id)
        if key in session.participants:
            session.participants.pop(key)
            met.ACTIVE_PARTICIPANTS.dec()

    def attach_ws(self, session: RtSession, participant_id: uuid.UUID,
                  ws: WebSocket) -> RtParticipant | None:
        p = session.participants.get(str(participant_id))
        if p:
            p.ws = ws
            p.connected = True
        return p

    def detach_ws(self, session: RtSession, participant_id: uuid.UUID) -> None:
        p = session.participants.get(str(participant_id))
        if p:
            p.connected = False
            p.ws = None

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
                if p.audio_mode in ("translated", "mixed"):
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
        disconnected = []
        for p in targets:
            if p.ws is None or not p.connected:
                continue
            try:
                await p.ws.send_text(payload)
            except Exception as e:
                log.debug("ws send failed to %s: %s", p.participant_id, e)
                p.connected = False
                disconnected.append(p)
        for p in disconnected:
            self.detach_ws(session, p.participant_id)
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
        mode hear the real speaker. Binary frame = [16B speaker uuid][PCM16].
        In LiveKit mode the SFU handles this and relay is skipped."""
        if session.mode == "livekit":
            return
        header = getattr(from_pid, "bytes", None)
        if header is None:
            return
        payload = header + pcm
        for p in session.participants.values():
            if (p.connected and p.ws is not None and p.participant_id != from_pid
                    and p.audio_mode in ("original", "mixed")):
                try:
                    await p.ws.send_bytes(payload)
                except Exception:
                    p.connected = False


manager = SessionManager()
