"""ARI event normalization + WebSocket event consumer (backend-only).

ARI events are NOT HTTP webhooks: they arrive over an authenticated ARI
WebSocket connection. This module keeps that boundary explicit — it never
parses HTTP posts, and `AsteriskARIProvider.parse_webhook` deliberately raises
on HTTP posts so the Asterisk provider can never be spoofed through the
carrier webhook endpoint.

Design contracts honored here (docs/ASTERISK_LOCAL_SIP_LAB.md, P1 design +
P2 acceptance matrix):

- Event → status mapping is a pure function over the ARI payloads Asterisk
  actually emits for PJSIP channels; unmapped events are ignored, never
  guessed.
- Delivery is idempotent across reconnect/restart: the consumer claims each
  channel's terminal outcome ONCE. ``CallService.transition_status`` is
  idempotent for identical status callbacks but cannot distinguish two
  different terminal statuses (busy → ended re-delivery would overwrite a
  BUSY call with ENDED), so the terminal claim lives here.
- WS disconnect/restart reconnects with bounded backoff; nothing fabricates
  a connected or ended state for channels whose events were missed.
- A normalized event whose DB row is not visible yet (the originate HTTP
  response may still be in-flight in ``create_outbound_call``) is retried
  once after a bounded grace period, then dropped with a logged warning —
  never duplicated into a phantom state.
- Channel → call attribution is deterministic: TalkFlow-chosen channel IDs
  are namespaced with ``CHANNEL_ID_PREFIX`` (see ari_client), so restarts do
  not lose the correlation map.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from app.telephony.ari_client import (
    ARIConfig,
    CHANNEL_ID_PREFIX,
)
from app.telephony.base import CallStatus

log = logging.getLogger("app.telephony.ari_events")

_TERMINAL_STATUSES = frozenset(
    {
        CallStatus.ENDED,
        CallStatus.FAILED,
        CallStatus.BUSY,
        CallStatus.NO_ANSWER,
        CallStatus.DECLINED,
        CallStatus.TIMEOUT,
        CallStatus.INVALID_NUMBER,
        CallStatus.UNSUPPORTED_COUNTRY,
    }
)

# Asterisk hangup causes (PJSIP/PSTN cause codes) → normalized CallStatus.
# Only genuinely distinguishable outcomes are mapped; everything else stays
# unmapped so ChannelHangupRequest defers to the final ChannelDestroyed /
# StasisEnd event instead of guessing a terminal status.
_CAUSE_MAP: dict[int, CallStatus] = {
    16: CallStatus.ENDED,  # normal clearing
    17: CallStatus.BUSY,  # user busy
    18: CallStatus.NO_ANSWER,  # no user response
    19: CallStatus.NO_ANSWER,  # no answer / subscriber absent
    20: CallStatus.NO_ANSWER,  # subscriber absent
    21: CallStatus.DECLINED,  # call rejected
    28: CallStatus.INVALID_NUMBER,  # invalid number format
    34: CallStatus.FAILED,  # no circuit available / congestion
}


@dataclass(frozen=True)
class ARIEventFrame:
    """A normalized ARI event relevant for call-state tracking."""

    event_type: str
    channel_id: str
    status: CallStatus | None  # None ⇒ informational only (no status change)
    raw: dict[str, Any]


def normalize_ari_event(payload: dict[str, Any]) -> ARIEventFrame | None:
    """Map one raw ARI event to an :class:`ARIEventFrame`, or ``None`` to ignore."""
    event_type = str(payload.get("type") or "")
    channel = payload.get("channel") or {}
    channel_id = str(channel.get("id") or "")
    if not channel_id:
        return None

    if event_type == "StasisStart":
        # Channel entered the Stasis app *before* dialing; ringing/connected
        # states arrive via ChannelStateChange — announcing CONNECTED here
        # would fabricate a state.
        return ARIEventFrame(event_type, channel_id, None, payload)

    if event_type in ("ChannelStateChange", "ChannelUp", "ChannelRinging"):
        state = str(channel.get("state") or "").lower()
        if event_type == "ChannelUp":
            state = "up"
        elif event_type == "ChannelRinging":
            state = "ringing"
        if state == "ringing":
            return ARIEventFrame(event_type, channel_id, CallStatus.RINGING, payload)
        if state == "up":
            return ARIEventFrame(event_type, channel_id, CallStatus.CONNECTED, payload)
        return ARIEventFrame(event_type, channel_id, None, payload)

    if event_type == "ChannelHangupRequest":
        # A request, not a final outcome: claim a terminal status only for
        # known causes; let ChannelDestroyed/StasisEnd close the rest.
        cause = payload.get("cause")
        status = _CAUSE_MAP.get(int(cause)) if isinstance(cause, int) else None
        if status is None:
            return ARIEventFrame(event_type, channel_id, None, payload)
        return ARIEventFrame(event_type, channel_id, status, payload)

    if event_type in ("ChannelDestroyed", "StasisEnd"):
        # Final event for the channel: always terminal (cause-aware fallback).
        cause = payload.get("cause")
        status = _CAUSE_MAP.get(int(cause)) if isinstance(cause, int) else None
        return ARIEventFrame(event_type, channel_id, status or CallStatus.ENDED, payload)

    return None  # DTMF, varset, bridge churn, dialplan events: not call state


# (call_sid, status, channel_id) → True when a live CallSession row was found
# and transitioned; False ⇒ session not visible yet (commit race) or unknown.
DispatchFn = Callable[[str, CallStatus, str], Awaitable[bool]]

StreamFactory = Callable[[], Any]  # awaited → async iterator of raw frames


def build_call_service_dispatch() -> DispatchFn:
    """Default dispatch: apply the status through ``CallService.transition_status``."""

    async def _dispatch(call_sid: str, status: CallStatus, channel_id: str) -> bool:
        from app.db.session import db_session
        from app.telephony.call_service import CallService

        async with db_session() as db:
            call = await CallService(db).transition_status(
                call_sid,
                status,
                extra_data={"source": "asterisk_ari", "channel": channel_id},
            )
            return call is not None

    return _dispatch


class AsteriskARIEventConsumer:
    """Consumes the ARI WebSocket and applies normalized events to sessions."""

    def __init__(
        self,
        config: ARIConfig,
        *,
        dispatch: DispatchFn,
        channel_map: dict[str, str] | None = None,
        open_stream: StreamFactory | None = None,
        retry_grace_seconds: float = 2.0,
        reconnect_initial_seconds: float = 1.0,
        reconnect_delay_seconds: float = 5.0,
        max_attempts: int | None = None,
    ) -> None:
        self._config = config
        self._dispatch = dispatch
        self._channel_map = channel_map if channel_map is not None else {}
        self._open_stream: StreamFactory = open_stream or self._open_ari_websocket
        self._retry_grace_seconds = max(0.0, retry_grace_seconds)
        self._reconnect_initial = max(0.0, reconnect_initial_seconds)
        self._reconnect_delay_seconds = max(0.0, reconnect_delay_seconds)
        self._max_attempts = max_attempts
        self._terminal_channels: set[str] = set()

    # ------------------------------------------------------------------ #
    # wiring helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_settings(
        cls, *, provider: Any = None
    ) -> "AsteriskARIEventConsumer":
        """Build the production consumer from pydantic-settings.

        ``provider`` is the registered :class:`AsteriskARIProvider` instance;
        its channel map (seeded on originate) is shared with this consumer.
        """
        from app.config import settings

        return cls(
            ARIConfig.from_settings(),
            dispatch=build_call_service_dispatch(),
            channel_map=router_channel_map(provider),
            retry_grace_seconds=settings.asterisk_event_retry_seconds,
            reconnect_delay_seconds=settings.asterisk_ws_reconnect_seconds,
        )

    @property
    def channel_map(self) -> dict[str, str]:
        return self._channel_map

    def start(self) -> "asyncio.Task[None]":
        """Run :meth:`consume_forever` as a background task."""
        return asyncio.create_task(self.consume_forever())

    async def consume_forever(self) -> None:
        """Connect → consume → reconnect loop with bounded backoff.

        Terminal-event absorption survives reconnects (kept on the instance),
        so a stream that drops mid-call cannot double-apply a terminal state
        after the operator restarts the stream.
        """
        attempts = 0
        delay = self._reconnect_initial
        cap = max(self._reconnect_delay_seconds, self._reconnect_initial)
        log.info("ARI event consumer starting (app=%s)", self._config.app_name)
        while True:
            if self._max_attempts is not None and attempts >= self._max_attempts:
                log.error(
                    "ARI event stream gave up after %s attempts; "
                    "no fabricated call state — waiting for an explicit restart",
                    attempts,
                )
                return
            try:
                stream = await self._open_stream()
            except Exception as exc:  # noqa: BLE001 — reconnect on any opener failure
                attempts += 1
                log.warning(
                    "ARI event stream unavailable (attempt %s): %s — retrying in %.1fs",
                    attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, cap) if cap > 0 else 0.0
                continue

            delay = self._reconnect_initial
            attempts = 0
            try:
                async for raw in stream:
                    await self.process_payload(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — stream dropped: reconnect below
                log.warning(
                    "ARI event stream dropped (%s); reconnecting with bounded backoff",
                    exc,
                )
            finally:
                closer = getattr(stream, "close", None)
                if closer is not None:
                    try:
                        await closer()
                    except Exception:  # noqa: BLE001 — cleanup must not mask the loop
                        pass

    # ------------------------------------------------------------------ #
    # event processing
    # ------------------------------------------------------------------ #
    async def process_payload(self, raw: Any) -> None:
        """Decode one raw WS frame (dict or JSON text) and dispatch it."""
        try:
            payload = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        await self.process_ari_payload(payload)

    async def process_ari_payload(self, payload: dict[str, Any]) -> None:
        frame = normalize_ari_event(payload)
        if frame is None or frame.status is None:
            return  # unmapped or purely informational event

        if frame.channel_id in self._terminal_channels:
            log.debug(
                "absorbing duplicate/late terminal ARI event %s for channel %s",
                frame.event_type,
                frame.channel_id,
            )
            return

        call_sid = self._resolve_call_sid(frame)
        if call_sid is None:
            log.warning(
                "ARI event %s for channel %s is not a TalkFlow-outbound leg; dropping",
                frame.event_type,
                frame.channel_id,
            )
            return

        await self._dispatch_with_grace(call_sid, frame)

        if frame.status in _TERMINAL_STATUSES:
            # Claim the terminal outcome regardless of the dispatch result: the
            # event itself is final for the channel and must never re-apply
            # (e.g. BUSY followed by a late ENDED re-delivery).
            self._terminal_channels.add(frame.channel_id)

    def _resolve_call_sid(self, frame: ARIEventFrame) -> str | None:
        mapped = self._channel_map.get(frame.channel_id)
        if mapped:
            return mapped
        if frame.channel_id.startswith(CHANNEL_ID_PREFIX):
            # Client-chosen deterministic ID: the correlation survives API
            # restarts without any ARI round-trip.
            return frame.channel_id
        return None

    async def _dispatch_with_grace(self, call_sid: str, frame: ARIEventFrame) -> None:
        found = await self._dispatch(call_sid, frame.status, frame.channel_id)  # type: ignore[arg-type]
        if not found:
            # The originate commit in create_outbound_call may still be in
            # flight; retry once after a bounded grace period, then give up
            # without inventing any state.
            log.info(
                "CallSession %s not visible yet for ARI event %s (channel %s); "
                "retrying after %.1fs",
                call_sid,
                frame.event_type,
                frame.channel_id,
                self._retry_grace_seconds,
            )
            if self._retry_grace_seconds:
                await asyncio.sleep(self._retry_grace_seconds)
            await self._dispatch(
                call_sid, frame.status, frame.channel_id
            )  # type: ignore[arg-type]

    def seed_channel(self, channel_id: str, call_sid: str) -> None:
        """Register a channel → call_sid mapping (used by originate)."""
        self._channel_map[channel_id] = call_sid

    # ------------------------------------------------------------------ #
    # production transport
    # ------------------------------------------------------------------ #
    async def _open_ari_websocket(self) -> AsyncIterator[Any]:
        """Open /ari/events with Basic-equivalent ``api_key`` auth (Asterisk ARI)."""
        try:
            from websockets.asyncio.client import connect as ws_connect
        except ImportError:  # pragma: no cover — older websockets installs
            from websockets import connect as ws_connect  # type: ignore[no-redef]

        base = self._config.base_url.replace("http", "ws", 1)
        app = urllib.parse.quote(self._config.app_name, safe="")
        key = urllib.parse.quote(
            f"{self._config.username}:{self._config.password}", safe=""
        )
        url = f"{base}/ari/events?app={app}&api_key={key}&subscribeAll=true"
        return await ws_connect(
            url, open_timeout=self._config.timeout_seconds
        )


def router_channel_map(provider: Any) -> dict[str, str]:
    """Return the provider's channel map when available; otherwise a fresh dict."""
    channel_map = getattr(provider, "channel_map", None)
    return channel_map if isinstance(channel_map, dict) else {}
