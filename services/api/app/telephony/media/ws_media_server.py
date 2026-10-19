"""WS media server: the endpoint Asterisk's ``chan_websocket`` client dials.

Per the recorded P3 decision (``docs/ASTERISK_LOCAL_SIP_LAB.md`` §P3) the
backend runs the WebSocket media server and Asterisk connects OUT to it as a
``connection_type=client`` externalMedia channel (each media channel dials out
of a ``websocket-client`` config object). The transport itself was verified
from the lab build's channel-driver source:

- the FIRST TEXT message is Asterisk's ``MEDIA_START`` handshake carrying
  ``optimal_frame_size`` and ``ptime`` (authoritative frame layout);
- after that, binary messages are raw codec frames (no header) and further
  TEXT messages are driver events/acks;
- the backend may send TEXT commands (``ANSWER``, ``HANGUP``,
  buffer/marking controls) — always honoring this build's 128-byte cap —
  and binary audio chunks (arbitrary chunking is tolerated by Asterisk, but
  the backend paces at a clean ``ptime`` cadence).

Nothing here knows about Stasis/bridging; the caller wires hooks and drives
the ARI lifecycle (see :mod:`app.telephony.media.external_media`).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from websockets.asyncio.server import Server, ServerConnection, serve

from app.telephony.media.ws_media_protocol import (
    ControlMessage,
    FrameSlicer,
    MediaStart,
)

log = logging.getLogger("app.telephony.media")

#: Subprotocol Asterisk's ``websocket-client`` config uses for chan_websocket.
WS_MEDIA_SUBPROTOCOL = "media"

#: Compression would silently rewrite frames before slicing; audio wants raw
#: bytes so cadence and byte accounting stay exact. The receive buffer must
#: never truncate a burst — the slicer owns size accounting.
_SERVE_KWARGS: dict[str, Any] = {"compression": None, "max_size": 4 * 1024 * 1024}


@dataclass
class MediaConnectionHooks:
    """Per-connection callbacks. Each may be a coroutine function or plain fn.

    ``on_frames`` receives ALREADY-sliced ``optimal_frame_size`` chunks in
    order; ``on_control`` gets every non-``MEDIA_START`` TEXT event, parsed.
    """

    on_media_start: Callable[[MediaStart, "WSMediaConnection"], Any] | None = None
    on_control: Callable[[ControlMessage, "WSMediaConnection"], Any] | None = None
    on_frames: Callable[[list[bytes], "WSMediaConnection"], Any] | None = None
    on_closed: Callable[[str, "WSMediaConnection"], Any] | None = None


async def _invoke_hook(hook: Callable[..., Any] | None, *args: Any) -> None:
    if hook is None:
        return
    result = hook(*args)
    if asyncio.iscoroutine(result):
        await result


def _swallow_task_exception(task: asyncio.Task[None]) -> None:
    if task.done() and not task.cancelled():
        exc = task.exception()
        if exc:
            log.warning("ws media hook raised: %s", exc)


class WSMediaConnection:
    """One Asterisk↔backend media WebSocket session (server side)."""

    def __init__(self, raw: ServerConnection, hooks: MediaConnectionHooks) -> None:
        self._raw = raw
        self._hooks = hooks
        self._slicer: FrameSlicer | None = None
        self._bg_tasks: set[asyncio.Task[None]] = set()
        #: set on the first TEXT message; the authoritative frame layout.
        self.media_start: MediaStart | None = None
        #: populated when the receive loop exits (hook reason for the audit log).
        self.closed_reason: str | None = None

    @property
    def subprotocol(self) -> str | None:
        sub = getattr(self._raw, "subprotocol", None)
        return str(sub) if sub else None

    @property
    def frame_size(self) -> int | None:
        return self.media_start.optimal_frame_size if self.media_start else None

    # -- send side ----------------------------------------------------------- #

    async def send_text(self, text: str) -> None:
        await self._raw.send(text)

    def send_audio(self, data: bytes) -> Awaitable[Any]:
        """Raw audio send (frame-size unchecked). Pace with :class:`PacedAudioSender`."""
        return self._raw.send(bytes(data))

    # -- receive loop -------------------------------------------------------- #

    async def close(self, code: int = 1000, reason: str = "closed") -> None:
        await self._raw.close(code=code, reason=reason)

    async def run(self) -> None:
        try:
            async for message in self._raw:
                if isinstance(message, bytes):
                    await self._on_binary(message)
                else:
                    await self._on_text(str(message))
        except Exception as exc:  # noqa: BLE001 — reason is surfaced to the audit log
            self.closed_reason = f"error: {type(exc).__name__}: {exc}"
            log.warning("ws media connection errored: %s", self.closed_reason)
        else:
            self.closed_reason = "peer closed"
        await _invoke_hook(self._hooks.on_closed, self.closed_reason or "closed", self)

    async def _on_text(self, message: str) -> None:
        if self.media_start is None:
            self._accept_media_start(message)
            return
        await _invoke_hook(self._hooks.on_control, ControlMessage.parse(message), self)

    def _accept_media_start(self, message: str) -> None:
        try:
            start = MediaStart.from_control(ControlMessage.parse(message))
        except ValueError as exc:
            raise RuntimeError(
                f"first TEXT message was not a valid MEDIA_START: {exc}"
            ) from exc
        self.media_start = start
        self._slicer = FrameSlicer(start.optimal_frame_size)
        log.info(
            "MEDIA_START id=%s channel=%s format=%s frame=%dB ptime=%dms",
            start.connection_id,
            start.channel,
            start.channel_id,
            start.optimal_frame_size,
            start.ptime_ms,
        )
        self._schedule_hook(self._hooks.on_media_start, start, self)

    def _schedule_hook(self, hook: Callable[..., Any] | None, *args: Any) -> None:
        """Hooks spawned from the receive loop never block or kill audio flow."""
        background_tasks = self._bg_tasks
        task = asyncio.create_task(_invoke_hook(hook, *args))

        def _done(finished: asyncio.Task[None]) -> None:
            _swallow_task_exception(finished)
            background_tasks.discard(finished)

        task.add_done_callback(_done)
        background_tasks.add(task)

    async def _on_binary(self, message: bytes) -> None:
        if self._slicer is None:
            log.warning("binary frame before MEDIA_START; dropped %d bytes", len(message))
            return
        frames = self._slicer.feed(message)
        if frames:
            await _invoke_hook(self._hooks.on_frames, frames, self)


class WSMediaServer:
    """Bind a loopback WS endpoint (subprotocol ``media``) for chan_websocket dials.

    ``port=0`` selects an ephemeral port (tests); the resolved port is then
    available via :attr:`port`.
    """

    def __init__(self, hooks: MediaConnectionHooks) -> None:
        self._hooks = hooks
        self._server: Server | None = None
        #: live media connections (latest last) — reachable for tests + drivers
        self.connections: list[WSMediaConnection] = []

    @property
    def port(self) -> int:
        if not self._server or not self._server.sockets:
            raise RuntimeError("server not started")
        _, port = self._server.sockets[0].getsockname()[:2]
        return int(port)

    async def start(self, host: str = "127.0.0.1", port: int = 8787) -> int:
        self._server = await serve(
            self._handle,
            host=host,
            port=port,
            subprotocols=[WS_MEDIA_SUBPROTOCOL],
            **_SERVE_KWARGS,
        )
        return self.port

    async def _handle(self, raw: ServerConnection) -> None:
        connection = WSMediaConnection(raw, self._hooks)
        self.connections.append(connection)
        try:
            await connection.run()
        finally:
            with contextlib.suppress(ValueError):
                self.connections.remove(connection)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


class PacedAudioSender:
    """Drain a frame queue at a constant inter-send interval.

    Contract: each send is FOLLOWED by ``interval_seconds`` of sleep, so the
    wire cadence is a clean ptime stream. There is no burst catch-up on
    purpose — bursting 150×640 B frames into one socket message defeats the
    20 ms contract the bridge expects (loopback can deliver faster than the
    channel core drains).
    """

    def __init__(
        self,
        send: Callable[[bytes], Awaitable[Any]],
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._send = send
        self._interval = interval_seconds
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._stop = asyncio.Event()
        #: number of frames actually flushed to the wire
        self.sent_count = 0

    def enqueue(self, frame: bytes) -> None:
        self._queue.put_nowait(frame)

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        """Deadline-paced sends: cadence is driven by the interval, and send
        latency never accumulates (each deadline is absolute, not shifted)."""
        loop = asyncio.get_running_loop()
        next_deadline: float | None = None
        while not self._stop.is_set():
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=self._interval)
            except TimeoutError:
                if next_deadline is not None and loop.time() > next_deadline:
                    next_deadline = loop.time()  # queue is drained; reset phase
                continue
            if self._stop.is_set():
                break
            if next_deadline is not None:
                await asyncio.sleep(max(0.0, next_deadline - loop.time()))
            await self._send(frame)
            self.sent_count += 1
            now = loop.time()
            next_deadline = (next_deadline if next_deadline is not None else now) + self._interval
            if now - next_deadline > self._interval:  # we slipped a whole period
                next_deadline = now + self._interval
