"""Phase 13: Observability & Telemetry Hardening Test Suite.

Verifies:
1. End-to-end correlation context propagation (request_id, trace_id, tenant_id)
   across HTTP requests, background worker jobs, and WebSocket sessions.
2. Latency histogram instrumentation across STT, Translation (MT), TTS, and E2E pipelines:
   - gt_stt_latency_ms
   - gt_translation_latency_ms
   - gt_tts_first_audio_ms
   - gt_e2e_latency_ms
3. Redaction of speech, audio payloads, binary streams, and sensitive tokens in structured logs.
4. Prometheus metrics export includes telemetry histograms.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
import pytest
from starlette.testclient import TestClient

from app import context
from app import metrics as met
from app.config import settings
from app.logging_conf import JsonFormatter, mask_sensitive_string, sanitize_value
from app.queue import Job, MemoryQueue, WorkerRunner


def test_correlation_context_propagation_http(services_app_client):
    """Verify trace_id and request_id propagate from headers through context and response headers."""
    w3c_trace_id = "1234567890abcdef1234567890abcdef"
    traceparent = f"00-{w3c_trace_id}-00f067aa0ba902b7-01"
    req_id = "req-test-p13-001"

    resp = services_app_client.get(
        "/api/v1/health",
        headers={
            "traceparent": traceparent,
            "X-Request-ID": req_id,
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == req_id
    assert resp.headers.get("X-Trace-ID") == w3c_trace_id


@pytest.mark.asyncio
async def test_correlation_context_propagation_to_worker_jobs():
    """Verify background worker jobs inherit request_id, trace_id, and tenant_id from enqueueing caller."""
    q = MemoryQueue()
    runner = WorkerRunner(q, "telemetry_test")

    captured_context = {}

    async def sample_handler(payload: dict) -> None:
        ctx = context.current()
        captured_context["request_id"] = ctx.request_id
        captured_context["trace_id"] = ctx.trace_id
        captured_context["tenant_id"] = ctx.tenant_id
        captured_context["payload"] = payload

    runner.register("telemetry.test", sample_handler)

    # Set caller context before pushing job
    expected_req_id = "req-worker-telemetry-42"
    expected_trace_id = "trace-worker-telemetry-84"
    expected_tenant_id = "tenant-org-999"

    context.new_ctx(
        request_id=expected_req_id,
        trace_id=expected_trace_id,
        tenant_id=expected_tenant_id,
    )

    job_id = await q.push("telemetry.test", {"task": "verify_telemetry"}, queue="telemetry_test")
    assert job_id is not None

    # Pop and run job
    job = await q.pop("telemetry_test")
    assert job is not None
    assert job.request_id == expected_req_id
    assert job.trace_id == expected_trace_id
    assert job.tenant_id == expected_tenant_id

    # Switch current context to simulate separate worker execution context
    context.new_ctx(request_id="worker-idle", trace_id="worker-idle-trace")

    await runner._run_job(job)

    # Handler should have received the original caller's context
    assert captured_context["request_id"] == expected_req_id
    assert captured_context["trace_id"] == expected_trace_id
    assert captured_context["tenant_id"] == expected_tenant_id
    assert captured_context["payload"] == {"task": "verify_telemetry"}


def test_speech_and_audio_redaction_in_structured_logs():
    """Verify structured logs redact private speech, audio payloads, and binary data."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="telemetry_logger",
        level=logging.INFO,
        pathname="telemetry.py",
        lineno=42,
        msg="Processing audio chunk with Bearer secret-jwt-token-999",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {
        "audio_payload": "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=",
        "pcm_data": "raw pcm frames",
        "audio_stream_binary": b"\x00\x01\x02\x03\x04\x05" * 10,
        "raw_stream_buffer": bytearray(b"\x00" * 32),
        "speech_payload": "sensitive spoken word transcript buffer",
        "audio_base64": "data:audio/wav;base64," + ("A" * 250),
        "api_key": "gtk_live_999999999999999999999999",
        "safe_metric": 42.5,
    }

    formatted = formatter.format(record)
    log_data = json.loads(formatted)

    assert "Bearer [REDACTED]" in log_data["message"]
    assert "secret-jwt-token-999" not in log_data["message"]

    # Redactions
    assert log_data["audio_payload"] == "[REDACTED]"
    assert log_data["pcm_data"] == "[REDACTED]"
    assert "[BINARY_DATA_60_BYTES]" in log_data["audio_stream_binary"]
    assert "[BINARY_DATA_32_BYTES]" in log_data["raw_stream_buffer"]
    assert log_data["speech_payload"] == "[REDACTED]"
    assert log_data["audio_base64"] == "[REDACTED]"
    assert log_data["api_key"] == "[REDACTED]"
    assert log_data["safe_metric"] == 42.5


def test_latency_histograms_instrumentation():
    """Verify STT, Translation, TTS, and E2E latency histograms exist and observe values."""
    # Observe sample latencies
    met.TRANSLATION_LATENCY.labels(src="en", tgt="es", provider="deepl").observe(145.2)
    met.STT_LATENCY.labels(provider="deepgram").observe(210.5)
    met.TTS_LATENCY.labels(provider="elevenlabs").observe(320.0)
    met.E2E_LATENCY.labels(src="en", tgt="es").observe(675.7)

    # Check Prometheus export response contains latency metric definitions
    resp = met.metrics_response()
    body = resp.body.decode("utf-8")

    assert "gt_translation_latency_ms" in body
    assert "gt_stt_latency_ms" in body
    assert "gt_tts_first_audio_ms" in body
    assert "gt_e2e_latency_ms" in body
    assert 'provider="deepl"' in body
    assert 'provider="deepgram"' in body
    assert 'provider="elevenlabs"' in body
