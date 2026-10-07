"""Phase 9: Observability, Metrics & Telemetry Hardening Test Suite.

Verifies:
1. Structured JSON logging with recursive sensitive data masking (passwords, tokens, API keys).
2. W3C traceparent header parsing and correlation context propagation (X-Trace-ID, X-Request-ID).
3. Prometheus label cardinality protection on dynamic unrouted paths.
4. Background worker job executions and queue depth Prometheus instrumentation.
5. Security violation tracking (CSRF failures).
6. /metrics endpoint gating (disabled flag and production token authentication).
"""
from __future__ import annotations

import asyncio
import json
import logging
import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.logging_conf import JsonFormatter, mask_sensitive_string, sanitize_value
from app.queue import Job, MemoryQueue, WorkerRunner
import app.metrics as met


def test_sensitive_data_masking_in_logs():
    """Verify JsonFormatter redacts secrets, bearer tokens, and credentials."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Authenticated user with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret and password=supersecret123",
        args=(),
        exc_info=None,
    )
    # Add extra fields containing sensitive dictionary keys
    record.extra_fields = {
        "user_email": "user@example.com",
        "password": "plain_text_password",
        "api_key": "gt_sec_9999999",
        "session_token": "token_abc123",
        "nested": {
            "refresh_token": "rt_88888",
            "safe_field": "visible_value",
        },
    }

    formatted = formatter.format(record)
    log_data = json.loads(formatted)

    # Message secrets must be redacted
    assert "Bearer [REDACTED]" in log_data["message"]
    assert "password=[REDACTED]" in log_data["message"]
    assert "supersecret123" not in log_data["message"]
    assert "eyJhbGciOi" not in log_data["message"]

    # Extra sensitive fields must be [REDACTED]
    assert log_data["user_email"] == "user@example.com"
    assert log_data["password"] == "[REDACTED]"
    assert log_data["api_key"] == "[REDACTED]"
    assert log_data["session_token"] == "[REDACTED]"
    assert log_data["nested"]["refresh_token"] == "[REDACTED]"
    assert log_data["nested"]["safe_field"] == "visible_value"


def test_w3c_traceparent_and_request_id_propagation(services_app_client):
    """Incoming W3C traceparent must populate X-Trace-ID and correlate response headers."""
    w3c_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    traceparent = f"00-{w3c_trace_id}-00f067aa0ba902b7-01"
    custom_req_id = "req-custom-98765"

    resp = services_app_client.get(
        "/api/v1/health",
        headers={
            "traceparent": traceparent,
            "X-Request-ID": custom_req_id,
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Trace-ID") == w3c_trace_id
    assert resp.headers.get("X-Request-ID") == custom_req_id


def test_prometheus_label_cardinality_protection(services_app_client):
    """Dynamic unrouted paths must collapse UUIDs and numeric IDs to avoid metric explosion."""
    from app.middleware import _norm_path
    from starlette.requests import Request

    # 1. Test unit normalization for raw URLs
    scope_uuid = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/meetings/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "headers": [],
    }
    req_uuid = Request(scope_uuid)
    assert _norm_path(req_uuid) == "/api/v1/meetings/{id}"

    scope_hex = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/documents/65733f8d75244e8897965300037ea91e",
        "headers": [],
    }
    req_hex = Request(scope_hex)
    assert _norm_path(req_hex) == "/api/v1/documents/{id}"


@pytest.mark.asyncio
async def test_worker_job_prometheus_metrics():
    """WorkerRunner must record job execution counts and latency in Prometheus metrics."""
    q = MemoryQueue()
    runner = WorkerRunner(q, queue_name="metric_q", backoff_multiplier=0.01)

    async def success_handler(payload: dict) -> None:
        await asyncio.sleep(0.01)

    runner.register("metric.job", success_handler)
    runner.start()

    try:
        await q.push("metric.job", {"x": 1}, queue="metric_q")

        # Wait for worker to execute
        for _ in range(20):
            if runner.metrics["succeeded"] == 1:
                break
            await asyncio.sleep(0.05)

        assert runner.metrics["succeeded"] == 1

        # Check Prometheus metric directly
        val = met.JOB_EXECUTIONS.labels(queue="metric_q", type="metric.job", status="success")._value.get()
        assert val >= 1.0
    finally:
        await runner.stop()
        await q.close()


def test_csrf_security_violation_metric(services_app_client):
    """CSRF failures must increment gt_security_violations_total{type='csrf_failed'}."""
    initial_violations = met.SECURITY_VIOLATIONS.labels(type="csrf_failed")._value.get()

    # Post with cookie auth but invalid CSRF token
    resp = services_app_client.post(
        "/api/v1/meetings",
        cookies={"refresh_token": "some_refresh_cookie"},
        headers={"x-talkflow-csrf": "forged_csrf_value"},
        json={"title": "Attacker Meeting"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."

    new_violations = met.SECURITY_VIOLATIONS.labels(type="csrf_failed")._value.get()
    assert new_violations == initial_violations + 1


def test_metrics_endpoint_gating_and_authentication(services_app_client, monkeypatch):
    """Metrics endpoint must enforce metrics_enabled and metrics_token authentication in production."""
    from app.routers import health

    # 1. Disabled endpoint returns 404
    monkeypatch.setattr(health.settings, "metrics_enabled", False)
    resp = services_app_client.get("/metrics")
    assert resp.status_code == 404

    # 2. Re-enabled in dev returns 200 without token
    monkeypatch.setattr(health.settings, "metrics_enabled", True)
    monkeypatch.setattr(health.settings, "app_env", "development")
    resp = services_app_client.get("/metrics")
    assert resp.status_code == 200
    assert "gt_http_requests_total" in resp.text

    # 3. Production mode with metrics_token requires valid authentication
    monkeypatch.setattr(health.settings, "app_env", "production")
    monkeypatch.setattr(health.settings, "metrics_token", "secret-ops-token-12345")

    # Unauthenticated request -> 401
    resp_unauth = services_app_client.get("/metrics")
    assert resp_unauth.status_code == 401

    # Invalid token -> 401
    resp_bad = services_app_client.get("/metrics", headers={"Authorization": "Bearer bad-token"})
    assert resp_bad.status_code == 401

    # Valid Bearer token -> 200
    resp_auth = services_app_client.get("/metrics", headers={"Authorization": "Bearer secret-ops-token-12345"})
    assert resp_auth.status_code == 200
    assert "gt_http_requests_total" in resp_auth.text

    # Valid X-Metrics-Token header -> 200
    resp_hdr = services_app_client.get("/metrics", headers={"X-Metrics-Token": "secret-ops-token-12345"})
    assert resp_hdr.status_code == 200
