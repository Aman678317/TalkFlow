"""Cleanup worker — periodic retention sweeps (PDD §40)."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker.cleanup")

SWEEP_INTERVAL_S = 3600


async def main() -> None:
    from app.config import settings
    from app.db.session import init_db, db_session, close_db
    from app.storage import init_storage
    from app.services import retention_service

    await init_db()
    await init_storage()
    log.info("cleanup worker started (interval=%ss)", SWEEP_INTERVAL_S)
    while True:
        try:
            async with db_session() as db:
                counts = await retention_service.sweep(db)
                log.info("sweep done: %s", counts)
        except Exception:
            log.exception("retention sweep failed")
        await asyncio.sleep(SWEEP_INTERVAL_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
