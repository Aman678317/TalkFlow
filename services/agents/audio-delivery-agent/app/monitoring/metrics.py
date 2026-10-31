"""Prometheus metrics registry for Agent 07 Audio Delivery Agent."""
from __future__ import annotations

import time
from typing import Dict


class AudioDeliveryMetrics:
    """In-memory Prometheus metrics tracker."""

    def __init__(self):
        self.ingested_chunks_total = 0
        self.delivered_chunks_total = 0
        self.dropped_chunks_total: Dict[str, int] = {
            "stale_deadline_exceeded": 0,
            "duplicate_chunk": 0,
            "buffer_overflow": 0,
            "non_synthetic_rejected": 0,
        }
        self.fanout_deliveries_total = 0
        self.barge_in_cancellations_total = 0
        self.latencies_ms: list[float] = []

    def record_ingest(self) -> None:
        self.ingested_chunks_total += 1

    def record_delivery(self, count: int = 1) -> None:
        self.delivered_chunks_total += count

    def record_drop(self, reason: str) -> None:
        self.dropped_chunks_total[reason] = self.dropped_chunks_total.get(reason, 0) + 1

    def record_fanout(self, recipients_count: int) -> None:
        self.fanout_deliveries_total += recipients_count

    def record_barge_in(self) -> None:
        self.barge_in_cancellations_total += 1

    def record_latency(self, latency_ms: float) -> None:
        self.latencies_ms.append(latency_ms)
        if len(self.latencies_ms) > 1000:
            self.latencies_ms.pop(0)

    def generate_prometheus_text(self) -> str:
        avg_latency = (
            sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0
        )
        lines = [
            "# HELP talkflow_audio_delivery_ingested_total Total audio chunks ingested from Agent 06",
            "# TYPE talkflow_audio_delivery_ingested_total counter",
            f"talkflow_audio_delivery_ingested_total {self.ingested_chunks_total}",
            "# HELP talkflow_audio_delivery_delivered_total Total audio chunks delivered to participants",
            "# TYPE talkflow_audio_delivery_delivered_total counter",
            f"talkflow_audio_delivery_delivered_total {self.delivered_chunks_total}",
            "# HELP talkflow_audio_delivery_fanout_total Total fanout deliveries across all participants",
            "# TYPE talkflow_audio_delivery_fanout_total counter",
            f"talkflow_audio_delivery_fanout_total {self.fanout_deliveries_total}",
            "# HELP talkflow_audio_delivery_barge_in_total Total barge-in cancellation events",
            "# TYPE talkflow_audio_delivery_barge_in_total counter",
            f"talkflow_audio_delivery_barge_in_total {self.barge_in_cancellations_total}",
            "# HELP talkflow_audio_delivery_latency_ms Average delivery latency in milliseconds",
            "# TYPE talkflow_audio_delivery_latency_ms gauge",
            f"talkflow_audio_delivery_latency_ms {avg_latency:.2f}",
        ]
        for reason, cnt in self.dropped_chunks_total.items():
            lines.append(
                f'talkflow_audio_delivery_dropped_total{{reason="{reason}"}} {cnt}'
            )
        return "\n".join(lines) + "\n"


metrics = AudioDeliveryMetrics()

