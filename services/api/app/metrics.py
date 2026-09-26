"""Prometheus metrics (PDD §42)."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

HTTP_REQUESTS = Counter(
    "gt_http_requests_total", "HTTP requests", ["method", "path", "status"])
HTTP_LATENCY = Histogram(
    "gt_http_request_duration_seconds", "HTTP latency", ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))

TRANSLATION_LATENCY = Histogram(
    "gt_translation_latency_ms", "End-to-end translation latency (ms)",
    ["src", "tgt", "provider"], buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10000))
STT_LATENCY = Histogram(
    "gt_stt_latency_ms", "STT latency (ms)", ["provider"],
    buckets=(100, 250, 500, 1000, 2500, 5000))
TTS_LATENCY = Histogram(
    "gt_tts_first_audio_ms", "TTS time-to-first-audio (ms)", ["provider"],
    buckets=(100, 250, 500, 1000, 2500, 5000))
E2E_LATENCY = Histogram(
    "gt_e2e_latency_ms", "Speech end -> translated audio delivered (ms)",
    ["src", "tgt"], buckets=(500, 1000, 1500, 2000, 2500, 3500, 5000, 8000, 15000))

TRANSLATION_FAILURES = Counter(
    "gt_translation_failures_total", "Translation failures", ["src", "tgt", "provider", "reason"])
STALE_AUDIO_DROPPED = Counter(
    "gt_stale_audio_dropped_total", "Stale translated audio dropped", ["reason"])
RECONNECTS = Counter("gt_ws_reconnects_total", "WebSocket reconnects with resume")
WS_CONNECTIONS = Gauge("gt_ws_connections_active", "Active WebSocket sessions")
ACTIVE_MEETINGS = Gauge("gt_active_meetings", "Active meetings")
ACTIVE_PARTICIPANTS = Gauge("gt_active_participants", "Active meeting participants")
QUEUE_DEPTH = Gauge("gt_queue_depth", "Job queue depth", ["queue"])
GPU_UTIL = Gauge("gt_gpu_utilization", "GPU utilization ratio (0..1)")

USAGE_CHARS = Counter("gt_usage_characters_total", "Translated characters", ["product"])
AUDIO_SECONDS = Counter("gt_usage_audio_seconds_total", "Audio seconds processed")


def metrics_response():
    from fastapi.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
