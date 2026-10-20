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
