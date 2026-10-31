"""Data models for Cost, Performance & Reliability Telemetry (Module K)."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class JobCostBreakdown(BaseModel):
    """Granular cost calculation per job based on model tiers."""
    job_id: str
    audio_minutes: float
    stt_cost_usd: float = 0.0
    mt_cost_usd: float = 0.0
    tts_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    currency: str = "USD"
    is_fully_local_zero_cost: bool = True


class SystemTelemetrySummary(BaseModel):
    """Aggregate performance, latency, and reliability metrics."""
    total_minutes_processed: float = 0.0
    total_jobs_completed: int = 0
    total_jobs_failed: int = 0
    failure_rate_percent: float = 0.0
    retry_count: int = 0
    mean_ttfa_ms: float = 0.0  # Time to first translated audio
    mean_end_to_end_latency_ms: float = 0.0
    mean_real_time_factor: float = 0.0
    total_cost_usd: float = 0.0
    cpu_percent: float = 0.0
    memory_used_mb: float = 0.0
    storage_used_mb: float = 0.0

