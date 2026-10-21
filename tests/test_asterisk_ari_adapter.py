"""Asterisk ARI adapter acceptance lane (P2 matrix, network-independent).

Deterministic coverage of the adapter design answers in
docs/ASTERISK_LOCAL_SIP_LAB.md — no Asterisk, no sockets, no sleeps beyond
zero:

- destinations outside the operator allowlist are rejected BEFORE any ARI
  action (no PSTN dialing, no originate);
- unreachable ARI is an honest provider-unavailable outcome;
- a timeout after originate is an UNKNOWN outcome reconciled via the
  deterministic channel ID — never blind-retried (that could duplicate a
  very real local call);
- ARI event payloads normalize to the unified CallStatus vocabulary, with
  terminal outcomes claimed once and late/duplicate terminal events absorbed
  across WS reconnects (CallService.transition_status is idempotent for
  identical statuses but cannot tell two different terminal states apart);
- the simulated provider remains the default and Asterisk is selectable only
  by explicit operator configuration (never silently swapped).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.config import settings
from app.errors import ProviderError, ValidationError
from app.telephony.ari_client import (
    ARIConfig,
    ARINotFound,
    ARIRequestFailed,
    ARIUnavailable,
    ARITimeout,
)
from app.telephony.providers.asterisk_provider import AsteriskARIProvider
from app.telephony.ari_events import AsteriskARIEventConsumer, normalize_ari_event
from app.telephony.base import CallStatus
from app.telephony.service import TelephonyService

CALL_ID = "3f2d9a1e-0000-4a9f-8c6b-1234abcd5678"
CID = f"talkflow-{CALL_ID}"


def _force_settings(monkeypatch, **values: Any) -> None:
    """Force settings values on EVERY binding product code may read.

    The ``app`` session fixture (tests/conftest.py) runs
    ``importlib.reload(app.config)`` the first time an app-fixture suite
    requests it. Any suite before us can therefore fork the settings story
    mid-session: function-level ``from app.config import settings`` reads the
    reloaded singleton while module-owned bindings (service.py, routers)
    keep the pre-reload object. Ordering must never change outcomes, so the
    same values are forced on all of them (same convention as the note in
    tests/test_telephony_webhook_security.py).
    """
    import app.config as cfg
    import app.routers.telephony as tele_router
    import app.telephony.service as svc

    holders = {id(cfg.settings): cfg.settings,
               id(svc.settings): svc.settings,
               id(tele_router.settings): tele_router.settings}
    for holder in holders.values():
        for name, value in values.items():
            monkeypatch.setattr(holder, name, value, raising=False)


# ---------------------------------------------------------------------- #
# fakes
# ---------------------------------------------------------------------- #
class FakeARIClient:
    """In-memory ARIClient stand-in: no network, deterministic."""

    def __init__(self, *, base_url: str = "http://127.0.0.1:8088") -> None:
        self._config = ARIConfig(
            base_url=base_url,
            username="test-user",
            password="test-password",
            app_name="talkflow",
            timeout_seconds=0.5,
        )
        self.calls: list[tuple[str, Any]] = []
        self.channels: dict[str, dict[str, Any]] = {}
        self.create_error: Exception | None = None
        self.dial_error: Exception | None = None
        self.dial_side_effect: Any = None
        self.get_error: Exception | None = None
        # Channels that exist server-side even though create_channel raised
        # ARITimeout (the request took effect but the response was lost).
        self.timeout_but_created: set[str] = set()

    @property
    def config(self) -> ARIConfig:
        return self._config

    async def create_channel(
        self,
        *,
        channel_id: str,
        endpoint: str,
        app: str,
        app_args: list[str],
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            ("create", channel_id, endpoint, app, dict(variables or {}))
        )
        if channel_id in self.timeout_but_created:
            raise ARITimeout("create took effect server-side; response lost")
        if self.create_error is not None:
            raise self.create_error
        # setdefault: a test-seeded channel (e.g. created before a lost
        # response, later observed in an advanced state) is not overwritten.
        self.channels.setdefault(channel_id, {"id": channel_id, "state": "Down"})
        return dict(self.channels[channel_id])

    async def dial(self, channel_id: str) -> None:
        self.calls.append(("dial", channel_id))
        if self.dial_error is not None:
            raise self.dial_error
        if self.dial_side_effect is not None:
            self.dial_side_effect(channel_id)

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        self.calls.append(("get", channel_id))
        if self.get_error is not None:
            raise self.get_error
        if channel_id in self.channels:
            return dict(self.channels[channel_id])
        raise ARINotFound(f"no channel {channel_id}")

    async def hangup(self, channel_id: str) -> None:
        self.calls.append(("hangup", channel_id))
        self.channels.pop(channel_id, None)


class _Dispatch:
    """Records dispatched statuses; scripted results for retry semantics."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, CallStatus, str]] = []
        self.results: list[bool] = []

    async def __call__(self, call_sid: str, status: CallStatus, channel_id: str) -> bool:
        self.calls.append((call_sid, status, channel_id))
        if self.results:
            return self.results.pop(0)
        return True


class _FakeStream:
    """Async-iterable WS stand-in with a close() shim."""

    def __init__(self, frames: list[Any]) -> None:
        self._frames = list(frames)
        self._iter: Any = None
        self.closed = False

    def __aiter__(self) -> "_FakeStream":
        self._iter = iter(self._frames)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True


def _provider(
    fake: FakeARIClient | None = None, *, allowlist: tuple[str, ...] = ("1001", "1002")
) -> AsteriskARIProvider:
    return AsteriskARIProvider(fake or FakeARIClient(), list(allowlist))


async def _create(p: AsteriskARIProvider, to: str = "1001") -> Any:
    return await p.create_call(
        to=to,
        from_="+15551230000",
        webhook_url="",
        stream_url="",
        custom_params={"call_id": CALL_ID},
    )


def _ari_event(
    event_type: str,
    channel_id: str,
    *,
    channel_extra: dict[str, Any] | None = None,
    **event_extra: Any,
) -> dict[str, Any]:
    channel = {"id": channel_id}
    if channel_extra:
        channel.update(channel_extra)
    payload = {"type": event_type, "channel": channel}
    payload.update(event_extra)
    return payload


def _consumer(
    dispatch: _Dispatch,
    *,
    open_stream: Any = None,
    channel_map: dict[str, str] | None = None,
    **kwargs: Any,
) -> AsteriskARIEventConsumer:
    cfg = ARIConfig(
        base_url="http://127.0.0.1:8088",
        username="u",
        password="p",
        app_name="talkflow",
    )
    return AsteriskARIEventConsumer(
        cfg,
        dispatch=dispatch,
        channel_map=channel_map if channel_map is not None else {},
        open_stream=open_stream if open_stream is not None else (lambda: None),
        **kwargs,
    )


# ---------------------------------------------------------------------- #
# destination policy
# ---------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_destination_outside_allowlist_rejected_before_originate():
    provider = _provider()
    for destination in ("+15551234567", "911", "1001@127.0.0.1", "  "):
        result = await _create(provider, to=destination)
        assert result.status is CallStatus.INVALID_NUMBER, destination
        assert result.error_code == "DESTINATION_NOT_IN_ALLOWLIST"
    # No ARI action at all: rejection happens before any originate.
    assert provider.ari.calls == []


def test_normalize_destination_trims_allowlisted_and_rejects_the_rest():
    provider = _provider()
    assert provider.normalize_destination(" 1001 ") == "1001"
    with pytest.raises(ValidationError):
        provider.normalize_destination("+15551234567")
    empty = AsteriskARIProvider(FakeARIClient(), [])
    with pytest.raises(ValidationError):
        empty.normalize_destination("1001")


# ---------------------------------------------------------------------- #
# origination + unknown-outcome reconciliation
# ---------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_originate_is_immediate_dial_with_correlation():
    """POST /ari/channels with app+endpoint dials immediately (verified on the
    live lab): exactly one ARI call, no eager follow-up dial."""
    provider = _provider()
    result = await _create(provider)
    assert result.status is CallStatus.CONNECTING  # ARI response state Down
    assert result.call_sid == CID
    assert provider.ari.calls == [
        (
            "create",
            CID,
            "PJSIP/1001",
            "talkflow",
            {"TALKFLOW_CALL_ID": CALL_ID, "TALKFLOW_DESTINATION": "1001"},
        ),
    ]


@pytest.mark.asyncio
async def test_unconfigured_ari_reports_honest_failure():
    fake = FakeARIClient(base_url="")  # no base URL ⇒ not configured
    provider = AsteriskARIProvider(fake, ["1001"])
    result = await _create(provider)
    assert result.status is CallStatus.FAILED
    assert result.error_code == "ARI_NOT_CONFIGURED"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_unreachable_ari_reports_provider_unavailable():
    fake = FakeARIClient()
    fake.create_error = ARIUnavailable("connection refused")
    result = await _create(_provider(fake))
    assert result.status is CallStatus.FAILED
    assert result.error_code == "ARI_UNAVAILABLE"


@pytest.mark.asyncio
async def test_originate_timeout_reconciles_existing_channel():
    """Timeout ≠ proof of failure: the channel may exist server-side."""
    fake = FakeARIClient()
    fake.timeout_but_created = {CID}
    fake.channels[CID] = {"id": CID, "state": "Down"}
    provider = _provider(fake)

    result = await _create(provider)

    assert result.status is CallStatus.CONNECTING
    assert result.call_sid == CID
    creates = [c for c in fake.calls if c[0] == "create"]
    gets = [c for c in fake.calls if c[0] == "get"]
    dials = [c for c in fake.calls if c[0] == "dial"]
    # Exactly one originate attempt (no blind retry) + one reconcile.
    # No dial: POST /ari/channels dialls immediately on its own.
    assert len(creates) == 1 and len(gets) == 1 and dials == []


@pytest.mark.asyncio
async def test_create_timeout_without_channel_never_retries():
    fake = FakeARIClient()
    fake.timeout_but_created = {CID}  # raises timeout, and no channel exists
    provider = _provider(fake)

    result = await _create(provider)

    assert result.status is CallStatus.FAILED
    assert result.error_code == "ARI_TIMEOUT_UNKNOWN"
    assert result.error_message and "no channel" in result.error_message
    assert len([c for c in fake.calls if c[0] == "create"]) == 1
    assert [c for c in fake.calls if c[0] == "dial"] == []


@pytest.mark.asyncio
async def test_originate_response_past_down_is_mapped_not_fabricated():
    """A slow response can carry an already-ringing channel; honor its state."""
    fake = FakeARIClient()
    # Pre-seed the channel the originate returns: response says Ringing.
    fake.channels[CID] = {"id": CID, "state": "Ringing"}
    provider = _provider(fake)

    result = await _create(provider)

    assert result.status is CallStatus.RINGING
    assert [c for c in provider.ari.calls if c[0] == "dial"] == []


@pytest.mark.asyncio
async def test_originate_rejected_is_honest_failure():
    fake = FakeARIClient()
    fake.create_error = ARIRequestFailed("originate refused", 400)
    result = await _create(_provider(fake))
    assert result.status is CallStatus.FAILED
    assert result.error_code == "ORIGINATE_REJECTED"


# ---------------------------------------------------------------------- #
# lifecycle mirroring
# ---------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_end_call_treats_missing_channel_as_success():
    provider = _provider()
    assert await provider.end_call("talkflow-nope") is True
    provider.ari.channels["c1"] = {"id": "c1", "state": "Up"}
    assert await provider.end_call("c1") is True
    assert ("hangup", "c1") in provider.ari.calls


@pytest.mark.asyncio
async def test_get_call_status_maps_ari_states():
    provider = _provider()
    provider.ari.channels["c-up"] = {"id": "c-up", "state": "Up"}
    provider.ari.channels["c-ring"] = {"id": "c-ring", "state": "Ringing"}
    provider.ari.channels["c-down"] = {"id": "c-down", "state": "Down"}
    assert (await provider.get_call_status("c-up")).status is CallStatus.CONNECTED
    assert (await provider.get_call_status("c-ring")).status is CallStatus.RINGING
    assert (await provider.get_call_status("c-down")).status is CallStatus.CONNECTING
    destroyed = await provider.get_call_status("talkflow-gone")
    assert destroyed.status is CallStatus.ENDED
    assert destroyed.error_code == "CHANNEL_DESTROYED"

    provider.ari.get_error = ARIUnavailable("ARI down")
    with pytest.raises(ProviderError):
        await provider.get_call_status("c-up")


# ---------------------------------------------------------------------- #
# inbound / webhook surface must fail closed
# ---------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_webhook_surface_fails_closed():
    provider = _provider()
    with pytest.raises(ProviderError):
        provider.parse_webhook({}, {"CallSid": "x"})
    assert provider.verify_webhook_signature("url", {}, "sig") is False
    with pytest.raises(ProviderError):
        provider.generate_twiml_stream_response(call_sid="x", stream_url="ws://u")


@pytest.mark.asyncio
async def test_answer_reject_are_honest_noops():
    provider = _provider()
    assert await provider.answer_call("sid") is False
    assert await provider.reject_call("sid", "busy") is False


# ---------------------------------------------------------------------- #
# event normalization
# ---------------------------------------------------------------------- #
def test_event_normalization_matrix():
    cases = [
        (_ari_event("StasisStart", "c1"), None),  # not yet dialed: no state
        (
            _ari_event("ChannelStateChange", "c1", channel_extra={"state": "Ringing"}),
            CallStatus.RINGING,
        ),
        (
            _ari_event("ChannelStateChange", "c1", channel_extra={"state": "Up"}),
            CallStatus.CONNECTED,
        ),
        (_ari_event("ChannelUp", "c1"), CallStatus.CONNECTED),
        (_ari_event("ChannelRinging", "c1"), CallStatus.RINGING),
        (_ari_event("ChannelHangupRequest", "c1", cause=17), CallStatus.BUSY),
        (_ari_event("ChannelHangupRequest", "c1", cause=19), CallStatus.NO_ANSWER),
        (_ari_event("ChannelHangupRequest", "c1", cause=999), None),  # defer to final
        (_ari_event("ChannelHangupRequest", "c1"), None),  # no cause: defer
        (_ari_event("ChannelDestroyed", "c1", cause=16), CallStatus.ENDED),
        (_ari_event("ChannelDestroyed", "c1", cause=17), CallStatus.BUSY),
        (_ari_event("ChannelDestroyed", "c1"), CallStatus.ENDED),  # final ⇒ ended
        (_ari_event("StasisEnd", "c1"), CallStatus.ENDED),
        (_ari_event("ChannelDtmfReceived", "c1", digit="5"), None),
        ({"type": "BridgeCreated"}, None),  # no channel id
        ({"type": "ChannelVarset", "channel": {"id": "c1"}}, None),
    ]
    for payload, expected in cases:
        frame = normalize_ari_event(payload)
        if expected is None:
            assert frame is None or frame.status is None, payload
        else:
            assert frame is not None and frame.status is expected, payload


# ---------------------------------------------------------------------- #
# consumer dispatch semantics
# ---------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_consumer_ignores_stasis_start_and_absorbs_late_terminal():
    dispatch = _Dispatch()
    consumer = _consumer(dispatch, channel_map={"c1": "CA1"}, retry_grace_seconds=0)

    await consumer.process_ari_payload(_ari_event("StasisStart", "c1"))
    assert dispatch.calls == []  # no fabricated CONNECTED for a pre-dial state

    await consumer.process_ari_payload(
        _ari_event("ChannelStateChange", "c1", channel_extra={"state": "Ringing"})
    )
    await consumer.process_ari_payload(_ari_event("ChannelDestroyed", "c1", cause=16))
    await consumer.process_ari_payload(_ari_event("StasisEnd", "c1"))  # late tail

    assert [(sid, st) for sid, st, _ in dispatch.calls] == [
        ("CA1", CallStatus.RINGING),
        ("CA1", CallStatus.ENDED),
    ]
    assert "c1" in consumer._terminal_channels


@pytest.mark.asyncio
async def test_consumer_skips_non_talkflow_channels():
    dispatch = _Dispatch()
    consumer = _consumer(dispatch, retry_grace_seconds=0)
    await consumer.process_ari_payload(
        _ari_event("ChannelStateChange", "PJSIP/other-1", channel_extra={"state": "Up"})
    )
    assert dispatch.calls == []


@pytest.mark.asyncio
async def test_consumer_retries_dispatch_during_commit_race():
    """Events may land on the WS before create_outbound_call commits."""
    dispatch = _Dispatch()
    dispatch.results = [False, True]
    consumer = _consumer(dispatch, channel_map={"c1": "CA1"}, retry_grace_seconds=0)

    await consumer.process_ari_payload(_ari_event("ChannelHangupRequest", "c1", cause=17))

    assert [(sid, st) for sid, st, _ in dispatch.calls] == [
        ("CA1", CallStatus.BUSY),
        ("CA1", CallStatus.BUSY),
    ]
    # The terminal claim applies regardless of the dispatch result.
    assert "c1" in consumer._terminal_channels


@pytest.mark.asyncio
async def test_consume_forever_absorbs_duplicates_across_reconnect():
    dispatch = _Dispatch()
    ringing = _ari_event("ChannelStateChange", "c1", channel_extra={"state": "Ringing"})
    busy = _ari_event("ChannelHangupRequest", "c1", cause=17)
    destroyed = _ari_event("ChannelDestroyed", "c1", cause=16)
    streams = [
        _FakeStream([json.dumps(ringing), busy]),
        # Reconnected stream re-delivers the terminal busy, then adds ENDED:
        # both absorbed — no duplicate/overwriting terminal transition.
        _FakeStream([busy, destroyed, json.dumps(destroyed)]),
    ]
    opens = {"n": 0}

    async def factory():
        opens["n"] += 1
        if opens["n"] <= len(streams):
            return streams[opens["n"] - 1]
        raise ConnectionError("no more streams (test sentinel)")

    consumer = _consumer(
        dispatch,
        open_stream=factory,
        channel_map={"c1": "CA1"},
        reconnect_initial_seconds=0,
        reconnect_delay_seconds=0,
        max_attempts=3,
    )
    await asyncio.wait_for(consumer.consume_forever(), timeout=5)

    assert [(sid, st) for sid, st, _ in dispatch.calls] == [
        ("CA1", CallStatus.RINGING),
        ("CA1", CallStatus.BUSY),
    ]
    assert opens["n"] == 5  # 2 successful streams + 3 bounded failures → gave up
    assert streams[1].closed  # dropped streams are closed before reconnecting


@pytest.mark.asyncio
async def test_consume_forever_gives_up_after_bounded_attempts():
    dispatch = _Dispatch()
    opens = {"n": 0}

    async def always_failing_factory():
        opens["n"] += 1
        raise ConnectionError("ARI unreachable")

    consumer = _consumer(
        dispatch,
        open_stream=always_failing_factory,
        reconnect_initial_seconds=0,
        reconnect_delay_seconds=0,
        max_attempts=3,
    )
    await asyncio.wait_for(consumer.consume_forever(), timeout=5)
    assert opens["n"] == 3
    assert dispatch.calls == []  # nothing fabricated while the PBX was down


# ---------------------------------------------------------------------- #
# provider selection (operator-controlled, simulated stays default)
# ---------------------------------------------------------------------- #
def test_default_provider_stays_simulated_and_selection_fails_loudly(monkeypatch):
    _force_settings(monkeypatch,
                    asterisk_telephony_enabled=False,
                    twilio_account_sid="",
                    twilio_auth_token="",
                    telnyx_api_key="")
    service = TelephonyService()

    assert service.get_provider().provider_name == "simulated"  # auto mode
    with pytest.raises(ProviderError) as exc_info:
        service.get_provider("asterisk")
    assert "ASTERISK_TELEPHONY_ENABLED" in str(exc_info.value)


def test_explicit_asterisk_selection_when_fully_configured(monkeypatch):
    _force_settings(monkeypatch,
                    asterisk_telephony_enabled=True,
                    asterisk_ari_base_url="http://127.0.0.1:8088",
                    asterisk_ari_username="talkflow-lab",
                    asterisk_ari_password="local-lab-pw",
                    asterisk_allowed_extensions="1001,1002",
                    twilio_account_sid="",
                    telnyx_api_key="")
    service = TelephonyService()

    assert service.get_provider("asterisk").provider_name == "asterisk"
    # Auto mode never selects Asterisk — even when explicitly enabled.
    assert service.get_provider().provider_name == "simulated"


def test_provider_status_reflects_explicit_asterisk_selection(monkeypatch):
    """Provider visibility requirement: explicit selection must show honestly,
    and local SIP never advertises PSTN availability."""
    import asyncio

    import app.routers.telephony as tele_router
    import app.telephony.service as tele_service

    class _FakeProvider:
        def is_ready(self) -> bool:
            return True

    class _FakeService:
        def get_registered_provider(self, name: str):
            return _FakeProvider() if name == "asterisk" else None

    _force_settings(monkeypatch, telephony_provider="asterisk")
    monkeypatch.setattr(tele_service, "get_telephony_service", lambda: _FakeService())
    result = asyncio.run(tele_router.get_provider_status())

    assert result["active_provider"] == "asterisk"
    assert result["real_pstn_available"] is False  # local SIP is NOT PSTN
    assert result["setup_required"] is False  # reflects readiness, not heuristic
    assert "asterisk" in result["setup_guide"]
