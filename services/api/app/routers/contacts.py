"""Contacts router (outbound-calling CRM): phonebook, CSV import/export,
consent ledger, attached documents, call jobs & campaigns.

Permissions:
- read paths  -> view_contacts (owner/admin/manager/member/viewer)
- write paths -> manage_contacts (owner/admin/manager)
- campaigns   -> manage_campaigns (owner/admin)

AI-agent outbound calling exists ONLY through campaigns created with an
explicit authorization ack by a manager-or-higher operator, and the gate
(app.telephony.gate) re-checks consent/DNC/window/caps at execution time.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import get_db
from app.deps import Principal, require_org_user
from app.errors import AppError, ValidationError
from app.services.contacts_service import ContactsService
from app.telephony.call_jobs import CallJobService, _dump_job

log = logging.getLogger("app.routers.contacts")

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])
campaign_router = APIRouter(prefix="/api/v1/campaigns", tags=["contacts"])


def _org(principal: Principal) -> uuid.UUID:
    if principal.org_id is None:
        raise ValidationError("Organization context required.")
    return principal.org_id


def _contact_out(c: M.Contact) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "phone_e164": c.phone_e164,
        "display_name": c.display_name,
        "language": c.language,
        "country": c.country,
        "timezone": c.timezone,
        "email": c.email,
        "notes": c.notes,
        "tags": c.tags_json,
        "do_not_call": c.do_not_call,
        "archived": c.archived,
        "last_call_session_id": str(c.last_call_session_id) if c.last_call_session_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _consent_out(row: M.ContactConsent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "contact_id": str(row.contact_id),
        "decision": row.decision,
        "source": row.source,
        "note": row.note,
        "evidence": row.evidence_json,
        "recorded_by": str(row.recorded_by) if row.recorded_by else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class ContactCreate(BaseModel):
    phone: str = Field(min_length=3, max_length=32)
    display_name: str = Field(default="", max_length=200)
    language: str = Field(default="en", max_length=16)
    country: str = Field(default="", max_length=8)
    timezone: str = Field(default="", max_length=64)
    email: str | None = None
    notes: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list)
    default_country: str = Field(default="US", max_length=8)


class ContactUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=16)
    timezone: str | None = Field(default=None, max_length=64)
    email: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None


class ConsentRequest(BaseModel):
    decision: str = Field(min_length=3, max_length=16)  # grant|revoke|dnc
    source: str = Field(default="manual_entry", max_length=32)
    note: str = Field(default="", max_length=2000)
    evidence: dict = Field(default_factory=dict)


class CallJobRequest(BaseModel):
    campaign_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: str = Field(default="human_dial", max_length=16)
    agent_prompt_id: uuid.UUID | None = None
    from_number: str = Field(default="", max_length=32)
    caller_language: str = Field(default="en", max_length=16)
    receiver_language_overrides_contact: bool = False
    window_start_hour_utc: int = Field(default=8, ge=0, le=23)
    window_end_hour_utc: int = Field(default=20, ge=1, le=24)
    max_attempts_per_contact: int = Field(default=2, ge=1, le=10)
    max_concurrent_calls: int = Field(default=1, ge=1, le=50)
    retry_backoff_minutes: int = Field(default=60, ge=0, le=10080)
    ai_agent_authorized: bool = False
    ai_disclosure_required: bool = True
    metadata: dict = Field(default_factory=dict)


class CampaignStatus(BaseModel):
    status: str = Field(min_length=4, max_length=20)


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #


@router.post("", status_code=201)
async def create_contact(
    payload: ContactCreate,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc = ContactsService(db)
    contact = await svc.create_contact(
        org_id=_org(principal), phone=payload.phone,
        display_name=payload.display_name, language=payload.language,
        country=payload.country, timezone=payload.timezone, email=payload.email,
        notes=payload.notes, tags=payload.tags,
        default_country=payload.default_country,
        actor_id=principal.user_id)
    await db.commit()
    return _contact_out(contact)


@router.get("")
async def list_contacts(
    q: str = Query(default="", max_length=200),
    archived: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    svc = ContactsService(db)
    rows, total = await svc.list_contacts(
        org_id=_org(principal), query=q, archived=archived, limit=limit, offset=offset)
    return {"items": [_contact_out(r) for r in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/export")
async def export_contacts(
    include_archived: bool = Query(default=True),
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc = ContactsService(db)
    rows, _total = await svc.list_contacts(
        org_id=_org(principal), include_archived=include_archived, limit=5000)
    csv_bytes = svc.export_rows(rows)
    return Response(content=csv_bytes, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=contacts.csv"})


@router.post("/import")
async def import_contacts(
    file: UploadFile = File(...),
    default_country: str = Form(default="US", max_length=8),
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    if (file.filename or "").lower().endswith(".json"):
        raise ValidationError("Only CSV imports are supported here.")
    data = await file.read()
    if not data:
        raise ValidationError("Empty CSV upload.")
    svc = ContactsService(db)
    report = await svc.import_csv(
        org_id=_org(principal), data=data,
        default_country=default_country, actor_id=principal.user_id)
    await db.commit()
    return report.to_dict()


@router.get("/{contact_id}")
async def get_contact(
    contact_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    svc = ContactsService(db)
    contact = await svc.get_contact(_org(principal), contact_id)
    return _contact_out(contact)


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc = ContactsService(db)
    contact = await svc.update_contact(
        _org(principal), contact_id,
        display_name=payload.display_name, language=payload.language,
        timezone=payload.timezone, email=payload.email, notes=payload.notes,
        tags=payload.tags)
    await db.commit()
    return _contact_out(contact)


@router.delete("/{contact_id}")
async def archive_contact(
    contact_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc = ContactsService(db)
    contact = await svc.archive_contact(_org(principal), contact_id,
                                        actor_id=principal.user_id)
    await db.commit()
    return _contact_out(contact)


# --------------------------------------------------------------------------- #
# Consent ledger
# --------------------------------------------------------------------------- #


@router.post("/{contact_id}/consent", status_code=201)
async def record_consent(
    contact_id: uuid.UUID,
    payload: ConsentRequest,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc = ContactsService(db)
    row = await svc.record_consent(
        org_id=_org(principal), contact_id=contact_id,
        decision=payload.decision, source=payload.source,
        note=payload.note, evidence=payload.evidence,
        actor_id=principal.user_id)
    await db.commit()
    return _consent_out(row)


@router.get("/{contact_id}/consent")
async def consent_history(
    contact_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    svc = ContactsService(db)
    rows = await svc.consent_history(_org(principal), contact_id)
    effective = await svc.effective_consent(_org(principal), contact_id)
    return {"effective_granted": effective,
            "history": [_consent_out(r) for r in rows]}


# --------------------------------------------------------------------------- #
# Contact documents
# --------------------------------------------------------------------------- #


@router.post("/{contact_id}/documents", status_code=201)
async def attach_document(
    contact_id: uuid.UUID,
    document_id: uuid.UUID = Form(...),
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc = ContactsService(db)
    await svc.attach_document(
        org_id=_org(principal), contact_id=contact_id, document_id=document_id,
        actor_id=principal.user_id)
    await db.commit()
    docs = await svc.list_documents(_org(principal), contact_id)
    return {"items": [{"id": str(d.id), "filename": d.filename, "status": d.status}
                      for d in docs]}


@router.get("/{contact_id}/documents")
async def contact_documents(
    contact_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    svc = ContactsService(db)
    docs = await svc.list_documents(_org(principal), contact_id)
    return {"items": [{"id": str(d.id), "filename": d.filename, "status": d.status}
                      for d in docs]}


# --------------------------------------------------------------------------- #
# Call jobs (idempotent scheduling + gate-enforced execution)
# --------------------------------------------------------------------------- #


@router.post("/{contact_id}/call", status_code=201)
async def call_contact(
    contact_id: uuid.UUID,
    payload: CallJobRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Place (or idempotently replay) a phone call to this contact."""
    principal.require("manage_contacts")
    svc_jobs = CallJobService(db)
    job, created = await svc_jobs.schedule_job(
        org_id=_org(principal), contact_id=contact_id,
        campaign_id=payload.campaign_id,
        idempotency_key=idempotency_key or payload.idempotency_key,
        actor_id=principal.user_id)
    job = await svc_jobs.execute_job(
        _org(principal), job.id, actor_id=principal.user_id,
        claimed_by_name=principal.identity_for_rate_limit)
    if job.status == "blocked":
        # synchronous dial: surface the gate block instead of hiding it in a 201
        raise AppError(
            f"Call blocked by outbound gate: {job.blocked_reason}",
            status=409, recoverable=True,
            details={"reason": job.blocked_reason, "job_id": str(job.id)})
    if job.status == "failed":
        raise AppError(
            "Carrier call dispatch failed; a new Idempotency-Key is required.",
            status=502, recoverable=True,
            details={"reason": "provider_failure", "job_id": str(job.id)})
    await db.commit()
    return {"created": created, "job": _dump_job(job)}


@router.post("/{contact_id}/jobs", status_code=201)
async def queue_job(
    contact_id: uuid.UUID,
    payload: CallJobRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a dial without placing it now (campaign workers place it later)."""
    principal.require("manage_contacts")
    if payload.campaign_id is None:
        raise ValidationError("campaign_id is required for queued jobs; "
                              "use POST /contacts/{id}/call for immediate dialing.")
    svc_jobs = CallJobService(db)
    job, created = await svc_jobs.schedule_job(
        org_id=_org(principal), contact_id=contact_id,
        campaign_id=payload.campaign_id,
        idempotency_key=idempotency_key or payload.idempotency_key,
        actor_id=principal.user_id)
    await db.commit()
    return {"created": created, "job": _dump_job(job)}


@router.get("/{contact_id}/jobs")
async def contact_jobs(
    contact_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    svc_jobs = CallJobService(db)
    rows, total = await svc_jobs.list_jobs(org_id=_org(principal),
                                           contact_id=contact_id, limit=200)
    return {"items": [_dump_job(j) for j in rows], "total": total}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_contacts")
    svc_jobs = CallJobService(db)
    job = await svc_jobs.cancel_job(_org(principal), job_id, actor_id=principal.user_id)
    await db.commit()
    return _dump_job(job)


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #


@campaign_router.post("", status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_campaigns")
    svc_requests = CallJobService(db)
    campaign = await svc_requests.create_campaign(
        org_id=_org(principal), name=payload.name, mode=payload.mode,
        agent_prompt_id=payload.agent_prompt_id, from_number=payload.from_number,
        caller_language=payload.caller_language,
        receiver_language_overrides_contact=payload.receiver_language_overrides_contact,
        window_start_hour_utc=payload.window_start_hour_utc,
        window_end_hour_utc=payload.window_end_hour_utc,
        max_attempts_per_contact=payload.max_attempts_per_contact,
        max_concurrent_calls=payload.max_concurrent_calls,
        retry_backoff_minutes=payload.retry_backoff_minutes,
        ai_agent_authorized=payload.ai_agent_authorized,
        ai_disclosure_required=payload.ai_disclosure_required,
        metadata=payload.metadata, actor_id=principal.user_id)
    await db.commit()
    return _campaign_out(campaign)


@campaign_router.get("")
async def list_campaigns(
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    res = await db.execute(
        select(M.Campaign).where(M.Campaign.org_id == _org(principal))
        .order_by(M.Campaign.created_at.desc()))
    return {"items": [_campaign_out(c) for c in res.scalars().all()]}


@campaign_router.post("/{campaign_id}/status")
async def set_campaign_status(
    campaign_id: uuid.UUID,
    payload: CampaignStatus,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Activating an AI campaign is the explicit authorization moment."""
    principal.require("manage_campaigns")
    sv_campaigns = CallJobService(db)
    campaign = await sv_campaigns.set_campaign_status(
        _org(principal), campaign_id, payload.status, actor_id=principal.user_id)
    await db.commit()
    return _campaign_out(campaign)


@campaign_router.get("/{campaign_id}/jobs")
async def campaign_jobs(
    campaign_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    principal.require("view_contacts")
    svc_jobs = CallJobService(db)
    await svc_jobs.get_campaign(_org(principal), campaign_id)
    rows, total = await svc_jobs.list_jobs(
        org_id=_org(principal), campaign_id=campaign_id, limit=500)
    return {"items": [_dump_job(j) for j in rows], "total": total}


def _campaign_out(c: M.Campaign) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "mode": c.mode,
        "status": c.status,
        "agent_prompt_id": str(c.agent_prompt_id) if c.agent_prompt_id else None,
        "from_number": c.from_number,
        "caller_language": c.caller_language,
        "receiver_language_overrides_contact": c.receiver_language_overrides_contact,
        "window_start_hour_utc": c.window_start_hour_utc,
        "window_end_hour_utc": c.window_end_hour_utc,
        "max_attempts_per_contact": c.max_attempts_per_contact,
        "max_concurrent_calls": c.max_concurrent_calls,
        "retry_backoff_minutes": c.retry_backoff_minutes,
        "ai_agent_authorized": c.ai_agent_authorized,
        "ai_disclosure_required": c.ai_disclosure_required,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
