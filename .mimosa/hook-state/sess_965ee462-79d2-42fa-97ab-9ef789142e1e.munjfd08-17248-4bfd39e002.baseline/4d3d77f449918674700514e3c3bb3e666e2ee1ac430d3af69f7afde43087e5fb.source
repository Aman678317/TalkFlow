"""Standalone worker process (production data-plane workers).

Drains Redis queues (documents, webhooks, cleanup, metering rollups). With the
in-process dev backend the API embeds workers automatically; this entrypoint is for
docker/k8s topologies where workers scale independently of API servers (section 58).

Usage:
  python -m globaltalk.workers.run [--tasks documents,webhooks,cleanup,metering] [--once]
"""
from __future__ import annotations

import argparse
import time

from globaltalk.core.db import SessionLocal, init_db
from globaltalk.core.logging import get_logger, setup_logging
from globaltalk.core.queue import (QUEUE_CLEANUP, QUEUE_DOCUMENTS, QUEUE_WEBHOOKS,
                                   drain_redis_queues, register_handler)

log = get_logger("worker")


def _register(task_filter: set[str]) -> None:
    if "documents" in task_filter:
        def handle_document(job: dict) -> None:
            from globaltalk.services.documents import process_document
            db = SessionLocal()
            try:
                process_document(db, job["document_id"])
            finally:
                db.close()
        register_handler(QUEUE_DOCUMENTS, handle_document)

    if "webhooks" in task_filter:
        def handle_webhook(job: dict) -> None:
            if job.get("delay_s"):
                time.sleep(min(job["delay_s"], 300))
            from globaltalk.services.webhooks import deliver
            db = SessionLocal()
            try:
                deliver(db, job["delivery_id"])
            finally:
                db.close()
        register_handler(QUEUE_WEBHOOKS, handle_webhook)

    if "cleanup" in task_filter:
        def handle_cleanup(job: dict) -> None:
            from globaltalk.workers.cleanup import run_retention
            db = SessionLocal()
            try:
                removed = run_retention(db)
                log.info("retention_run", extra={"removed": removed})
            finally:
                db.close()
        register_handler(QUEUE_CLEANUP, handle_cleanup)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="documents,webhooks,cleanup,metering")
    parser.add_argument("--once", action="store_true", help="drain queues once and exit")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()

    setup_logging()
    init_db()
    tasks = {t.strip() for t in args.tasks.split(",") if t.strip()}
    _register(tasks)
    log.info("worker_started", extra={"tasks": sorted(tasks)})

    from globaltalk.core.cache import cache_backend_name
    if cache_backend_name() != "redis":
        log.warning("worker_no_redis", extra={
            "note": "in-process queue backend detected; the API process already runs "
                    "workers inline. This worker idles (used for Redis deployments)."})

    while True:
        processed = drain_redis_queues()
        if "metering" in tasks and processed == 0:
            _metering_rollup_tick()
        if args.once:
            break
        if processed == 0:
            time.sleep(args.poll_seconds)


_last_rollup = 0.0


def _metering_rollup_tick() -> None:
    """Periodic billing aggregation + usage-threshold webhooks (once per hour)."""
    global _last_rollup
    now = time.time()
    if now - _last_rollup < 3600:
        return
    _last_rollup = now
    try:
        from globaltalk.models import Organization
        from globaltalk.services.billing import compute_invoice
        db = SessionLocal()
        try:
            for org in db.query(Organization).all():
                compute_invoice(db, org.id, preview=True)
        finally:
            db.close()
        log.info("metering_rollup_done")
    except Exception:
        log.exception("metering_rollup_failed")


if __name__ == "__main__":
    main()
