"""Document worker (standalone process for production).

Consumes `documents` queue jobs and runs the parse->translate->reconstruct
pipeline. In dev, the API process runs the same handlers in-process
(WORKER_INPROC); this entrypoint exists for horizontal scaling:

    python -m workers.document_worker   (or: docker compose up worker)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker.documents")


async def main() -> None:
    from app.config import settings
    from app.logging_conf import setup_logging
    setup_logging(settings.log_level)
    from app.db.session import init_db, close_db
    from app.cache import init_cache
    from app.queue import WorkerRunner, init_queue, queue
    from app.storage import init_storage
    from app.ai import ai
    from app.db.session import db_session
    from app.services import document_service

    await init_db()
    await init_cache(settings)
    await init_queue(settings)
    await init_storage()
    async with db_session() as db:
        await ai.load_registry(db)

    runner = WorkerRunner(queue(), "documents")
    runner.register("document.process", document_service.process_document_job)
    runner.start()
    log.info("document worker started (queue=documents)")
    try:
        while True:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runner.stop()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
