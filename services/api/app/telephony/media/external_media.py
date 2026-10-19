"""ARI ``externalMedia`` websocket-transport assembly + media-channel lifecycle.

Turns the verified ARI dispatcher contract (``res/ari/resource_channels.c``,
Asterisk 22.11.0) into typed request builders, and owns the lifecycle state
for a backend-driven media channel:

- websocket transport **requires** ``encapsulation=none`` and only accepts
  ``connection_type`` ∈ {client, server} (default ``client``);
- with ``connection_type=client`` the ``external_host`` MUST name an existing
  ``websocket-client`` config object (ARI validates the lookup and 400s
  otherwise) — Asterisk then dials the backend's WS server per call;
- with ``connection_type=server`` the host must be empty (ARI substitutes the
  special ``INCOMING`` connection id) — the backend dials INTO Asterisk's WS
  server and the channel binds that incoming connection;
- ``direction`` ∈ {both, in, out} is the backend's audio perspective and is
  appended to the dialstring as ``d(<dir>)`` — the exact dialstring grammar
  is:

      WebSocket/<host>[/<transport_data>][/<d(dir)>]

  (the slash before ``d(...)`` is only appended when ``transport_data`` is
  absent, mirroring ``external_media_websocket`` verbatim; combining rich
  option payloads with a direction follows the same quirk the C code has).
- the media channel is originated into the backend's Stasis app, so its
  events arrive on the SAME authenticated ARI WebSocket used for call-state
  events; its channel id is namespaced with ``talkflow-`` for deterministic
  attribution (a media channel has no CallSession row, so the existing event
  consumer's retry-once-then-drop path is exercised — never a phantom call).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from app.telephony.ari_client import ARINotFound, CHANNEL_ID_PREFIX

log = logging.getLogger("app.telephony.media")

WS_DIAL_TECH = "WebSocket"
INCOMING_CONNECTION_ID = "INCOMING"


class MediaDirection(str, Enum):
    """Backend-perspective audio direction (values sent on the wire)."""

    BOTH = "both"
    IN = "in"
    OUT = "out"

    def __str__(self) -> str:  # keep ARI param serialisation trivial
        return self.value


class ExternalMediaError(ValueError):
    """Invalid externalMedia websocket request (fail before ARI is called)."""


@dataclass(frozen=True)
class ExternalMediaWebSocketOptions:
    """Verified request parameters for POST /ari/channels/externalMedia."""

    app: str
    format: str = "slin16"
    external_host: str = ""
    connection_type: str = "client"
    direction: MediaDirection = MediaDirection.BOTH
    transport_data: str = ""
    data: str = ""
    channel_id: str | None = None
    default_bridge_id: str | None = None

    def validate(self) -> None:
        if not self.app:
            raise ExternalMediaError("app cannot be empty")
        if not self.connection_type:
            raise ExternalMediaError("connection_type cannot be empty")
        if self.connection_type not in {"client", "server"}:
            raise ExternalMediaError(f"unsupported connection_type: {self.connection_type!r}")
        if not self.format:
            raise ExternalMediaError("format cannot be empty")
        if self.connection_type == "client" and not self.external_host:
            raise ExternalMediaError(
                "external_host (websocket-client config id) is required for client connections"
            )
        if self.connection_type == "server" and self.external_host not in (
            "",
            INCOMING_CONNECTION_ID,
        ):
            raise ExternalMediaError(
                "server connections dial Asterisk's WS server; external_host must be empty"
            )
        if self.connection_type == "client" and self.external_host == INCOMING_CONNECTION_ID:
            raise ExternalMediaError("'INCOMING' marks a server connection, not a client id")

    @property
    def resolved_channel_id(self) -> str:
        return self.channel_id or f"{CHANNEL_ID_PREFIX}media-{uuid.uuid4().hex[:12]}"

    @property
    def resolved_bridge_id(self) -> str:
        return self.default_bridge_id or f"{CHANNEL_ID_PREFIX}bridge-{uuid.uuid4().hex[:12]}"

    def dialstring(self) -> str:
        """Exact dialstring Asterisk assembles (to be typed verbatim in the docs).

        Mirrors ``external_media_websocket`` in ``res/ari/resource_channels.c``:
        the ``d(...)`` token needs the separating slash ONLY when
        ``transport_data`` is absent — the C code appends ``"/"`` under
        ``S_COR(!transport_data && direction, "/", "")``.
        """
        host = self.external_host or INCOMING_CONNECTION_ID
        parts: list[str] = [f"{WS_DIAL_TECH}/{host}"]
        if self.transport_data:
            parts.append(self.transport_data)
            if self.direction is not None:
                parts.append(f"d({self.direction.value})")
        elif self.direction is not None:
            parts.append(f"/d({self.direction.value})")
        return "".join(parts)

    def request_params(self, *, channel_id: str | None = None) -> dict[str, Any]:
        """The ARI POST body for the websocket externalMedia dialogue."""
        self.validate()
        params: dict[str, Any] = {
            "transport": "websocket",
            "encapsulation": "none",  # websocket transport *requires* none
            "connection_type": self.connection_type,
            "external_host": self.external_host,
            "app": self.app,
            "format": self.format,
            "channelId": channel_id or self.resolved_channel_id,
        }
        if self.direction is not None:
            params["direction"] = str(self.direction)
        if self.transport_data:
            params["transportData"] = self.transport_data
        if self.data:
            params["data"] = self.data
        return params


class ARIProtocol(Protocol):
    """Surface this module needs — satisfied by ``ARIClient`` (DI-friendly)."""

    async def request_json(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    async def list_channels(self) -> list[dict[str, Any]]: ...


@dataclass
class MediaChannelInfo:
    """Normalized view of the media channel created by externalMedia."""

    channel_id: str
    dialstring: str
    format: str
    raw_response: dict[str, Any] = field(default_factory=dict)


class ExternalMediaSession:
    """Lifecycle for one backend media channel (create → bridge → teardown).

    Teardown is idempotent and audited: the session's own channel id and
    bridge id are removed, and the audit scans the application for stray
    channels whose id still matches our namespace or whose channel *name* is
    a ``WebSocket/...`` so a residual-zero claim has real teeth.
    """

    def __init__(self, ari: ARIProtocol, options: ExternalMediaWebSocketOptions) -> None:
        self._ari = ari
        self.options = options
        options.validate()
        self.channel_id: str = options.resolved_channel_id
        self._created = False

    # -- creation ---------------------------------------------------------- #

    async def create(self) -> MediaChannelInfo:
        params = self.options.request_params(channel_id=self.channel_id)
        raw = await self._ari.request_json(
            "POST", "/ari/channels/externalMedia", params=params
        )
        self._created = True
        dialstring = raw.get("dialstring") or self.options.dialstring()
        return MediaChannelInfo(
            channel_id=self.channel_id,
            dialstring=str(dialstring),
            format=self.options.format,
            raw_response=raw,
        )

    # -- bridging ---------------------------------------------------------- #

    async def create_bridge(self, *, bridge_id: str | None = None, name: str = "talkflow-media") -> str:
        """POST /ari/bridges (mixing) with a client-chosen bridge id."""
        resolved = bridge_id or self.options.resolved_bridge_id
        await self._ari.request_json(
            "POST",
            "/ari/bridges",
            params={"type": "mixing", "bridgeId": resolved, "name": name},
        )
        return resolved

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        await self._ari.request_json(
            "POST", f"/ari/bridges/{bridge_id}/addChannel", params={"channel": channel_id}
        )

    async def remove_channel_from_bridge(self, bridge_id: str, channel_id: str) -> None:
        try:
            await self._ari.request_json(
                "POST", f"/ari/bridges/{bridge_id}/removeChannel", params={"channel": channel_id}
            )
        except ARINotFound:
            log.info("bridge %s gone while removing channel %s", bridge_id, channel_id)

    # -- teardown + audit -------------------------------------------------- #

    async def _hangup_channel(self, channel_id: str) -> None:
        try:
            await self._ari.request_json("DELETE", f"/ari/channels/{channel_id}")
        except ARINotFound:
            log.info("channel %s already terminated", channel_id)

    async def _delete_bridge(self, bridge_id: str) -> None:
        try:
            await self._ari.request_json("DELETE", f"/ari/bridges/{bridge_id}")
        except ARINotFound:
            log.info("bridge %s already gone", bridge_id)

    @staticmethod
    def _appears_torn_down(channel: dict[str, Any]) -> bool:
        return (
            channel.get("state") == "Down"
            and channel.get("dialplan", {}).get("context", "") == "default"
        )

    async def teardown(
        self,
        *,
        bridge_id: str | None = None,
        peer_channel_id: str | None = None,
    ) -> dict[str, Any]:
        """Idempotent teardown: delete bridge + hang up channels, then audit.

        The WS-level ``HANGUP`` command is the WS server session's job (see
        ``ws_media_server``); this covers the ARI-visible artifacts.
        """
        if bridge_id:
            await self._delete_bridge(bridge_id)
        await self._hangup_channel(self.channel_id)
        if peer_channel_id:
            await self._hangup_channel(peer_channel_id)
        audit = await self.audit_residual()
        self._created = False
        return audit

    async def audit_residual(self) -> dict[str, Any]:
        """Residual report after teardown — ZERO means the dialogue is truly gone."""
        media_ids: list[str] = []
        websocket_named: list[str] = []
        try:
            rows = await self._ari.list_channels()
        except ARINotFound:
            rows = []
        for channel in rows:
            cid = str(channel.get("id", ""))
            name = str(channel.get("name", ""))
            if cid.startswith(CHANNEL_ID_PREFIX + "media-"):
                media_ids.append(cid)
            if name.startswith("WebSocket/"):
                websocket_named.append(f"{name}({cid})")
        return {
            "media_channel_ids": media_ids,
            "websocket_named_channels": websocket_named,
            "residual_zero": not media_ids and not websocket_named,
        }
