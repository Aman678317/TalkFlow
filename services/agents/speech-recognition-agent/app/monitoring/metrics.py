"""Prometheus metrics instrumentation for Speech Recognition Agent."""
from __future__ import annotations

import time
from typing import Tuple
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class STTMetrics:
    """Prometheus metrics collector for STT latency and throughput."""

    def __init__(self):
        self.registry = CollectorRegistry(auto_describe=True)

        self.requests_total = Counter(
            "stt_requests_total",
            "Total speech recognition requests processed",
            ["status", "provider", "model"],
            registry=self.registry,
        )

        self.recognition_latency = Histogram(
            "stt_recognition_latency_seconds",
            "Speech recognition latency in seconds",
            ["provider", "model"],
            buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0),
            registry=self.registry,
        )

        self.active_sessions = Gauge(
            "stt_active_sessions",
            "Number of active concurrent STT sessions",
            registry=self.registry,
        )

        self.partial_emissions = Counter(
            "stt_partial_emissions_total",
            "Total streaming partial transcript updates emitted",
            registry=self.registry,
        )

        self.hallucinations_detected = Counter(
            "stt_hallucinations_detected_total",
            "Total acoustic hallucinations or repetitions filtered",
            ["reason"],
            registry=self.registry,
        )

    def observe_transcription(self, provider: str, model: str, duration_sec: float, success: bool = True):
        status = "success" if success else "error"
        self.requests_total.labels(status=status, provider=provider, model=model).inc()
        if success:
            self.recognition_latency.labels(provider=provider, model=model).observe(duration_sec)

    def export_metrics(self) -> Tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


metrics = STTMetrics()

