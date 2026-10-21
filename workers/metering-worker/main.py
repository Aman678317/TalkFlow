"""Metering worker — periodic invoice finalization + usage threshold webhooks.

Billing derives from the immutable usage ledger at period boundaries
(PDD §21.1 ledger rule).

Two failure modes this file used to have (found by the day-2 ownership map,
issue #109 follow-up):

* the threshold markers were stored INSIDE ``quota_json``, so the next pass
  iterated them as if they were limits and divided by a dict — a
  ``TypeError`` that the blanket ``except`` swallowed as "metering pass
  failed". After the first 80 %/100 % crossing the worker stopped
  finalizing invoices and stopped dispatching threshold webhooks, for every
  organization;
* one bad subscription killed the whole pass, so a single organization with
  odd data blocked every other organization's billing.

The limits are now read without the reserved marker key, only numeric
limits are compared, and each subscription is processed on its own.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker.metering")

CHECK_INTERVAL_S = 900  # 15 min

#: The threshold markers live under this reserved key inside ``quota_json``.
#: It is NOT a limit and must never be compared against usage.
THRESHOLD_KEY = "_thresholds"
THRESHOLDS = (0.8, 1.0)


def _limits_and_state(quota_json: dict | None) -> tuple[dict[str, float], dict[str, str]]:
    """The numeric limits of a subscription and its threshold markers.

    The reserved marker key is split out before anything is compared, so a
    marker map can never be mistaken for a limit.
    """
    raw = dict(quota_json or {})
    state = raw.pop(THRESHOLD_KEY, None)
    if not isinstance(state, dict):
        state = {}
    limits: dict[str, float] = {}
    for unit, limit in raw.items():
        if unit.startswith("_"):
            continue
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            continue  # a non-numeric limit is skipped, never divided by
        limits[unit] = float(limit)
    return limits, state


async def _process_subscription(db, sub, now) -> None:
    """Finalize a due invoice, then dispatch the usage-threshold webhooks."""
    from app.services import billing_service, usage_service, webhook_service

    # finalize previous month once, at period end
    if sub.current_period_end and sub.current_period_end <= now:
        await billing_service.finalize_invoice(
            db, sub.org_id, sub.current_period_start, sub.current_period_end)
        sub.current_period_start = sub.current_period_end
        sub.current_period_end = (
            sub.current_period_end + timedelta(days=32)).replace(day=1)
        await db.commit()

    # usage threshold webhook at 80% / 100%
    used = await usage_service.current_period_usage(db, sub.org_id)
    limits, state = _limits_and_state(sub.quota_json)
    for unit, limit in limits.items():
        if limit <= 0 or limit == float("inf"):
            continue
        pct = used.get(unit, 0) / limit
        flag_key = f"threshold_{unit}"
        for threshold in THRESHOLDS:
            mark = f"{flag_key}_{threshold}"
            if pct >= threshold and mark not in state:
                state[mark] = now.isoformat()
                await webhook_service.dispatch(
                    db, sub.org_id, "usage.threshold",
                    {"unit": unit, "used": used.get(unit, 0),
                     "limit": limit, "threshold": threshold})
    if state:
        quota = dict(sub.quota_json or {})
        quota[THRESHOLD_KEY] = state
        sub.quota_json = quota


async def _process_all(db, subs, now) -> None:
    """Process every subscription, isolating a failure to the one that caused it.

    One organization with odd data must not stop the others' billing.
    """
    for sub in subs:
        try:
            await _process_subscription(db, sub, now)
        except Exception:
            log.exception("metering pass failed for org=%s", getattr(sub, "org_id", "?"))
            await db.rollback()


async def main() -> None:
    from sqlalchemy import select
    from app.db.session import init_db, db_session
    from app.db import models as M
    from app.db.base import utcnow

    await init_db()
    log.info("metering worker started")
    while True:
        try:
            async with db_session() as db:
                subs = (await db.execute(select(M.Subscription).where(
                    M.Subscription.status == "active"))).scalars().all()
                await _process_all(db, subs, utcnow())
                await db.commit()
        except Exception:
            log.exception("metering pass failed")
        await asyncio.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
