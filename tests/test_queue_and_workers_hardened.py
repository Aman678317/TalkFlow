"""Phase 8: Redis, Queues & Background Workers Hardening Test Suite.

Verifies:
1. At-least-once delivery with explicit acknowledgment (ack/nack).
2. Automatic retry with backoff and Dead-Letter Queue (DLQ) routing upon exhaustion.
3. DLQ inspection and replay capability (reprocess_dlq).
4. Graceful worker shutdown: in-flight jobs finish cleanly without cancellation errors.
5. Worker execution timeout protection against hung handlers.
6. Production fail-closed gate: queues and cache reject in-memory fallback in production.
7. /ready endpoint verifies background queue readiness.
"""
from __future__ import annotations

import asyncio
import time
import pytest

from app.config import settings
from app.queue import (
    Job, JobQueue, MemoryQueue, WorkerRunner, init_queue, queue, close_queue
)
from app.cache import init_cache, MemoryCache


@pytest.mark.asyncio
async def test_queue_push_pop_and_ack():
    """Verify standard queue lifecycle with explicit at-least-once acknowledgment."""
    q = MemoryQueue()
    try:
        job_id = await q.push("test.job", {"val": 42}, queue="test_q", max_attempts=2)
        assert job_id is not None
        assert await q.depth("test_q") == 1

        # Pop job
        job = await q.pop("test_q", timeout_s=0.5)
        assert job is not None
        assert job.job_id == job_id
        assert job.payload == {"val": 42}
        assert await q.depth("test_q") == 0

        # Processing map should track in-flight job
        assert job_id in q._processing.get("test_q", {})

        # Ack should remove from in-flight tracking
        await q.ack(job, queue="test_q")
        assert job_id not in q._processing.get("test_q", {})
    finally:
        await q.close()


@pytest.mark.asyncio
async def test_worker_retry_backoff_and_dlq_routing():
    """Verify failing jobs are retried up to max_attempts, then routed to DLQ."""
    q = MemoryQueue()
    attempts_recorded = []

    async def flaky_handler(payload: dict) -> None:
        attempts_recorded.append(time.time())
        raise ValueError(f"Forced failure: {payload['item']}")

    runner = WorkerRunner(q, queue_name="flaky_q", backoff_multiplier=0.01)
    runner.register("flaky.task", flaky_handler)
    runner.start()

    try:
        # Enqueue job with max_attempts=3
        job_id = await q.push("flaky.task", {"item": "doc-99"}, queue="flaky_q", max_attempts=3)
        assert await q.dlq_depth("flaky_q") == 0

        # Wait for retries and eventual dead-lettering
        # Exponential backoff is min(60, 2**attempts) -> attempt 1 fails, waits 2s; attempt 2 fails, waits 4s...
        # Wait until DLQ depth reaches 1
        for _ in range(50):
            if await q.dlq_depth("flaky_q") == 1:
                break
            await asyncio.sleep(0.1)

        assert await q.dlq_depth("flaky_q") == 1
        assert len(attempts_recorded) == 3
        assert runner.metrics["failed"] == 3
        assert runner.metrics["dead_lettered"] == 1

        # Inspect DLQ job
        dlq_job = await q.pop_dlq("flaky_q")
        assert dlq_job is not None
        assert dlq_job.job_id == job_id
        assert dlq_job.attempts == 3
        assert "Forced failure: doc-99" in (dlq_job.last_error or "")
        assert await q.dlq_depth("flaky_q") == 0

        # Re-enqueue into DLQ and test reprocess_dlq
        await q.nack(dlq_job, "flaky_q", requeue=False)
        assert await q.dlq_depth("flaky_q") == 1

        reprocessed = await q.reprocess_dlq("flaky_q", max_jobs=10)
        assert reprocessed == 1
        assert await q.dlq_depth("flaky_q") == 0
        # Job is now back in flaky_q with attempts reset to 0
        assert await q.depth("flaky_q") >= 1
    finally:
        await runner.stop()
        await q.close()


@pytest.mark.asyncio
async def test_graceful_worker_shutdown_preserves_inflight_job():
    """Worker stop() must wait for in-flight jobs to complete without abrupt cancellation."""
    q = MemoryQueue()
    completed = []

    async def slow_handler(payload: dict) -> None:
        await asyncio.sleep(0.25)
        completed.append(payload["id"])

    runner = WorkerRunner(q, queue_name="slow_q")
    runner.register("slow.job", slow_handler)
    runner.start()

    try:
        await q.push("slow.job", {"id": "job-1"}, queue="slow_q")

        # Let the worker pop and start executing the job
        await asyncio.sleep(0.05)

        # Trigger graceful stop while job-1 is running
        t0 = time.time()
        await runner.stop(timeout_s=2.0)
        elapsed = time.time() - t0

        # Must have waited for slow_handler to finish
        assert "job-1" in completed
        assert elapsed >= 0.15
        assert runner.metrics["succeeded"] == 1
        assert runner.metrics["failed"] == 0
    finally:
        await q.close()


@pytest.mark.asyncio
async def test_worker_job_timeout_protection():
    """Worker must abort jobs that hang past job_timeout_s and fail the attempt."""
    q = MemoryQueue()
    runner = WorkerRunner(q, queue_name="hung_q", job_timeout_s=0.2)

    async def hanging_handler(payload: dict) -> None:
        await asyncio.sleep(10.0)

    runner.register("hung.job", hanging_handler)
    runner.start()

    try:
        job_id = await q.push("hung.job", {"foo": "bar"}, queue="hung_q", max_attempts=1)

        # Worker should time out after 0.2s and dead-letter since max_attempts=1
        for _ in range(40):
            if await q.dlq_depth("hung_q") == 1:
                break
            await asyncio.sleep(0.1)

        assert await q.dlq_depth("hung_q") == 1
        assert runner.metrics["failed"] == 1
        assert runner.metrics["dead_lettered"] == 1

        dead_job = await q.pop_dlq("hung_q")
        assert dead_job is not None
        assert dead_job.job_id == job_id
    finally:
        await runner.stop()
        await q.close()


@pytest.mark.asyncio
async def test_production_fails_closed_without_redis(monkeypatch):
    """Production configuration must reject running without a reachable Redis instance."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "redis_url", "")

    # 1. Queue must fail closed
    with pytest.raises(RuntimeError, match="Production requires REDIS_URL"):
        await init_queue(settings)

    # 2. Cache must fail closed
    with pytest.raises(RuntimeError, match="Production requires REDIS_URL"):
        await init_cache(settings)

    # 3. Bad redis URL in production must fail closed
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:54321/0")
    with pytest.raises(RuntimeError, match="Production requires a healthy Redis connection"):
        await init_queue(settings)

    with pytest.raises(RuntimeError, match="Production requires a healthy Redis connection"):
        await init_cache(settings)


@pytest.mark.asyncio
async def test_ready_health_endpoint_checks_queue(services_app_client):
    """The /ready endpoint must verify database, cache, storage, and queue readiness."""
    resp = services_app_client.get("/ready")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ready"] is True
    assert "queue" in data["checks"]
    assert data["checks"]["queue"] is True

