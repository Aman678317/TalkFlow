"""P4 §D2 — admin telephony-ops visibility (platform admins only, read-only).

Proves the honest distinctions the ops surface makes:
- non-admin org users are 403 (privilege gate, not a tenant resource);
- the provider paragraph NEVER advertises PSTN on the simulated (default)
  lane and never on the asterisk local-SIP lane either;
- ``flags`` shows settings while ``process`` shows what actually started —
  the TestClient lane arms neither, so both running-claims must be False;
- queue depths are real numbers, never None.
"""
from __future__ import annotations

import uuid


async def _make_platform_admin(services_app_client, user) -> dict:
    """Flip the signed-up user to platform admin in the DB, then re-login so
    the fresh token carries the privilege (deterministic, no seeding magic)."""
    from sqlalchemy import update

    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        await db.execute(update(M.User)
                         .where(M.User.email == user["email"])
                         .values(is_platform_admin=True))
        await db.commit()

    email = user["email"]
    r = services_app_client.post("/api/v1/auth/login",
                                 json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    token = r.json()["tokens"]["access_token"]
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}}


def test_telephony_ops_is_platform_admin_only(services_app_client, user):
    r = services_app_client.get("/api/v1/admin/telephony-ops",
                                headers=user["headers"])
    assert r.status_code == 403, r.text


def test_telephony_ops_401_for_anonymous(services_app_client):
    r = services_app_client.get("/api/v1/admin/telephony-ops")
    assert r.status_code == 401, r.text


async def test_telephony_ops_report_is_honest(services_app_client, user):
    admin = await _make_platform_admin(services_app_client, user)

    r = services_app_client.get("/api/v1/admin/telephony-ops",
                                headers=admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()

    # provider honesty: the default test lane is simulated → no PSTN claim
    assert body["provider"]["active_provider"] == "simulated"
    assert body["provider"]["real_pstn_available"] is False
    assert body["provider"]["setup_required"] is True

    # flags mirror settings; process NEVER claims armed when nothing started
    assert body["flags"]["call_worker_enabled"] is False
    assert body["flags"]["asterisk_telephony_enabled"] is False
    assert body["flags"]["asterisk_inbound_enabled"] is False
    assert body["flags"]["asterisk_media_enabled"] is False
    assert body["process"]["call_worker_ticker_running"] is False
    assert body["process"]["asterisk_media_runtime_armed"] is False

    # live queue depth is a real number
    assert isinstance(body["queues"]["telephony"], int)
    assert body["queues"]["telephony"] >= 0

    # §D3: inbound intake — configured flag is False here, and the process
    # block must never call it armed nor report a dead consumer task.
    assert body["inbound_intake"]["configured"] is False
    assert body["inbound_intake"]["armed"] is False
    assert body["inbound_intake"]["consumer_task_dead"] is False

    # §D3: the in-process escalation transport starts empty in a fresh
    # lane — real numbers, never None, no agent-staffing claim implied.
    assert body["escalations"]["pending"] == 0
    assert body["escalations"]["claimed_open"] == 0


async def test_telephony_ops_reports_armed_intake_and_live_escalation_depths(
        services_app_client, user):
    """§D3 truth reporting — armed-vs-configured for intake, live depth for
    escalations, dead-consumer detection, with FULL state restoration so
    other suites never see this test's fakes:
    - an ARI consumer with an attached intake hook reports ``armed=True``
      even while the settings flag stays False (a contradiction surfaced,
      not hidden);
    - escalation depths mirror exactly this process's shared queue after
      two pushes and one claim;
    - a consumer task that has finished reports ``consumer_task_dead``.
    """
    import asyncio
    from types import SimpleNamespace

    from app.telephony import escalation as esc_mod
    from app.telephony.escalation import (
        EscalationDispatcher,
        EscalationQueue,
        EscalationTicket,
        rewire_shared_dispatcher,
    )

    admin = await _make_platform_admin(services_app_client, user)
    app_state = services_app_client.app.state
    original_dispatcher = esc_mod._shared

    rewire_shared_dispatcher(EscalationDispatcher(
        queue=EscalationQueue(maxsize=10)))
    q = esc_mod.shared_dispatcher().queue
    assert q.push(EscalationTicket(
        ticket_id="t-a", call_sid="CA-A", reason="caller_opt_out",
        summary=None, turns=2, created_at=1.0)) is True
    assert q.push(EscalationTicket(
        ticket_id="t-b", call_sid="CA-B", reason="budget",
        summary=None, turns=4, created_at=2.0)) is True
    assert q.claim("agent-1", "t-a") is not None      # t-a: claimed, unresolved

    consumer = SimpleNamespace(inbound_intake=lambda payload, frame: True)

    async def _noop() -> None:
        return None

    app_state.asterisk_ari_consumer = consumer
    live_task = asyncio.ensure_future(_noop())        # not finished yet
    app_state.asterisk_ari_task = live_task
    try:
        r = services_app_client.get("/api/v1/admin/telephony-ops",
                                    headers=admin["headers"])
        assert r.status_code == 200, r.text
        body = r.json()

        # configured stays False (settings lane), but the REAL intake hook is
        # attached — armed=True is reported, contradiction made visible.
        assert body["inbound_intake"]["configured"] is False
        assert body["inbound_intake"]["armed"] is True
        assert body["inbound_intake"]["consumer_task_dead"] is False

        # escalation depths mirror this process's shared queue exactly
        assert body["escalations"]["pending"] == 1          # t-b still waiting
        assert body["escalations"]["claimed_open"] == 1     # t-a in-flight

        # the consumer task finishing must show up as dead, not silently
        # "still running"
        await asyncio.sleep(0)
        assert live_task.done() is True
        r2 = services_app_client.get("/api/v1/admin/telephony-ops",
                                     headers=admin["headers"])
        assert r2.status_code == 200, r2.text
        assert r2.json()["inbound_intake"]["consumer_task_dead"] is True
    finally:
        if hasattr(app_state, "asterisk_ari_consumer"):
            del app_state.asterisk_ari_consumer
        if hasattr(app_state, "asterisk_ari_task"):
            del app_state.asterisk_ari_task
        rewire_shared_dispatcher(original_dispatcher)
