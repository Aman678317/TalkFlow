"""WS media server over real loopback sockets (server + client in-process).

The client side of the tests plays Asterisk exactly as the lab build's
``chan_websocket`` behaves: one TEXT ``MEDIA_START`` first, then raw binary
frames, further TEXT events, and 128-byte-cap-friendly commands.
"""
from __future__ import annotations

import asyncio
import contextlib
import time

import pytest
from websockets.asyncio.client import connect

from app.telephony.media.ws_media_protocol import ControlMessage, build_command
from app.telephony.media.ws_media_server import (
    MediaConnectionHooks,
    PacedAudioSender,
    WSMediaServer,
)

MEDIA_BEAT = 0.02  # 20 ms ptime — matches the real slin16 layout


def _media_start_text() -> str:
    return (
        "MEDIA_START connection_id:00000000-0000-0000-0000-000000000000 "
        "channel:WebSocket/pjsip-1001-00000001 channel_id:media-chan-1 "
        "format:slin16 optimal_frame_size:640 ptime:20"
    )


@contextlib.asynccontextmanager
async def running_server(frames: list, controls: list, closed: list):
    hooks = MediaConnectionHooks(
        on_frames=lambda received, _conn: frames.extend(received),
        on_control=lambda msg, _conn: controls.append(msg),
        on_closed=lambda reason, _conn: closed.append(reason),
    )
    server = WSMediaServer(hooks)
    port = await server.start(port=0)
    try:
        yield server, port
    finally:
        await server.stop()


async def dial_asterisk_like_client(port: int):
    """Connect with the same subprotocol the lab channels request."""
    return await connect(
        f"ws://127.0.0.1:{port}/",
        subprotocols=["media"],
        open_timeout=5,
        compression=None,
    )


async def test_server_binds_ephemeral_and_negotiates_media() -> None:
    frames: list[bytes] = []
    controls: list = []
    closed: list[str] = []
    async with running_server(frames, controls, closed) as (server, port):
        assert port > 0
        ws = await dial_asterisk_like_client(port)
        await asyncio.sleep(0.05)
        connection = server.connections[0]
        assert connection.subprotocol == "media"
        await ws.close()
        for _ in range(50):
            if closed:
                break
            await asyncio.sleep(0.01)
        assert closed == ["peer closed"]


async def test_media_start_then_frames_then_command_roundtrip() -> None:
    frames: list[bytes] = []
    controls: list[ControlMessage] = []
    closed: list[str] = []
    async with running_server(frames, controls, closed) as (_server, port):
        async with await dial_asterisk_like_client(port) as ws:
            await ws.send(_media_start_text())
            # one full frame split across two messages, then two full frames
            await ws.send(b"\x00" * 500)
            await ws.send(b"\x11" * 140 + b"\x22" * 640)
            await ws.send(b"\x33" * 640)
            # 500 + 780 + 640 raw bytes → exactly three 640-byte frames, no tail,
            # with the first frame split across two messages (leftover reassembly)
            expected_first = b"\x00" * 500 + b"\x11" * 140
            for _ in range(200):
                if len(frames) >= 3:
                    break
                await asyncio.sleep(0.01)
            assert frames == [expected_first, b"\x22" * 640, b"\x33" * 640]

            # backend → Asterisk: plain-text command honoring the 128-byte cap
            connection = _server.connections[0]
            await connection.send_text(build_command("ANSWER"))
            got = await asyncio.wait_for(ws.recv(), timeout=2)
            assert got == "ANSWER"
            # Asterisk → backend control event parsed into the hooks (async hook
            # dispatch — settle before asserting)
            await ws.send("GET_STATUS")
            for _ in range(50):
                if controls:
                    break
                await asyncio.sleep(0.01)
            assert any(msg.event == "GET_STATUS" for msg in controls)
    assert closed == ["peer closed"]


async def test_paced_sender_respects_interval() -> None:
    received: list[tuple[float, int]] = []

    async def send(frame: bytes) -> None:
        received.append((time.monotonic(), len(frame)))

    pacer = PacedAudioSender(send, interval_seconds=MEDIA_BEAT)
    pacer.enqueue(bytes(100))
    pacer.enqueue(bytes(100))
    pacer.enqueue(bytes(100))
    runner = asyncio.create_task(pacer.run())
    for _ in range(200):
        if pacer.sent_count >= 3:
            break
        await asyncio.sleep(0.005)
    pacer.stop()
    await asyncio.wait_for(runner, timeout=2)
    assert pacer.sent_count == 3
    deltas = [round(b[0] - a[0], 4) for a, b in zip(received, received[1:])]
    assert all(0.015 <= d <= 0.1 for d in deltas), deltas  # post-send sleep pacing

