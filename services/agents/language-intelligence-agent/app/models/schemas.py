"""Pydantic schemas for Language Intelligence Agent REST API and analytical outputs."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateLanguage(BaseModel):
    language: str
    confidence: float
    provider: Optional[str] = None


class LanguageSpan(BaseModel):
    language: str
    script: str
    text: str
    text_start_offset: int
    text_end_offset: int
    word_start_index: Optional[int] = None
    word_end_index: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    confidence: float
    evidence_status: str = "detected"


class DetectionResult(BaseModel):
    language: str
    confidence: float
    provider: str
    alternatives: List[CandidateLanguage] = Field(default_factory=list)


class LanguageAnalysisResponse(BaseModel):
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    seq: int = 1
    original_text: str
    primary_language: str
    primary_language_script: str
    secondary_languages: List[str] = Field(default_factory=list)
    is_multilingual: bool = False
    detection_status: str = "success"  # success | ambiguous | insufficient_confidence
    confidence: float
    language_spans: List[LanguageSpan] = Field(default_factory=list)
    uncertain_spans: List[LanguageSpan] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    capability_status: Dict[str, Any] = Field(default_factory=dict)
    analysis_latency_ms: float = 0.0
    provider: str = "language_intelligence"
    model_version: str = "1.0.0"


class AgentInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    primary_text_provider: str
    fallback_text_provider: str
    code_switch_enabled: bool
    hinglish_detection_enabled: bool
    supported_languages_count: int
    active_sessions: int
    agent_brain_enabled: bool
    agent_brain_model: Optional[str] = None
    uptime_seconds: float
