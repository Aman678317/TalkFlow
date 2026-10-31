"""Prometheus-compatible metrics for Language Intelligence Agent."""
from __future__ import annotations

import time
from typing import Dict, Tuple
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Request counters
REQUEST_COUNT = Counter(
    "talkflow_lang_requests_total",
    "Total language intelligence requests processed",
    ["method", "status"],
)

# Detected language counter
LANGUAGE_COUNT = Counter(
    "talkflow_lang_detected_total",
    "Total utterances classified by language and script",
    ["language", "script", "provider"],
)

# Code-switching occurrences
CODE_SWITCH_COUNT = Counter(
    "talkflow_lang_codeswitch_total",
    "Total code-switching utterances detected",
    ["primary_language", "secondary_languages"],
)

# Ambiguity counter
AMBIGUITY_COUNT = Counter(
    "talkflow_lang_ambiguity_total",
    "Total utterances marked ambiguous or undetermined",
    ["reason"],
)

# Latency histogram
LATENCY_HISTOGRAM = Histogram(
    "talkflow_lang_latency_seconds",
    "End-to-end language detection latency in seconds",
    ["endpoint"],
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Active sessions gauge
ACTIVE_SESSIONS_GAUGE = Gauge(
    "talkflow_lang_active_sessions",
    "Number of currently active conversation sessions",
)


class LanguageMetricsManager:
    """Manages telemetry recording and Prometheus export."""

    @staticmethod
    def record_detection(
        language: str,
        script: str,
        provider: str,
        latency_sec: float,
        is_multilingual: bool = False,
        secondary_langs: str = "",
        status: str = "success",
        reason: str = "none",
    ) -> None:
        REQUEST_COUNT.labels(method="analyze", status=status).inc()
        LANGUAGE_COUNT.labels(language=language, script=script, provider=provider).inc()
        LATENCY_HISTOGRAM.labels(endpoint="analyze").observe(latency_sec)

        if is_multilingual:
            CODE_SWITCH_COUNT.labels(primary_language=language, secondary_languages=secondary_langs).inc()

        if status in ("ambiguous", "insufficient_confidence") or language == "und":
            AMBIGUITY_COUNT.labels(reason=reason).inc()

    @staticmethod
    def set_active_sessions(count: int) -> None:
        ACTIVE_SESSIONS_GAUGE.set(count)

    @staticmethod
    def export_metrics() -> Tuple[bytes, str]:
        """Returns (prometheus_data, content_type)."""
        return generate_latest(), CONTENT_TYPE_LATEST


metrics = LanguageMetricsManager()

