"""Background job queue: Redis-backed list queue in prod; in-process thread pool in dev.

Document jobs and webhook deliveries are pushed here. Workers claim jobs with a
status-machine on the DB row (queued → running → done/failed), so at-least-once
semantics survive worker restarts even with the in-process backend.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from globaltalk.core.cache import cache_backend_name, get_cache
from globaltalk.core.logging import get_logger

log = get_logger("queue")

QUEUE_DOCUMENTS = "globaltalk:queue:documents"
QUEUE_WEBHOOKS = "globaltalk:queue:webhooks"
QUEUE_CLEANUP = "globaltalk:queue:cleanup"

_executor: ThreadPoolExecutor | None = None
_handlers: dict[str, Callable[[dict], None]] = {}


def register_handler(queue: str, fn: Callable[[dict], None]) -> None:
    _handlers[queue] = fn


def push(queue: str, job: dict) -> None:
    payload = json.dumps(job, default=str)
    if cache_backend_name() == "redis":
        get_cache()._r.lpush(queue, payload)  # type: ignore[attr-defined]
    else:
        _spawn_local(queue, job)


def _spawn_local(queue: str, job: dict) -> None:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gt-worker")

    def run():
        handler = _handlers.get(queue)
        if not handler:
            log.warning("queue_no_handler", extra={"queue": queue})
            return
        try:
            handler(job)
        except Exception:
            log.exception("queue_job_failed", extra={"queue": queue, "job": job.get("id")})

    _executor.submit(run)


def drain_redis_queues(max_items: int = 50) -> int:
    """Called by the worker process (prod) to consume Redis queues."""
    if cache_backend_name() != "redis":
        return 0
    processed = 0
    r = get_cache()._r  # type: ignore[attr-defined]
    for queue in (QUEUE_DOCUMENTS, QUEUE_WEBHOOKS, QUEUE_CLEANUP):
        for _ in range(max_items):
            item = r.rpop(queue)
            if item is None:
                break
            handler = _handlers.get(queue)
            if handler:
                try:
                    handler(json.loads(item))
                    processed += 1
                except Exception:
                    log.exception("queue_job_failed", extra={"queue": queue})
    return processed
