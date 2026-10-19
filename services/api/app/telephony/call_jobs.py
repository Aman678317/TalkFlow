"""Call-job orchestration: idempotent scheduling + gate-enforced dialing.

Every outbound dial through the phonebook goes through:
  schedule_job (idempotent by org + Idempotency-Key) -> execute_job
    -> gate.evaluate (consent/DNC/window/caps, app.telephony.gate)
    -> CallService.create_outbound_call (carrier execution)

Idempotency: (org_id, idempotency_key) is unique — replaying a request with
the same key returns the SAME job and SAME call session; no second PSTN call
is ever placed for one key.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.base import utcnow
from app.errors import NotFoundError, ValidationError
from app.services import audit_service
from app.services.contacts_service import ContactsService
from app.telephony import gate
from app.telephony.call_service import CallService

log = logging.getLogger("app.telephony.call_jobs")

_ATTEMPT_STATUSES = ("called", "failed", "placing", "claimed")
_ACTIVE_STATUSES = ("claimed", "placing")


class CallJobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.contacts = ContactsService(db)
        self.calls = CallService(db)

    # ------------------------------------------------------------------ #
    # Scheduling (idempotent)
    # ------------------------------------------------------------------ #

    async def schedule_job(
        self, *,
        org_id: uuid.UUID,
        contact_id: uuid.UUID,
        campaign_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        actor_id: uuid.UUID | None = None,
        not_before: datetime | None = None,
        metadata: dict | None = None,
    ) -> tuple[M.CallJob, bool]:
        """Create (or return the existing) queued dial. Returns (job, created)."""
        key = (idempotency_key or "").strip()
        if key:
            existing = await self.get_job_by_key(org_id, key)
            if existing is not None:
                return existing, False

        contact = await self.contacts.get_contact(org_id, contact_id)
        campaign: M.Campaign | None = None
        if campaign_id is not None:
            campaign = await self.get_campaign(org_id, campaign_id)
            if campaign.status not in ("draft", "active"):
                raise ValidationError(
                    f"Campaign '{campaign.name}' is {campaign.status}; "
                    "only draft/active campaigns accept new jobs.")

        to_number = contact.phone_e164
        caller_language = (campaign.caller_language if campaign else "en") or "en"
        receiver_language = contact.language
        if campaign is not None and campaign.receiver_language_overrides_contact:
            receiver_language = campaign.caller_language

        job = M.CallJob(
            org_id=org_id,
            contact_id=contact_id,
            campaign_id=campaign_id,
            mode=(campaign.mode if campaign else "human_dial"),
            status="pending",
            idempotency_key=(key or None),
            to_number=to_number,
            from_number=(campaign.from_number if campaign else "") or "",
            caller_language=caller_language,
            receiver_language=receiver_language or "en",
            attempts=0,
            not_before=not_before,
            created_by=actor_id,
            metadata_json=dict(metadata or {}),
        )
        self.db.add(job)
        try:
            await self.db.flush()
        except Exception as exc:  # concurrent replay raced the unique key
            if key:
                await self.db.rollback()
                existing = await self.get_job_by_key_refetch(org_id, key)
                if existing is not None:
                    return existing, False
            raise
        await audit_service.record(
            self.db, action="calljob.schedule", org_id=org_id, actor_id=actor_id,
            resource_type="call_job", resource_id=str(job.id),
            details={"contact_id": str(contact_id),
                     "campaign_id": str(campaign_id) if campaign_id else None,
                     "mode": job.mode})
        return job, True

    async def get_job_by_key(self, org_id: uuid.UUID, key: str) -> M.CallJob | None:
        res = await self.db.execute(
            select(M.CallJob).where(
                M.CallJob.org_id == org_id, M.CallJob.idempotency_key == key))
        return res.scalars().first()

    async def get_job_by_key_refetch(self, org_id: uuid.UUID, key: str) -> M.CallJob | None:
        """Read through a fresh transaction after a rollback."""
        try:
            res = await self.db.execute(
                select(M.CallJob).where(
                    M.CallJob.org_id == org_id, M.CallJob.idempotency_key == key))
            return res.scalars().first()
        except Exception:
            log.exception("refetch after idempotency race failed")
            return None

    async def get_job(self, org_id: uuid.UUID, job_id: uuid.UUID) -> M.CallJob:
        row = await self.db.get(M.CallJob, job_id)
        if row is None or row.org_id != org_id:
            raise NotFoundError("Call job not found.")
        return row

    # ------------------------------------------------------------------ #
    # Gate context (DB aggregation)
    # ------------------------------------------------------------------ #

    async def _gate_input(self, job: M.CallJob) -> tuple[M.Contact, M.Campaign | None, gate.GateInput]:
        contact = await self.db.get(M.Contact, job.contact_id)
        campaign: M.Campaign | None = None
        if job.campaign_id is not None:
            campaign = await self.db.get(M.Campaign, job.campaign_id)

        attempts_res = await self.db.execute(
            select(func.count())
            .select_from(M.CallJob)
            .where(M.CallJob.org_id == job.org_id, M.CallJob.contact_id == job.contact_id,
                   M.CallJob.status.in_(_ATTEMPT_STATUSES),
                   M.CallJob.id != job.id,
                   *([M.CallJob.campaign_id == job.campaign_id] if job.campaign_id else [])))
        contact_attempts = int(attempts_res.scalar() or 0)

        active_res = await self.db.execute(
            select(func.count())
            .select_from(M.CallJob)
            .where(M.CallJob.org_id == job.org_id, M.CallJob.status.in_(_ACTIVE_STATUSES),
                   M.CallJob.id != job.id,
                   *([M.CallJob.campaign_id == job.campaign_id] if job.campaign_id else [])))
        active_calls = int(active_res.scalar() or 0)

        consent: bool | None = None
        if contact is not None:
            consent = await self.contacts.effective_consent(job.org_id, contact.id)

        gi = gate.GateInput(
            mode=job.mode,
            campaign_active=(campaign.status == "active") if campaign else True,
            campaign_ai_authorized=(
                bool(campaign.ai_agent_authorized and campaign.ai_agent_authorized_by) if campaign else False),
            campaign_ai_disclosure_required=(
                bool(campaign.ai_disclosure_required) if campaign else True),
            campaign_agent_prompt_id=(campaign.agent_prompt_id if campaign else None),
            campaign_window_start_hour_utc=campaign.window_start_hour_utc if campaign else 0,
            campaign_window_end_hour_utc=campaign.window_end_hour_utc if campaign else 24,
            campaign_max_attempts=campaign.max_attempts_per_contact if campaign else 10**6,
            campaign_max_concurrent=campaign.max_concurrent_calls if campaign else 10**6,
            contact_do_not_call=bool(contact.do_not_call) if contact is not None else False,
            consent_granted=consent,
            contact_attempts=contact_attempts,
            active_concurrent_calls=active_calls,
            next_attempt_eligible_at=job.not_before,
            now=datetime.now(timezone.utc),
        )
        return contact, campaign, gi

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    async def execute_job(self, org_id: uuid.UUID, job_id: uuid.UUID, *,
                          actor_id: uuid.UUID | None = None,
                          claimed_by_name: str = "") -> M.CallJob:
        """Claim a pending job and, if the gate allows, place the call."""
        job = await self.get_job(org_id, job_id)
        contact, campaign, gi = await self._gate_input(job)

        if job.status in ("called", "blocked", "canceled"):
            return job
        if job.status == "placing":
            return job  # already being handled; idempotent no-op

        decision = gate.evaluate(gi)
        if not decision.allowed:
            job.status = "blocked"
            job.blocked_reason = decision.reason
            job.blocked_detail_json = decision.detail
            job.claimed_at = utcnow()
            job.claimed_by = claimed_by_name[:120]
            await self.db.flush()
            await audit_service.record(
                self.db, action="calljob.blocked", org_id=org_id, actor_id=actor_id,
                resource_type="call_job", resource_id=str(job.id),
                outcome="blocked",
                details={"reason": decision.reason, "detail": decision.detail})
            return job

        # Atomic claim: flip 'pending' -> 'placing' only from 'pending'. Racing
        # executors (operator + auto-dial worker, or several workers) resolve to
        # exactly one winner; the loser re-reads the live state and no-ops. This
        # keeps at-least-once queue delivery from double-dialing one job.
        claim = await self.db.execute(
            update(M.CallJob)
            .where(M.CallJob.id == job.id, M.CallJob.status == "pending")
            .values(
                status="placing",
                claimed_at=utcnow(),
                claimed_by=(claimed_by_name or str(actor_id or ""))[:120],
            )
            .execution_options(synchronize_session="fetch"))
        if claim.rowcount == 0:
            await self.db.refresh(job)
            log.info("call job %s already claimed (status=%s); skipping",
                     job.id, job.status)
            return job
        # Commit the claim BEFORE the (potentially slow) provider dial: the
        # row flips to 'placing' durably so competing executors see it, and we
        # never hold a DB write transaction across a provider round-trip
        # (SQLite/Postgres lock-friendliness). A mid-dial crash can only leave
        # the job in 'placing' — which still cannot double-dial.
        await self.db.commit()

        if contact is None:
            job.status = "blocked"
            job.blocked_reason = "contact_not_found"
            await self.db.flush()
            return job

        try:
            call = await self.calls.create_outbound_call(
                org_id=org_id,
                user_id=actor_id,
                to_number=contact.phone_e164,
                from_number=job.from_number or None,
                caller_language=job.caller_language,
                receiver_language=job.receiver_language,
                caller_name=(campaign.name if campaign else contact.display_name) or "Caller",
                recipient_name=contact.display_name or "",
                mode=("ai_agent" if job.mode == "ai_agent" else "human_to_human"),
                agent_id=(campaign.agent_prompt_id if campaign else None),
            )
        except Exception as exc:
            log.exception("Call placement failed for job %s", job.id)
            job.attempts = job.attempts + 1
            job.status = "failed"
            job.blocked_reason = "provider_failure"
            job.blocked_detail_json = {"error": str(exc)[:500]}
            await self.db.flush()
            return job

        job.status = "called"
        job.attempts = job.attempts + 1
        job.call_session_id = call.id
        contact.last_call_session_id = call.id
        contact.updated_at = utcnow()
        await self.db.flush()
        await audit_service.record(
            self.db, action="calljob.placed", org_id=org_id, actor_id=actor_id,
            resource_type="call_job", resource_id=str(job.id),
            details={"call_session_id": str(call.id), "call_sid": call.call_sid})
        return job

    async def cancel_job(self, org_id: uuid.UUID, job_id: uuid.UUID, *,
                         actor_id: uuid.UUID | None = None) -> M.CallJob:
        job = await self.get_job(org_id, job_id)
        if job.status in ("placing", "claimed"):
            raise ValidationError(f"Job already {job.status}; cannot cancel.")
        job.status = "canceled"
        job.updated_at = utcnow()
        await self.db.flush()
        await audit_service.record(
            self.db, action="calljob.cancel", org_id=org_id, actor_id=actor_id,
            resource_type="call_job", resource_id=str(job.id))
        return job

    # ------------------------------------------------------------------ #
    # Campaigns
    # ------------------------------------------------------------------ #

    async def get_campaign(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> M.Campaign:
        row = await self.db.get(M.Campaign, campaign_id)
        if row is None or row.org_id != org_id:
            raise NotFoundError("Campaign not found.")
        return row

    async def create_campaign(
        self, *, org_id: uuid.UUID, name: str, mode: str = "human_dial",
        agent_prompt_id: uuid.UUID | None = None, from_number: str = "",
        caller_language: str = "en", receiver_language_overrides_contact: bool = False,
        window_start_hour_utc: int = 8, window_end_hour_utc: int = 20,
        max_attempts_per_contact: int = 2, max_concurrent_calls: int = 1,
        retry_backoff_minutes: int = 60,
        ai_agent_authorized: bool = False, ai_disclosure_required: bool = True,
        metadata: dict | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> M.Campaign:
        if mode not in ("human_dial", "ai_agent"):
            raise ValidationError("mode must be human_dial or ai_agent")
        if ai_agent_authorized and mode != "ai_agent":
            raise ValidationError("ai_agent_authorized applies only to ai_agent campaigns")
        if mode == "ai_agent" and not ai_agent_authorized:
            raise ValidationError(
                "ai_agent campaigns must be created with explicit authorization ack "
                "(ai_agent_authorized=true records the operator decision).")
        if mode == "human_dial" and ai_agent_authorized:
            raise ValidationError("'ai_agent_authorized' applies only to ai_agent campaigns.")
        if not (0 <= window_start_hour_utc < 24) or not (0 < window_end_hour_utc <= 24) \
                or window_end_hour_utc <= window_start_hour_utc:
            raise ValidationError("Calling window must satisfy 0 <= start < end <= 24 (UTC).")
        if max_concurrent_calls < 1 or max_attempts_per_contact < 1:
            raise ValidationError("Concurrency and attempt caps must be >= 1.")

        campaign = M.Campaign(
            org_id=org_id,
            name=name[:200],
            mode=mode,
            agent_prompt_id=agent_prompt_id,
            from_number=from_number,
            caller_language=caller_language,
            receiver_language_overrides_contact=receiver_language_overrides_contact,
            window_start_hour_utc=window_start_hour_utc,
            window_end_hour_utc=window_end_hour_utc,
            max_attempts_per_contact=max_attempts_per_contact,
            max_concurrent_calls=max_concurrent_calls,
            retry_backoff_minutes=retry_backoff_minutes,
            status="draft",
            ai_agent_authorized=ai_agent_authorized,
            ai_agent_authorized_by=(actor_id if (mode == "ai_agent" and ai_agent_authorized) else None),
            ai_agent_authorized_at=(utcnow() if (mode == "ai_agent" and ai_agent_authorized) else None),
            ai_disclosure_required=ai_disclosure_required,
            created_by=actor_id,
            metadata_json=dict(metadata or {}),
        )
        self.db.add(campaign)
        await self.db.flush()
        await audit_service.record(
            self.db, action="campaign.create", org_id=org_id, actor_id=actor_id,
            resource_type="campaign", resource_id=str(campaign.id),
            details={"mode": mode})
        return campaign

    async def set_campaign_status(self, org_id: uuid.UUID, campaign_id: uuid.UUID,
                                  status: str, *, actor_id: uuid.UUID | None = None
                                  ) -> M.Campaign:
        if status not in ("draft", "active", "paused", "completed", "stopped"):
            raise ValidationError("Invalid campaign status.")
        campaign = await self.get_campaign(org_id, campaign_id)
        campaign.status = status
        campaign.updated_at = utcnow()
        await self.db.flush()
        await audit_service.record(
            self.db, action=f"campaign.{status}", org_id=org_id, actor_id=actor_id,
            resource_type="campaign", resource_id=str(campaign.id))
        return campaign

    async def list_jobs(self, *, org_id: uuid.UUID, campaign_id: uuid.UUID | None = None,
                        contact_id: uuid.UUID | None = None,
                        status: str | None = None,
                        limit: int = 50, offset: int = 0) -> tuple[list[M.CallJob], int]:
        stmt = select(M.CallJob).where(M.CallJob.org_id == org_id)
        if campaign_id is not None:
            stmt = stmt.where(M.CallJob.campaign_id == campaign_id)
        if contact_id is not None:
            stmt = stmt.where(M.CallJob.contact_id == contact_id)
        if status:
            stmt = stmt.where(M.CallJob.status == status)
        total_res = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = int(total_res.scalar() or 0)
        stmt = stmt.order_by(M.CallJob.created_at.desc()).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all()), total


def _dump_job(job: M.CallJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "contact_id": str(job.contact_id),
        "campaign_id": str(job.campaign_id) if job.campaign_id else None,
        "mode": job.mode,
        "status": job.status,
        "idempotency_key": job.idempotency_key,
        "to_number": job.to_number,
        "from_number": job.from_number,
        "caller_language": job.caller_language,
        "receiver_language": job.receiver_language,
        "attempts": job.attempts,
        "blocked_reason": job.blocked_reason,
        "blocked_detail": job.blocked_detail_json,
        "call_session_id": str(job.call_session_id) if job.call_session_id else None,
        "not_before": job.not_before.isoformat() if job.not_before else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
