"""Event contracts and schemas for TalkFlow Agent 02."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AudioSegmentPayload(BaseModel):
    segment_id: str
    sequence_number: int = 0
    start_timestamp: float = 0.0
    end_timestamp: float = 0.0
    duration_seconds: float = 0.0
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm16"
    audio_data_base64: Optional[str] = None
    is_final: bool = True
    quality_metrics: Optional[Dict[str, Any]] = None


class InboundAudioSegmentEvent(BaseModel):
    version: int = 1
    type: str  # "audio.segment.final" or "audio.segment.partial"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    seq: Optional[int] = None
    timestamp: float = Field(default_factory=time.time)
    payload: Optional[AudioSegmentPayload] = None


class TranscriptPartialPayload(BaseModel):
    utterance_id: str
    segment_id: str
    revision: int
    text: str
    language_hint: str
    language_probability: float
    is_final: bool = False
    provider: str
    model: str
    duration_ms: float = 0.0


class TranscriptPartialEvent(BaseModel):
    version: int = 1
    type: str = "transcript.partial"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    revision: int
    text: str
    language_hint: str
    language_probability: float
    is_final: bool = False
    provider: str
    model: str
    timestamp: float = Field(default_factory=time.time)


class TranscriptFinalPayload(BaseModel):
    utterance_id: str
    segment_id: str
    sequence_number: int = 0
    text: str
    language_hint: str
    language_probability: float
    confidence: float
    is_final: bool = True
    provider: str
    model: str
    duration_ms: float
    recognition_latency_ms: float
    words: List[Dict[str, Any]] = Field(default_factory=list)
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)


class TranscriptFinalEvent(BaseModel):
    version: int = 1
    type: str = "transcript.final"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    seq: int = 0
    duration_ms: float = 0.0
    text: str
    language_hint: str
    language_probability: float = 0.0
    confidence: float = 0.0
    is_final: bool = True
    provider: str = "faster-whisper"
    model: str = "base"
    recognition_latency_ms: float = 0.0
    quality_flags: List[str] = Field(default_factory=list)
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    words: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)

