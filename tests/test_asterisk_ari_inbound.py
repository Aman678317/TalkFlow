"""Inbound Stasis leg intake — P3 lab decision acceptance (deterministic).

docs/ASTERISK_LOCAL_SIP_LAB.md §P3 "Inbound Stasis legs":
- dialplan shape `Stasis(talkflow,inbound)` only; other args stay ignored;
- caller AND dialed exten must both be allowlisted local extensions, and the
  owning org explicitly configured — anything else is rejected BEFORE any
  session row exists (best-effort hangup, no invented state);
- an accepted leg joins the outbound correlation machinery: channel map
  seeded, lifecycle ringing → connected → ended through the existing
  normalizer, exactly one terminal claim, reconnect- AND restart-safe
  (deterministic call_sid absorbs re-deliveries).
No Asterisk, no sockets: the intake is driven with synthetic ARI payloads and
the app's real SQLite session/event machinery.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.telephony.ari_client import ARIConfig
from app.telephony.ari_events import (
    AsteriskARIEventConsumer,
    build_call_service_dispatch,
    normalize_ari_event,
)
from app.telephony.ari_inbound import InboundIntake, inbound_call_sid
from app.telephony.base import CallStatus


def _force_settings(monkeypatch, **values: Any) -> None:
    """Force settings on every binding the product may read (same rationale
    as tests/test_asterisk_ari_adapter.py — the app fixture's app.config
    reload can fork module-owned bindings from the current singleton)."""
    import app.config as cfg
    import app.telephony.service as svc

    holders = {id(cfg.settings): cfg.settings, id(svc.settings): svc.settings}
    for holder in holders.values():
        for name, value in values.items():
            monkeypatch.setattr(holder, name, value, raising=False)


def stasis_start(channel_id: str = "PJSIP/1001-0000000f",
                 caller: str = "1001", exten: str = "1002",
                 args: tuple[str, ...] = ("inbound",),
                 caller_name: str = "Lab Ext") -> dict[str, Any]:
    return {
        "type": "StasisStart",
        "args": list(args),
        "channel": {
            "id": channel_id,
            "name": f"PJSIP/{caller}-00000001",
            "state": "Ring",
            "caller": {"number": caller, "name": caller_name},
            "dialplan": {"exten": exten, "context": "talkflow-inbound"},
        },
    }


class Recorders:
    def __init__(self) -> None:
        self.answered: list[str] = []
        self.hungup: list[str] = []

    async def answer(self, channel_id: str) -> None:
        self.answered.append(channel_id)

    async def hangup(self, channel_id: str) -> None:
        self.hungup.append(channel_id)


def make_intake(org_id: uuid.UUID | None, rec: Recorders,
                *, allowed: tuple[str, ...] = ("1001", "1002"),
                channel_map: dict[str, str] | None = None,
                dispatch=None) -> tuple[InboundIntake, dict[str, str]]:
    channel_map = channel_map if channel_map is not None else {}
    intake = InboundIntake(
        dispatch=dispatch or build_call_service_dispatch(),
        channel_map=channel_map,
        org_id=org_id,
        allowed_extensions=allowed,
        answer=rec.answer,
        hangup=rec.hangup,
    )
    return intake, channel_map


async def _events_for_sid(call_sid: str) -> list[tuple[str, str]]:
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession).where(M.CallSession.call_sid == call_sid))
        call = res.scalars().one()
        res = await db.execute(
            select(M.CallEvent)
            .where(M.CallEvent.call_id == call.id)
            .order_by(M.CallEvent.created_at))
        return [(row.event_type, str(row.payload_json.get("status")))
                for row in res.scalars().all()]


# --------------------------------------------------------------------------- #
# accepted legs
# --------------------------------------------------------------------------- #

async def test_accepted_inbound_leg_creates_session_rings_and_answers(
        services_app_client, user) -> None:
    rec = Recorders()
    intake, channel_map = make_intake(uuid.UUID(user["org_id"]), rec)
    ch = f"PJSIP/1001-{uuid.uuid4().hex[:8]}"
    payload = stasis_start(ch)
    frame = normalize_ari_event(payload)
    assert frame is not None

    handled = await intake(payload, frame)

    assert handled is True
    sid = inbound_call_sid(ch)
    assert rec.answered == [ch]
    assert rec.hungup == []
    assert channel_map == {ch: sid}
    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession).where(M.CallSession.call_sid == sid))
        call = res.scalars().one()
    assert call.direction == "inbound"
    assert call.mode == "ai_agent"
    assert call.provider == "asterisk"
    assert call.status == CallStatus.RINGING.value
    assert call.from_number == "1001"
    assert call.to_number == "1002"
    assert call.caller_name == "Lab Ext"
    assert call.metadata_json["ari_channel"] == ch
    assert call.metadata_json["source"] == "asterisk_ari_inbound"
    events = await _events_for_sid(sid)
    assert events == [("status_change", CallStatus.RINGING.value)]


async def test_inbound_leg_lifecycle_flows_through_consumer(
        services_app_client, user) -> None:
    rec = Recorders()
    org_id = uuid.UUID(user["org_id"])
    dispatch = build_call_service_dispatch()
    intake, channel_map = make_intake(
        org_id, rec, channel_map={}, dispatch=dispatch)
    consumer = AsteriskARIEventConsumer(
        ARIConfig(app_name="talkflow"), dispatch=dispatch,
        channel_map=channel_map, inbound_intake=intake)
    ch = f"PJSIP/1002-{uuid.uuid4().hex[:8]}"

    await consumer.process_ari_payload(stasis_start(ch, caller="1002"))
    await consumer.process_ari_payload(
        {"type": "ChannelStateChange",
         "channel": {"id": ch, "state": "Up"}})
    await consumer.process_ari_payload(
        {"type": "ChannelDestroyed", "channel": {"id": ch}, "cause": 16})
    # A late duplicate terminal (WS reconnect re-delivery) is absorbed.
    await consumer.process_ari_payload(
        {"type": "StasisEnd", "channel": {"id": ch}, "cause": 16})

    sid = inbound_call_sid(ch)
    events = await _events_for_sid(sid)
    assert events == [
        ("status_change", CallStatus.RINGING.value),
        ("status_change", CallStatus.CONNECTED.value),
        ("status_change", CallStatus.ENDED.value),
    ]
    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession).where(M.CallSession.call_sid == sid))
        call = res.scalars().one()
    assert call.status == CallStatus.ENDED.value
    assert call.ended_at is not None
    assert rec.answered == [ch]


async def test_redelivered_stasis_start_is_absorbed(
        services_app_client, user) -> None:
    rec = Recorders()
    intake, _ = make_intake(uuid.UUID(user["org_id"]), rec)
    ch = f"PJSIP/1001-{uuid.uuid4().hex[:8]}"
    payload = stasis_start(ch)

    first = await intake(payload, normalize_ari_event(payload))
    second = await intake(payload, normalize_ari_event(payload))

    assert (first, second) == (True, True)
    sid = inbound_call_sid(ch)
    assert rec.answered == [ch]  # answered once
    events = await _events_for_sid(sid)
    assert events == [("status_change", CallStatus.RINGING.value)]


async def test_restart_redelivery_reseeds_without_duplicating(
        services_app_client, user) -> None:
    # The session already exists (created before a restart); a fresh intake
    # (empty handled set, empty channel map) must re-seed the map and NOT
    # duplicate the session nor re-ring it.
    ch = "PJSIP/1001-00000017"
    sid = inbound_call_sid(ch)
    rec = Recorders()
    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        db.add(M.CallSession(
            org_id=uuid.UUID(user["org_id"]), created_by=None,
            call_sid=sid, direction="inbound", from_number="1001",
            to_number="1002", status="connected", mode="ai_agent",
            provider="asterisk",
            metadata_json={"ari_channel": ch,
                           "source": "asterisk_ari_inbound"}))
        await db.commit()

    intake, channel_map = make_intake(uuid.UUID(user["org_id"]), rec)
    handled = await intake(stasis_start(ch), normalize_ari_event(stasis_start(ch)))

    assert handled is True
    assert channel_map == {ch: sid}
    assert rec.answered == []  # no answer re-issue for a connected leg
    assert rec.hungup == []
    async with db_session() as db:
        res = await db.execute(select(M.CallSession)
                               .where(M.CallSession.call_sid == sid))
        assert len(list(res.scalars().all())) == 1
    events = await _events_for_sid(sid)
    assert events == []  # no fabricated RINGING over a connected call


# --------------------------------------------------------------------------- #
# rejections — no state, ever
# --------------------------------------------------------------------------- #

async def test_unknown_caller_is_rejected_before_any_state(
        services_app_client, user) -> None:
    rec = Recorders()
    intake, channel_map = make_intake(uuid.UUID(user["org_id"]), rec)
    payload = stasis_start(caller="9999")  # not an allowlisted AOR

    handled = await intake(payload, normalize_ari_event(payload))

    assert handled is True
    assert rec.hungup == ["PJSIP/1001-0000000f"]
    assert rec.answered == []
    assert channel_map == {}
    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        rows = list((await db.execute(
            select(M.CallSession)
            .where(M.CallSession.org_id == uuid.UUID(user["org_id"]))
        )).scalars().all())
    assert rows == []


async def test_inbound_rejects_everything_when_org_unconfigured(
        services_app_client, user) -> None:
    rec = Recorders()
    intake, _ = make_intake(None, rec)

    handled = await intake(stasis_start(), normalize_ari_event(stasis_start()))

    assert handled is True
    assert rec.hungup == ["PJSIP/1001-0000000f"]
    assert rec.answered == []
    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        rows = list((await db.execute(
            select(M.CallSession)
            .where(M.CallSession.org_id == uuid.UUID(user["org_id"]))
        )).scalars().all())
    assert rows == []


@pytest.mark.parametrize("args", [("translation",), ("inbound", "extra"), []])
async def test_route_arg_must_match_exactly(args, services_app_client, user):
    rec = Recorders()
    intake, channel_map = make_intake(uuid.UUID(user["org_id"]), rec)
    payload = stasis_start(args=args)

    handled = await intake(payload, normalize_ari_event(payload))

    assert handled is False  # not an inbound leg: left to the normal path
    assert rec.answered == [] and rec.hungup == []
    assert channel_map == {}
    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        rows = list((await db.execute(
            select(M.CallSession)
            .where(M.CallSession.org_id == uuid.UUID(user["org_id"]))
        )).scalars().all())
    assert rows == []


# --------------------------------------------------------------------------- #
# settings wiring
# --------------------------------------------------------------------------- #

class _FakeAriWithAnswer:
    def __init__(self) -> None:
        self.answered: list[str] = []
        self.hungup: list[str] = []

    async def answer(self, channel_id: str) -> None:
        self.answered.append(channel_id)

    async def hangup(self, channel_id: str) -> None:
        self.hungup.append(channel_id)


class _FakeProvider:
    def __init__(self) -> None:
        self.channel_map: dict[str, str] = {}
        self.ari = _FakeAriWithAnswer()


async def test_from_settings_arms_inbound_intake_when_enabled(monkeypatch) -> None:
    _force_settings(monkeypatch,
                    asterisk_inbound_enabled=True,
                    asterisk_inbound_org_id=str(uuid.uuid4()),
                    asterisk_allowed_extensions="1001,1002")
    provider = _FakeProvider()

    consumer = AsteriskARIEventConsumer.from_settings(provider=provider)

    assert consumer.inbound_intake is not None
    assert consumer.channel_map is provider.channel_map  # map is SHARED
    # the intake rejects through the same allowlist + the provider's hangup
    payload = stasis_start(caller="9999")
    frame = normalize_ari_event(payload)
    assert frame is not None
    assert consumer.inbound_intake is not None
    handled = await consumer.inbound_intake(payload, frame)
    assert handled is True
    assert provider.ari.hungup == ["PJSIP/1001-0000000f"]
    assert provider.ari.answered == []


def test_from_settings_leaves_inbound_disarmed_by_default(monkeypatch) -> None:
    _force_settings(monkeypatch, asterisk_inbound_enabled=False)
    consumer = AsteriskARIEventConsumer.from_settings(provider=_FakeProvider())
    assert consumer.inbound_intake is None
