"""MeetingSession hub — conversation state, participant routing table, sequence assignment,
event ring buffer for reconnect/resume, same-target translation dedup cache (section 88).

State ownership: the hub (deterministic infrastructure) owns timing, sequences, routing and
source-of-truth. AI providers never mutate hub state directly — they return results that the
hub validates and records. The canonical human source (transcript finals) is immutable once
persisted.
"""
from __future__ import annotations

import asyncio
import base64
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from globaltalk.core.logging import get_logger
from globaltalk.realtime.protocol import EventType, make_event

log = get_logger("realtime")

EVENT_BUFFER_SIZE = 2000


@dataclass
class ParticipantConn:
    participant_id: str
    identity: str
    display_name: str
    ws: WebSocket
    speaking_language: str = "AUTO"
    listening_language: str = "en"
    audio_mode: str = "translated"          # original | translated | mixed
    caption_mode: str = "both"              # original | translated | both
    latency_mode: str = "balanced"
    connected: bool = True
    last_sequence: int = 0
    audio_active: bool = False
    joined_at: float = field(default_factory=time.time)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def short(self) -> str:
        return self.participant_id[:8]


@dataclass
class MeetingSession:
    meeting_id: str
    room_name: str
    org_id: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    participants: dict[str, ParticipantConn] = field(default_factory=dict)
    _sequence: int = 0
    _events: deque = field(default_factory=lambda: deque(maxlen=EVENT_BUFFER_SIZE))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    translation_cache: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    pipelines: dict[str, Any] = field(default_factory=dict)  # participant_id -> AudioPipeline

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def record(self, event_type: str, persist: bool = True, **payload) -> dict[str, Any]:
        evt = make_event(event_type, session_id=self.session_id,
                         conversation_id=self.meeting_id,
                         sequence=self.next_sequence(), **payload)
        if persist:
            self._events.append(evt)
        return evt

    def events_after(self, sequence: int) -> list[dict[str, Any]]:
        return [e for e in self._events if (e.get("sequence") or 0) > sequence]

    def listeners_for_language(self, language: str, *, want_audio: bool = False,
                               exclude: str | None = None) -> list[ParticipantConn]:
        out = []
        for p in self.participants.values():
            if not p.connected or p.participant_id == exclude:
                continue
            if p.listening_language != language:
                continue
            if want_audio and p.audio_mode not in ("translated", "mixed"):
                continue
            out.append(p)
        return out

    def required_target_languages(self, source_language: str, exclude: str | None = None,
                                  need_audio: bool = False) -> set[str]:
        langs = set()
        for p in self.participants.values():
            if not p.connected or p.participant_id == exclude:
                continue
            if p.listening_language == source_language:
                continue  # understands the source natively
            if need_audio and p.audio_mode not in ("translated", "mixed") \
                    and p.caption_mode == "original":
                continue
            langs.add(p.listening_language)
        return langs

    async def send(self, p: ParticipantConn, evt: dict[str, Any]) -> None:
        try:
            async with p.send_lock:
                await p.ws.send_json(evt)
            p.last_sequence = evt.get("sequence") or p.last_sequence
        except Exception:
            p.connected = False

    async def send_binary(self, p: ParticipantConn, data: bytes) -> None:
        try:
            async with p.send_lock:
                await p.ws.send_bytes(data)
        except Exception:
            p.connected = False

    async def broadcast(self, evt: dict[str, Any], *, only: list[ParticipantConn] | None = None,
                        exclude: str | None = None) -> None:
        targets = only if only is not None else list(self.participants.values())
        await asyncio.gather(*(
            self.send(p, evt) for p in targets
            if p.connected and p.participant_id != exclude), return_exceptions=True)

    def translation_cache_key(self, source_segment_id: str, target_language: str) -> tuple[str, str]:
        return (source_segment_id, target_language)


class Hub:
    """Process-wide registry of live meeting sessions. Redis pub/sub (prod) lets multiple
    API nodes share fan-out; on a single node the in-process hub is authoritative."""

    def __init__(self) -> None:
        self._sessions: dict[str, MeetingSession] = {}
        self._lock = threading.Lock()

    def get(self, meeting_id: str) -> MeetingSession | None:
        return self._sessions.get(meeting_id)

    def get_or_create(self, meeting_id: str, room_name: str, org_id: str) -> MeetingSession:
        with self._lock:
            s = self._sessions.get(meeting_id)
            if s is None:
                s = MeetingSession(meeting_id=meeting_id, room_name=room_name, org_id=org_id)
                self._sessions[meeting_id] = s
                log.info("meeting_session_created", extra={"meeting_id": meeting_id})
            return s

    def drop_if_empty(self, meeting_id: str) -> None:
        with self._lock:
            s = self._sessions.get(meeting_id)
            if s and not any(p.connected for p in s.participants.values()):
                for pipe in list(s.pipelines.values()):
                    try:
                        pipe.shutdown()
                    except Exception:
                        pass
                del self._sessions[meeting_id]
                log.info("meeting_session_closed", extra={"meeting_id": meeting_id})

    def active_meetings(self) -> int:
        return len(self._sessions)

    def active_participants(self) -> int:
        return sum(1 for s in self._sessions.values() for p in s.participants.values()
                   if p.connected)


hub = Hub()


def audio_b64(wav_bytes: bytes) -> str:
    return base64.b64encode(wav_bytes).decode()


# --------------------------------------------------------------------------- tasks
# asyncio only keeps WEAK references to tasks — fire-and-forget tasks can be garbage
# collected mid-await. All background tasks in the realtime plane are registered here.
_bg_tasks: set = set()


def spawn(coro, *, name: str = "") -> asyncio.Task:
    task = asyncio.create_task(coro, name=name or None)
    _bg_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _bg_tasks.discard(t)
        if not t.cancelled() and t.exception():
            log.error("background_task_failed",
                      extra={"task": name or t.get_name(),
                             "error": f"{type(t.exception()).__name__}: {t.exception()}"})

    task.add_done_callback(_done)
    return task
