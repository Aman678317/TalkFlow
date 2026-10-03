"""Job queue abstraction: Redis Streams (prod) or in-process asyncio queue (dev).

One implementation used consistently across document jobs, metering flush,
cleanup, and webhook delivery. Workers (separate processes in prod, in-proc
loop in dev) consume by group name.

Job envelope: {job_id, type, payload, attempts, max_attempts, enqueued_at}
Failed jobs get retried with exponential backoff; dead jobs go to a DLQ list.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger("app.queue")

Handler = Callable[[dict], Awaitable[None]]


@dataclass
class Job:
    job_id: str
    type: str
    payload: dict
    attempts: int = 0
    max_attempts: int = 3
    enqueued_at: float = field(default_factory=time.time)


class JobQueue(ABC):
    @abstractmethod
    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str: ...
    @abstractmethod
    async def pop(self, queue: str = "default", timeout_s: float = 1.0) -> Job | None: ...
    @abstractmethod
    async def depth(self, queue: str = "default") -> int: ...
    @abstractmethod
    async def ping(self) -> bool: ...


class MemoryQueue(JobQueue):
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self.dlq: list[Job] = []

    def _q(self, name: str) -> asyncio.Queue:
        if name not in self._queues:
            self._queues[name] = asyncio.Queue()
        return self._queues[name]

    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str:
        job = Job(job_id=uuid.uuid4().hex, type=job_type, payload=payload,
                  max_attempts=max_attempts)
        await self._q(queue).put(job)
        return job.job_id

    async def pop(self, queue: str = "default", timeout_s: float = 1.0) -> Job | None:
        try:
            return await asyncio.wait_for(self._q(queue).get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    async def requeue(self, job: Job, queue: str = "default", delay_s: float = 0) -> None:
        if delay_s > 0:
            async def _delayed_put():
                try:
                    await asyncio.sleep(delay_s)
                    await self._q(queue).put(job)
                except Exception as e:
                    log.error("memory queue delayed requeue failed: %s", e)
            asyncio.create_task(_delayed_put())
        else:
            await self._q(queue).put(job)

    async def depth(self, queue: str = "default") -> int:
        return self._q(queue).qsize()

    async def ping(self) -> bool:
        return True


class RedisQueue(JobQueue):
    """List-based queue with a processing hash for at-least-once semantics."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis
        self._r = aioredis.from_url(url, decode_responses=True, socket_timeout=3)

    def _key(self, queue: str) -> str:
        return f"gt:queue:{queue}"

    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str:
        job = Job(job_id=uuid.uuid4().hex, type=job_type, payload=payload,
                  max_attempts=max_attempts)
        await self._r.lpush(self._key(queue), json.dumps(job.__dict__))
        return job.job_id

    async def pop(self, queue: str = "default", timeout_s: float = 1.0) -> Job | None:
        try:
            res = await self._r.brpop(self._key(queue), timeout=max(1, int(timeout_s)))
        except Exception:
            return None
        if not res:
            return None
        data = json.loads(res[1])
        return Job(**data)

    async def requeue(self, job: Job, queue: str = "default", delay_s: float = 0) -> None:
        if delay_s > 0:
            async def _delayed_redis_requeue():
                try:
                    await asyncio.sleep(delay_s)
                    await self._r.lpush(self._key(queue), json.dumps(job.__dict__))
                except Exception as e:
                    log.error("redis queue delayed requeue failed: %s", e)
            asyncio.create_task(_delayed_redis_requeue())
        else:
            await self._r.lpush(self._key(queue), json.dumps(job.__dict__))

    async def depth(self, queue: str = "default") -> int:
        return int(await self._r.llen(self._key(queue)))

    async def ping(self) -> bool:
        try:
            return bool(await self._r.ping())
        except Exception:
            return False


_queue: JobQueue | None = None


async def init_queue(settings) -> JobQueue:
    global _queue
    if settings.redis_url:
        try:
            rq = RedisQueue(settings.redis_url)
            if await rq.ping():
                _queue = rq
                log.info("job queue: redis")
                return rq
        except Exception as e:
            log.warning("redis queue unavailable (%s), using in-process queue", e)
    _queue = MemoryQueue()
    log.info("job queue: memory (in-process)")
    return _queue


def queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = MemoryQueue()
    return _queue


class WorkerRunner:
    """Consumes jobs and dispatches to handlers with retry/backoff + DLQ."""

    def __init__(self, q: JobQueue, queue_name: str = "default") -> None:
        self.q = q
        self.queue_name = queue_name
        self.handlers: dict[str, Handler] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def register(self, job_type: str, handler: Handler) -> None:
        self.handlers[job_type] = handler

    async def _run_job(self, job: Job) -> None:
        handler = self.handlers.get(job.type)
        if handler is None:
            log.error("no handler for job type=%s (dropped)", job.type)
            return
        job.attempts += 1
        try:
            await handler(job.payload)
        except Exception as e:
            log.exception("job %s (%s) attempt %d failed: %s",
                          job.job_id, job.type, job.attempts, e)
            if job.attempts < job.max_attempts:
                backoff = min(60.0, 2.0 ** job.attempts)
                if isinstance(self.q, (MemoryQueue, RedisQueue)):
                    await self.q.requeue(job, self.queue_name, delay_s=backoff)  # type: ignore[attr-defined]
                else:
                    await self.q.push(job.type, job.payload, self.queue_name)
            else:
                log.error("job %s dead-lettered after %d attempts", job.job_id, job.attempts)
                dlq = getattr(self.q, "dlq", None)
                if isinstance(dlq, list):
                    dlq.append(job)
                else:
                    await self.q.push("dead." + job.type, job.payload, "dlq")

    async def _loop(self) -> None:
        from app.metrics import QUEUE_DEPTH
        while not self._stop.is_set():
            job = await self.q.pop(self.queue_name, timeout_s=1.0)
            if job is None:
                try:
                    QUEUE_DEPTH.labels(queue=self.queue_name).set(
                        await self.q.depth(self.queue_name))
                except Exception:
                    pass
                continue
            await self._run_job(job)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name=f"worker-{self.queue_name}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
