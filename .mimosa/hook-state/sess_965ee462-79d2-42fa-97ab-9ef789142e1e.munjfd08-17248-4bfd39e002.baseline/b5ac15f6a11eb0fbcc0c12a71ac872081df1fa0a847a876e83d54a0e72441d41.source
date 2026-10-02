"""Usage-first billing (sections 29/62). Plans/limits/prices are CONFIGURATION here —
core application logic never hardcodes pricing. Invoices are computed FROM immutable
usage events (metering measures; billing prices)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from globaltalk.core.audit import usage_summary
from globaltalk.models import BillingEvent, Subscription

# price cents per unit over the plan's included quota
PLAN_LIMITS: dict[str, dict[str, float]] = {
    "free": {"characters": 500_000, "audio_seconds": 600, "document_pages": 50,
             "translation_requests": 2_000, "storage_bytes": 100 * 1024 * 1024,
             "api_requests": 5_000, "seats": 3},
    "pro": {"characters": 5_000_000, "audio_seconds": 6_000, "document_pages": 500,
            "translation_requests": 20_000, "storage_bytes": 2 * 1024 ** 3,
            "api_requests": 100_000, "seats": 15},
    "business": {"characters": 50_000_000, "audio_seconds": 60_000, "document_pages": 5_000,
                 "translation_requests": 200_000, "storage_bytes": 20 * 1024 ** 3,
                 "api_requests": 1_000_000, "seats": 100},
    "enterprise": {k: float("inf") for k in
                   ("characters", "audio_seconds", "document_pages", "translation_requests",
                    "storage_bytes", "api_requests", "seats")},
}

OVERAGE_CENTS_PER_UNIT: dict[str, float] = {
    "characters": 0.002,        # $2 per 1M chars
    "audio_seconds": 0.05,      # $3 per minute
    "document_pages": 10.0,     # $0.10 per page
    "translation_requests": 0.02,
    "api_requests": 0.001,
    "storage_bytes": 0.0,       # storage priced separately in enterprise contracts
}

BASE_PRICE_CENTS = {"free": 0, "pro": 2_900, "business": 12_900, "enterprise": 0}


def get_subscription(db: Session, org_id: str) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
    if not sub:
        sub = Subscription(org_id=org_id, plan="free", status="active",
                           current_period_start=datetime.now(timezone.utc))
        db.add(sub)
        db.commit()
    return sub


def compute_invoice(db: Session, org_id: str, *, preview: bool = False,
                    period_days: int = 30) -> dict:
    sub = get_subscription(db, org_id)
    limits = PLAN_LIMITS.get(sub.plan, PLAN_LIMITS["free"])
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    usage = usage_summary(db, org_id, since)
    breakdown = {}
    overage_cents = 0.0
    for dim, used in usage.items():
        included = limits.get(dim)
        if included is None:
            continue
        over = max(0.0, used - included)
        rate = OVERAGE_CENTS_PER_UNIT.get(dim, 0.0)
        cost = over * rate
        breakdown[dim] = {"used": round(used, 2), "included": included,
                          "overage": round(over, 2),
                          "overage_cents": round(cost, 2)}
        overage_cents += cost
    total = BASE_PRICE_CENTS.get(sub.plan, 0) + int(round(overage_cents))
    result = {
        "plan": sub.plan, "period_days": period_days,
        "base_cents": BASE_PRICE_CENTS.get(sub.plan, 0),
        "overage_cents": round(overage_cents, 2),
        "total_cents": total, "currency": "USD", "breakdown": breakdown,
        "usage": {k: round(v, 2) for k, v in usage.items()},
        "preview": preview,
    }
    if not preview:
        db.add(BillingEvent(org_id=org_id, event_type="invoice", amount_cents=total,
                            period_start=since,
                            period_end=datetime.now(timezone.utc),
                            breakdown=breakdown, status="open"))
        db.commit()
    _check_thresholds(db, org_id, usage, limits)
    return result


def _check_thresholds(db: Session, org_id: str, usage: dict, limits: dict) -> None:
    for dim, used in usage.items():
        inc = limits.get(dim)
        if inc and inc != float("inf") and used >= 0.8 * inc:
            from globaltalk.services.webhooks import dispatch_event
            dispatch_event(db, org_id, "usage.threshold",
                           {"dimension": dim, "used": round(used, 2), "included": inc})
            break  # one threshold event per computation cycle is enough
