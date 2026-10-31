"""Pydantic schemas for Speech Recognition Agent."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WordTimestamp(BaseModel):
    word: str
    start: float = Field(..., description="Start time in seconds relative to segment")
    end: float = Field(..., description="End time in seconds relative to segment")
    confidence: float = Field(default=1.0, description="Confidence score 0.0 to 1.0")


class SegmentTiming(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    words: List[WordTimestamp] = Field(default_factory=list)


class STTResult(BaseModel):
    text: str
    language: str
    language_probability: float = 0.0
    confidence: float = 0.0
    provider: str = "faster-whisper"
    model: str = "base"
    duration_ms: float = 0.0
    segments: List[SegmentTiming] = Field(default_factory=list)
    words: List[WordTimestamp] = Field(default_factory=list)
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0


class TranscribeRequest(BaseModel):
    session_id: Optional[str] = "default_session"
    conversation_id: Optional[str] = "default_session"
    speaker_id: Optional[str] = "user_001"
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    language_hint: Optional[str] = None
    sample_rate: int = 16000


class TranscribeResponse(BaseModel):
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    text: str
    language_hint: str
    language_probability: float
    confidence: float
    is_final: bool = True
    provider: str
    model: str
    duration_ms: float
    recognition_latency_ms: float
    segments: List[SegmentTiming] = Field(default_factory=list)
    words: List[WordTimestamp] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)


class LanguageCapability(BaseModel):
    code: str
    name: str
    provider: str
    model: str
    available: bool = True
    evaluation_status: str = "verified"
    code_switch_supported: bool = True
    known_limitations: Optional[str] = None


class AgentInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    provider: str
    model: str
    device: str
    compute_type: str
    canonical_format: Dict[str, Any]
    supported_languages_count: int
    streaming_supported: bool
    agent_brain_enabled: bool
    agent_brain_model: Optional[str] = None
    active_sessions: int
    uptime_seconds: float

