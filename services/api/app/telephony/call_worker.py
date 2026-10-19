"""P4 auto-dial worker: due pending CallJobs get an automatic consumer.

Plan §11 explicitly leaves "the auto-dial worker that consumes queued jobs"
unbuilt: until now jobs stayed ``pending`` until an operator claimed them
through the contacts API. This module adds the autonomous lane while reusing
ALL existing enforcement (consent/DNC/window/caps gate → provider dial →
status transitions — nothing bypasses ``CallJobService.execute_job``):

    CallJobTicker   (interval scan: pending + due by ``not_before``)
      -> queue("telephony").push("calljob.execute", {org_id, job_id})
         -> WorkerRunner handler  ->  CallJobService.execute_job

At-least-once delivery safety: racing executors (operator + worker, or several
workers) resolve through ``execute_job``'s atomic ``pending -> placing`` claim
(exactly one winner; the loser re-reads live state and no-ops), so a scanned
job can never double-dial. Handler failures retry with queue backoff and
dead-letter (visible), they are never silently swallowed.

Operator contract: disabled by default (``call_worker_enabled=False``);
enabling is an explicit opt-in, like ``ASTERISK_TELEPHONY_ENABLED``.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.config import settings
from app.db import models as M
from app.db.session import db_session

log = logging.getLogger("app.telephony.call_worker")

QUEUE_NAME = "telephony"
JOB_TYPE = "calljob.execute"


async def handle_calljob_execute(payload: dict) -> None:
    """Queue handler: claim + gate + place ONE job (idempotent, at-least-once safe)."""
    from app.telephony.call_jobs import CallJobService

    org_id = uuid.UUID(str(payload["org_id"]))
    job_id = uuid.UUID(str(payload["job_id"]))
    async with db_session() as db:
        try:
            await CallJobService(db).execute_job(
                org_id, job_id, claimed_by_name="call-worker")
            await db.commit()
        except Exception:
            await db.rollback()
            raise


class CallJobTicker:
    """Scans due pending jobs each tick and pushes them onto the telephony queue."""

    def __init__(self, *, interval: float | None = None,
                 batch: int | None = None, q=None) -> None:
        self.interval = (interval if interval is not None
                         else settings.call_worker_interval_seconds)
        self.batch = batch if batch is not None else settings.call_worker_batch_size
        self._q = q
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        # Bounded self-dedupe: a pending job is re-scannable every tick until a
        # consumer claims it; without dedupe each tick would push a duplicate
        # copy. Queues remain at-least-once — their own redeliveries and DLQ
        # replay are unaffected; a restart simply reseeds this window.
        self._recent_pushed: dict[str, float] = {}

    def _queue(self):
        if self._q is None:
            from app.queue import queue
            self._q = queue()
        return self._q

    async def due_pending_ids(self, now: datetime | None = None) -> list[tuple[str, str]]:
        """Oldest-first, org-fair scan of actionable pending jobs."""
        now = now or datetime.now(timezone.utc)
        async with db_session() as db:
            res = await db.execute(
                select(M.CallJob.org_id, M.CallJob.id)
                .where(
                    M.CallJob.status == "pending",
                    or_(M.CallJob.not_before.is_(None),
                        M.CallJob.not_before <= now),
                )
                .order_by(M.CallJob.org_id, M.CallJob.created_at)
                .limit(self.batch))
            return [(str(row[0]), str(row[1])) for row in res.all()]

    async def scan_once(self, now: datetime | None = None) -> int:
        """One tick: enqueue due pending jobs not recently enqueued. Returns count."""
        monotonic_now = time.monotonic()
        ttl_s = max(30.0, 5.0 * max(0.05, self.interval))
        for pushed_job_id in [j for j, ts in self._recent_pushed.items()
                              if monotonic_now - ts > ttl_s]:
            self._recent_pushed.pop(pushed_job_id, None)

        due = await self.due_pending_ids(now)
        fresh = [(org_id, job_id) for org_id, job_id in due
                 if job_id not in self._recent_pushed]
        for org_id, job_id in fresh:
            await self._queue().push(
                JOB_TYPE, {"org_id": org_id, "job_id": job_id}, queue=QUEUE_NAME)
            self._recent_pushed[job_id] = monotonic_now
        if fresh:
            log.info("auto-dial worker enqueued %d due call job(s)", len(fresh))
        return len(fresh)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.scan_once()
            except Exception:  # noqa: BLE001 — a scan failure must not kill the ticker
                log.exception("call-job ticker scan failed (continuing)")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(),
                                       timeout=max(0.05, self.interval))

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="call-job-ticker")
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
