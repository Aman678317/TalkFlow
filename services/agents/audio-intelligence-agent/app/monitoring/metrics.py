"""Prometheus-compatible performance and telemetry metrics."""
from __future__ import annotations

import time
from typing import Any
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Counters
FRAMES_PROCESSED_TOTAL = Counter(
    "audio_agent_frames_processed_total",
    "Total incoming audio frames processed",
    ["session_id"],
)

FRAMES_DROPPED_TOTAL = Counter(
    "audio_agent_frames_dropped_total",
    "Total audio frames dropped due to backpressure or errors",
    ["reason"],
)

SEGMENTS_TOTAL = Counter(
    "audio_agent_segments_total",
    "Total speech segments emitted",
    ["status"],  # "partial" or "final"
)

# Gauges
ACTIVE_SESSIONS = Gauge(
    "audio_agent_active_sessions",
    "Number of currently active audio streaming sessions",
)

QUEUE_DEPTH = Gauge(
    "audio_agent_queue_depth",
    "Current number of queued frames per session",
    ["session_id"],
)

# Histograms
FRAME_PROCESSING_LATENCY_MS = Histogram(
    "audio_agent_frame_latency_ms",
    "Total latency to process a 50ms audio frame in milliseconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0],
)

VAD_LATENCY_MS = Histogram(
    "audio_agent_vad_latency_ms",
    "Latency of VAD inference in milliseconds",
    buckets=[0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
)

DENOISE_LATENCY_MS = Histogram(
    "audio_agent_denoise_latency_ms",
    "Latency of noise suppression in milliseconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

SEGMENTATION_LATENCY_MS = Histogram(
    "audio_agent_segmentation_latency_ms",
    "Latency of segmentation logic in milliseconds",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

QUEUE_WAIT_MS = Histogram(
    "audio_agent_queue_wait_ms",
    "Time frames wait in bounded ingestion queue before processing",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0],
)

SNR_DB_OBSERVED = Histogram(
    "audio_agent_snr_db",
    "Observed Signal-to-Noise Ratio distribution in decibels",
    buckets=[-5, 0, 5, 10, 15, 20, 25, 30, 40],
)


class MetricsManager:
    """Helper wrapper for recording Prometheus metrics."""

    @staticmethod
    def record_frame(session_id: str) -> None:
        try:
            FRAMES_PROCESSED_TOTAL.labels(session_id=session_id).inc()
        except Exception:
            pass

    @staticmethod
    def record_dropped_frame(reason: str) -> None:
        try:
            FRAMES_DROPPED_TOTAL.labels(reason=reason).inc()
        except Exception:
            pass

    @staticmethod
    def record_segment(status: str) -> None:
        try:
            SEGMENTS_TOTAL.labels(status=status).inc()
        except Exception:
            pass

    @staticmethod
    def set_active_sessions(count: int) -> None:
        try:
            ACTIVE_SESSIONS.set(count)
        except Exception:
            pass

    @staticmethod
    def observe_frame_latency(ms: float) -> None:
        try:
            FRAME_PROCESSING_LATENCY_MS.observe(ms)
        except Exception:
            pass

    @staticmethod
    def observe_vad_latency(ms: float) -> None:
        try:
            VAD_LATENCY_MS.observe(ms)
        except Exception:
            pass

    @staticmethod
    def observe_denoise_latency(ms: float) -> None:
        try:
            DENOISE_LATENCY_MS.observe(ms)
        except Exception:
            pass

    @staticmethod
    def observe_segmentation_latency(ms: float) -> None:
        try:
            SEGMENTATION_LATENCY_MS.observe(ms)
        except Exception:
            pass

    @staticmethod
    def observe_queue_wait(ms: float) -> None:
        try:
            QUEUE_WAIT_MS.observe(ms)
        except Exception:
            pass

    @staticmethod
    def observe_snr(snr_db: float) -> None:
        try:
            SNR_DB_OBSERVED.observe(snr_db)
        except Exception:
            pass

    @staticmethod
    def export_metrics() -> tuple[bytes, str]:
        """Returns Prometheus text representation and content type."""
        return generate_latest(), CONTENT_TYPE_LATEST


metrics = MetricsManager()

