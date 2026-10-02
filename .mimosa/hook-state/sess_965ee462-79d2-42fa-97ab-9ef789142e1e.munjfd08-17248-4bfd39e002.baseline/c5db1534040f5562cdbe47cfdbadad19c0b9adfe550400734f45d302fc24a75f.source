"""Billing — derived from the immutable usage ledger, never the reverse (PDD §62).

Pricing lives in PLAN_PRICING config (data, not code paths). Plan changes emit
immutable billing_events. Invoices are computed by the metering worker from
usage_records grouped by unit_type.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.base import utcnow
from app.services.usage_service import DEFAULT_PLAN_QUOTAS

log = logging.getLogger("app.billing")

# cents per unit, per plan. Enterprise = negotiated (0 here, quoted offline).
PLAN_PRICING = {
    "free": {"base_cents": 0, "characters": 0.0, "audio_minutes": 0.0,
             "document_pages": 0.0, "api_requests": 0.0},
    "pro": {"base_cents": 2400, "characters": 0.002, "audio_minutes": 12.0,
            "document_pages": 10.0, "api_requests": 0.05,
            "included": {"characters": 5_000_000, "audio_minutes": 1000,
                         "document_pages": 200, "api_requests": 100_000}},
    "business": {"base_cents": 12000, "characters": 0.0015, "audio_minutes": 9.0,
                 "document_pages": 8.0, "api_requests": 0.03,
                 "included": {"characters": 50_000_000, "audio_minutes": 10_000,
                              "document_pages": 2_000, "api_requests": 1_000_000}},
    "enterprise": {"base_cents": 0, "characters": 0.0, "audio_minutes": 0.0,
                   "document_pages": 0.0, "api_requests": 0.0},
}


async def get_or_create_subscription(db: AsyncSession, org: M.Organization) -> M.Subscription:
    sub = (await db.execute(select(M.Subscription).where(
        M.Subscription.org_id == org.id))).scalars().first()
    if sub is None:
        now = utcnow()
        sub = M.Subscription(
            org_id=org.id, plan_code=org.plan, status="active",
            current_period_start=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            current_period_end=(now.replace(day=1, hour=0, minute=0, second=0,
                                            microsecond=0) + timedelta(days=32)).replace(day=1),
            quota_json=DEFAULT_PLAN_QUOTAS.get(org.plan, DEFAULT_PLAN_QUOTAS["free"]),
        )
        db.add(sub)
        await db.commit()
    return sub



async def change_plan(db: AsyncSession, org: M.Organization, new_plan: str,
                      actor_id: uuid.UUID | None) -> M.Subscription:
    if new_plan not in PLAN_PRICING:
        from app.errors import ValidationError
        raise ValidationError(f"Unknown plan '{new_plan}'.",
                              details={"plans": list(PLAN_PRICING)})
    sub = await get_or_create_subscription(db, org)
    old = sub.plan_code
    sub.plan_code = new_plan
    sub.quota_json = DEFAULT_PLAN_QUOTAS.get(new_plan, DEFAULT_PLAN_QUOTAS["free"])
    org.plan = new_plan
    db.add(M.BillingEvent(
        org_id=org.id, kind="plan_changed", amount_cents=PLAN_PRICING[new_plan]["base_cents"],
        period=utcnow().strftime("%Y-%m"),
        lines_json=[{"kind": "plan_change", "from": old, "to": new_plan}],
        metadata_json={"actor_id": str(actor_id) if actor_id else None},
        created_at=utcnow()))
    from app.services import audit_service
    await audit_service.record(db, action="billing.plan_changed", org_id=org.id,
                               actor_id=actor_id, resource_type="subscription",
                               resource_id=str(sub.id),
                               details={"from": old, "to": new_plan})
    await db.commit()
    return sub


async def compute_invoice(db: AsyncSession, org_id: uuid.UUID,
                          period_start: datetime, period_end: datetime) -> dict:
    """Derive invoice lines from the usage ledger for one period."""
    sub = await get_or_create_subscription(db, await _org(db, org_id))
    pricing = PLAN_PRICING.get(sub.plan_code, PLAN_PRICING["free"])
    included = pricing.get("included", {})
    res = await db.execute(
        select(M.UsageRecord.unit_type, func.sum(M.UsageRecord.units))
        .where(M.UsageRecord.org_id == org_id,
               M.UsageRecord.created_at >= period_start,
               M.UsageRecord.created_at < period_end)
        .group_by(M.UsageRecord.unit_type))
    usage = {u: float(t or 0) for u, t in res.all()}
    lines = [{"description": f"{sub.plan_code} plan base", "amount_cents": pricing["base_cents"]}]
    total = pricing["base_cents"]
    for unit, rate in ((k, v) for k, v in pricing.items()
                       if k not in ("base_cents", "included") and v):
        units = usage.get(unit, 0.0)
        billable = max(0.0, units - included.get(unit, 0.0))
        cents = int(round(billable * rate))
        if cents > 0:
            lines.append({"description": f"{int(billable)} {unit} @ {rate}c",
                          "amount_cents": cents})
            total += cents
    return {"org_id": str(org_id),
            "period": period_start.strftime("%Y-%m"),
            "plan": sub.plan_code, "lines": lines, "total_cents": total,
            "currency": "USD", "usage": usage}


async def finalize_invoice(db: AsyncSession, org_id: uuid.UUID,
                           period_start: datetime, period_end: datetime) -> M.BillingEvent:
    inv = await compute_invoice(db, org_id, period_start, period_end)
    ev = M.BillingEvent(
        org_id=org_id, kind="invoice_created",
        amount_cents=inv["total_cents"], currency=inv["currency"],
        period=inv["period"], lines_json=inv["lines"],
        metadata_json={"usage": inv["usage"]}, created_at=utcnow())
    db.add(ev)
    await db.commit()
    log.info("invoice %s org=%s total=%dc", inv["period"], org_id, inv["total_cents"])
    return ev


async def list_events(db: AsyncSession, org_id: uuid.UUID, limit: int = 50):
    res = await db.execute(select(M.BillingEvent).where(
        M.BillingEvent.org_id == org_id)
        .order_by(M.BillingEvent.created_at.desc()).limit(limit))
    return res.scalars().all()


async def _org(db: AsyncSession, org_id: uuid.UUID) -> M.Organization:
    org = await db.get(M.Organization, org_id)
    if org is None:
        from app.errors import NotFoundError
        raise NotFoundError("Organization not found.")
    return org
