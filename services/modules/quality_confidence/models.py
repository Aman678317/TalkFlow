"""Data models for Audio Quality, Uncertainty & Confidence Tracking (Module G)."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class UncertainSpan(BaseModel):
    """An identified word or span exhibiting low transcription or translation confidence."""
    text: str
    start_ms: int
    end_ms: int
    confidence: float
    reason: str  # 'acoustic_uncertainty', 'hallucination_pattern', 'repetition_loop'


class SegmentQualityAudit(BaseModel):
    """Immutable per-segment quality and telemetry audit record."""
    audit_id: str
    segment_id: str
    source_segment_id: Optional[str] = None
    speaker_id: str = "speaker_0"
    start_ms: int = 0
    end_ms: int = 0
    duration_ms: int = 0
    
    # Text
    source_text: str = ""
    translated_text: str = ""
    source_language: str = "en"
    target_language: str = "es"
    
    # Confidence & Quality
    transcription_confidence: float = 0.95
    has_acoustic_uncertainty: bool = False
    uncertain_spans: List[UncertainSpan] = Field(default_factory=list)
    quality_decision: str = "ACCEPT"  # 'ACCEPT', 'ACCEPT_WITH_WARNINGS', 'REJECT', 'MANUAL_REVIEW'
    quality_score: float = 0.95
    quality_flags: List[str] = Field(default_factory=list)
    
    # TTS Delivery Status
    tts_status: str = "SUCCESS"  # 'SUCCESS', 'FALLBACK', 'RETRIED', 'FAILED'
    tts_provider: str = "edge_tts"
    tts_voice: str = "default"
    retry_count: int = 0
    error_message: Optional[str] = None
    
    # Manual Review
    is_manually_corrected: bool = False
    corrected_text: Optional[str] = None
    reviewed_by: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)

