"""TalkFlow event schemas for Agent 06 Voice Generation."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Agent05QualityFinalEvent(BaseModel):
    """Inbound quality assessment event emitted by Agent 05 (Translation Quality QA)."""
    version: int = 1
    type: str = "quality.assessment.final"
    evaluation_id: str
    candidate_hash: str
    session_id: str
    conversation_id: str
    speaker_id: str = "user_001"
    utterance_id: Optional[str] = None
    segment_id: str
    translation_id: Optional[str] = None
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    decision: str  # ACCEPT | ACCEPT_WITH_WARNINGS | RETRY_WITH_ALTERNATE_PROVIDER | HOLD_FOR_HUMAN | REJECT
    overall_score: float
    is_safe_for_voice: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class TTSStartedEvent(BaseModel):
    """Emitted when speech synthesis initiates."""
    version: int = 1
    type: str = "tts.started"
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    utterance_id: str
    translation_id: str
    seq: int = 1
    target_lang: str
    voice_id: str
    provider: str
    created_at: float = Field(default_factory=time.time)


class TTSChunkEvent(BaseModel):
    """Emitted for every generated audio chunk dispatched to Agent 07."""
    version: int = 1
    type: str = "tts.chunk"
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    utterance_id: str
    translation_id: str
    seq: int = 1
    target_lang: str
    voice_id: str
    provider: str
    model: str
    chunk_index: int
    is_final_chunk: bool = False
    sample_rate: int = 24000
    channels: int = 1
    encoding: str = "pcm_s16le"
    format: str = "wav"
    duration_ms: float = 0.0
    audio_base64: str
    synthetic: bool = True
    is_dev: bool = False
    created_at: float = Field(default_factory=time.time)


class TTSCompletedEvent(BaseModel):
    """Emitted when all chunks for an utterance have finished synthesis."""
    version: int = 1
    type: str = "tts.completed"
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    utterance_id: str
    translation_id: str
    target_lang: str
    voice_id: str
    provider: str
    total_chunks: int
    total_duration_ms: float
    generation_latency_ms: float
    first_chunk_latency_ms: float
    created_at: float = Field(default_factory=time.time)


class TTSFailedEvent(BaseModel):
    """Emitted when synthesis encounters an unrecoverable error."""
    version: int = 1
    type: str = "tts.failed"
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    utterance_id: Optional[str] = None
    translation_id: Optional[str] = None
    target_lang: str
    error_code: str
    error_message: str
    created_at: float = Field(default_factory=time.time)


class TTSCancelledEvent(BaseModel):
    """Emitted when synthesis is cancelled due to barge-in or invalidation."""
    version: int = 1
    type: str = "tts.cancelled"
    session_id: str
    segment_id: Optional[str] = None
    utterance_id: Optional[str] = None
    reason: str
    created_at: float = Field(default_factory=time.time)

