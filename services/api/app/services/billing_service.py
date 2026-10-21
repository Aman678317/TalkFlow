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
from app.services.usage_service import DEFAULT_PLAN_QUOTAS, METERED_DIMENSIONS

log = logging.getLogger("app.billing")

# cents per unit, per plan. Enterprise = negotiated (0 here, quoted offline).
#
# The priced dimensions are the ones the LEDGER records (issue #109 class 4):
# the previous table priced "audio_minutes" while the ledger counts audio
# SECONDS, and it never priced the translation volume at all — so
# "translation volume is never billed" while the page claimed the invoice
# came from real metering. The audio rate is the same money per minute as
# before (12c/min = 0.2c/s), and the translation rate is the plan's existing
# per-request rate.
#
# ``telephony_minutes`` is metered and limited but NOT priced: the plan
# table carries no telephony rate, and inventing one would be a commercial
# decision. The invoice discloses the tracked volume instead.
PLAN_PRICING = {
    "free": {"base_cents": 0, "characters": 0.0, "audio_seconds": 0.0,
             "document_pages": 0.0, "translation_requests": 0.0, "api_requests": 0.0},
    "pro": {"base_cents": 2400, "characters": 0.002, "audio_seconds": 0.2,
            "document_pages": 10.0, "translation_requests": 0.05, "api_requests": 0.05,
            "included": {"characters": 5_000_000, "audio_seconds": 60_000,
                         "document_pages": 200, "translation_requests": 100_000,
                         "api_requests": 100_000}},
    "business": {"base_cents": 12000, "characters": 0.0015, "audio_seconds": 0.15,
                 "document_pages": 8.0, "translation_requests": 0.03, "api_requests": 0.03,
                 "included": {"characters": 50_000_000, "audio_seconds": 600_000,
                              "document_pages": 2_000, "translation_requests": 1_000_000,
                              "api_requests": 1_000_000}},
    "enterprise": {"base_cents": 0, "characters": 0.0, "audio_seconds": 0.0,
                   "document_pages": 0.0, "translation_requests": 0.0, "api_requests": 0.0},
}

#: Dimensions the ledger meters and the plan limits, but that this plan
#: table does not price. The invoice discloses them (amount 0 + the reason)
#: instead of pretending they do not exist.
UNPRICED_DIMENSIONS = ("telephony_minutes",)


def plan_catalog() -> dict:
    """The plan table for the client.

    The frontend used to hard-code the plan prices and quotas, and they
    contradicted the server (issue #109 class 4) — the server is the single
    source of truth, so it publishes the table.
    """
    labels = {"free": "Free", "pro": "Pro", "business": "Business",
              "enterprise": "Enterprise"}
    plans = []
    for code, pricing in PLAN_PRICING.items():
        plans.append({
            "code": code,
            "label": labels.get(code, code.title()),
            "base_cents": pricing.get("base_cents", 0),
            "currency": "USD",
            # Enterprise is negotiated (priced offline), so the server says so
            # instead of the client inventing a number.
            "price_note": "Custom (quoted offline)" if code == "enterprise" else "",
            "per_unit_cents": {k: v for k, v in pricing.items()
                               if k not in ("base_cents", "included")},
            "included": pricing.get("included", {}),
        })
    return {
        "plans": plans,
        "metered_dimensions": list(METERED_DIMENSIONS),
        "unpriced_dimensions": list(UNPRICED_DIMENSIONS),
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
    # Metered but not priced by this plan: say so, with the volume, instead of
    # leaving the reader to assume it was never metered (issue #109 class 4).
    for unit in UNPRICED_DIMENSIONS:
        units = usage.get(unit, 0.0)
        if units > 0:
            lines.append({
                "description": (f"{int(units)} {unit} (metered; not priced by the "
                                f"{sub.plan_code} plan)"),
                "amount_cents": 0,
                "unpriced": True,
            })
    return {"org_id": str(org_id),
            "period": period_start.strftime("%Y-%m"),
            "plan": sub.plan_code, "lines": lines, "total_cents": total,
            "currency": "USD", "usage": usage,
            "unpriced_dimensions": list(UNPRICED_DIMENSIONS)}


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
