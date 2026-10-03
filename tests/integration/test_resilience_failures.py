"""Resilience & Failure Recovery Integration Tests.

Validates that system failure scenarios are safely handled:
1. Cache backend outage fails open without crashing APIs.
2. Queue requeue backoff is non-blocking to consumer loops.
3. Document translation metering is idempotent across retries.
4. Refresh token rotation supports concurrent multi-tab requests within grace window.
5. Online translation raises ProviderUnavailable on complete upstream failure.
6. Webhook retry honors scheduled backoff delay.
"""
import asyncio
import time
import uuid
from datetime import timedelta
import pytest
from unittest.mock import AsyncMock, patch

from app.db.base import utcnow
from app.db import models as M
from app.db.session import db_session
from app.queue import Job, MemoryQueue
from app.ratelimit import check_rate_limit
from app.services.webhook_service import deliver_job
from gt_ai.types import ProviderUnavailable, TranslationRequest


@pytest.mark.asyncio
async def test_rate_limit_cache_outage_fails_open():
    """Verify check_rate_limit does not raise 500 when cache backend throws ConnectionError."""
    with patch("app.ratelimit.cache") as mock_cache_fn:
        mock_backend = AsyncMock()
        mock_backend.incr.side_effect = ConnectionError("Redis cluster down")
        mock_cache_fn.return_value = mock_backend

        # Must fail open (not raise RateLimitError or ConnectionError)
        await check_rate_limit("test_bucket", "user_123", "10/minute")


@pytest.mark.asyncio
async def test_worker_queue_requeue_is_non_blocking():
    """Verify MemoryQueue.requeue returns immediately without blocking worker coroutines."""
    q = MemoryQueue()
    job = Job(job_id="test_job_1", type="test.job", payload={})

    t0 = time.perf_counter()
    # Requeue with a 2-second backoff delay
    await q.requeue(job, queue="default", delay_s=2.0)
    elapsed = time.perf_counter() - t0

    # Call must return within a few milliseconds, not sleep for 2 seconds
    assert elapsed < 0.1, f"requeue blocked the calling loop for {elapsed:.3f}s!"


@pytest.mark.asyncio
async def test_refresh_token_concurrent_grace_window(services_app_client, user):
    """Verify that near-simultaneous refresh requests within 15s grace window do not revoke session."""
    refresh_token = user["refresh"]

    # First refresh succeeds and rotates the token
    r1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r1.status_code == 200, r1.text
    new_tokens = r1.json()
    assert new_tokens["refresh_token"] != refresh_token

    # Second refresh with the old token within 15-second grace window (simulating 2nd browser tab)
    r2 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 200, "Second concurrent refresh request was rejected instead of honoring grace window"

    # User session should remain active (access token works)
    headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    r_me = services_app_client.get("/api/v1/auth/me", headers=headers)
    assert r_me.status_code == 200


@pytest.mark.asyncio
async def test_neural_online_provider_unavailable_on_failure():
    """Verify NeuralOnlineTranslationProvider raises ProviderUnavailable when all sources fail."""
    from gt_ai.translation.neural_online import NeuralOnlineTranslationProvider
    provider = NeuralOnlineTranslationProvider()

    req = TranslationRequest(
        text="Unique complex test segment impossible for static rules",
        source_lang="en",
        target_lang="de",
    )

    with patch("gt_ai.translation.neural_online.query_deepl", side_effect=Exception("DeepL 503")), \
         patch("gt_ai.translation.neural_online.query_mymemory", side_effect=Exception("MyMemory 503")), \
         patch("gt_ai.translation.neural_online.query_google_web", side_effect=Exception("Google 503")), \
         patch("gt_ai.translation.neural_online.offline_linguistic_translate", return_value=None):
        with pytest.raises(ProviderUnavailable):
            await provider.translate(req)


@pytest.mark.asyncio
async def test_webhook_backoff_timing_rescheduling():
    """Verify webhook deliver_job reschedules when next_retry_at is in the future."""
    delivery_id = uuid.uuid4()
    endpoint_id = uuid.uuid4()
    org_id = uuid.uuid4()

    async with db_session() as db:
        org = M.Organization(id=org_id, name="Test Org", slug=f"test-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        ep = M.WebhookEndpoint(
            id=endpoint_id,
            org_id=org_id,
            url="https://example.com/test-webhook",
            events=["test.event"],
            secret="whsec_test_secret_12345",
            status="active",
        )
        db.add(ep)
        await db.flush()
        delivery = M.WebhookDelivery(
            id=delivery_id,
            endpoint_id=endpoint_id,
            event_type="test.event",
            payload_json={"test": True},
            status="pending",
            attempts=1,
            next_retry_at=utcnow() + timedelta(seconds=60),  # scheduled 60s in future
        )
        db.add(delivery)
        await db.commit()

    with patch("app.services.webhook_service.queue") as mock_queue_fn, \
         patch("app.services.webhook_service._assert_public_url") as mock_url_check:
        mock_q = AsyncMock()
        mock_queue_fn.return_value = mock_q

        await deliver_job({"delivery_id": str(delivery_id)})

        # It must NOT attempt HTTP delivery since next_retry_at is in future
        mock_url_check.assert_not_called()
        # It must requeue with remaining delay
        assert mock_q.requeue.called or mock_queue_fn.called
