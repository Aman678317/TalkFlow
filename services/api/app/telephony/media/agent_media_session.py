"""Bridge turn-loop runtime: externalMedia ↔ AgentGraph ↔ ``call_events``.

One :class:`AgentMediaSession` per *connected* AI-agent outbound call:

    caller PJSIP channel ─┐
                          ├─ mixing bridge ─ externalMedia(chan_websocket) ─ WS media server
    AgentMediaSession ────┘        (validated P3 topology, lab evidence §P3)
        └─ AgentTurnLoop (disclosure → verify → purpose → respond → end/escalate)
              └─ MediaCallEventSink → immutable call_events ledger

Lab-proven facts this module relies on (do not guess, see doc §P3):

- ``MEDIA_START`` carries the client-chosen media channel id
  (``talkflow-media-*``) — the deterministic correlation key between a WS
  connection and its session;
- teardown keeps bridge zero-frame flow until the media channel is deleted,
  after which Asterisk closes the WS itself ("peer closed") — so channels are
  deleted BEFORE the residual audit runs;
- outbound sends must be paced (``PacedAudioSender``), never burst.

Honest boundaries (unchanged from PR #71): no real STT/TTS is wired. Without
a recognizer the source yields one zero-confidence turn and the graph's OWN
``low_stt_confidence`` rule escalates — fail-closed by the existing guard,
not an invention here. Without a synthesizer, agent lines are decided,
guarded and persisted but no frames leave the backend. This module makes no
PSTN or human-audio claim; the whole runtime is default-off behind
``asterisk_media_enabled`` and attaches only to ``mode="ai_agent"`` calls.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from app.telephony.ai_agent_graph import GraphConfig, build_graph
from app.telephony.media.agent_turn_loop import (
    EVENT_OUTCOME,
    TERMINAL_FAILED,
    TERMINAL_STOPPED,
    AgentTurnLoop,
    TurnEventSink,
    TurnLoopOutcome,
    Utterance,
    safe_record,
)
from app.telephony.media.external_media import (
    ExternalMediaSession,
    ExternalMediaWebSocketOptions,
    MediaChannelInfo,
    MediaDirection,
)
from app.telephony.media.ws_media_protocol import (
    EVENT_MEDIA_XON,
    EVENT_MEDIA_XOFF,
    ControlMessage,
    MediaStart,
)
from app.telephony.media.ws_media_server import (
    MediaConnectionHooks,
    PacedAudioSender,
    WSMediaConnection,
    WSMediaServer,
)

log = logging.getLogger("app.telephony.media")


# --------------------------------------------------------------------------- #
# caller-side utterance collection
# --------------------------------------------------------------------------- #

#: Segmenter constants (16 kHz mono, 20 ms frames — lab mic audio is ~RMS 8500).
SILENCE_RMS_THRESHOLD = 900.0
MIN_SPEECH_FRAMES = 5        # 100 ms of audio above threshold starts a segment
MIN_SILENCE_FRAMES = 25      # 500 ms of trailing silence finalizes it
MAX_SEGMENT_FRAMES = 1000    # 20 s hard cap per segment (bounded memory)


class MediaUtteranceSource:
    """Caller turns from the WS audio stream (+ optional recognizer hook).

    Production default ships WITHOUT a recognizer: the first turn yields one
    honest empty utterance (confidence 0) so the graph fail-closes on its own
    ``low_stt_confidence`` rule, then ``None``. When a ``transcribe`` hook is
    configured (future STT wiring / lab drives), caller audio is segmented by
    simple RMS gating — silence-finalized, capped — and each segment goes to
    the hook; the hook owns any confidence it reports.
    """
    def __init__(
        self,
        *,
        gone: asyncio.Event,
        transcribe: Callable[[list[bytes]], Awaitable[Any]] | None = None,
        segment_wait_seconds: float = 2.0,
    ) -> None:
        self._gone = gone
        self._transcribe = transcribe
        self._segment_wait = max(0.05, segment_wait_seconds)
        self._frames_seen = 0
        self._emitted_unavailable = False
        self._last_was_empty = False
        # asynchronous face for the recognizer path:
        self._arrival = asyncio.Event()
        self._pending: list[tuple[bytes, float]] = []  # (frame, rms)
        self._speech_count = 0
        self._silence_count = 0
        self._buffer: list[bytes] = []

    # -- intake (called from the WS receive loop) --------------------------- #

    def feed_frames(self, frames: list[bytes]) -> None:
        self._frames_seen += len(frames)
        if self._transcribe is None:
            return  # no recognizer: frames are counted, never interpreted
        from app.telephony.media.ws_media_protocol import rms_linear16

        for frame in frames:
            try:
                level = rms_linear16(frame)
            except ValueError:
                level = SILENCE_RMS_THRESHOLD  # odd-length frame: ignore level
            self._pending.append((frame, level))
        self._arrival.set()

    # -- Awaitable UtteranceSource ------------------------------------------ #

    async def next_utterance(self) -> Utterance | None:
        if self._gone.is_set():
            return None
        if self._transcribe is None:
            # No recognizer wired: exactly one fail-closed turn, then done —
            # the graph escalates on its own low-confidence rule.
            if not self._emitted_unavailable:
                self._emitted_unavailable = True
                return Utterance(
                    text="", confidence=0.0, frame_count=self._frames_seen)
            return None

        while not self._gone.is_set():
            region = self._advance_segmenter()
            if region is not None:
                self._last_was_empty = False
                return await self._recognize(region)
            if self._last_was_empty:
                return None  # consecutive empty turns terminate, never loop
            wakeup = await self._wait_arrival_or_gone()
            if wakeup == "gone":
                return None
            if wakeup == "timeout":
                self._last_was_empty = True
                return Utterance(
                    text="", confidence=0.0, frame_count=self._frames_seen)
        return None

    async def _wait_arrival_or_gone(self) -> str:
        """Bounded wait for new audio / channel-gone / segment deadline.

        Return ``"arrival"`` | ``"gone"`` | ``"timeout"``.

        NOTE: deliberately implemented as a bounded poll instead of
        ``asyncio.wait({Event.wait() tasks})`` — that task-completion plumbing
        proved schedule-order fragile in this environment (a completion wakeup
        could be missed, blocking the turn until the full timeout). A small
        poll slice is deterministic, wakes on ``gone`` within one slice (stop
        interrupts are honored promptly) and costs nothing at utterance scale.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._segment_wait
        while True:
            if self._gone.is_set():
                return "gone"
            if self._arrival.is_set():
                self._arrival.clear()
                return "arrival"
            remaining = deadline - loop.time()
            if remaining <= 0:
                return "timeout"
            await asyncio.sleep(min(0.025, remaining))

    # -- segmenter internals ------------------------------------------------ #

    def _advance_segmenter(self) -> list[bytes] | None:
        """Consume pending frames; return a finalized segment when present."""
        while self._pending:
            frame, level = self._pending.pop(0)
            voiced = level >= SILENCE_RMS_THRESHOLD
            if self._buffer and len(self._buffer) >= MAX_SEGMENT_FRAMES:
                self._pending.clear()
                self._arrival.clear()
                return self._buffer
            if voiced:
                if not self._buffer:
                    self._speech_count = 0
                self._speech_count += 1
                self._silence_count = 0
                self._buffer.append(frame)
            elif self._buffer:
                self._silence_count += 1
                self._buffer.append(frame)
                if self._silence_count >= MIN_SILENCE_FRAMES:
                    segment = self._buffer
                    self._reset_segmenter()
                    return segment
        if self._buffer and self._speech_count >= MIN_SPEECH_FRAMES:
            return None  # segment in progress; keep collecting
        if self._buffer:
            # leading non-speech noise below the onset guard: drop it
            self._reset_segmenter()
        return None

    def _reset_segmenter(self) -> None:
        self._buffer = []
        self._speech_count = 0
        self._silence_count = 0

    async def _recognize(self, segment: list[bytes]) -> Utterance:
        assert self._transcribe is not None
        result = await self._transcribe(segment)
        if isinstance(result, Utterance):
            return result
        # plain text result: hook satisfied the words but not the protocol
        text = (result or "").strip() if isinstance(result, str) else ""
        return Utterance(
            text=text,
            confidence=1.0 if text else 0.0,
            frame_count=len(segment),
        )


# --------------------------------------------------------------------------- #
# agent speech → paced frames (or honest silence-free no-op)
# --------------------------------------------------------------------------- #


class PaceSpeaker:
    """SpeechRenderer implementation over the live ``WSMediaConnection``.

    With a ``synthesize`` hook: text → slin16 frames → :class:`PacedAudioSender`
    (one frame per absolute ptime deadline — the lab-validated cadence; never
    a burst). Without one: ``wired=False``, ``render`` returns 0 and the
    loop's audit records ``tts="absent"`` — the words exist, the audio doesn't.
    """

    def __init__(self, *, synthesize: Callable[[str], Awaitable[Any]] | None) -> None:
        self._synthesize = synthesize
        self._conn: WSMediaConnection | None = None
        self._pacer: PacedAudioSender | None = None
        self._pacer_task: asyncio.Task[None] | None = None

    @property
    def wired(self) -> bool:
        return self._synthesize is not None

    def attach(self, conn: WSMediaConnection, ptime_ms: int) -> None:
        if self._conn is not None:
            return
        self._conn = conn
        interval = max(0.005, (ptime_ms or 20) / 1000.0)
        self._pacer = PacedAudioSender(conn.send_audio, interval_seconds=interval)

    async def render(self, text: str) -> int:
        if not self._synthesize:
            return 0
        raw = await self._synthesize(text)
        frames = self._coerce_frames(raw)
        if not frames or self._pacer is None:
            return 0
        self._start_pacer()
        for frame in frames:
            self._pacer.enqueue(frame)
        return len(frames)

    @staticmethod
    def _coerce_frames(raw: Any) -> list[bytes]:
        """Tolerate ``bytes``/``list[bytes]`` synthesizer outputs."""
        if isinstance(raw, (bytes, bytearray)):
            return [bytes(raw)]
        return [bytes(f) for f in raw if f] if raw else []

    def _start_pacer(self) -> None:
        if self._pacer_task is None and self._pacer is not None and self._conn is not None:
            self._pacer_task = asyncio.create_task(self._pacer.run(),
                                                   name="agent-media-pacer")

    def stop(self) -> None:
        if self._pacer is not None:
            self._pacer.stop()
        self._pacer = None
        self._pacer_task = None

    # -- flow control passthrough (MEDIA_XOFF / MEDIA_XON, plan §P2) --------- #

    def pause(self) -> None:
        """Hold the outbound audio stream; the pacer keeps its queue order."""
        if self._pacer is not None:
            self._pacer.pause()

    def resume(self) -> None:
        """Resume the outbound stream at the ptime cadence (no catch-up)."""
        if self._pacer is not None:
            self._pacer.resume()


# --------------------------------------------------------------------------- #
# call_events persistence
# --------------------------------------------------------------------------- #


class MediaCallEventSink:
    """Persist turn/media events onto the call's immutable ``call_events`` ledger.

    Each record commits its own short session (no DB transaction ever spans a
    provider interaction). Caller speech is stored as a sha256 fingerprint
    only; agent-authored lines are stored verbatim (org content, audit value).
    """

    def __init__(self, call_sid: str) -> None:
        self._call_sid = call_sid
        self._call_id: uuid.UUID | None = None

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        from app.db.base import utcnow
        from app.db import models as M
        from app.db.session import db_session

        async with db_session() as db:
            if self._call_id is None:
                res = await db.execute(
                    select(M.CallSession.id)
                    .where(M.CallSession.call_sid == self._call_sid))
                self._call_id = res.scalars().first()
            if self._call_id is None:
                raise RuntimeError(
                    f"no CallSession row for sid {self._call_sid}")
            db.add(M.CallEvent(
                call_id=self._call_id,
                event_type=event_type[:64],
                payload_json=dict(payload),
                created_at=utcnow(),
            ))
            await db.commit()


# --------------------------------------------------------------------------- #
# one connected call
# --------------------------------------------------------------------------- #


@dataclass
class AgentMediaSpec:
    """Everything one agent media session needs; built by the runtime."""

    app_name: str
    external_host: str                 # websocket-client config object name
    media_format: str = "slin16"
    direction: str = "both"
    graph_config: GraphConfig | None = None
    transcribe: Callable[[list[bytes]], Awaitable[Any]] | None = None
    synthesize: Callable[[str], Awaitable[Any]] | None = None
    segment_wait_seconds: float = 2.0
    extras: dict[str, Any] = field(default_factory=dict)


class AgentMediaSession:
    """Assemble the ARI dialogue, run the turn loop, tear down with order.

    Lifecycle is driven from a single background task (``run_until_done``):
    start → turn loop → outcome event → teardown. ``request_stop`` is the
    operator/interrupt seam (§6: a stop ends the graph within the same turn).
    """

    def __init__(
        self,
        ari: Any,
        *,
        call_sid: str,
        caller_channel_id: str,
        spec: AgentMediaSpec,
        sink: TurnEventSink,
        registry: dict[str, "AgentMediaSession"],
    ) -> None:
        self.call_sid = call_sid
        self.caller_channel_id = caller_channel_id
        self._spec = spec
        self._sink = sink
        self._registry = registry
        self._gone = asyncio.Event()
        self._done = asyncio.Event()
        self._torn_down = False
        self.graph = build_graph(spec.graph_config)
        self.source = MediaUtteranceSource(
            gone=self._gone,
            transcribe=spec.transcribe,
            segment_wait_seconds=spec.segment_wait_seconds,
        )
        self.speaker = PaceSpeaker(synthesize=spec.synthesize)
        self.external = ExternalMediaSession(
            ari,
            ExternalMediaWebSocketOptions(
                app=spec.app_name,
                format=spec.media_format,
                external_host=spec.external_host,
                connection_type="client",
                direction=MediaDirection(spec.direction),
            ),
        )
        self.media_channel_id: str = self.external.channel_id
        self.bridge_id: str | None = None
        self.media_info: MediaChannelInfo | None = None
        self.media_start: MediaStart | None = None
        self.conn: WSMediaConnection | None = None
        self.frames_in = 0
        self.controls: dict[str, int] = {}
        self.ws_closed_reason: str | None = None
        self.outcome: TurnLoopOutcome | None = None
        #: monotonic timestamp of bridge membership — feeds media_bridge_left
        self._joined_at: float | None = None
        #: ``media_codec_negotiated`` is emitted once per session
        self._codec_negotiated_emitted = False
        self._codec_negotiated_task: asyncio.Task[None] | None = None

        self._loop: AgentTurnLoop | None = None
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle ---------------------------------------------------------- #

    def start_task(self) -> asyncio.Task[None]:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self.run_until_done(),
                name=f"agent-media-{self.call_sid}",
            )
        return self._task

    async def run_until_done(self) -> dict[str, Any]:
        try:
            return await self._lifecycle()
        except asyncio.CancelledError:
            outcome = TurnLoopOutcome(terminal=TERMINAL_STOPPED,
                                      summary="task cancelled")
            await asyncio.shield(self._teardown(outcome))
            raise
        except Exception:  # noqa: BLE001 — a failed session must still tear down
            log.exception("agent media session failed (call %s)", self.call_sid)
            await asyncio.shield(self._teardown(
                TurnLoopOutcome(terminal=TERMINAL_FAILED)))
            raise

    async def _lifecycle(self) -> dict[str, Any]:
        self.media_info = await self.external.create()
        self._registry[self.media_channel_id] = self
        self.bridge_id = await self.external.create_bridge()
        await self.external.add_channel_to_bridge(
            self.bridge_id, self.caller_channel_id)
        joined_members = [self.caller_channel_id]
        try:
            await self.external.add_channel_to_bridge(
                self.bridge_id, self.media_channel_id)
            joined_members.append(self.media_channel_id)
        except Exception:  # noqa: BLE001 — membership failure degrades audio, not the call
            log.exception(
                "media channel %s could not join bridge %s (call %s)",
                self.media_channel_id, self.bridge_id, self.call_sid)
        self._joined_at = time.monotonic()
        await safe_record(self._sink, "media_bridge_joined", {
            "leg_id": self.media_channel_id,
            "call_sid": self.call_sid,
            "codec": self._spec.media_format,
            "direction": self._spec.direction,
            "caller_channel_id": self.caller_channel_id,
            "media_channel_id": self.media_channel_id,
            "bridge_id": self.bridge_id,
            "members": joined_members,
        })
        await safe_record(self._sink, "agent_media_session_started", {
            "call_sid": self.call_sid,
            "caller_channel_id": self.caller_channel_id,
            "media_channel_id": self.media_channel_id,
            "bridge_id": self.bridge_id,
            "dialstring": self.media_info.dialstring,
        })

        self._loop = AgentTurnLoop(
            self.graph,
            source=self.source,
            renderer=self.speaker,
            events=self._sink,
        )
        outcome = await self._loop.run()
        self.outcome = outcome
        return await self._teardown(outcome)

    def request_stop(self, reason: str = "operator") -> None:
        """Stop interrupt: loop exits at the next boundary; teardown follows."""
        if self._loop is not None:
            self._loop.stop()
        self._gone.set()

    # -- WS-side callbacks (routed by the runtime) --------------------------- #

    def attach(self, conn: WSMediaConnection, media_start: MediaStart) -> None:
        if self.conn is not None:
            return
        self.conn = conn
        self.media_start = media_start
        self.speaker.attach(conn, media_start.ptime_ms)
        if not self._codec_negotiated_emitted:
            self._codec_negotiated_emitted = True
            self._codec_negotiated_task = asyncio.create_task(
                self._emit_codec_negotiated(media_start),
                name=f"codec-event-{self.call_sid}",
            )

    async def _emit_codec_negotiated(self, media_start: MediaStart) -> None:
        """Persist the wire-negotiated codec once (best-effort, ledger only)."""
        await safe_record(self._sink, "media_codec_negotiated", {
            "leg_id": self.media_channel_id,
            "call_sid": self.call_sid,
            "codec": media_start.format,
            "direction": self._spec.direction,
            "frame_size": media_start.optimal_frame_size,
            "ptime_ms": media_start.ptime_ms,
        })

    def route_frames(self, frames: list[bytes]) -> None:
        self.frames_in += len(frames)
        self.source.feed_frames(frames)

    def note_control(self, message: ControlMessage) -> None:
        key = message.event
        self.controls[key] = self.controls.get(key, 0) + 1
        # P2 flow control: Asterisk says who may send. XOFF holds the outbound
        # stream (queued frames keep order); XON resumes the ptime cadence.
        if key == EVENT_MEDIA_XOFF:
            self.speaker.pause()
        elif key == EVENT_MEDIA_XON:
            self.speaker.resume()

    def mark_closed(self, reason: str) -> None:
        self.ws_closed_reason = reason
        self._gone.set()
        self.speaker.stop()

    # -- leg loss / reconnect ------------------------------------------------- #

    async def handle_leg_loss(self, reason: str) -> None:
        """Called when the media leg is lost (WS closed, channel gone).

        Emits media_leg_lost, then attempts reconnect if the call is still active.
        """
        if self._torn_down:
            return
        log.warning("Media leg lost for call %s: %s", self.call_sid, reason)
        await safe_record(self._sink, "media_leg_lost", {
            "call_sid": self.call_sid,
            "media_channel_id": self.media_channel_id,
            "bridge_id": self.bridge_id,
            "reason": reason,
            "frames_before_loss": self.frames_in,
        })
        # Attempt reconnect only if call is still in progress (not torn down)
        if not self._torn_down and not self._gone.is_set():
            asyncio.create_task(self._attempt_reconnect())

    async def _attempt_reconnect(self) -> None:
        """Re-create media channel, re-bridge, and emit media_leg_restored."""
        try:
            log.info("Attempting media reconnect for call %s", self.call_sid)
            # Create new media channel
            self.media_info = await self.external.create()
            self.media_channel_id = self.external.channel_id
            self._registry[self.media_channel_id] = self

            # Re-bridge: add new media channel to existing bridge
            if self.bridge_id:
                await self.external.add_channel_to_bridge(
                    self.bridge_id, self.media_channel_id)
                joined_members = [self.media_channel_id]
                try:
                    # the caller is normally still a member — tolerate Asterisk
                    # rejecting a duplicate add (409) without failing reconnect
                    await self.external.add_channel_to_bridge(
                        self.bridge_id, self.caller_channel_id)
                    joined_members.append(self.caller_channel_id)
                except Exception:  # noqa: BLE001 — the caller leg already bridges
                    log.info(
                        "caller %s re-add skipped during reconnect (call %s)",
                        self.caller_channel_id, self.call_sid)
                await safe_record(self._sink, "media_bridge_joined", {
                    "leg_id": self.media_channel_id,
                    "call_sid": self.call_sid,
                    "codec": self._spec.media_format,
                    "direction": self._spec.direction,
                    "bridge_id": self.bridge_id,
                    "members": joined_members,
                    "reason": "rejoin",
                })

            await safe_record(self._sink, "media_leg_restored", {
                "call_sid": self.call_sid,
                "old_media_channel_id": self.media_channel_id,
                "new_media_channel_id": self.media_channel_id,
                "bridge_id": self.bridge_id,
                "codec": self.external.options.format,
                "gap_seconds": 0,  # could track actual gap if needed
            })
            log.info("Media leg restored for call %s (new channel %s)",
                     self.call_sid, self.media_channel_id)
        except Exception:  # noqa: BLE001
            log.exception("Media reconnect failed for call %s", self.call_sid)
            # Don't tear down the whole call — let the turn loop continue
            # with whatever media path remains (or none)

    # -- teardown (lab §P3 ordering: channels BEFORE the audit) -------------- #

    async def _teardown(self, outcome: TurnLoopOutcome) -> dict[str, Any]:
        if self._torn_down:
            return {}
        self._torn_down = True
        self.speaker.stop()
        try:
            audit = await self.external.teardown(
                bridge_id=self.bridge_id,
                peer_channel_id=self.caller_channel_id,
            )
        except Exception:  # noqa: BLE001 — teardown failures recorded, not fatal
            log.exception("agent media teardown failed (call %s)", self.call_sid)
            audit = {
                "media_channel_ids": [], "websocket_named_channels": [],
                "residual_zero": False, "error": "teardown_failed",
            }
        payload = {
            "call_sid": self.call_sid,
            "media_channel_id": self.media_channel_id,
            "bridge_id": self.bridge_id,
            "outcome": outcome.as_payload(),
            "frames_in": self.frames_in,
            "controls": dict(self.controls),
            "ws_closed_reason": self.ws_closed_reason,
            "residual": audit,
        }
        duration = (
            round(time.monotonic() - self._joined_at, 3)
            if self._joined_at is not None else 0.0
        )
        await safe_record(self._sink, "media_bridge_left", {
            "leg_id": self.media_channel_id,
            "call_sid": self.call_sid,
            "reason": outcome.terminal,
            "duration_seconds": duration,
            "bridge_id": self.bridge_id,
        })
        await safe_record(self._sink, "agent_media_session_ended", payload)
        self._registry.pop(self.media_channel_id, None)
        self._gone.set()
        self._done.set()
        return payload

    # -- typed accessors ------------------------------------------------------ #

    @property
    def finished(self) -> asyncio.Event:
        """Set when the session is FULLY torn down (events persisted too)."""
        return self._done


# --------------------------------------------------------------------------- #
# process-wide runtime
# --------------------------------------------------------------------------- #

ConnectedHook = Callable[[str, str], Awaitable[None]]


class AsteriskAgentMediaRuntime:
    """Hosts the WS media server + per-call agent sessions (one per process).

    ``main.py`` starts it when ``asterisk_media_enabled``; the ARI event
    consumer raises :meth:`on_call_connected` for CONNECTED events, which
    filters to eligible ``mode="ai_agent"`` calls and launches a session.
    """

    def __init__(
        self,
        ari: Any,
        *,
        bind_host: str,
        bind_port: int,
        spec_builder: Callable[[str, str], AgentMediaSpec] | None = None,
        sink_factory: Callable[[str], TurnEventSink] | None = None,
    ) -> None:
        self._ari = ari
        self._host = bind_host
        self._port = bind_port
        self._spec_builder = spec_builder or self.build_spec
        self._sink_factory = sink_factory or MediaCallEventSink
        self._registry_by_channel: dict[str, AgentMediaSession] = {}
        self.sessions_by_call: dict[str, AgentMediaSession] = {}
        self._conns: dict[int, AgentMediaSession] = {}  # id(conn) → session
        self._server: WSMediaServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @classmethod
    def from_settings(cls, *, provider: Any = None) -> "AsteriskAgentMediaRuntime":
        from app.config import settings
        from app.telephony.ari_client import ARIConfig, ARIClient

        ari = getattr(provider, "ari", None) or ARIClient(ARIConfig.from_settings())
        return cls(
            ari,
            bind_host=settings.asterisk_media_bind_host,
            bind_port=settings.asterisk_media_bind_port,
        )

    # -- server assembly ------------------------------------------------------ #

    async def start(self) -> int:
        self._server = WSMediaServer(MediaConnectionHooks(
            on_media_start=self._route_media_start,
            on_frames=self._route_frames,
            on_control=self._route_control,
            on_closed=self._route_closed,
        ))
        port = await self._server.start(self._host, self._port)
        log.info("agent media runtime UP on %s:%s (externalMedia client dials "
                 "the configured websocket-client object)", self._host, port)
        return port

    async def stop(self) -> None:
        for session in list(self.sessions_by_call.values()):
            session.request_stop("shutdown")
        if self._tasks:
            # Bounded poll instead of asyncio.wait: see the scheduling note on
            # MediaUtteranceSource._wait_arrival_or_gone — task-completion
            # wakeups must be allowed to arrive while stop() itself is parked.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 5.0
            while any(not t.done() for t in self._tasks):
                if loop.time() >= deadline:
                    break
                await asyncio.sleep(0.05)
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        for conn_id in list(self._conns):
            session = self._conns.pop(conn_id)
            session.mark_closed("shutdown")
        if self._server:
            await self._server.stop()
            self._server = None

    # -- eligibility + session launch ----------------------------------------- #

    def build_spec(self, call_sid: str, channel_id: str) -> AgentMediaSpec:
        from app.config import settings

        documents = tuple(sorted({
            doc.strip()
            for doc in settings.asterisk_agent_permitted_documents.split(",")
            if doc.strip()
        }))
        return AgentMediaSpec(
            app_name=settings.asterisk_ari_app_name,
            external_host=settings.asterisk_media_external_host,
            media_format="slin16",
            graph_config=GraphConfig(permitted_documents=documents),
            segment_wait_seconds=settings.asterisk_agent_segment_wait_seconds,
        )

    async def on_call_connected(self, call_sid: str, channel_id: str) -> None:
        """CONNECTED hook; never raises (a media failure must not break state)."""
        try:
            if not await self._is_eligible(call_sid):
                return
            self.start_for_call(call_sid, channel_id)
        except Exception:  # noqa: BLE001 — media attach never breaks call state
            log.exception("agent media attach failed for call %s", call_sid)

    async def _is_eligible(self, call_sid: str) -> bool:
        from app.db import models as M
        from app.db.session import db_session

        async with db_session() as db:
            res = await db.execute(
                select(M.CallSession.mode)
                .where(M.CallSession.call_sid == call_sid))
            row = res.first()
        return bool(row is not None and row[0] == "ai_agent")

    def start_for_call(self, call_sid: str, channel_id: str) -> AgentMediaSession:
        if call_sid in self.sessions_by_call:
            return self.sessions_by_call[call_sid]
        session = AgentMediaSession(
            self._ari,
            call_sid=call_sid,
            caller_channel_id=channel_id,
            spec=self._spec_builder(call_sid, channel_id),
            sink=self._sink_factory(call_sid),
            registry=self._registry_by_channel,
        )
        self.sessions_by_call[call_sid] = session
        task = session.start_task()

        def _finished(done: asyncio.Task[None]) -> None:
            self._tasks.discard(done)
            self._registry_by_channel.pop(session.media_channel_id, None)
            self.sessions_by_call.pop(session.call_sid, None)
            if done.done() and not done.cancelled():
                exc = done.exception()
                if exc:
                    log.warning("agent media session errored: %s", exc)

        task.add_done_callback(_finished)
        self._tasks.add(task)
        return session

    # -- WS hook routing ------------------------------------------------------- #

    async def _route_media_start(self, media_start: MediaStart,
                                 conn: WSMediaConnection) -> None:
        session = self._registry_by_channel.get(media_start.channel_id)
        if session is None:
            log.info("unmapped MEDIA_START for channel %s "
                     "(no live agent session)", media_start.channel_id)
            return
        session.attach(conn, media_start)
        self._conns[id(conn)] = session

    async def _route_frames(self, frames: list[bytes],
                            conn: WSMediaConnection) -> None:
        session = self._conns.get(id(conn))
        if session is not None:
            session.route_frames(frames)

    async def _route_control(self, message: ControlMessage,
                             conn: WSMediaConnection) -> None:
        session = self._conns.get(id(conn))
        if session is not None:
            session.note_control(message)

    async def _route_closed(self, reason: str, conn: WSMediaConnection) -> None:
        session = self._conns.pop(id(conn), None)
        if session is not None:
            session.mark_closed(reason)
            await session.handle_leg_loss(reason)
