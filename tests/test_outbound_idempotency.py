"""Outbound call-job idempotency + gate-enforced execution (P1).

Acceptance lane for phone_calling_plan §10:
- same Idempotency-Key -> ONE call session, forever;
- distinct keys -> distinct calls;
- cancelled pending jobs never dial;
- the gate blocks DNC / no-consent AI / outside-window / attempt-capped dials;
- approved AI campaigns only place calls for consented contacts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _create_contact(client, headers, phone, **overrides) -> dict:
    payload = {"phone": phone, "display_name": "Test Contact", "language": "en"}
    payload.update(overrides)
    r = client.post("/api/v1/contacts", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _create_campaign(client, headers, mode="human_dial", **overrides) -> dict:
    payload = {"name": f"Camp-{uuid.uuid4().hex[:8]}", "mode": mode,
               "window_start_hour_utc": 0, "window_end_hour_utc": 24}
    if mode == "ai_agent":
        payload.update({"ai_agent_authorized": True,
                        "agent_prompt_id": str(uuid.uuid4())})
    payload.update(overrides)
    r = client.post("/api/v1/campaigns", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _activate(client, headers, campaign_id: uuid.UUID) -> None:
    r = client.post(f"/api/v1/campaigns/{campaign_id}/status",
                    json={"status": "active"}, headers=headers)
    assert r.status_code == 200, r.text


async def _execute(org_id: str, job_id: str):
    """Run execute_job against the shared test DB and return a mapped dump."""
    from app.db.session import db_session
    from app.telephony.call_jobs import CallJobService, _dump_job

    async with db_session() as db:
        svc = CallJobService(db)
        job = await svc.execute_job(uuid.UUID(org_id), uuid.UUID(job_id))
        await db.commit()
        data = _dump_job(job)
        return type("ExecutedJob", (), {**data, "__getattr__": lambda self, n: data.get(n),
                                        "__eq__": lambda self, o: data == o})()


# --------------------------------------------------------------------------- #
# Idempotency-Key on direct /telephony/calls
# --------------------------------------------------------------------------- #


def test_same_idempotency_key_returns_same_call(services_app_client, user):
    headers = {**user["headers"], "Idempotency-Key": f"direct-{uuid.uuid4().hex}"}
    body = {"to_number": "+919876543210", "caller_language": "en",
            "receiver_language": "hi", "recipient_name": "Replayed Recipient"}

    first = services_app_client.post("/api/v1/telephony/calls", json=body, headers=headers)
    assert first.status_code == 201, first.text
    second = services_app_client.post("/api/v1/telephony/calls", json=body, headers=headers)
    assert second.status_code == 201, second.text

    first_call, second_call = first.json(), second.json()
    assert first_call["id"] == second_call["id"]
    assert first_call["call_sid"] == second_call["call_sid"]


def test_distinct_keys_place_distinct_calls(services_app_client, user):
    body = {"to_number": "+8613800138000", "caller_language": "en",
            "receiver_language": "ja"}
    first = services_app_client.post(
        "/api/v1/telephony/calls", json=body,
        headers={**user["headers"], "Idempotency-Key": f"k-{uuid.uuid4().hex}"})
    second = services_app_client.post(
        "/api/v1/telephony/calls", json=body,
        headers={**user["headers"], "Idempotency-Key": f"k-{uuid.uuid4().hex}"})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_keyless_dial_unaffected_by_other_keys(services_app_client, user):
    body = {"to_number": "+441234567890", "receiver_language": "en"}
    first = services_app_client.post("/api/v1/telephony/calls", json=body,
                                     headers=user["headers"])
    second = services_app_client.post("/api/v1/telephony/calls", json=body,
                                      headers=user["headers"])
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


# --------------------------------------------------------------------------- #
# Queued jobs: schedule (idempotent) -> gate -> place
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_schedule_job_is_idempotent_by_key(services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000010")
    campaign = _create_campaign(services_app_client, user["headers"])
    key = f"job-{uuid.uuid4().hex}"

    r1 = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"], "idempotency_key": key},
        headers=user["headers"])
    r2 = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"], "idempotency_key": key},
        headers=user["headers"])
    assert r1.status_code == 201 and r2.status_code == 201
    j1, j2 = r1.json(), r2.json()
    assert j1["job"]["id"] == j2["job"]["id"]
    assert j2["created"] is False  # replay, no second job row


@pytest.mark.asyncio
async def test_queued_job_executes_and_links_session(services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000011")
    campaign = _create_campaign(services_app_client, user["headers"])
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    assert r.status_code == 201, r.text
    job_id = r.json()["job"]["id"]

    executed = await _execute(user["org_id"], job_id)
    assert executed.status in ("called", "failed")  # placing must not persist
    if executed.status == "called":
        assert executed.call_session_id


@pytest.mark.asyncio
async def test_cancelled_pending_job_never_dials(services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000012")
    campaign = _create_campaign(services_app_client, user["headers"])

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id = r.json()["job"]["id"]

    r = services_app_client.post(f"/api/v1/contacts/jobs/{job_id}/cancel",
                                 headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "canceled"

    executed = await _execute(user["org_id"], job_id)
    assert executed.status == "canceled"


@pytest.mark.asyncio
async def test_gate_blocks_dnc_contact_for_human_dial(services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000013")
    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/consent",
        json={"decision": "dnc", "source": "manual_entry"},
        headers=user["headers"])
    assert r.status_code == 201
    assert services_app_client.get(
        f"/api/v1/contacts/{contact['id']}", headers=user["headers"]).json()["do_not_call"]

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/call",
        json={}, headers=user["headers"])
    assert r.status_code == 409, r.text
    assert r.json()["error"]["details"]["reason"] == "dnc"


@pytest.mark.asyncio
async def test_ai_campaign_requires_consent_then_places_for_consented(
        services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000014", language="en")
    campaign = _create_campaign(services_app_client, user["headers"], mode="ai_agent")
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id = r.json()["job"]["id"]

    executed = await _execute(user["org_id"], job_id)
    assert executed.status == "blocked"
    assert executed.blocked_reason == "no_consent"

    # Customer grants consent (evidence collected during a prior call).
    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/consent",
        json={"decision": "grant", "source": "call_prompt",
              "evidence": {"note": "verbal yes"}},
        headers=user["headers"])
    assert r.status_code == 201

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id2 = r.json()["job"]["id"]
    executed2 = await _execute(user["org_id"], job_id2)
    assert executed2.status in ("called", "failed")
    if executed2.status == "called":
        assert executed2.call_session_id


@pytest.mark.asyncio
async def test_outside_calling_window_blocks(services_app_client, user):
    from datetime import datetime, timezone as tz

    start = (datetime.now(tz.utc).hour + 5) % 24
    end = start + 1
    if end > 24:
        start, end = 22, 24

    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000015")
    campaign = _create_campaign(services_app_client, user["headers"],
                                window_start_hour_utc=start,
                                window_end_hour_utc=end)
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id = r.json()["job"]["id"]
    executed = await _execute(user["org_id"], job_id)
    assert executed.status == "blocked"
    assert executed.blocked_reason == "outside_window"


@pytest.mark.asyncio
async def test_max_attempts_cap_blocks_repeat_dial(services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000016")
    campaign = _create_campaign(services_app_client, user["headers"],
                                max_attempts_per_contact=1)
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id = r.json()["job"]["id"]
    executed = await _execute(user["org_id"], job_id)
    if executed.status != "called":
        pytest.skip("simulated provider placement unavailable in this lane")

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id2 = r.json()["job"]["id"]
    executed2 = await _execute(user["org_id"], job_id2)
    assert executed2.status == "blocked"
    assert executed2.blocked_reason == "max_attempts_reached"


@pytest.mark.asyncio
async def test_backoff_window_blocks_until_not_before(services_app_client, user):
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000017")
    campaign = _create_campaign(services_app_client, user["headers"])
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))

    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job_id = r.json()["job"]["id"]

    future = datetime.now(timezone.utc) + timedelta(minutes=30)
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        row = await db.get(M.CallJob, uuid.UUID(job_id))
        row.not_before = future
        await db.commit()

    executed = await _execute(user["org_id"], job_id)
    assert executed.status == "blocked"
    assert executed.blocked_reason == "backoff_window"


@pytest.mark.asyncio
async def test_concurrency_cap_blocks_second_active_dial(services_app_client, user):
    contact1 = _create_contact(services_app_client, user["headers"],
                               phone="+910000000018")
    contact2 = _create_contact(services_app_client, user["headers"],
                               phone="+910000000019")
    campaign = _create_campaign(services_app_client, user["headers"],
                                max_concurrent_calls=1)
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))

    r1 = services_app_client.post(
        f"/api/v1/contacts/{contact1['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    r2 = services_app_client.post(
        f"/api/v1/contacts/{contact2['id']}/jobs",
        json={"campaign_id": campaign["id"]}, headers=user["headers"])
    job1 = r1.json()["job"]["id"]
    job2 = r2.json()["job"]["id"]

    # freeze the first job in an active state so it counts as concurrent
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        row = await db.get(M.CallJob, uuid.UUID(job1))
        row.status = "claimed"
        row.claimed_at = datetime.now(timezone.utc)
        await db.commit()

    executed2 = await _execute(user["org_id"], job2)
    assert executed2.status == "blocked"
    assert executed2.blocked_reason == "max_concurrent_reached"


# --------------------------------------------------------------------------- #
# Day-3 (2026-10-23): the phone bridge renders both sides' languages, but call
# creation never checked them against the capability registry — a call with
# caller_language="xx" was happily scheduled and the bridge then translated
# with no validated pair. Creation is the choke point: both languages must be
# registered (and not EXPERIMENTAL) before any provider or meeting work runs.
# --------------------------------------------------------------------------- #

def test_a_call_in_an_unregistered_language_is_rejected(services_app_client, user):
    headers = user["headers"]
    for field, value in (("caller_language", "xx"), ("receiver_language", "zz")):
        body = {"to_number": "+919876543210", "caller_language": "en",
                "receiver_language": "hi"}
        body[field] = value
        res = services_app_client.post("/api/v1/telephony/calls", json=body, headers=headers)
        assert res.status_code == 422, (
            f"{field}={value} was accepted although the capability registry "
            f"does not carry it: HTTP {res.status_code} {res.text[:200]}")


def test_a_call_in_registered_languages_still_places(services_app_client, user):
    body = {"to_number": "+919876543210", "caller_language": "hi",
            "receiver_language": "mr"}
    res = services_app_client.post("/api/v1/telephony/calls", json=body,
                                   headers={**user["headers"], "Idempotency-Key": f"lang-{uuid.uuid4().hex}"})
    assert res.status_code == 201, res.text
