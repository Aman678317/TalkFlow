"""Latency tracking and percentile calculations for translation stages."""
from __future__ import annotations

import statistics
import time
from typing import Dict, List, Optional, Tuple


class LatencyTracker:
    """Records latencies in sliding windows and calculates percentiles."""

    def __init__(self, window_size: int = 500) -> None:
        self.window_size = window_size
        self._samples: Dict[Tuple[str, str], List[float]] = {}

    def record(self, src: str, tgt: str, latency_ms: float) -> None:
        pair = (src.lower(), tgt.lower())
        if pair not in self._samples:
            self._samples[pair] = []
        samples = self._samples[pair]
        samples.append(latency_ms)
        if len(samples) > self.window_size:
            samples.pop(0)

    def get_stats(self, src: str, tgt: str) -> Dict[str, float]:
        pair = (src.lower(), tgt.lower())
        samples = self._samples.get(pair, [])
        if not samples:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}

        sorted_s = sorted(samples)
        n = len(sorted_s)
        p50 = sorted_s[int(0.50 * n)]
        p95 = sorted_s[min(int(0.95 * n), n - 1)]
        p99 = sorted_s[min(int(0.99 * n), n - 1)]
        mean = statistics.mean(sorted_s)

        return {
            "count": float(n),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "mean": round(mean, 2),
        }


latency_tracker = LatencyTracker()

