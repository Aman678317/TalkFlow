"""Prometheus metrics exporter for Neural Translation Agent."""
from __future__ import annotations

import time
from typing import Tuple
from prometheus_client import Counter, Gauge, Histogram, generate_latest

TRANSLATION_REQUESTS = Counter(
    "gt_translation_requests_total",
    "Total number of translation requests received",
    ["source_lang", "target_lang", "provider", "status"],
)

TRANSLATION_LATENCY = Histogram(
    "gt_translation_stage_latency_ms",
    "Latency of neural translation inference in milliseconds",
    ["source_lang", "target_lang", "provider"],
    buckets=(50, 100, 200, 400, 800, 1500, 2500, 5000, 10000),
)

TRANSLATION_FAILURES = Counter(
    "gt_translation_failures_total",
    "Total number of translation failures",
    ["source_lang", "target_lang", "reason"],
)

ACTIVE_SESSIONS = Gauge(
    "gt_translation_active_sessions",
    "Number of active multi-target translation sessions",
)


class TranslationMetrics:
    """Manages telemetry counters and metric exports."""

    @staticmethod
    def record_translation(src: str, tgt: str, provider: str, latency_ms: float, success: bool = True) -> None:
        status = "success" if success else "failed"
        TRANSLATION_REQUESTS.labels(source_lang=src, target_lang=tgt, provider=provider, status=status).inc()
        TRANSLATION_LATENCY.labels(source_lang=src, target_lang=tgt, provider=provider).observe(latency_ms)

    @staticmethod
    def record_failure(src: str, tgt: str, reason: str) -> None:
        TRANSLATION_FAILURES.labels(source_lang=src, target_lang=tgt, reason=reason).inc()

    @staticmethod
    def export_metrics() -> Tuple[bytes, str]:
        return generate_latest(), "text/plain; version=0.0.4; charset=utf-8"


metrics = TranslationMetrics()

