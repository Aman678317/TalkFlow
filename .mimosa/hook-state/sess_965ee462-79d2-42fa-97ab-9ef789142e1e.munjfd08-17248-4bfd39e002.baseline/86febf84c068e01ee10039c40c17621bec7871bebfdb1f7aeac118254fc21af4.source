"""Metering worker — periodic invoice finalization + usage threshold webhooks.

Billing derives from the immutable usage ledger at period boundaries
(PDD §21.1 ledger rule).
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


async def main() -> None:
    from sqlalchemy import select
    from app.db.session import init_db, db_session, close_db
    from app.db import models as M
    from app.db.base import utcnow
    from app.services import billing_service, usage_service, webhook_service

    await init_db()
    log.info("metering worker started")
    while True:
        try:
            async with db_session() as db:
                subs = (await db.execute(select(M.Subscription).where(
                    M.Subscription.status == "active"))).scalars().all()
                now = utcnow()
                for sub in subs:
                    # finalize previous month once, at period end
                    if sub.current_period_end and sub.current_period_end <= now:
                        await billing_service.finalize_invoice(
                            db, sub.org_id, sub.current_period_start,
                            sub.current_period_end)
                        sub.current_period_start = sub.current_period_end
                        sub.current_period_end = (
                            sub.current_period_end + timedelta(days=32)).replace(day=1)
                        await db.commit()
                    # usage threshold webhook at 80% / 100%
                    used = await usage_service.current_period_usage(db, sub.org_id)
                    quota = sub.quota_json or {}
                    for unit, limit in quota.items():
                        if not limit or limit == float("inf"):
                            continue
                        pct = used.get(unit, 0) / limit
                        flag_key = f"threshold_{unit}"
                        state = sub.quota_json.get("_thresholds", {}) if isinstance(sub.quota_json, dict) else {}
                        for threshold in (0.8, 1.0):
                            mark = f"{flag_key}_{threshold}"
                            if pct >= threshold and mark not in state:
                                state[mark] = now.isoformat()
                                await webhook_service.dispatch(
                                    db, sub.org_id, "usage.threshold",
                                    {"unit": unit, "used": used.get(unit, 0),
                                     "limit": limit, "threshold": threshold})
                        qj = dict(sub.quota_json or {})
                        qj["_thresholds"] = state
                        sub.quota_json = qj
                await db.commit()
        except Exception:
            log.exception("metering pass failed")
        await asyncio.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
