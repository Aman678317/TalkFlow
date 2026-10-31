"""Cost, Performance & Reliability Telemetry Engine (Module K).

Monitors minutes processed, time to first translated audio (TTFA), end-to-end latency,
real-time factor (RTF), memory/CPU/storage usage, and cost per completed job.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import Dict, List, Optional
import psutil

from modules.telemetry.models import JobCostBreakdown, SystemTelemetrySummary

logger = logging.getLogger("talkflow.modules.telemetry")


class TelemetryEngine:
    """Enterprise performance, cost tracking, and SLA monitoring coordinator."""

    def __init__(self, storage_dir: str = "storage") -> None:
        self.storage_dir = Path(storage_dir)
        self._total_minutes: float = 0.0
        self._completed_jobs: int = 0
        self._failed_jobs: int = 0
        self._retry_count: int = 0
        self._ttfa_samples: List[float] = []
        self._latency_samples: List[float] = []
        self._rtf_samples: List[float] = []
        self._job_costs: Dict[str, JobCostBreakdown] = {}

    def record_job_metrics(
        self,
        job_id: str,
        audio_minutes: float,
        ttfa_ms: float,
        end_to_end_ms: float,
        stt_provider: str = "faster-whisper",
        mt_provider: str = "google-gtx",
        tts_provider: str = "edge_tts",
        is_success: bool = True,
        retries: int = 0,
    ) -> JobCostBreakdown:
        """Records telemetry from a completed or failed localization job."""
        self._total_minutes += max(0.0, audio_minutes)
        self._retry_count += retries

        if is_success:
            self._completed_jobs += 1
            if ttfa_ms > 0:
                self._ttfa_samples.append(ttfa_ms)
            if end_to_end_ms > 0:
                self._latency_samples.append(end_to_end_ms)
                # RTF = processing_time_sec / audio_duration_sec
                audio_sec = audio_minutes * 60.0
                if audio_sec > 0:
                    rtf = (end_to_end_ms / 1000.0) / audio_sec
                    self._rtf_samples.append(rtf)
        else:
            self._failed_jobs += 1

        # Calculate costs based on model tiers
        # Local models = $0.00
        # Commercial cloud rates (e.g. AWS/Azure/OpenAI): STT $0.006/min, TTS $0.015/min, MT $0.00002/char (~$0.018/min)
        is_local_stt = "whisper" in stt_provider.lower()
        is_local_mt = "qwen" in mt_provider.lower() or "argos" in mt_provider.lower()
        is_local_tts = "dev_tone" in tts_provider.lower() or "piper" in tts_provider.lower()

        stt_cost = 0.0 if is_local_stt else round(audio_minutes * 0.006, 4)
        mt_cost = 0.0 if is_local_mt else round(audio_minutes * 0.004, 4)
        tts_cost = 0.0 if is_local_tts else round(audio_minutes * 0.015, 4)
        total_cost = round(stt_cost + mt_cost + tts_cost, 4)

        cost_breakdown = JobCostBreakdown(
            job_id=job_id,
            audio_minutes=round(audio_minutes, 2),
            stt_cost_usd=stt_cost,
            mt_cost_usd=mt_cost,
            tts_cost_usd=tts_cost,
            total_cost_usd=total_cost,
            is_fully_local_zero_cost=(total_cost == 0.0),
        )
        self._job_costs[job_id] = cost_breakdown
        return cost_breakdown

    def get_system_summary(self) -> SystemTelemetrySummary:
        """Returns aggregate SLA, hardware, and cost metrics."""
        total_jobs = self._completed_jobs + self._failed_jobs
        fail_rate = (self._failed_jobs / total_jobs * 100.0) if total_jobs > 0 else 0.0

        mean_ttfa = (sum(self._ttfa_samples) / len(self._ttfa_samples)) if self._ttfa_samples else 0.0
        mean_lat = (sum(self._latency_samples) / len(self._latency_samples)) if self._latency_samples else 0.0
        mean_rtf = (sum(self._rtf_samples) / len(self._rtf_samples)) if self._rtf_samples else 0.0
        total_cost = sum(c.total_cost_usd for c in self._job_costs.values())

        # Hardware metrics
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            mem_used_mb = round((mem.total - mem.available) / (1024 * 1024), 1)
        except Exception:
            cpu_pct = 0.0
            mem_used_mb = 0.0

        # Storage consumption
        storage_mb = 0.0
        if self.storage_dir.exists():
            try:
                storage_bytes = sum(f.stat().st_size for f in self.storage_dir.rglob("*") if f.is_file())
                storage_mb = round(storage_bytes / (1024 * 1024), 2)
            except Exception:
                pass

        return SystemTelemetrySummary(
            total_minutes_processed=round(self._total_minutes, 2),
            total_jobs_completed=self._completed_jobs,
            total_jobs_failed=self._failed_jobs,
            failure_rate_percent=round(fail_rate, 2),
            retry_count=self._retry_count,
            mean_ttfa_ms=round(mean_ttfa, 1),
            mean_end_to_end_latency_ms=round(mean_lat, 1),
            mean_real_time_factor=round(mean_rtf, 3),
            total_cost_usd=round(total_cost, 4),
            cpu_percent=cpu_pct,
            memory_used_mb=mem_used_mb,
            storage_used_mb=storage_mb,
        )


# Global Telemetry Instance
telemetry_engine = TelemetryEngine()

