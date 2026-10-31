"""Data models for Dynamic Model Selection & Benchmarking (Module F)."""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ModelProfile(BaseModel):
    """Metadata, hardware requirements, and quality tier for a model candidate."""
    model_id: str
    task: str  # 'stt', 'mt', 'tts', 'diarization', 'vad', 'enhancement'
    name: str
    provider: str
    supported_languages: List[str] = Field(default_factory=lambda: ["en"])
    quality_score: float = 0.90  # 0.0 to 1.0 (estimated BLEU/WER/MOS proxy)
    typical_latency_ms: float = 200.0
    typical_rtf: float = 0.25  # Real-Time Factor (< 1.0 is faster than real time)
    memory_mb: int = 512
    device_required: str = "cpu"  # 'cpu', 'cuda', 'mps', 'any'
    license_type: str = "permissive"  # 'permissive' (MIT/Apache), 'open_source', 'commercial_api'
    cost_per_minute_usd: float = 0.0
    supports_streaming: bool = True
    is_available_locally: bool = True
    is_healthy: bool = True


class RoutingConstraint(BaseModel):
    """Execution constraints for selecting the optimal model."""
    task: str
    target_language: str
    source_language: Optional[str] = None
    max_latency_ms: Optional[float] = None
    prefer_local_only: bool = False
    max_cost_per_minute: Optional[float] = None
    require_streaming: bool = False
    hardware_available: str = "cpu"


class ModelSelectionResult(BaseModel):
    """Resolved primary and fallback model candidates."""
    task: str
    primary_model: ModelProfile
    fallback_chain: List[ModelProfile] = Field(default_factory=list)
    reasoning: str
    evaluated_candidates_count: int

