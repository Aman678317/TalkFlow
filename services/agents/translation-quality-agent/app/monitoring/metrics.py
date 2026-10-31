"""Prometheus telemetry counters and histogram metrics for Translation Quality Agent."""
from __future__ import annotations

from typing import Tuple
from prometheus_client import Counter, Gauge, Histogram, generate_latest

QA_EVALUATIONS = Counter(
    "gt_qa_evaluations_total",
    "Total number of translation quality evaluations performed",
    ["source_lang", "target_lang", "decision"],
)

QA_CRITICAL_ERRORS = Counter(
    "gt_qa_critical_errors_total",
    "Total number of critical translation errors blocked",
    ["source_lang", "target_lang"],
)

QA_LATENCY = Histogram(
    "gt_qa_latency_ms",
    "Latency of translation quality evaluation in milliseconds",
    ["source_lang", "target_lang"],
    buckets=(5, 10, 20, 50, 100, 250, 500, 1000, 2500, 5000),
)

PENDING_HUMAN_REVIEWS = Gauge(
    "gt_qa_pending_human_reviews",
    "Current count of translations held in human review queue",
)


class MetricsManager:
    """Manages telemetry counters and metric exports."""

    def record_evaluation(
        self,
        source_lang: str,
        target_lang: str,
        decision: str,
        score: float,
        latency_ms: float,
        has_critical: bool,
    ) -> None:
        try:
            QA_EVALUATIONS.labels(source_lang=source_lang, target_lang=target_lang, decision=decision).inc()
            QA_LATENCY.labels(source_lang=source_lang, target_lang=target_lang).observe(latency_ms)
            if has_critical:
                QA_CRITICAL_ERRORS.labels(source_lang=source_lang, target_lang=target_lang).inc()
        except Exception:
            pass

    def export_prometheus(self) -> Tuple[bytes, str]:
        return generate_latest(), "text/plain; version=0.0.4; charset=utf-8"


metrics = MetricsManager()

