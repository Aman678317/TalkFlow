"""Standalone background queue worker runner for GlobalTalk AI.

Runs document processing, webhooks, and default maintenance queues.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app.config import settings
from app.logging_conf import setup_logging
from app.db.session import init_db
from app.cache import init_cache
from app.queue import init_queue, WorkerRunner, queue
from app.storage import init_storage
from app.services import document_service, webhook_service

log = logging.getLogger("app.workers_runner")


async def main() -> None:
    setup_logging(settings.log_level)
    log.info("Starting GlobalTalk standalone workers (%s)...", settings.app_env)
    await init_db()
    await init_cache(settings)
    await init_queue(settings)
    await init_storage()

    q = queue()
    doc_worker = WorkerRunner(q, "documents")
    doc_worker.register("document.process", document_service.process_document_job)
    doc_worker.start()

    wh_worker = WorkerRunner(q, "webhooks")
    wh_worker.register("webhook.deliver", webhook_service.deliver_job)
    wh_worker.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    log.info("Queue workers active (documents, webhooks)...")
    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        log.info("Shutting down workers...")
        await doc_worker.stop()
        await wh_worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
