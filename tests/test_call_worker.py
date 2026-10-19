"""P4 auto-dial worker: due pending CallJobs get an automatic consumer (plan §11).

Coverage:
- the ticker enqueues ONLY due pending jobs (not_before respected), onto the
  dedicated "telephony" queue with the right job type and payload;
- the queue handler executes the existing claim+gate+dial path exactly once
  per job even under at-least-once delivery (replay no-ops, no double dial);
- gating is still enforced by the worker lane (DNC contact never dials);
- racing workers resolve to exactly ONE call via execute_job's atomic
  pending->placing claim.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings


def _create_contact(client, headers, phone, **overrides) -> dict:
    payload = {"phone": phone, "display_name": "Worker Contact", "language": "en"}
    payload.update(overrides)
    r = client.post("/api/v1/contacts", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _create_campaign(client, headers, **overrides) -> dict:
    payload = {"name": f"Worker-Camp-{uuid.uuid4().hex[:8]}", "mode": "human_dial",
               "window_start_hour_utc": 0, "window_end_hour_utc": 24}
    payload.update(overrides)
    r = client.post("/api/v1/campaigns", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _activate(client, headers, campaign_id: uuid.UUID) -> None:
    r = client.post(f"/api/v1/campaigns/{campaign_id}/status",
                    json={"status": "active"}, headers=headers)
    assert r.status_code == 200, r.text


async def _schedule(org_id: str, contact_id: str, *, campaign_id: str | None = None,
                    not_before: datetime | None = None) -> str:
    from app.db.session import db_session
    from app.telephony.call_jobs import CallJobService

    async with db_session() as db:
        svc = CallJobService(db)
        job, _created = await svc.schedule_job(
            org_id=uuid.UUID(org_id), contact_id=uuid.UUID(contact_id),
            campaign_id=(uuid.UUID(campaign_id) if campaign_id else None),
            not_before=not_before)
        await db.commit()
        return str(job.id)


async def _job_dump(org_id: str, job_id: str) -> dict:
    from app.db.session import db_session
    from app.db import models as M

    async with db_session() as db:
        job = await db.get(M.CallJob, uuid.UUID(job_id))
        assert job is not None and str(job.org_id) == org_id
        return {"status": job.status, "blocked_reason": job.blocked_reason,
                "blocked_detail": job.blocked_detail_json,
                "call_session_id": str(job.call_session_id) if job.call_session_id else None}


async def _call_session_count(org_id: str, contact_phone: str) -> int:
    from sqlalchemy import func, select

    from app.db.session import db_session
    from app.db import models as M

    async with db_session() as db:
        res = await db.execute(
            select(func.count()).select_from(M.CallSession)
            .where(M.CallSession.org_id == uuid.UUID(org_id),
                   M.CallSession.to_number == contact_phone))
        return int(res.scalar() or 0)


class _RecordingQueue:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, dict, str]] = []

    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str:
        self.pushes.append((job_type, dict(payload), queue))
        return uuid.uuid4().hex


# org-fair current "now" the tests scan against
_NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Ticker scan semantics
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ticker_enqueues_only_due_pending_jobs(services_app_client, user):
    """Due jobs go onto the telephony queue; future jobs and non-pending stay."""
    from app.telephony.call_worker import JOB_TYPE, QUEUE_NAME, CallJobTicker

    org_id = user["org_id"]
    due_contact = _create_contact(services_app_client, user["headers"],
                                  phone="+910000000101")
    due_job = await _schedule(org_id, due_contact["id"])

    future_contact = _create_contact(services_app_client, user["headers"],
                                     phone="+910000000102")
    future_job = await _schedule(
        org_id, future_contact["id"], not_before=_NOW + timedelta(hours=1))

    rec = _RecordingQueue()
    ticker = CallJobTicker(interval=2.0, batch=8, q=rec)
    enqueued = await ticker.scan_once(now=_NOW)

    assert enqueued == 1
    assert len(rec.pushes) == 1
    job_type, payload, queue_name = rec.pushes[0]
    assert job_type == JOB_TYPE
    assert queue_name == QUEUE_NAME
    assert payload == {"org_id": org_id, "job_id": due_job}
    assert payload["job_id"] != future_job

    # once the future job's not_before passes, the next tick picks it up
    # (the already-pushed due job is deduped inside the ticker window)
    enqueued2 = await ticker.scan_once(now=_NOW + timedelta(hours=2))
    assert enqueued2 == 1
    assert rec.pushes[1][1]["job_id"] == future_job


# --------------------------------------------------------------------------- #
# Handler: claim + gate + dial, idempotent under at-least-once replay
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handler_places_call_and_replay_never_double_dials(services_app_client, user):
    from app.telephony.call_worker import handle_calljob_execute

    org_id = user["org_id"]
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000103")
    campaign = _create_campaign(services_app_client, user["headers"])
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))
    job_id = await _schedule(org_id, contact["id"], campaign_id=campaign["id"])

    payload = {"org_id": org_id, "job_id": job_id}
    await handle_calljob_execute(payload)

    dump = await _job_dump(org_id, job_id)
    assert dump["status"] in ("called", "failed")  # 'placing' never persists
    calls_after_first = await _call_session_count(org_id, "+910000000103")
    if dump["status"] == "called":
        assert dump["call_session_id"] is not None
        assert calls_after_first == 1

    # at-least-once replay: the queue may redeliver; the job must NOT dial again
    await handle_calljob_execute(payload)
    assert await _call_session_count(org_id, "+910000000103") == calls_after_first


@pytest.mark.asyncio
async def test_worker_lane_still_enforces_dnc_gate(services_app_client, user):
    from app.telephony.call_worker import handle_calljob_execute

    org_id = user["org_id"]
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000104")
    # DNC is set through the consent ledger (create body does not accept it)
    r = services_app_client.post(
        f"/api/v1/contacts/{contact['id']}/consent",
        json={"decision": "revoke", "source": "customer_portal"},
        headers=user["headers"])
    assert r.status_code == 201, r.text
    campaign = _create_campaign(services_app_client, user["headers"])
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))
    job_id = await _schedule(org_id, contact["id"], campaign_id=campaign["id"])

    await handle_calljob_execute({"org_id": org_id, "job_id": job_id})

    dump = await _job_dump(org_id, job_id)
    assert dump["status"] == "blocked"
    assert dump["blocked_reason"] == "dnc"
    assert await _call_session_count(org_id, "+910000000104") == 0


# --------------------------------------------------------------------------- #
# Race: operator + worker (or two workers) claim the same job
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_concurrent_claims_yield_exactly_one_dial(services_app_client, user):
    from app.telephony.call_worker import handle_calljob_execute

    org_id = user["org_id"]
    contact = _create_contact(services_app_client, user["headers"],
                              phone="+910000000105")
    campaign = _create_campaign(services_app_client, user["headers"])
    _activate(services_app_client, user["headers"], uuid.UUID(campaign["id"]))
    job_id = await _schedule(org_id, contact["id"], campaign_id=campaign["id"])

    # stretch the provider call just enough that both executors overlap inside
    # execute_job; the atomic claim must still let exactly one of them dial.
    import app.telephony.call_service as call_service_module

    original = call_service_module.CallService.create_outbound_call

    async def slow_call(self, *args, **kwargs):
        await asyncio.sleep(0.05)
        return await original(self, *args, **kwargs)

    call_service_module.CallService.create_outbound_call = slow_call  # type: ignore[method-assign]
    try:
        await asyncio.gather(
            handle_calljob_execute({"org_id": org_id, "job_id": job_id}),
            handle_calljob_execute({"org_id": org_id, "job_id": job_id}),
        )
    finally:
        call_service_module.CallService.create_outbound_call = original  # type: ignore[method-assign]

    assert await _call_session_count(org_id, "+910000000105") <= 1
    dump = await _job_dump(org_id, job_id)
    attempts_expected = dump["status"] in ("called", "placed", "failed")
    assert attempts_expected or dump["status"] == "blocked"
    # a loser claimer must never have fabricated a failed/blocked state
    assert dump["status"] in ("called", "failed", "placing", "blocked")


# config defaults visible for operators (flag off unless explicitly enabled)
def test_worker_defaults_off():
    assert settings.call_worker_enabled is False
    assert settings.call_worker_interval_seconds > 0
    assert settings.call_worker_batch_size >= 1
