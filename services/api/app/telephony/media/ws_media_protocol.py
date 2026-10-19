"""Media-over-WebSocket protocol codec for Asterisk ``chan_websocket`` (pure).

This encodes the Media-over-WebSocket channel-protocol facts verified against
the actual channel-driver source of the lab build (Asterisk 22.11.0,
``channels/chan_websocket.c``) and the ARI dispatcher that creates such
channels (``res/ari/resource_channels.c``). Nothing here performs I/O: the
network entry point lives in :mod:`app.telephony.media.ws_media_server` and
the request assembly lives in :mod:`app.telephony.media.external_media`.

Wire facts (do not guess, these are read from the driver source):

- Binary WebSocket frames carry the RAW codec payload — no framing header,
  no length prefix. Asterisk re-chunks whatever it receives into
  ``optimal_frame_size`` frames (_leftover data between binary messages is
  preserved_, see ``process_binary_message``); well-behaved senders send one
  ``optimal_frame_size`` chunk per 20 ms.
- The frame size for a format comes from Asterisk itself in the first TEXT
  control message (``MEDIA_START``): ``optimal_frame_size`` +
  ``ptime``. For ``slin16`` (2 bytes/sample at 16 kHz) the driver's default
  is 20 ms * 320 B/ms = 640 bytes, but the value received on the wire is
  authoritative and validated here.
- Control traffic is TEXT frames, both directions, capped at 128 bytes
  (``MAX_TEXT_MESSAGE_LEN``) by this driver build — commands must stay terse.
- Plain-text is the default control format (``chan_websocket.conf`` global
  ``control_msg_format``); a per-dial JSON format also exists. ``MEDIA_START``
  plain-text layout is exactly::

    MEDIA_START connection_id:<id> channel:<name> channel_id:<uniqueid> format:<fmt> optimal_frame_size:<n> ptime:<n>

- ``direction`` (``d(both|in|out)``) is from the *backend's* perspective:
  ``in`` = backend only receives audio, ``out`` = backend only sends,
  ``both`` (default) = full duplex. Buffering/marking commands are refused
  by Asterisk while direction is ``in`` (no backend→PBX path exists).
- The app may command the channel: ``ANSWER``, ``HANGUP``,
  ``START_MEDIA_BUFFERING``, ``STOP_MEDIA_BUFFERING <id>``,
  ``MARK_MEDIA <id>``, ``FLUSH_MEDIA``, ``REPORT_QUEUE_DRAINED``,
  ``GET_STATUS``, ``PAUSE_MEDIA``, ``CONTINUE_MEDIA`` (and the JSON-only
  ``SET_MEDIA_DIRECTION``). Asterisk reports ``MEDIA_START``, ``MEDIA_XON`` /
  ``MEDIA_XOFF`` (queue backpressure at 800/900 of 1000 frames),
  ``QUEUE_DRAINED``, ``MEDIA_BUFFERING_COMPLETED``, ``MEDIA_MARK_PROCESSED``,
  ``DTMF_END digit:<c> channel_id:<id>``, ``STATUS`` and ``ERROR``.
- An externalMedia websocket channel originated with ``connection_type=client``
  makes Asterisk dial the backend's WS server (a ``websocket-client``
  config object); a channel originally with ``connection_type=server`` binds
  to a backend connection that dial's INTO Asterisk's own WS server using the
  special ``INCOMING`` connection id.
"""
from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

# --------------------------------------------------------------------------- #
# constants (driver build facts)
# --------------------------------------------------------------------------- #

#: Channel technology name used in the externalMedia dialstring.
WS_CHANNEL_TECH = "WebSocket"

#: Special connection id meaning "bind to a backend-dialed incoming WS".
INCOMING_CONNECTION_ID = "INCOMING"

#: chan_websocket caps every TEXT control message at this length (this build).
MAX_CONTROL_MESSAGE_BYTES = 128

#: Channel send queue bound + backpressure thresholds (driver constants).
QUEUE_LENGTH_MAX = 1000
QUEUE_LENGTH_XOFF_LEVEL = 900
QUEUE_LENGTH_XON_LEVEL = 800

EVENT_MEDIA_START = "MEDIA_START"
EVENT_MEDIA_XON = "MEDIA_XON"
EVENT_MEDIA_XOFF = "MEDIA_XOFF"
EVENT_QUEUE_DRAINED = "QUEUE_DRAINED"
EVENT_MEDIA_BUFFERING_COMPLETED = "MEDIA_BUFFERING_COMPLETED"
EVENT_MEDIA_MARK_PROCESSED = "MEDIA_MARK_PROCESSED"
EVENT_DTMF_END = "DTMF_END"
EVENT_STATUS = "STATUS"
EVENT_ERROR = "ERROR"

COMMAND_ANSWER = "ANSWER"
COMMAND_HANGUP = "HANGUP"
COMMAND_START_MEDIA_BUFFERING = "START_MEDIA_BUFFERING"
COMMAND_STOP_MEDIA_BUFFERING = "STOP_MEDIA_BUFFERING"
COMMAND_MARK_MEDIA = "MARK_MEDIA"
COMMAND_FLUSH_MEDIA = "FLUSH_MEDIA"
COMMAND_GET_STATUS = "GET_STATUS"
COMMAND_REPORT_QUEUE_DRAINED = "REPORT_QUEUE_DRAINED"
COMMAND_PAUSE_MEDIA = "PAUSE_MEDIA"
COMMAND_CONTINUE_MEDIA = "CONTINUE_MEDIA"
COMMAND_SET_MEDIA_DIRECTION = "SET_MEDIA_DIRECTION"


class WSMediaProtocolError(ValueError):
    """Malformed protocol artifact (bad MEDIA_START, oversize command, ...)."""


# --------------------------------------------------------------------------- #
# control messages
# --------------------------------------------------------------------------- #


def _maybe_int(value: str | None, name: str) -> int | None:
    try:
        return int(value or "")
    except ValueError as exc:
        raise WSMediaProtocolError(f"{name} is not an integer: {value!r}") from exc


@dataclass(frozen=True)
class ControlMessage:
    """A decoded TEXT control message (plain-text or JSON control format).

    ``fields`` holds every ``key:value`` token that followed the event name;
    ``text`` keeps multi-word prose (used by ``ERROR``, which appends arbitrary
    driver text after the event name). Parsing is intentionally lenient: an
    unknown event with free-form tail still round-trips instead of raising.
    """

    event: str
    fields: Mapping[str, str] = field(default_factory=dict)
    text: str = ""

    @classmethod
    def parse_plain(cls, raw: bytes | str) -> "ControlMessage":
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        except UnicodeDecodeError as exc:
            raise WSMediaProtocolError(f"control message is not UTF-8: {exc}") from exc
        tokens = text.strip().split(" ") if text.strip() else []
        if not tokens:
            raise WSMediaProtocolError("empty control message")
        event = tokens[0]
        fields: dict[str, str] = {}
        prose: list[str] = []
        for token in tokens[1:]:
            key, sep, value = token.partition(":")
            if sep and key:
                fields[key] = value
            else:
                prose.append(token)
        return cls(event=event, fields=fields, text=" ".join(prose))

    @classmethod
    def parse_json(cls, raw: bytes | str) -> "ControlMessage":
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WSMediaProtocolError(f"JSON control message invalid: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
            raise WSMediaProtocolError("JSON control message lacks an 'event'")
        fields = {
            str(k): v if isinstance(v, str) else json.dumps(v, separators=(",", ":"))
            for k, v in payload.items()
            if k != "event"
        }
        return cls(event=payload["event"], fields=fields, text="")

    @classmethod
    def parse(cls, raw: bytes | str | dict[str, Any]) -> "ControlMessage":
        if isinstance(raw, dict):
            return cls.parse_json(json.dumps(raw))
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        stripped = text.strip()
        if stripped.startswith("{"):
            return cls.parse_json(stripped)
        return cls.parse_plain(stripped)


@dataclass(frozen=True)
class MediaStart:
    """The handshake Asterisk emits immediately after the WS connection lands."""

    connection_id: str
    channel: str
    channel_id: str
    format: str
    optimal_frame_size: int
    ptime_ms: int

    @classmethod
    def from_control(cls, msg: ControlMessage) -> "MediaStart":
        if msg.event != EVENT_MEDIA_START:
            raise WSMediaProtocolError(f"not a MEDIA_START message: {msg.event}")
        missing = [
            key
            for key in ("connection_id", "channel", "channel_id", "format", "optimal_frame_size", "ptime")
            if key not in msg.fields
        ]
        if missing:
            raise WSMediaProtocolError(
                f"MEDIA_START missing fields: {', '.join(missing)} (got {sorted(msg.fields)})"
            )
        return cls(
            connection_id=msg.fields["connection_id"],
            channel=msg.fields["channel"],
            channel_id=msg.fields["channel_id"],
            format=msg.fields["format"],
            optimal_frame_size=_maybe_int(msg.fields["optimal_frame_size"], "optimal_frame_size") or 0,
            ptime_ms=_maybe_int(msg.fields["ptime"], "ptime") or 0,
        )

    @classmethod
    def maybe(cls, msg: ControlMessage) -> "MediaStart | None":
        if msg.event != EVENT_MEDIA_START:
            return None
        return cls.from_control(msg)


def parse_media_start(raw: bytes | str | dict[str, Any]) -> MediaStart:
    """One-shot helper for the first expected TEXT message on the connection."""
    return MediaStart.from_control(ControlMessage.parse(raw))


def build_command(command: str, argument: str = "") -> str:
    """Build a plain-text app→Asterisk command honoring the 128-byte cap."""
    payload = f"{command} {argument}".strip()
    if len(payload) > MAX_CONTROL_MESSAGE_BYTES:
        raise WSMediaProtocolError(
            f"command exceeds the {MAX_CONTROL_MESSAGE_BYTES}-byte cap: {len(payload)} bytes"
        )
    return payload


def build_json_command(command: str, **extra: Any) -> str:
    """Build a JSON-format app→Asterisk command (compactly, cap honored)."""
    payload = json.dumps({"command": command, **extra}, separators=(",", ":"))
    if len(payload) > MAX_CONTROL_MESSAGE_BYTES:
        raise WSMediaProtocolError(
            f"JSON command exceeds the {MAX_CONTROL_MESSAGE_BYTES}-byte cap: {len(payload)} bytes"
        )
    return payload


# --------------------------------------------------------------------------- #
# audio framing (backend→Asterisk sends; Asterisk→backend receives)
# --------------------------------------------------------------------------- #


class FrameSlicer:
    """Reassemble the inbound binary byte-stream into ``optimal_frame_size`` frames.

    Asterisk sends one binary message per channel frame but explicitly tolerates
    arbitrary chunking (data between messages is split/joined via leftover
    buffers, see ``process_binary_message``). Callers on this side feed every binary
    message into :meth:`feed` and receive all frames completed by it, so audio
    arriving fragmented or coalesced still yields exact ``optimal_frame_size``
    frames in order.
    """

    def __init__(self, frame_size: int) -> None:
        if frame_size <= 0:
            raise ValueError(f"frame_size must be positive, got {frame_size}")
        self.frame_size = frame_size
        self._leftover = bytearray()

    @property
    def bytes_buffered(self) -> int:
        return len(self._leftover)

    def feed(self, chunk: bytes) -> list[bytes]:
        data = bytes(self._leftover) + chunk if self._leftover else bytes(chunk)
        self._leftover.clear()
        complete_count = len(data) // self.frame_size
        frames = [
            data[i * self.frame_size : (i + 1) * self.frame_size]
            for i in range(complete_count)
        ]
        remainder = data[complete_count * self.frame_size :]
        if remainder:
            self._leftover.extend(remainder)
        return frames

    def flush(self) -> bytes | None:
        """Return any trailing partial frame (drain-time inspection only)."""
        if not self._leftover:
            return None
        tail = bytes(self._leftover)
        self._leftover.clear()
        return tail


class FrameChunker:
    """Split outbound PCM bytes into exact frames; zero-pads the final partial.

    Streaming senders produce whole frames themselves and bypass this, but
    one-shot utterance playback (TTS raw reads) needs deterministic
    frame-boundary splitting plus tail padding so the receiving queue never
    sees a short frame mid-stream.
    """

    def __init__(self, frame_size: int) -> None:
        if frame_size <= 0:
            raise ValueError(f"frame_size must be positive, got {frame_size}")
        self.frame_size = frame_size

    def chunk(self, data: bytes, *, pad_tail: bool = True) -> list[bytes]:
        frames = [
            bytes(data[i : i + self.frame_size])
            for i in range(0, len(data), self.frame_size)
        ]
        if frames:
            tail = frames[-1]
            if len(tail) < self.frame_size:
                if pad_tail:
                    frames[-1] = tail + bytes(self.frame_size - len(tail))
                else:
                    frames.pop()
        return frames


# --------------------------------------------------------------------------- #
# reusable measurement (lab + tests + pacing validation)
# --------------------------------------------------------------------------- #


def rms_linear16(frame: bytes) -> float:
    """RMS (0..32767) of little-endian signed 16-bit mono samples."""
    if len(frame) % 2:
        raise ValueError("linear16 frame length must be even")
    if not frame:
        return 0.0
    samples = struct.unpack("<" + "h" * (len(frame) // 2), frame)
    acc = 0
    for s in samples:
        acc += s * s
    return (acc / len(samples)) ** 0.5


@dataclass
class CadenceTracker:
    """Collects inter-frame arrival deltas to prove (≈)ptime pacing on the wire."""

    deltas: list[float] = field(default_factory=list)
    frame_count: int = 0
    byte_count: int = 0
    last_ts: float | None = field(default=None, repr=False)

    def record(self, frame: bytes) -> None:
        now = time.monotonic()
        self.frame_count += 1
        self.byte_count += len(frame)
        if self.last_ts is not None:
            self.deltas.append(now - self.last_ts)
        self.last_ts = now

    def reset_phase(self) -> None:
        """Restart the delta series (e.g. across a burst/pause phase boundary)."""
        self.last_ts = None

    def percentile(self, pct: float) -> float | None:
        if not self.deltas:
            return None
        ordered = sorted(self.deltas)
        idx = min(len(ordered) - 1, max(0, int(round(pct * (len(ordered) - 1)))))
        return ordered[idx]
