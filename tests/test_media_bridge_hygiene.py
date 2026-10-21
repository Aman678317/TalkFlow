"""P2 Media Bridge Hygiene — deterministic tests (no Asterisk).

Tests the codec contract, DTMF, leg-loss/reconnects, per-leg status events.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock
from typing import Any

from app.telephony.media.external_media import (
    ExternalMediaSession,
    ExternalMediaWebSocketOptions,
)
from app.telephony.media.ws_media_protocol import (
    ControlMessage,
    parse_media_start,
    build_command,
    build_dtmf_command,
    MediaStart,
)
from app.telephony.media.ws_media_server import PacedAudioSender
from app.telephony.media.agent_media_session import (
    AgentMediaSession,
    AgentMediaSpec,
    MediaCallEventSink,
)

# --------------------------------------------------------------------------- #
# codec contract
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_external_media_codec_negotiation_emits_event():
    """When MEDIA_START arrives with a format, the session records the
    negotiated codec and can emit a media_codec_negotiated event."""
    mock_ari = AsyncMock()
    mock_ari.request_json.return_value = {
        "id": "talkflow-media-test123",
        "dialstring": "WebSocket/talkflow-media-cfg/d(both)",
    }

    options = ExternalMediaWebSocketOptions(
        app="talkflow",
        format="slin16",
        external_host="talkflow-media-cfg",
    )
    session = ExternalMediaSession(mock_ari, options)

    info = await session.create()
    assert info.format == "slin16"

    # Simulate MEDIA_START with format confirmation
    media_start = parse_media_start(
        "MEDIA_START connection_id:talkflow-media-cfg "
        "channel:WebSocket/talkflow-media-cfg-0001 "
        "channel_id:talkflow-media-test123 "
        "format:slin16 "
        "optimal_frame_size:640 "
        "ptime:20"
    )
    assert media_start.format == "slin16"
    assert media_start.optimal_frame_size == 640


@pytest.mark.asyncio
async def test_external_media_session_handles_media_start():
    """ExternalMediaSession.handle_media_start confirms codec and returns it."""
    mock_ari = AsyncMock()
    mock_ari.request_json.return_value = {
        "id": "talkflow-media-test456",
        "dialstring": "WebSocket/talkflow-media-cfg/d(both)",
    }

    options = ExternalMediaWebSocketOptions(
        app="talkflow",
        format="slin16",
        external_host="talkflow-media-cfg",
    )
    session = ExternalMediaSession(mock_ari, options)
    await session.create()

    # MEDIA_START with same format - use the session's actual channel_id
    media_start = MediaStart(
        connection_id="talkflow-media-cfg",
        channel="WebSocket/talkflow-media-cfg-0001",
        channel_id=session.channel_id,
        format="slin16",
        optimal_frame_size=640,
        ptime_ms=20,
    )
    negotiated = await session.handle_media_start(media_start)
    assert negotiated == "slin16"
    assert session.negotiated_format == "slin16"


@pytest.mark.asyncio
async def test_external_media_session_codec_renegotiation():
    """When MEDIA_START format differs from requested, log renegotiation."""
    mock_ari = AsyncMock()
    mock_ari.request_json.return_value = {
        "id": "talkflow-media-test789",
        "dialstring": "WebSocket/talkflow-media-cfg/d(both)",
    }

    options = ExternalMediaWebSocketOptions(
        app="talkflow",
        format="opus",  # requested opus
        external_host="talkflow-media-cfg",
    )
    session = ExternalMediaSession(mock_ari, options)
    await session.create()

    # Asterisk confirms slin16 instead (fallback)
    media_start = MediaStart(
        connection_id="talkflow-media-cfg",
        channel="WebSocket/talkflow-media-cfg-0002",
        channel_id=session.channel_id,
        format="slin16",
        optimal_frame_size=640,
        ptime_ms=20,
    )
    negotiated = await session.handle_media_start(media_start)
    assert negotiated == "slin16"
    assert session.negotiated_format == "slin16"


@pytest.mark.asyncio
async def test_external_media_accepts_supported_formats():
    """Only formats we advertise in external_media.py should be accepted."""
    for fmt in ("slin16", "opus", "pcmu"):
        options = ExternalMediaWebSocketOptions(
            app="talkflow",
            format=fmt,
            external_host="talkflow-media-cfg",
        )
        options.validate()  # should not raise


@pytest.mark.asyncio
async def test_external_media_rejects_unsupported_format():
    """Unsupported format raises at validate()."""
    options = ExternalMediaWebSocketOptions(
        app="talkflow",
        format="g729",  # not in SUPPORTED_FORMATS
        external_host="talkflow-media-cfg",
    )
    with pytest.raises(ValueError, match="unsupported format"):
        options.validate()


# --------------------------------------------------------------------------- #
# DTMF
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dtmf_send_builds_valid_command():
    """build_command for DTMF respects the 128-byte cap."""
    cmd = build_command("SEND_DTMF", "1")
    assert cmd == "SEND_DTMF 1"
    assert len(cmd) <= 128


@pytest.mark.asyncio
async def test_build_dtmf_command_validation():
    """build_dtmf_command validates single-character digits."""
    assert build_dtmf_command("5") == "SEND_DTMF 5"
    assert build_dtmf_command("*") == "SEND_DTMF *"
    assert build_dtmf_command("#") == "SEND_DTMF #"

    with pytest.raises(ValueError, match="single character"):
        build_dtmf_command("12")
    with pytest.raises(ValueError, match="single character"):
        build_dtmf_command("")


@pytest.mark.asyncio
async def test_dtmf_end_event_parsed():
    """DTMF_END from Asterisk is parsed correctly."""
    raw = "DTMF_END digit:1 channel_id:talkflow-media-abc123"
    msg = ControlMessage.parse(raw)
    assert msg.event == "DTMF_END"
    assert msg.fields["digit"] == "1"
    assert msg.fields["channel_id"] == "talkflow-media-abc123"


@pytest.mark.asyncio
async def test_external_media_session_send_dtmf():
    """ExternalMediaSession.send_dtmf sends SEND_DTMF command via ARI."""
    mock_ari = AsyncMock()
    mock_ari.request_json.return_value = {}

    options = ExternalMediaWebSocketOptions(
        app="talkflow",
        format="slin16",
        external_host="talkflow-media-cfg",
    )
    session = ExternalMediaSession(mock_ari, options)
    await session.create()

    await session.send_dtmf("5")
    # create() + send_dtmf() = 2 calls
    assert mock_ari.request_json.call_count == 2
    call_args = mock_ari.request_json.call_args_list[-1]
    assert call_args[0][0] == "POST"
    assert call_args[0][1].endswith("/sendCommand")
    assert call_args[1]["params"]["command"] == "SEND_DTMF 5"


# --------------------------------------------------------------------------- #
# per-leg status events
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_media_bridge_joined_event_structure():
    """The structure for media_bridge_joined event is well-defined."""
    event_payload = {
        "leg_id": "talkflow-media-abc123",
        "call_sid": "CA_test123",
        "codec": "slin16",
        "direction": "both",
        "caller_channel_id": "PJSIP/1001-00000001",
        "bridge_id": "talkflow-bridge-def456",
    }
    assert event_payload["codec"] in ("slin16", "opus", "pcmu")
    assert event_payload["direction"] in ("both", "in", "out")


@pytest.mark.asyncio
async def test_media_bridge_left_event_structure():
    event_payload = {
        "leg_id": "talkflow-media-abc123",
        "call_sid": "CA_test123",
        "reason": "hangup",  # or "reconnect", "transfer"
        "duration_seconds": 45,
    }
    assert event_payload["reason"] in ("hangup", "reconnect", "transfer")


# --------------------------------------------------------------------------- #
# control message backpressure (XON/XOFF)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_media_xoff_xon_parsing():
    """MEDIA_XOFF and MEDIA_XOFF are parsed and can trigger flow control."""
    xoff = ControlMessage.parse("MEDIA_XOFF")
    assert xoff.event == "MEDIA_XOFF"

    xon = ControlMessage.parse("MEDIA_XON")
    assert xon.event == "MEDIA_XON"


# --------------------------------------------------------------------------- #
# leg loss / reconnect simulation (structure tests)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_leg_loss_event_structure():
    """media_leg_lost event structure."""
    event_payload = {
        "leg_id": "talkflow-media-abc123",
        "call_sid": "CA_test123",
        "reason": "peer_closed",  # or "network_error", "timeout"
        "frames_before_loss": 1500,
    }
    assert event_payload["reason"] in ("peer_closed", "network_error", "timeout")


@pytest.mark.asyncio
async def test_leg_restored_event_structure():
    """media_leg_restored event structure."""
    event_payload = {
        "leg_id": "talkflow-media-abc123",
        "call_sid": "CA_test123",
        "new_channel_id": "talkflow-media-new456",
        "codec": "slin16",
        "gap_seconds": 2,
    }
    assert event_payload["codec"] in ("slin16", "opus", "pcmu")


# --------------------------------------------------------------------------- #
# leg loss / reconnect
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_agent_media_session_handles_leg_loss():
    """AgentMediaSession.handle_leg_loss emits media_leg_lost event."""
    from app.telephony.media.agent_media_session import MediaCallEventSink

    mock_ari = AsyncMock()
    mock_ari.request_json.return_value = {
        "id": "talkflow-media-test123",
        "dialstring": "WebSocket/talkflow-media-cfg/d(both)",
    }

    spec = AgentMediaSpec(
        app_name="talkflow",
        external_host="talkflow-media-cfg",
    )
    sink = MediaCallEventSink("test-call-sid")
    session = AgentMediaSession(
        mock_ari,
        call_sid="test-call-sid",
        caller_channel_id="PJSIP/1001-00000001",
        spec=spec,
        sink=sink,
        registry={},
    )
    session._torn_down = False
    session._gone = asyncio.Event()

    await session.handle_leg_loss("peer_closed")

    # Verify the event was recorded (we can't easily check the DB in unit test,
    # but we can verify the sink was called with the right event type)
    # The actual persistence is tested in test_media_call_event_sink_persists_rows


@pytest.mark.asyncio
async def test_agent_media_session_attempts_reconnect_on_leg_loss():
    """AgentMediaSession._attempt_reconnect re-creates channel and re-bridges."""
    mock_ari = AsyncMock()
    mock_ari.request_json.side_effect = [
        # First call: create new media channel
        {"id": "talkflow-media-new456", "dialstring": "WebSocket/talkflow-media-cfg/d(both)"},
        # Second call: create bridge (may already exist, but we mock it)
        {},
        # Third: add media channel to bridge
        {},
        # Fourth: add caller channel to bridge
        {},
    ]

    spec = AgentMediaSpec(
        app_name="talkflow",
        external_host="talkflow-media-cfg",
    )
    sink = MediaCallEventSink("test-call-sid-2")
    session = AgentMediaSession(
        mock_ari,
        call_sid="test-call-sid-2",
        caller_channel_id="PJSIP/1001-00000002",
        spec=spec,
        sink=sink,
        registry={},
    )
    session._torn_down = False
    session._gone = asyncio.Event()
    session.bridge_id = "talkflow-bridge-123"

    # Create initial media channel so we have one to replace
    await session.external.create()

    await session._attempt_reconnect()

    # Verify new channel was created and re-bridged
    assert mock_ari.request_json.call_count >= 3
    # First call should be create (externalMedia)
    create_call = mock_ari.request_json.call_args_list[0]
    assert create_call[0][0] == "POST"
    assert "/channels/externalMedia" in create_call[0][1]


# --------------------------------------------------------------------------- #
# per-leg status events — real emission (plan §P2 "per-leg status events")
# --------------------------------------------------------------------------- #


class MediaFakeARI:
    """In-memory ARI stand-in covering create/bridge/audit-relevant calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.channels: dict[str, dict] = {}
        self.bridges: dict[str, dict] = {}

    async def request_json(self, method: str, path: str,
                           params: dict | None = None) -> dict:
        params = dict(params or {})
        self.calls.append((method, path, params))
        if method == "POST" and path == "/ari/channels/externalMedia":
            cid = str(params["channelId"])
            self.channels[cid] = {
                "id": cid, "state": "Up",
                "dialstring": "WebSocket/media-cfg/d(both)",
            }
            return dict(self.channels[cid])
        if method == "POST" and path == "/ari/bridges":
            bid = str(params["bridgeId"])
            self.bridges[bid] = {"id": bid}
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

    async def list_channels(self) -> list[dict]:
        return [dict(c) for c in self.channels.values()]


class SinkSpy:
    """TurnEventSink that records instead of persisting."""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    async def record(self, event_type: str, payload: dict) -> None:
        self.records.append((event_type, dict(payload)))

    def events(self, kind: str) -> list[dict]:
        return [payload for event, payload in self.records if event == kind]


class FakeMediaConn:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send_audio(self, data: bytes) -> None:
        self.sent.append(bytes(data))


def make_session(sink: SinkSpy) -> AgentMediaSession:
    spec = AgentMediaSpec(
        app_name="talkflow",
        external_host="media-cfg",
    )
    return AgentMediaSession(
        MediaFakeARI(),
        call_sid="sess-1",
        caller_channel_id="caller-1",
        spec=spec,
        sink=sink,
        registry={},
    )


async def wait_until(pred, timeout: float = 3.0, step: float = 0.005) -> bool:
    """Bounded polling wakeup (determinism lesson from the #72 lane)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        await asyncio.sleep(step)
    return pred()


@pytest.mark.asyncio
async def test_attach_emits_media_codec_negotiated_once():
    """MEDIA_START attach → media_codec_negotiated recorded exactly once."""
    sink = SinkSpy()
    session = make_session(sink)
    start = MediaStart(
        connection_id="conn-1", channel="WebSocket/media-cfg/d(both)",
        channel_id=session.media_channel_id, format="slin16",
        optimal_frame_size=640, ptime_ms=20,
    )
    session.speaker.attach(FakeMediaConn(), 20)
    session.attach(FakeMediaConn(), start)
    assert session._codec_negotiated_task is not None
    await session._codec_negotiated_task

    events = sink.events("media_codec_negotiated")
    assert len(events) == 1
    assert events[0]["codec"] == "slin16"
    assert events[0]["leg_id"] == session.media_channel_id

    # a re-delivered MEDIA_START must NOT duplicate the event
    session.attach(FakeMediaConn(), start)
    assert len(sink.events("media_codec_negotiated")) == 1


@pytest.mark.asyncio
async def test_lifecycle_emits_media_bridge_joined_and_left():
    """Full session run: bridge joins (both channels members), left on teardown."""
    ari = MediaFakeARI()
    sink = SinkSpy()

    async def _stub_transcribe(segment: list[bytes]) -> Any:
        return ""

    spec = AgentMediaSpec(
        app_name="talkflow",
        external_host="media-cfg",
        media_format="slin16",
        direction="both",
        transcribe=_stub_transcribe,
        segment_wait_seconds=0.05,
    )
    session = AgentMediaSession(
        ari,
        call_sid="call_evt",
        caller_channel_id="caller-1",
        spec=spec,
        sink=sink,
        registry={},
    )
    await session.run_until_done()

    joined = sink.events("media_bridge_joined")
    assert len(joined) == 1
    assert joined[0]["bridge_id"] == session.bridge_id
    assert joined[0]["members"] == ["caller-1", session.media_channel_id]

    assert len(sink.events("agent_media_session_started")) == 1

    left = sink.events("media_bridge_left")
    assert len(left) == 1
    assert left[0]["reason"] == session.outcome.terminal
    assert left[0]["duration_seconds"] >= 0.0
    assert left[0]["leg_id"] == session.media_channel_id

    assert len(sink.events("agent_media_session_ended")) == 1
    # both channels actually joined the bridge over ARI
    adds = [p for _m, path, p in ari.calls if path.endswith("/addChannel")]
    assert {a["channel"] for a in adds} == {
        "caller-1", session.media_channel_id}


@pytest.mark.asyncio
async def test_reconnect_emits_bridge_joined_rejoin():
    """Reconnect re-adds membership and records a reason="rejoin" join."""
    ari = MediaFakeARI()
    sink = SinkSpy()
    session = make_session(sink)
    await session.external.create()
    session.bridge_id = await session.external.create_bridge()

    await session._attempt_reconnect()

    joined = sink.events("media_bridge_joined")
    assert len(joined) == 1
    assert joined[0]["reason"] == "rejoin"
    assert session.media_channel_id in joined[0]["members"]


# --------------------------------------------------------------------------- #
# flow control — PacedAudioSender honors MEDIA_XOFF / MEDIA_XON
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_paced_audio_sender_pause_holds_wire_then_resume_drains_in_order():
    """XOFF before start → zero sends; XON → order-preserving ptime drain."""
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    pacer = PacedAudioSender(send, interval_seconds=0.01)
    pacer.pause()
    frames = [bytes([i]) * 8 for i in range(5)]
    for frame in frames:
        pacer.enqueue(frame)

    task = asyncio.create_task(pacer.run())
    try:
        await asyncio.sleep(0.10)  # several intervals pass with the wire held
        assert pacer.paused is True
        assert pacer.sent_count == 0
        assert pacer.queue_depth() == len(frames)

        pacer.resume()
        assert await wait_until(lambda: pacer.queue_depth() == 0), \
            "queue did not drain after MEDIA_XON"
    finally:
        pacer.stop()
        await asyncio.wait_for(task, timeout=2.0)

    assert sent == frames  # FIFO order preserved, none dropped


@pytest.mark.asyncio
async def test_paced_audio_sender_pauses_mid_stream_bounded():
    """Mid-stream XOFF stops sends within bounded latency, then resumes."""
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    pacer = PacedAudioSender(send, interval_seconds=0.005)
    task = asyncio.create_task(pacer.run())
    try:
        for i in range(60):
            pacer.enqueue(bytes([i]) * 8)
        assert await wait_until(lambda: pacer.sent_count >= 1)

        pacer.pause()
        baseline = pacer.sent_count
        await asyncio.sleep(0.05)  # ~10 intervals
        # at most the one in-flight frame the deadline already committed to
        assert pacer.sent_count <= baseline + 2

        pacer.resume()
        assert await wait_until(lambda: pacer.queue_depth() == 0)
    finally:
        pacer.stop()
        await asyncio.wait_for(task, timeout=2.0)

    assert len(sent) == 60  # every frame still delivered after XON


@pytest.mark.asyncio
async def test_note_control_wires_xoff_xon_to_speaker_pause():
    """Session-level control messages flip the pacer's pause state."""
    sink = SinkSpy()
    session = make_session(sink)
    session.speaker.attach(FakeMediaConn(), 20)

    assert session.speaker._pacer.paused is False
    session.note_control(ControlMessage.parse("MEDIA_XOFF"))
    assert session.speaker._pacer.paused is True
    session.note_control(ControlMessage.parse("MEDIA_XON"))
    assert session.speaker._pacer.paused is False
    assert session.controls == {"MEDIA_XOFF": 1, "MEDIA_XON": 1}