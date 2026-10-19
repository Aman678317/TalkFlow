"""externalMedia websocket request assembly + media-channel lifecycle.

Mirror of verified Asterisk 22.11.0 behavior: the dispatcher requires
``encapsulation=none`` for the websocket transport, defaults
``connection_type=client`` with ``external_host`` = a websocket-client id
(validated by a live lookup), and substitutes ``INCOMING`` for empty hosts on
server connections. Lifecycle tests use a recording fake ARI so no HTTP or
Asterisk is needed.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.telephony.ari_client import ARINotFound
from app.telephony.media.external_media import (
    ExternalMediaError,
    ExternalMediaSession,
    ExternalMediaWebSocketOptions,
    MediaDirection,
)


class FakeARI:
    """Records every request; scripted per-path responses."""

    def __init__(self, *, channels: list[dict[str, Any]] | None = None,
                 not_found_paths: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._channels = channels or []
        self._not_found = not_found_paths or set()

    async def request_json(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append((method, path, dict(params or {})))
        if path in self._not_found:
            raise ARINotFound(path)
        return {"id": "ok"}

    async def list_channels(self) -> list[dict[str, Any]]:
        self.calls.append(("LIST", "/ari/channels", {}))
        return list(self._channels)


def _client_options(**overrides: Any) -> ExternalMediaWebSocketOptions:
    defaults: dict[str, Any] = {
        "app": "talkflow",
        "format": "slin16",
        "external_host": "talkflow-media-cfg",
    }
    defaults.update(overrides)
    return ExternalMediaWebSocketOptions(**defaults)


# --------------------------------------------------------------------------- #
# validation + dialstring grammar
# --------------------------------------------------------------------------- #


def test_client_mode_requires_external_host() -> None:
    with pytest.raises(ExternalMediaError, match="external_host"):
        _client_options(external_host="").validate()


def test_incoming_is_reserved_for_server_mode() -> None:
    with pytest.raises(ExternalMediaError, match="'INCOMING' marks a server connection"):
        _client_options(external_host="INCOMING").validate()


def test_server_mode_requires_empty_external_host() -> None:
    with pytest.raises(ExternalMediaError, match="server connections"):
        _client_options(connection_type="server").validate()


def test_empty_app_or_format_rejected() -> None:
    with pytest.raises(ExternalMediaError, match="app"):
        _client_options(app="").validate()
    with pytest.raises(ExternalMediaError, match="format"):
        _client_options(format="").validate()


def test_unknown_connection_type_rejected() -> None:
    with pytest.raises(ExternalMediaError, match="connection_type"):
        _client_options(connection_type="multicast").validate()


def test_dialstring_grammar_matches_the_c_assembly() -> None:
    # external_media_websocket(): "WebSocket/%s%s%s%s%s" with transport_data''
    # and no direction '' → exactly one d() appended after the connection id.
    assert (
        _client_options().dialstring() == "WebSocket/talkflow-media-cfg/d(both)"
    )
    assert (
        _client_options(direction=MediaDirection.OUT).dialstring()
        == "WebSocket/talkflow-media-cfg/d(out)"
    )
    # direction None: never a stray "d(None)" token on the wire.
    assert (
        _client_options(direction=None).dialstring() == "WebSocket/talkflow-media-cfg"
    )


def test_server_mode_dialstring_uses_incoming() -> None:
    opts = _client_options(connection_type="server", external_host="",
                           direction=MediaDirection.IN)
    assert opts.dialstring() == "WebSocket/INCOMING/d(in)"


def test_request_params_cover_the_verified_contract() -> None:
    opts = _client_options()
    params = opts.request_params()
    assert params["transport"] == "websocket"
    assert params["encapsulation"] == "none"  # required for websocket transport
    assert params["connection_type"] == "client"
    assert params["external_host"] == "talkflow-media-cfg"
    assert params["app"] == "talkflow"
    assert params["format"] == "slin16"
    assert params["direction"] == "both"
    assert params["channelId"].startswith("talkflow-media-")
    # data is passed through for the Stasis dialogue
    assert "data" not in params


def test_channel_and_bridge_ids_are_client_namespaced() -> None:
    opts = _client_options(channel_id="talkflow-media-fixed",
                           default_bridge_id="talkflow-bridge-fixed")
    assert opts.resolved_channel_id == "talkflow-media-fixed"
    assert opts.resolved_bridge_id == "talkflow-bridge-fixed"


# --------------------------------------------------------------------------- #
# lifecycle against a fake ARI
# --------------------------------------------------------------------------- #


async def test_session_create_posts_verified_params() -> None:
    ari = FakeARI()
    session = ExternalMediaSession(ari, _client_options())
    info = await session.create()
    method, path, params = ari.calls[0]
    assert (method, path) == ("POST", "/ari/channels/externalMedia")
    assert params["encapsulation"] == "none"
    assert info.channel_id == session.channel_id
    # the response's dialstring wins when present
    assert info.dialstring == "WebSocket/talkflow-media-cfg/d(both)"  # fallback value


async def test_bridge_and_teardown_calls_are_exact_and_idempotent() -> None:
    ari = FakeARI()
    session = ExternalMediaSession(ari, _client_options())
    bridge_id = await session.create_bridge(bridge_id="talkflow-bridge-1")
    assert bridge_id == "talkflow-bridge-1"
    await session.add_channel_to_bridge("talkflow-bridge-1", "media-chan")
    await session.teardown(bridge_id="talkflow-bridge-1", peer_channel_id="sip-1")
    paths = [(m, p) for (m, p, _) in ari.calls]
    assert ("POST", "/ari/bridges") in paths
    assert ("POST", "/ari/bridges/talkflow-bridge-1/addChannel") in paths
    assert ("DELETE", "/ari/bridges/talkflow-bridge-1") in paths
    assert ("POST", "/ari/bridges/talkflow-bridge-1/removeChannel") not in paths  # unused
    assert ("DELETE", "/ari/channels/" + session.channel_id) in paths
    assert ("DELETE", "/ari/channels/sip-1") in paths
    # repeat teardown: 404s are absorbed, no raising
    ari._not_found = {
        "/ari/bridges/talkflow-bridge-1",
        "/ari/channels/" + session.channel_id,
        "/ari/channels/sip-1",
    }
    await session.teardown(bridge_id="talkflow-bridge-1", peer_channel_id="sip-1")


async def test_residual_audit_catches_stray_channels() -> None:
    clean = FakeARI(channels=[
        {"id": "talkflow-<uuid>", "name": "PJSIP/1001-00000001", "state": "Up"},
    ])
    session_clean = ExternalMediaSession(clean, _client_options())
    audit = await session_clean.audit_residual()
    assert audit["residual_zero"] is True

    dirty = FakeARI(channels=[
        {"id": "Other-1", "name": "WebSocket/INCOMING-xyz", "state": "Up"},
        {"id": "talkflow-media-leak", "name": "PJSIP/x", "state": "Up"},
    ])
    session_dirty = ExternalMediaSession(dirty, _client_options())
    audit = await session_dirty.audit_residual()
    assert audit["residual_zero"] is False
    assert "talkflow-media-leak" in audit["media_channel_ids"]
    assert any("WebSocket/INCOMING-xyz" in name for name in
               audit["websocket_named_channels"])


async def test_teardown_reports_residual_zero_when_audit_clean() -> None:
    ari = FakeARI(channels=[])
    session = ExternalMediaSession(ari, _client_options())
    await session.create()
    audit = await session.teardown()
    assert audit["residual_zero"] is True
