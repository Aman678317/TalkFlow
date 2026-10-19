"""Agent bridge turn-loop runtime — ARI assembly + WS routing + persistence.

Network-independent except where explicitly noted: the WS routing tests run a
real loopback ``WSMediaServer`` and connect the lab-Asterisk-shaped client
(TEXT ``MEDIA_START`` first, then raw frames — exactly like the §P3 spike).
ARI interactions go through an in-memory fake implementing the
``ExternalMediaSession`` surface.

Contracts verified here:
- the ARI request envelope is the validated one (websocket transport,
  encapsulation none, connection_type client, named websocket-client host,
  slin16, direction both, namespaced channel id);
- teardown is complete and ordered (channels deleted BEFORE the residual
  audit — lab §P3 finding) and surfaces ``residual_zero`` in the event;
- ``MEDIA_START`` correlates by the client-chosen media channel id; frames
  route into utterance collection; controls are counted;
- a session stopped while blocked terminates in bounded time;
- eligibility: only ``mode="ai_agent"`` CallSession rows get a session, and
  repeated CONNECTED deliveries resolve to ONE session;
- persistence writes ``call_events`` rows for a real CallSession (DB);
- without a recognizer the loop fail-closes (the graph's own rule) and the
  session itself hangs the caller up.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from websockets.asyncio.client import connect as ws_connect

from app.config import settings
from app.telephony.ai_agent_graph import GraphConfig
from app.telephony.media.agent_media_session import (
    AgentMediaSession,
    AgentMediaSpec,
    AsteriskAgentMediaRuntime,
    MediaCallEventSink,
    PaceSpeaker,
)


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #


class FakeARI:
    """In-memory stand-in for the ``ExternalMediaSession`` ARI surface."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.channels: dict[str, dict[str, Any]] = {}
        self.bridges: dict[str, dict[str, Any]] = {}

    async def request_json(self, method: str, path: str,
                           params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        self.calls.append((method, path, params))
        if method == "POST" and path == "/ari/channels/externalMedia":
            cid = str(params["channelId"])
            self.channels[cid] = {
                "id": cid, "state": "Up",
                "dialstring": (f"WebSocket/{params.get('external_host', '')}"
                               f"/d({params.get('direction', 'both')})"),
            }
            return dict(self.channels[cid])
        if method == "POST" and path == "/ari/bridges":
            bid = str(params["bridgeId"])
            self.bridges[bid] = {"id": bid, "type": params["type"]}
            return dict(self.bridges[bid])
        if method == "POST" and path.endswith("/addChannel"):
            return {"ok": True}
        if method == "DELETE" and path.startswith("/ari/channels/"):
            self.channels.pop(path.rsplit("/", 1)[1], None)
            return {}
        if method == "DELETE" and path.startswith("/ari/bridges/"):
            self.bridges.pop(path.rsplit("/", 1)[1], None)
            return {}
        raise AssertionError(f"unexpected ARI call {method} {path}")

    async def list_channels(self) -> list[dict[str, Any]]:
        return [dict(channel) for channel in self.channels.values()]

    def call_index(self, method: str, path: str) -> int:
        for index, (executed_method, executed_path, _p) in enumerate(self.calls):
            if (executed_method == method
                    and (executed_path == path
                         or executed_path.startswith(path))):
                return index
        return -1


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.records.append((event_type, dict(payload)))

    def events(self, kind: str) -> list[dict[str, Any]]:
        return [payload for event, payload in self.records if event == kind]


class FakeMediaConn:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send_audio(self, data: bytes) -> None:
        self.sent.append(bytes(data))


def make_spec(**overrides: Any) -> AgentMediaSpec:
    base: dict[str, Any] = dict(
        app_name="talkflow",
        external_host="media-cfg",
        media_format="slin16",
        graph_config=GraphConfig(verify_identity=True),
    )
    base.update(overrides)
    return AgentMediaSpec(**base)


async def _stub_transcribe(segment: list[bytes]) -> Any:
    return ""  # a wired hook with nothing behind it: the words stay empty


def media_start_text(channel_id: str) -> str:
    return (
        f"MEDIA_START connection_id:{uuid.uuid4()} "
        f"channel:WebSocket/media-cfg/d(both) channel_id:{channel_id} "
        f"format:slin16 optimal_frame_size:640 ptime:20"
    )


async def dial_asterisk_like_client(port: int):
    return await ws_connect(
        f"ws://127.0.0.1:{port}/", subprotocols=["media"],
        open_timeout=5, compression=None)


def make_runtime(ari: FakeARI, sink: RecordingSink,
                 *, spec_overrides: dict[str, Any] | None = None) -> AsteriskAgentMediaRuntime:
    def _spec(call_sid: str, channel_id: str) -> AgentMediaSpec:
        overrides = {"transcribe": _stub_transcribe,
                     "segment_wait_seconds": 30.0}
        overrides.update(spec_overrides or {})
        return make_spec(**overrides)

    return AsteriskAgentMediaRuntime(
        ari, bind_host="127.0.0.1", bind_port=0,
        spec_builder=_spec,
        sink_factory=lambda call_sid: sink)


# --------------------------------------------------------------------------- #
# ARI envelope + teardown (network-free)
# --------------------------------------------------------------------------- #


async def test_session_assembles_valid_envelope_and_tears_down_ordered() -> None:
    ari = FakeARI()
    sink = RecordingSink()
    session = AgentMediaSession(
        ari, call_sid="talkflow-abc", caller_channel_id="caller-1",
        spec=make_spec(), sink=sink, registry={})
    payload = await session.run_until_done()
    assert payload["outcome"]["terminal"] == "escalated"   # no recognizer wired
    assert payload["outcome"]["escalation_reason"] == "low_stt_confidence"

    method, path, envelope = ari.calls[0]
    envelope = dict(envelope)
    assert (method, path) == ("POST", "/ari/channels/externalMedia")
    assert envelope["transport"] == "websocket"
    assert envelope["encapsulation"] == "none"
    assert envelope["connection_type"] == "client"
    assert envelope["external_host"] == "media-cfg"
    assert envelope["app"] == "talkflow"
    assert envelope["format"] == "slin16"
    assert envelope["direction"] == "both"
    assert envelope["channelId"] == session.media_channel_id
    assert session.media_channel_id.startswith("talkflow-media-")

    bridge_calls = [call for call in ari.calls
                    if call[1] == "/ari/bridges" and call[0] == "POST"]
    assert len(bridge_calls) == 1
    assert bridge_calls[0][2]["type"] == "mixing"
    assert bridge_calls[0][2]["bridgeId"] == session.bridge_id
    add = [call for call in ari.calls if call[1].endswith("/addChannel")][0]
    assert add[2]["channel"] == "caller-1"

    # teardown ordering (lab §P3): channels deleted BEFORE the residual audit
    delete_bridge = ari.call_index("DELETE", "/ari/bridges/")
    delete_media = ari.call_index(
        "DELETE", f"/ari/channels/{session.media_channel_id}")
    delete_caller = ari.call_index("DELETE", "/ari/channels/caller-1")
    assert 0 <= delete_bridge < delete_media < delete_caller

    started = sink.events("agent_media_session_started")[0]
    assert started["caller_channel_id"] == "caller-1"
    assert started["dialstring"].startswith("WebSocket/media-cfg")
    ended = sink.events("agent_media_session_ended")[0]
    assert ended["outcome"]["terminal"] == "escalated"
    assert ended["residual"]["residual_zero"] is True
    assert ended["frames_in"] == 0
    assert ari.channels == {} and ari.bridges == {}


async def test_registry_is_clean_after_every_session_run() -> None:
    ari = FakeARI()
    registry: dict[str, AgentMediaSession] = {}
    session = AgentMediaSession(
        ari, call_sid="talkflow-xyz", caller_channel_id="caller-2",
        spec=make_spec(), sink=RecordingSink(), registry=registry)
    await session.run_until_done()
    assert registry == {}  # teardown pops itself: no session leakage


# --------------------------------------------------------------------------- #
# WS routing (real loopback server, Asterisk-shaped client)
# --------------------------------------------------------------------------- #


async def test_unmapped_media_start_is_not_attached() -> None:
    runtime = make_runtime(FakeARI(), RecordingSink(),
                           spec_overrides={"transcribe": None})
    port = await runtime.start()
    try:
        client = await dial_asterisk_like_client(port)
        await client.send(media_start_text("talkflow-media-unknown"))
        await asyncio.sleep(0.1)
        assert runtime._registry_by_channel == {}
        assert runtime._conns == {}
        await client.close()
    finally:
        await runtime.stop()


async def test_media_start_routes_frames_and_fail_closed_outcome() -> None:
    ari = FakeARI()
    sink = RecordingSink()
    runtime = make_runtime(ari, sink, spec_overrides={
        "transcribe": _stub_transcribe, "segment_wait_seconds": 0.15})
    port = await runtime.start()
    try:
        session = runtime.start_for_call("talkflow-call-1", "caller-9")
        channel_id = session.media_channel_id
        assert runtime.sessions_by_call["talkflow-call-1"] is session

        client = await dial_asterisk_like_client(port)
        await client.send(media_start_text(channel_id))
        for _ in range(100):
            if session.conn is not None:
                break
            await asyncio.sleep(0.01)
        assert session.conn is not None, "MEDIA_START never attached"
        assert session.media_start.optimal_frame_size == 640
        assert session.media_start.ptime_ms == 20

        # one control event + three silent frames: silent audio never becomes
        # a turn, so the bounded empty turn escalates (graph's own rule)
        await client.send("MEDIA_XON")
        await client.send(b"\x00" * 640 * 3)
        await asyncio.sleep(0.4)
        assert session.frames_in >= 3
        assert session.controls.get("MEDIA_XON") == 1

        await asyncio.wait_for(session.finished.wait(), timeout=10.0)
        assert session.outcome is not None
        assert session.outcome.terminal == "escalated"
        ended = sink.events("agent_media_session_ended")[0]
        assert ended["residual"]["residual_zero"] is True
        assert ari.call_index(
            "DELETE", f"/ari/channels/{channel_id}") >= 0
        assert ari.call_index("DELETE", "/ari/channels/caller-9") >= 0
        await client.close()
    finally:
        await runtime.stop()


async def test_request_stop_wakes_a_blocked_session_bounded() -> None:
    runtime = make_runtime(FakeARI(), RecordingSink())  # 30 s segment wait
    port = await runtime.start()
    try:
        session = runtime.start_for_call("talkflow-stop-1", "caller-s")
        await asyncio.sleep(0.05)  # lifecycle reached the blocked utterance
        started = asyncio.get_running_loop().time()
        session.request_stop("operator")
        await asyncio.wait_for(session.finished.wait(), timeout=2.0)
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 1.5  # the interrupt did NOT wait out the 30 s timeout
        assert session.outcome is not None
        assert session.outcome.terminal in ("stopped", "caller_gone")
    finally:
        await runtime.stop()


async def test_runtime_stop_reliably_finishes_lingering_sessions() -> None:
    ari = FakeARI()
    runtime = make_runtime(ari, RecordingSink())  # 30 s segment wait
    port = await runtime.start()
    session = runtime.start_for_call("talkflow-stop-live", "caller-live")
    await asyncio.sleep(0.05)
    await asyncio.wait_for(runtime.stop(), timeout=5.0)
    assert runtime._server is None
    assert session.finished.is_set()
    assert ari.call_index("DELETE", "/ari/channels/caller-live") >= 0


async def test_concurrent_connected_deliveries_resolve_one_session() -> None:
    runtime = make_runtime(FakeARI(), RecordingSink())
    port = await runtime.start()
    try:
        first = runtime.start_for_call("talkflow-dup", "caller-x")
        again = runtime.start_for_call("talkflow-dup", "caller-x")
        assert first is again
        assert len(runtime.sessions_by_call) == 1
        await asyncio.sleep(0.05)  # let lifecycle register the media channel
        assert len(runtime._registry_by_channel) == 1
    finally:
        await runtime.stop()


# --------------------------------------------------------------------------- #
# speak path
# --------------------------------------------------------------------------- #


async def test_pace_speaker_routes_synthesized_frames() -> None:
    conn = FakeMediaConn()

    async def synth(text: str) -> list[bytes]:
        return [b"\x11" * 640, b"\x22" * 640]

    speaker = PaceSpeaker(synthesize=synth)
    assert speaker.wired is True
    speaker.attach(conn, ptime_ms=20)
    rendered = await speaker.render("hello")
    assert rendered == 2
    for _ in range(100):
        if len(conn.sent) >= 2:
            break
        await asyncio.sleep(0.01)
    assert conn.sent == [b"\x11" * 640, b"\x22" * 640]
    speaker.stop()


async def test_pace_speaker_without_tts_records_honest_zero() -> None:
    speaker = PaceSpeaker(synthesize=None)
    assert speaker.wired is False
    assert await speaker.render("any words") == 0


# --------------------------------------------------------------------------- #
# persistence + eligibility (real DB, app fixtures)
# --------------------------------------------------------------------------- #


async def _create_call_session(org_id: str, user_id: str, sid: str,
                               mode: str) -> None:
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        db.add(M.CallSession(
            org_id=uuid.UUID(org_id),
            created_by=uuid.UUID(user_id),
            call_sid=sid,
            from_number="1001",
            to_number="1002",
            mode=mode,
            provider="asterisk",
            status="connected",
        ))
        await db.commit()


async def test_media_call_event_sink_persists_rows(services_app_client, user) -> None:
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session

    sid = f"talkflow-{uuid.uuid4()}"
    await _create_call_session(user["org_id"], user["user_id"], sid, "ai_agent")

    sink = MediaCallEventSink(sid)
    await sink.record("agent_turn_said", {"text": "disclosure line"})
    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession.id).where(M.CallSession.call_sid == sid))
        call_id = res.scalars().one()
        res = await db.execute(
            select(M.CallEvent).where(M.CallEvent.call_id == call_id))
        rows = list(res.scalars().all())
    assert len(rows) == 1
    assert rows[0].event_type == "agent_turn_said"
    assert rows[0].payload_json == {"text": "disclosure line"}


async def test_media_call_event_sink_requires_a_live_call_session() -> None:
    sink = MediaCallEventSink("talkflow-missing")
    with pytest.raises(RuntimeError):
        await sink.record("agent_turn_said", {})


async def test_eligibility_only_starts_ai_agent_calls(services_app_client, user) -> None:
    sid = f"talkflow-{uuid.uuid4()}"
    await _create_call_session(user["org_id"], user["user_id"], sid, "human_dial")
    ari = FakeARI()
    runtime = make_runtime(ari, RecordingSink())
    port = await runtime.start()
    try:
        await runtime.on_call_connected(sid, "caller-h")  # human_dial: ignored
        assert runtime.sessions_by_call == {}
        assert ari.calls == []

        from sqlalchemy import update

        from app.db import models as M
        from app.db.session import db_session
        async with db_session() as db:
            await db.execute(update(M.CallSession)
                             .where(M.CallSession.call_sid == sid)
                             .values(mode="ai_agent"))
            await db.commit()

        await runtime.on_call_connected(sid, "caller-ai")
        assert list(runtime.sessions_by_call) == [sid]
        session = runtime.sessions_by_call[sid]
        assert session.caller_channel_id == "caller-ai"
        for _ in range(100):
            if ari.calls:
                break
            await asyncio.sleep(0.01)
        method, path, envelope = ari.calls[0]
        assert (method, path) == ("POST", "/ari/channels/externalMedia")
        # The runtime dials with ITS spec (fixture values here); the product
        # settings → spec mapping is pinned separately in
        # test_build_spec_uses_settings.
        assert envelope["external_host"] == "media-cfg"
        assert envelope["app"] == "talkflow"
        assert session.media_channel_id.startswith("talkflow-media-")
    finally:
        await runtime.stop()


def test_build_spec_uses_settings() -> None:
    """Product path: the default spec_builder maps settings into the spec."""
    from app.config import settings

    runtime = AsteriskAgentMediaRuntime(
        FakeARI(), bind_host="127.0.0.1", bind_port=0)
    saved = (settings.asterisk_media_external_host,
             settings.asterisk_ari_app_name,
             settings.asterisk_agent_permitted_documents,
             settings.asterisk_agent_segment_wait_seconds)
    try:
        settings.asterisk_media_external_host = "spec-cfg"
        settings.asterisk_ari_app_name = "spec-app"
        settings.asterisk_agent_permitted_documents = "doc-b, doc-a ,,doc-c"
        settings.asterisk_agent_segment_wait_seconds = 1.5
        spec = runtime.build_spec(f"talkflow-{uuid.uuid4()}", "chan-1")
    finally:
        (settings.asterisk_media_external_host,
         settings.asterisk_ari_app_name,
         settings.asterisk_agent_permitted_documents,
         settings.asterisk_agent_segment_wait_seconds) = saved
    assert spec.external_host == "spec-cfg"
    assert spec.app_name == "spec-app"
    assert spec.graph_config.permitted_documents == ("doc-a", "doc-b", "doc-c")
    assert spec.segment_wait_seconds == 1.5
    assert spec.media_format == "slin16"
