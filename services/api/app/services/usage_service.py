"""Usage metering (PDD §21, §29).

Rules:
- usage_records is an IMMUTABLE ledger; billing derives from it, never the reverse
- every request path records usage with request_id correlation
- quota checks happen BEFORE expensive work where practical
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import context, metrics as met
from app.db import models as M
from app.db.base import utcnow
from app.errors import QuotaExceededError

log = logging.getLogger("app.usage")

#: The canonical metered dimensions. The LEDGER records exactly these unit
#: names and the plan limits are expressed in the SAME names, so a limit is
#: always checked against the units that actually accrue (issue #109 class 4:
#: the limits said "documents" / "meeting_minutes" / "audio_minutes" while the
#: ledger recorded "document_pages" / "telephony_minutes" / audio seconds —
#: two limits could never trip and three quota cards could never show a
#: percentage).
METERED_DIMENSIONS = (
    "characters",
    "translation_requests",
    "api_requests",
    "document_pages",
    "audio_seconds",
    "telephony_minutes",
)

#: plan -> monthly quotas. NOT hardcoded in business logic: read via
#: subscription.quota_json. The values are the previous limits expressed in
#: the canonical units (the audio allowance in seconds, the call allowance as
#: telephony minutes); translation_requests reuses the per-request allowance.
DEFAULT_PLAN_QUOTAS = {
    "free": {"characters": 500_000, "translation_requests": 5_000,
             "api_requests": 5_000, "document_pages": 20,
             "audio_seconds": 3_600, "telephony_minutes": 300},
    "pro": {"characters": 5_000_000, "translation_requests": 100_000,
            "api_requests": 100_000, "document_pages": 200,
            "audio_seconds": 60_000, "telephony_minutes": 5_000},
    "business": {"characters": 50_000_000, "translation_requests": 1_000_000,
                 "api_requests": 1_000_000, "document_pages": 2_000,
                 "audio_seconds": 600_000, "telephony_minutes": 50_000},
    "enterprise": {k: float("inf") for k in METERED_DIMENSIONS},
}

#: The old limit names, and how they map onto the canonical dimensions. The
#: audio limit changes VALUE (minutes -> seconds) because the ledger counts
#: seconds; the other two are pure renames.
_QUOTA_KEY_MIGRATION = {
    "documents": "document_pages",
    "meeting_minutes": "telephony_minutes",
}


def normalize_quotas(raw: dict | None) -> dict[str, float]:
    """The plan's limits in the canonical dimension names.

    Existing subscriptions carry the old limit names, so the limits are
    migrated on read: "documents" -> "document_pages",
    "meeting_minutes" -> "telephony_minutes", and the minutes-based audio
    limit is converted to the seconds the ledger records. No migration is
    needed for the rows themselves.
    """
    if not raw:
        return dict(DEFAULT_PLAN_QUOTAS["free"])
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key == "audio_minutes":
            out["audio_seconds"] = float(value) * 60.0
        elif key in _QUOTA_KEY_MIGRATION:
            out[_QUOTA_KEY_MIGRATION[key]] = float(value)
        else:
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                continue
    return out


async def record_usage(
    db: AsyncSession, *, org_id: uuid.UUID | None, product: str, unit_type: str,
    units: float, user_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None, model_version: str = "",
    source_lang: str = "", target_lang: str = "", status: str = "ok",
    metadata: dict | None = None,
) -> M.UsageRecord:
    rec = M.UsageRecord(
        org_id=org_id or uuid.UUID(int=0),
        user_id=user_id, api_key_id=api_key_id,
        request_id=context.current().request_id,
        product=product, unit_type=unit_type, units=units,
        model_version=model_version, source_lang=source_lang, target_lang=target_lang,
        status=status, metadata_json=metadata or {},
        created_at=utcnow(),
    )
    db.add(rec)
    if product in ("text", "document") and unit_type == "characters":
        met.USAGE_CHARS.labels(product=product).inc(units)
    if unit_type == "audio_seconds":
        met.AUDIO_SECONDS.inc(units)
    return rec


async def current_period_usage(db: AsyncSession, org_id: uuid.UUID) -> dict[str, float]:
    sub = (await db.execute(select(M.Subscription).where(
        M.Subscription.org_id == org_id))).scalars().first()
    start = (sub.current_period_start if sub and sub.current_period_start
             else datetime.now(timezone.utc).replace(day=1, hour=0, minute=0,
                                                    second=0, microsecond=0))
    res = await db.execute(
        select(M.UsageRecord.unit_type, func.sum(M.UsageRecord.units))
        .where(M.UsageRecord.org_id == org_id, M.UsageRecord.created_at >= start)
        .group_by(M.UsageRecord.unit_type))
    return {unit: float(total or 0) for unit, total in res.all()}


async def plan_quotas(db: AsyncSession, org_id: uuid.UUID) -> dict[str, float]:
    """The org's plan limits in the canonical dimension names.

    Read from the subscription when there is one, else the plan defaults.
    Every caller (quota checks, the usage endpoints) goes through here, so a
    limit is always expressed in the unit the ledger records.
    """
    sub = (await db.execute(select(M.Subscription).where(
        M.Subscription.org_id == org_id))).scalars().first()
    if sub is None:
        return normalize_quotas(DEFAULT_PLAN_QUOTAS["free"])
    return normalize_quotas(sub.quota_json or DEFAULT_PLAN_QUOTAS.get(
        sub.plan_code, DEFAULT_PLAN_QUOTAS["free"]))


async def check_quota(db: AsyncSession, org_id: uuid.UUID, unit_type: str,
                      add_units: float, *,
                      quotas: dict[str, float] | None = None) -> None:
    """Check a limit before the expensive work.

    ``quotas`` lets a hot path (the realtime pipeline, one check per
    utterance) pass the plan limits it already holds instead of re-reading
    the subscription on every segment.
    """
    if quotas is None:
        quotas = await plan_quotas(db, org_id)
    limit = quotas.get(unit_type)
    if limit is None or limit == float("inf"):
        return
    used = (await current_period_usage(db, org_id)).get(unit_type, 0.0)
    if used + add_units > limit:
        raise QuotaExceededError(
            f"Monthly quota for {unit_type} exceeded ({int(used)}/{int(limit)}). "
            "Upgrade your plan or wait for the next billing period.",
            details={"unit_type": unit_type, "used": used, "limit": limit})


async def usage_summary(db: AsyncSession, org_id: uuid.UUID,
                        days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    res = await db.execute(
        select(M.UsageRecord.product, M.UsageRecord.unit_type,
               func.sum(M.UsageRecord.units), func.count())
        .where(M.UsageRecord.org_id == org_id, M.UsageRecord.created_at >= since)
        .group_by(M.UsageRecord.product, M.UsageRecord.unit_type))
    by_product: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for product, unit, total, count in res.all():
        by_product.setdefault(product, {})[unit] = float(total or 0)
        by_product[product][f"{unit}_requests"] = float(count)
        totals[unit] = totals.get(unit, 0.0) + float(total or 0)
    # per-day series
    res = await db.execute(
        select(func.date(M.UsageRecord.created_at), M.UsageRecord.unit_type,
               func.sum(M.UsageRecord.units))
        .where(M.UsageRecord.org_id == org_id, M.UsageRecord.created_at >= since)
        .group_by(func.date(M.UsageRecord.created_at), M.UsageRecord.unit_type)
        .order_by(func.date(M.UsageRecord.created_at)))
    days_map: dict[str, dict[str, float]] = {}
    for day, unit, total in res.all():
        days_map.setdefault(str(day), {})[unit] = float(total or 0)
    by_day = [{"date": d, **v} for d, v in sorted(days_map.items())]
    return {"period": f"last_{days}_days", "totals": totals,
            "by_product": by_product, "by_day": by_day}
