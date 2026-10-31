"""Data models and schemas for Audio Intelligence Agent."""
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class AudioQualityMetrics(BaseModel):
    """Acoustic quality assessment metrics."""
    rms: float = Field(..., description="Root Mean Square volume (0.0 to 1.0)")
    peak: float = Field(..., description="Peak amplitude (0.0 to 1.0)")
    snr_db: float = Field(..., description="Estimated Signal-to-Noise Ratio in decibels")
    clipping_ratio: float = Field(..., description="Fraction of samples clipped at min/max range")
    silence_ratio: float = Field(..., description="Fraction of frames identified as silence")
    speech_duration_ms: int = Field(..., description="Duration of detected active speech in ms")
    noise_level_db: float = Field(..., description="Estimated background noise floor in dBFS")
    confidence: float = Field(..., description="Overall acoustic quality confidence score (0.0 to 1.0)")
    quality_status: str = Field(..., description="'good', 'fair', or 'poor'")
    issues: List[str] = Field(default_factory=list, description="Detected acoustic warnings or faults")


class AudioChunk(BaseModel):
    """Complete representation of a processed audio chunk / segment."""
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    sequence: int
    start_ms: int
    end_ms: int
    duration_ms: int
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    quality: AudioQualityMetrics
    status: str = Field(..., description="'partial' or 'final'")
    storage_ref: Optional[str] = Field(None, description="Path or URL to persisted audio payload if stored")
    # pcm_bytes is usually excluded from JSON serialization and sent via binary wire or storage ref


class AudioProcessResponse(BaseModel):
    """Response returned by batch audio processing endpoint."""
    session_id: str
    total_audio_duration_ms: int
    speech_duration_ms: int
    segments_count: int
    segments: List[AudioChunk]
    overall_quality: AudioQualityMetrics
    processing_time_ms: float


class AgentInfoResponse(BaseModel):
    """Metadata describing agent identity, configuration, and capabilities."""
    name: str
    version: str
    description: str
    canonical_format: dict[str, Any]
    supported_formats: List[str]
    vad_provider: str
    noise_suppression_provider: str
    llm_agent_enabled: bool
    llm_model: Optional[str]
    active_sessions: int
    uptime_seconds: float

