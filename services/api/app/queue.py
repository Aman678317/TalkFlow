"""Job queue abstraction: Redis (production) or in-process asyncio queue (dev/test).

Features:
- At-least-once processing semantics with explicit ack/nack.
- Dead letter queue (DLQ) routing upon exhausting max_attempts.
- Native Redis sorted-set delayed requeueing (survives worker restarts).
- DLQ inspection and replay capability (reprocess_dlq).
- Graceful worker shutdown: finishes in-flight jobs before terminating.
- Execution timeout per job preventing hung workers.
- Production fail-closed gate: refuses to run on memory queue when is_production is True.
"""
from __future__ import annotations

import asyncio
import contextlib
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
    last_error: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    tenant_id: str | None = None


class JobQueue(ABC):
    @abstractmethod
    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str: ...

    @abstractmethod
    async def pop(self, queue: str = "default", timeout_s: float = 1.0) -> Job | None: ...

    @abstractmethod
    async def ack(self, job: Job, queue: str = "default") -> None: ...

    @abstractmethod
    async def nack(self, job: Job, queue: str = "default", requeue: bool = True,
                   delay_s: float = 0.0) -> None: ...

    @abstractmethod
    async def requeue(self, job: Job, queue: str = "default", delay_s: float = 0.0) -> None: ...

    @abstractmethod
    async def depth(self, queue: str = "default") -> int: ...

    @abstractmethod
    async def dlq_depth(self, queue: str = "default") -> int: ...

    @abstractmethod
    async def pop_dlq(self, queue: str = "default") -> Job | None: ...

    @abstractmethod
    async def reprocess_dlq(self, queue: str = "default", max_jobs: int = 50) -> int: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...


class MemoryQueue(JobQueue):
    """In-memory queue for local dev and automated testing."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Job]] = {}
        self._processing: dict[str, dict[str, Job]] = {}
        self._dlq: dict[str, list[Job]] = {}
        self._delayed_tasks: set[asyncio.Task] = set()

    def _q(self, name: str) -> asyncio.Queue[Job]:
        if name not in self._queues:
            self._queues[name] = asyncio.Queue()
        return self._queues[name]

    @property
    def dlq(self) -> list[Job]:
        """Backward compatibility for existing tests/callers."""
        all_jobs: list[Job] = []
        for jobs in self._dlq.values():
            all_jobs.extend(jobs)
        return all_jobs

    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str:
        from app import context
        ctx = context.current()
        job = Job(
            job_id=uuid.uuid4().hex,
            type=job_type,
            payload=payload,
            max_attempts=max_attempts,
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            tenant_id=ctx.tenant_id,
        )
        await self._q(queue).put(job)
        return job.job_id

    async def pop(self, queue: str = "default", timeout_s: float = 1.0) -> Job | None:
        try:
            job = await asyncio.wait_for(self._q(queue).get(), timeout=timeout_s)
            self._processing.setdefault(queue, {})[job.job_id] = job
            return job
        except asyncio.TimeoutError:
            return None

    async def ack(self, job: Job, queue: str = "default") -> None:
        proc = self._processing.get(queue)
        if proc:
            proc.pop(job.job_id, None)

    async def nack(self, job: Job, queue: str = "default", requeue: bool = True,
                   delay_s: float = 0.0) -> None:
        await self.ack(job, queue)
        if requeue and job.attempts < job.max_attempts:
            await self.requeue(job, queue, delay_s=delay_s)
        else:
            self._dlq.setdefault(queue, []).append(job)

    async def requeue(self, job: Job, queue: str = "default", delay_s: float = 0.0) -> None:
        await self.ack(job, queue)
        if delay_s > 0:
            async def _delayed_put() -> None:
                try:
                    await asyncio.sleep(delay_s)
                    await self._q(queue).put(job)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log.error("memory queue delayed requeue failed: %s", e)
                finally:
                    self._delayed_tasks.discard(task)

            task = asyncio.create_task(_delayed_put())
            self._delayed_tasks.add(task)
        else:
            await self._q(queue).put(job)

    async def depth(self, queue: str = "default") -> int:
        return self._q(queue).qsize()

    async def dlq_depth(self, queue: str = "default") -> int:
        return len(self._dlq.get(queue, []))

    async def pop_dlq(self, queue: str = "default") -> Job | None:
        jobs = self._dlq.get(queue, [])
        if jobs:
            return jobs.pop(0)
        return None

    async def reprocess_dlq(self, queue: str = "default", max_jobs: int = 50) -> int:
        jobs = self._dlq.get(queue, [])
        count = 0
        while jobs and count < max_jobs:
            job = jobs.pop(0)
            job.attempts = 0
            job.last_error = None
            await self._q(queue).put(job)
            count += 1
        return count

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        for t in list(self._delayed_tasks):
            t.cancel()
        self._delayed_tasks.clear()


class RedisQueue(JobQueue):
    """Production Redis-backed queue with at-least-once tracking and native delayed ZSET."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis
        self._r = aioredis.from_url(url, decode_responses=True, socket_timeout=3,
                                    socket_connect_timeout=3)

    def _key(self, queue: str) -> str:
        return f"gt:queue:{queue}"

    def _processing_key(self, queue: str) -> str:
        return f"gt:queue:{queue}:processing"

    def _delayed_key(self, queue: str) -> str:
        return f"gt:queue:{queue}:delayed"

    def _dlq_key(self, queue: str) -> str:
        return f"gt:queue:{queue}:dlq"

    async def _promote_delayed(self, queue: str) -> int:
        """Atomically promote any delayed jobs due now into active queue."""
        now = time.time()
        delayed_k = self._delayed_key(queue)
        queue_k = self._key(queue)
        due_items = await self._r.zrangebyscore(delayed_k, min=0, max=now, start=0, num=50)
        if not due_items:
            return 0
        pipe = self._r.pipeline(transaction=True)
        for item in due_items:
            pipe.lpush(queue_k, item)
            pipe.zrem(delayed_k, item)
        await pipe.execute()
        return len(due_items)

    async def push(self, job_type: str, payload: dict, queue: str = "default",
                   max_attempts: int = 3) -> str:
        from app import context
        ctx = context.current()
        job = Job(
            job_id=uuid.uuid4().hex,
            type=job_type,
            payload=payload,
            max_attempts=max_attempts,
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            tenant_id=ctx.tenant_id,
        )
        await self._r.lpush(self._key(queue), json.dumps(job.__dict__))
        return job.job_id

    async def pop(self, queue: str = "default", timeout_s: float = 1.0) -> Job | None:
        try:
            await self._promote_delayed(queue)
            res = await self._r.brpop(self._key(queue), timeout=max(1, int(timeout_s)))
        except Exception:
            return None
        if not res:
            return None
        data = json.loads(res[1])
        job = Job(**data)
        # Store in processing hash for at-least-once visibility
        try:
            await self._r.hset(self._processing_key(queue), job.job_id, json.dumps(job.__dict__))
        except Exception as e:
            log.warning("failed to track in-flight job in redis: %s", e)
        return job

    async def ack(self, job: Job, queue: str = "default") -> None:
        try:
            await self._r.hdel(self._processing_key(queue), job.job_id)
        except Exception as e:
            log.warning("redis ack failed for job %s: %s", job.job_id, e)

    async def nack(self, job: Job, queue: str = "default", requeue: bool = True,
                   delay_s: float = 0.0) -> None:
        await self.ack(job, queue)
        if requeue and job.attempts < job.max_attempts:
            await self.requeue(job, queue, delay_s=delay_s)
        else:
            await self._r.lpush(self._dlq_key(queue), json.dumps(job.__dict__))

    async def requeue(self, job: Job, queue: str = "default", delay_s: float = 0.0) -> None:
        await self.ack(job, queue)
        encoded = json.dumps(job.__dict__)
        if delay_s > 0:
            await self._r.zadd(self._delayed_key(queue), {encoded: time.time() + delay_s})
        else:
            await self._r.lpush(self._key(queue), encoded)

    async def depth(self, queue: str = "default") -> int:
        await self._promote_delayed(queue)
        return int(await self._r.llen(self._key(queue)))

    async def dlq_depth(self, queue: str = "default") -> int:
        return int(await self._r.llen(self._dlq_key(queue)))

    async def pop_dlq(self, queue: str = "default") -> Job | None:
        item = await self._r.rpop(self._dlq_key(queue))
        if item:
            return Job(**json.loads(item))
        return None

    async def reprocess_dlq(self, queue: str = "default", max_jobs: int = 50) -> int:
        count = 0
        for _ in range(max_jobs):
            item = await self._r.rpop(self._dlq_key(queue))
            if not item:
                break
            data = json.loads(item)
            data["attempts"] = 0
            data["last_error"] = None
            await self._r.lpush(self._key(queue), json.dumps(data))
            count += 1
        return count

    async def sweep_stale_processing(self, queue: str = "default", stale_after_s: float = 300.0) -> int:
        """Reclaims unacked jobs from crashed workers back into active queue."""
        now = time.time()
        proc_items = await self._r.hgetall(self._processing_key(queue))
        reclaimed = 0
        for job_id, raw in proc_items.items():
            data = json.loads(raw)
            if now - data.get("enqueued_at", now) > stale_after_s:
                await self._r.hdel(self._processing_key(queue), job_id)
                await self._r.lpush(self._key(queue), raw)
                reclaimed += 1
        return reclaimed

    async def ping(self) -> bool:
        try:
            return bool(await self._r.ping())
        except Exception:
            return False

    async def close(self) -> None:
        try:
            if hasattr(self._r, "aclose"):
                await self._r.aclose()
            else:
                await self._r.close()
        except Exception:
            pass


_queue: JobQueue | None = None


async def init_queue(settings) -> JobQueue:
    global _queue
    if getattr(settings, "redis_url", ""):
        try:
            rq = RedisQueue(settings.redis_url)
            if await rq.ping():
                _queue = rq
                log.info("job queue: redis")
                return rq
            raise RuntimeError(f"Redis queue ping failed at {settings.redis_url}")
        except Exception as e:
            if settings.is_production:
                raise RuntimeError(
                    f"Production requires a healthy Redis connection for background queues: {e}"
                ) from e
            log.warning("redis queue unavailable (%s), using in-process memory queue", e)

    if settings.is_production:
        raise RuntimeError(
            "Production requires REDIS_URL to be configured for background job queues."
        )

    _queue = MemoryQueue()
    log.info("job queue: memory (in-process)")
    return _queue


def queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = MemoryQueue()
    return _queue


async def close_queue() -> None:
    global _queue
    if _queue is not None:
        await _queue.close()
    _queue = None


class WorkerRunner:
    """Consumes jobs and dispatches to handlers with retry/backoff, DLQ, and graceful shutdown."""

    def __init__(self, q: JobQueue, queue_name: str = "default",
                 job_timeout_s: float = 300.0, backoff_multiplier: float = 1.0) -> None:
        self.q = q
        self.queue_name = queue_name
        self.job_timeout_s = job_timeout_s
        self.backoff_multiplier = backoff_multiplier
        self.handlers: dict[str, Handler] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._current_job: Job | None = None
        self.metrics = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "retried": 0,
            "dead_lettered": 0,
        }

    def register(self, job_type: str, handler: Handler) -> None:
        self.handlers[job_type] = handler

    async def _run_job(self, job: Job) -> None:
        from app import context
        from app.metrics import JOB_EXECUTIONS, JOB_LATENCY
        if job.request_id or job.trace_id or job.tenant_id:
            context.new_ctx(
                request_id=job.request_id or uuid.uuid4().hex[:16],
                trace_id=job.trace_id or uuid.uuid4().hex,
                tenant_id=job.tenant_id,
            )
        handler = self.handlers.get(job.type)
        if handler is None:
            log.error("no handler for job type=%s (routing to DLQ)", job.type)
            job.last_error = f"no handler registered for job type '{job.type}'"
            await self.q.nack(job, self.queue_name, requeue=False)
            self.metrics["dead_lettered"] += 1
            with contextlib.suppress(Exception):
                JOB_EXECUTIONS.labels(queue=self.queue_name, type=job.type, status="dead_lettered").inc()
            return

        self._current_job = job
        job.attempts += 1
        self.metrics["processed"] += 1
        t0 = time.perf_counter()
        try:
            if self.job_timeout_s > 0:
                await asyncio.wait_for(handler(job.payload), timeout=self.job_timeout_s)
            else:
                await handler(job.payload)
            await self.q.ack(job, self.queue_name)
            self.metrics["succeeded"] += 1
            elapsed = time.perf_counter() - t0
            with contextlib.suppress(Exception):
                JOB_EXECUTIONS.labels(queue=self.queue_name, type=job.type, status="success").inc()
                JOB_LATENCY.labels(queue=self.queue_name, type=job.type).observe(elapsed)
        except Exception as e:
            self.metrics["failed"] += 1
            job.last_error = str(e)[:300]
            log.exception("job %s (%s) attempt %d/%d failed: %s",
                          job.job_id, job.type, job.attempts, job.max_attempts, e)
            if job.attempts < job.max_attempts:
                backoff = min(60.0, (2.0 ** job.attempts) * self.backoff_multiplier)
                self.metrics["retried"] += 1
                await self.q.nack(job, self.queue_name, requeue=True, delay_s=backoff)
                with contextlib.suppress(Exception):
                    JOB_EXECUTIONS.labels(queue=self.queue_name, type=job.type, status="retried").inc()
            else:
                self.metrics["dead_lettered"] += 1
                log.error("job %s dead-lettered after %d attempts", job.job_id, job.attempts)
                await self.q.nack(job, self.queue_name, requeue=False)
                with contextlib.suppress(Exception):
                    JOB_EXECUTIONS.labels(queue=self.queue_name, type=job.type, status="dead_lettered").inc()
        finally:
            self._current_job = None

    async def _loop(self) -> None:
        from app.metrics import QUEUE_DEPTH, QUEUE_DLQ_DEPTH
        while not self._stop.is_set():
            job = await self.q.pop(self.queue_name, timeout_s=1.0)
            if job is None:
                try:
                    QUEUE_DEPTH.labels(queue=self.queue_name).set(
                        await self.q.depth(self.queue_name))
                    QUEUE_DLQ_DEPTH.labels(queue=self.queue_name).set(
                        await self.q.dlq_depth(self.queue_name))
                except Exception:
                    pass
                continue
            await self._run_job(job)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name=f"worker-{self.queue_name}")

    async def stop(self, timeout_s: float = 10.0) -> None:
        """Graceful shutdown: signals loop to stop and allows current in-flight job to finish."""
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout_s)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                log.warning("worker %s shutdown exceeded %0.1fs budget; force cancelling",
                            self.queue_name, timeout_s)
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._task
            self._task = None

