"""Phase 4 — one slow listener must not slow the room down.

`SessionManager.broadcast` used to `await ws.send_text(...)` for every target in
turn, from the caller's task. That task is the meeting's fan-out — the one that
produces captions and translated audio for *everyone* — so a single browser tab
that stops reading its socket (backgrounded, throttled, on a train) held up every
other listener behind it, and held the pipeline behind them. Nothing bounded how
far behind a connection could fall, and nothing said so when it did.

These tests drive the real `SessionManager` with fake sockets whose writes the
test controls: a listener that never drains, one that errors mid-write, one that
takes ten seconds to accept a frame.

Evidence level: unit over the real session manager. Not a browser and not a
network — the closed TCP window is simulated by a write that does not return.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.config import settings
from app.realtime.protocol import ServerEventType
from app.realtime.session_manager import RtParticipant, manager


class _Socket:
    """A websocket the test decides how to answer with."""

    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.events: list[dict] = []
        self.frames: list[bytes] = []
        #: Both kinds in the order they were actually written, so interleaving
        #: can be asserted rather than inferred.
        self.journal: list[tuple[str, object]] = []
        self.gate = asyncio.Event()
        self.writes_started = 0

    async def send_text(self, payload: str) -> None:
        self.writes_started += 1
        if self.behaviour == "stall":
            await self.gate.wait()
        elif self.behaviour == "raise":
            raise RuntimeError("Broken pipe")
        self.events.append(json.loads(payload))
        self.journal.append(("event", json.loads(payload).get("data", {})))

    async def send_bytes(self, payload: bytes) -> None:
        self.writes_started += 1
        if self.behaviour == "stall":
            await self.gate.wait()
        self.frames.append(payload)
        self.journal.append(("audio", payload.decode()))


@pytest.fixture(autouse=True)
def _restore_send_settings():
    """These tests retune the queue on purpose; the next file must not inherit it."""
    size, deadline = settings.rt_send_queue_size, settings.rt_send_timeout_s
    yield
    settings.rt_send_queue_size = size
    settings.rt_send_timeout_s = deadline


async def _session(queue: int | None = None):
    meeting_id = uuid.uuid4()
    session = await manager.create_session(meeting_id, uuid.uuid4(),
                                          f"m-{meeting_id.hex[:6]}", "ws")
    if queue is not None:
        settings.rt_send_queue_size = queue
    return session


def _participant(sock: _Socket, *, mode: str = "translated",
                 hear: str = "en") -> RtParticipant:
    p = RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                      display_name="t", speak_lang="hi", hear_lang=hear,
                      audio_mode=mode, captions_enabled=True)
    p.ws = sock
    p.connected = True
    return p


async def _close(session) -> None:
    await manager.close_session(session.session_id)


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_listener_that_never_reads_does_not_hold_up_the_room():
    """The point of the whole change, stated as a timeout on the broadcast."""
    session = await _session()
    stuck_sock, quick_sock = _Socket("stall"), _Socket("ok")
    try:
        stuck = _participant(stuck_sock)
        quick = _participant(quick_sock)
        session.participants.update({str(stuck.participant_id): stuck,
                                     str(quick.participant_id): quick})

        for i in range(20):
            await asyncio.wait_for(
                manager.broadcast(session, ServerEventType.TRANSCRIPT_PARTIAL,
                                  {"text": f"turn {i}"}, to=[stuck, quick]), 0.5)

        assert [e["data"]["text"] for e in quick_sock.events] == [f"turn {i}"
                                                                  for i in range(20)], (
            "the healthy listener stopped getting the room because a stalled one "
            "was served first in the loop")
        assert stuck_sock.writes_started == 1, (
            "the fan-out was still being made to wait on the stalled socket")
        assert stuck.dropped_events == 0, (
            "20 frames into a 128-deep queue should not have dropped anything")
    finally:
        stuck_sock.gate.set()
        await _close(session)


@pytest.mark.asyncio
async def test_the_backlog_is_bounded_and_the_freshest_frame_wins():
    session = await _session(queue=4)
    try:
        sock = _Socket("stall")
        p = _participant(sock)
        session.participants[str(p.participant_id)] = p

        for i in range(50):
            manager.send_audio(session, p, f"frame-{i}".encode())

        assert p.outbox.qsize() == 4, (
            f"the backlog grew to {p.outbox.qsize()}: a stalled connection was "
            "an unbounded buffer rather than a bounded one")
        assert p.dropped_audio == 46
        assert p.send_slow and session.quality_degraded

        sock.gate.set()
        await asyncio.sleep(0.05)
        assert [f.decode() for f in sock.frames] == [f"frame-{i}" for i in range(46, 50)], (
            "a bounded queue must lose the *oldest* frames: a listener four "
            "seconds late is not served by being ten late")
    finally:
        await _close(session)


@pytest.mark.asyncio
async def test_an_arriving_caption_evicts_audio_not_another_caption():
    """The room can survive losing audio; it cannot survive losing the words.

    Media outruns captions on a stalled connection, so a full backlog is nearly
    always media — and head eviction then costs a stale frame rather than the
    caption that just arrived.
    """
    session = await _session(queue=3)
    try:
        sock = _Socket("stall")
        p = _participant(sock)
        session.participants[str(p.participant_id)] = p

        for i in range(3):
            manager.send_audio(session, p, f"old-{i}".encode())
        await manager.broadcast(session, ServerEventType.TRANSLATION_PARTIAL,
                                {"text": "the newest caption"}, to=[p])
        sock.gate.set()
        await asyncio.sleep(0.05)

        assert p.dropped_audio == 1 and p.dropped_events == 0
        assert [e["data"]["text"] for e in sock.events] == ["the newest caption"]
        assert [f.decode() for f in sock.frames] == ["old-1", "old-2"]
    finally:
        await _close(session)


@pytest.mark.asyncio
async def test_a_socket_that_errors_mid_write_is_treated_as_gone():
    session = await _session()
    try:
        sock = _Socket("raise")
        dead = _participant(sock)
        session.participants[str(dead.participant_id)] = dead

        await manager.broadcast(session, ServerEventType.TRANSCRIPT_FINAL,
                                {"text": "hi"}, to=[dead])
        await asyncio.sleep(0.05)

        assert dead.connected is False and dead.ws is None, (
            "a failed write left a dead socket attached, so every later turn "
            "paid for it again")
    finally:
        await _close(session)


@pytest.mark.asyncio
async def test_a_write_that_never_completes_gives_up_instead_of_freezing():
    """The queue bounds memory; only a deadline bounds the writer."""
    session = await _session()
    original = settings.rt_send_timeout_s
    settings.rt_send_timeout_s = 0.2
    try:
        sock = _Socket("stall")
        p = _participant(sock)
        session.participants[str(p.participant_id)] = p

        await manager.broadcast(session, ServerEventType.TRANSCRIPT_PARTIAL,
                                {"text": "one"}, to=[p])
        await asyncio.sleep(0.4)

        assert p.connected is False, (
            "the writer was still holding a socket that had not accepted a frame")
        assert p.sender is None or p.sender.done()
    finally:
        settings.rt_send_timeout_s = original
        sock.gate.set()
        await _close(session)


@pytest.mark.asyncio
async def test_events_and_audio_reach_the_browser_in_the_order_produced():
    """One queue, not two lanes: the `tts.chunk` JSON and its binary frame
    describe the same bytes, and the frontend's dedup registry assumes the pair
    arrives together and in order."""
    session = await _session()
    try:
        sock = _Socket("ok")
        p = _participant(sock)
        session.participants[str(p.participant_id)] = p

        for i in range(5):
            await manager.broadcast(session, ServerEventType.TTS_CHUNK,
                                    {"seq": i}, to=[p])
            manager.send_audio(session, p, f"audio-{i}".encode())
        await asyncio.sleep(0.05)

        expected = []
        for i in range(5):
            expected.append(("event", {"seq": i}))
            expected.append(("audio", f"audio-{i}"))
        assert sock.journal == expected, (
            f"delivery order changed: {sock.journal}")
        assert p.dropped_events == 0 and p.dropped_audio == 0
    finally:
        await _close(session)


@pytest.mark.asyncio
async def test_a_reconnect_starts_a_clean_queue_not_the_old_backlog():
    """The frames buffered for a dead socket describe a turn nobody will play."""
    session = await _session()
    try:
        old = _Socket("stall")
        p = _participant(old)
        session.participants[str(p.participant_id)] = p
        for i in range(6):
            manager.send_audio(session, p, f"a{i}".encode())
        first_task = p.sender

        manager.detach_ws(session, p.participant_id)
        fresh = _Socket("ok")
        p.ws, p.connected = fresh, True
        manager.send_audio(session, p, b"after-reconnect")
        await asyncio.sleep(0.05)

        assert first_task.cancelled(), "the old writer was left on the new socket"
        assert p.sender is not first_task
        assert fresh.frames == [b"after-reconnect"], (
            "the reconnected listener was handed the backlog of the dead one")
    finally:
        old.gate.set()
        await _close(session)


@pytest.mark.asyncio
async def test_a_reconnect_through_the_real_attach_path_leaves_no_writer():
    """`ws.py` builds a fresh participant object for the same id on reconnect.

    The object it replaces owns a writer task pointed at a socket nobody will
    read from again, and the gauge would count both — so replacing a participant
    has to stop the old one's writer, or every reconnect in a running meeting
    leaves a task and a backlog behind.
    """
    session = await _session()
    try:
        old_sock = _Socket("stall")
        first = _participant(old_sock)
        manager.add_participant(session, first)
        manager.attach_ws(session, first.participant_id, old_sock)
        for i in range(5):
            manager.send_audio(session, first, f"a{i}".encode())
        old_task = first.sender

        # Same participant id, new object and socket — what a reconnect does.
        fresh_sock = _Socket("ok")
        second = _participant(fresh_sock)
        second.participant_id = first.participant_id
        manager.add_participant(session, second)
        manager.attach_ws(session, second.participant_id, fresh_sock)
        manager.send_audio(session, second, b"after-reconnect")
        await asyncio.sleep(0.05)

        assert old_task.cancelled(), "the replaced participant's writer was leaked"
        assert fresh_sock.frames == [b"after-reconnect"], (
            "the new connection inherited the dead socket's backlog")
        assert second.dropped_audio == 0 and second.dropped_events == 0
    finally:
        old_sock.gate.set()
        await _close(session)


@pytest.mark.asyncio
async def test_losing_frames_is_said_by_the_meeting_health_of_the_room():
    """A stage that produced everything and delivered none of it is not healthy,
    and nothing else on the server would know."""
    session = await _session(queue=2)
    try:
        p = _participant(_Socket("stall"))
        session.participants[str(p.participant_id)] = p
        for i in range(10):
            manager.send_audio(session, p, f"a{i}".encode())

        stats = manager.send_stats(session)
        assert stats["dropped_audio"] == 8
        assert stats["queued"] == 2
        assert stats["slow"] == [str(p.participant_id)]
        assert stats["queue_size"] == 2
        assert stats["sent"] == 0
    finally:
        p.ws.gate.set()
        await _close(session)
