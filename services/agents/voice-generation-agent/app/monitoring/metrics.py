"""Metrics and performance telemetry for Agent 06."""
from __future__ import annotations

import time
from typing import Dict


class TTSMetrics:
    """In-memory telemetry counters and latency summaries."""

    def __init__(self) -> None:
        self.requests_total: int = 0
        self.requests_success: int = 0
        self.requests_failed: int = 0
        self.gate_rejected_total: int = 0
        self.cancellations_total: int = 0
        self.chunks_generated_total: int = 0
        self.audio_duration_seconds_total: float = 0.0
        self.synthesis_time_seconds_total: float = 0.0

        # Provider counts
        self.provider_usage: Dict[str, int] = {
            "dev_tone": 0,
            "system": 0,
            "kokoro": 0,
            "piper": 0,
            "azure": 0,
        }

        # Language counts
        self.language_usage: Dict[str, int] = {}

    def record_synthesis(
        self,
        provider: str,
        language: str,
        duration_ms: float,
        latency_ms: float,
        chunk_count: int = 1,
    ) -> None:
        """Record successful synthesis."""
        self.requests_total += 1
        self.requests_success += 1
        self.chunks_generated_total += chunk_count
        self.audio_duration_seconds_total += duration_ms / 1000.0
        self.synthesis_time_seconds_total += latency_ms / 1000.0

        prov_clean = provider.lower()
        self.provider_usage[prov_clean] = self.provider_usage.get(prov_clean, 0) + 1

        lang_clean = language.lower()
        self.language_usage[lang_clean] = self.language_usage.get(lang_clean, 0) + 1

    def record_failure(self) -> None:
        self.requests_total += 1
        self.requests_failed += 1

    def record_rejection(self) -> None:
        self.gate_rejected_total += 1

    def record_cancellation(self) -> None:
        self.cancellations_total += 1

    def to_prometheus(self) -> str:
        """Format metrics in Prometheus text exposition format."""
        lines = [
            "# HELP talkflow_tts_requests_total Total number of TTS synthesis requests received",
            "# TYPE talkflow_tts_requests_total counter",
            f"talkflow_tts_requests_total {self.requests_total}",
            f'talkflow_tts_requests_total{{status="success"}} {self.requests_success}',
            f'talkflow_tts_requests_total{{status="failure"}} {self.requests_failed}',
            "# HELP talkflow_tts_gate_rejected_total Total requests rejected by quality gate",
            "# TYPE talkflow_tts_gate_rejected_total counter",
            f"talkflow_tts_gate_rejected_total {self.gate_rejected_total}",
            "# HELP talkflow_tts_cancellations_total Total synthesis cancellations recorded",
            "# TYPE talkflow_tts_cancellations_total counter",
            f"talkflow_tts_cancellations_total {self.cancellations_total}",
            "# HELP talkflow_tts_chunks_total Total audio chunks emitted",
            "# TYPE talkflow_tts_chunks_total counter",
            f"talkflow_tts_chunks_total {self.chunks_generated_total}",
            "# HELP talkflow_tts_audio_seconds_total Total seconds of synthetic audio generated",
            "# TYPE talkflow_tts_audio_seconds_total counter",
            f"talkflow_tts_audio_seconds_total {self.audio_duration_seconds_total:.3f}",
            "# HELP talkflow_tts_latency_seconds_total Total synthesis compute time",
            "# TYPE talkflow_tts_latency_seconds_total counter",
            f"talkflow_tts_latency_seconds_total {self.synthesis_time_seconds_total:.3f}",
        ]
        for prov, count in self.provider_usage.items():
            lines.append(f'talkflow_tts_provider_usage_total{{provider="{prov}"}} {count}')
        for lang, count in self.language_usage.items():
            lines.append(f'talkflow_tts_language_usage_total{{language="{lang}"}} {count}')

        return "\n".join(lines) + "\n"


metrics = TTSMetrics()

