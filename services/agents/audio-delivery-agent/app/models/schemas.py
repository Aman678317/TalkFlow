"""Pydantic schemas for Agent 07 Audio Delivery API requests and responses."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AudioChunkIngestRequest(BaseModel):
    """Payload representing an incoming audio chunk from Agent 06 (Voice Generation)."""
    version: int = 1
    type: str = "tts.chunk"
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    utterance_id: Optional[str] = None
    translation_id: Optional[str] = None
    seq: int = 1
    target_lang: str
    voice_id: str = "default_voice"
    provider: str = "dev_synthetic"
    model: str = "dev-tone-v1"
    chunk_index: int = 0
    is_final_chunk: bool = False
    sample_rate: int = 24000
    channels: int = 1
    encoding: str = "pcm_s16le"
    format: str = "wav"
    duration_ms: float = 0.0
    audio_base64: str = ""
    synthetic: bool = True
    audio_origin: str = "synthetic_tts"
    start_wall_ms: Optional[float] = None
    created_at: float = Field(default_factory=time.time)


class UtteranceFinalizeRequest(BaseModel):
    """Payload representing synthesis completion from Agent 06."""
    version: int = 1
    type: str = "tts.completed"
    session_id: str
    conversation_id: str
    speaker_id: str
    segment_id: str
    utterance_id: Optional[str] = None
    translation_id: Optional[str] = None
    target_lang: str
    voice_id: str = "default_voice"
    provider: str = "dev_synthetic"
    total_chunks: int = 1
    total_duration_ms: float = 0.0
    created_at: float = Field(default_factory=time.time)


class RegisterParticipantRequest(BaseModel):
    """Request to register or update a participant in a meeting room."""
    participant_id: str
    room_id: str
    tenant_id: str = "org_default"
    display_name: str = "Participant"
    hear_lang: str = "en"
    speaking_lang: str = "en"
    playback_mode: str = "translated"  # original | translated | both | muted
    translation_audio_enabled: bool = True
    original_audio_enabled: bool = False
    captions_enabled: bool = True
    supports_tts_chunk_index: bool = True


class UpdatePreferencesRequest(BaseModel):
    """Request to update audio delivery preferences for a participant."""
    hear_lang: Optional[str] = None
    playback_mode: Optional[str] = None
    translation_audio_enabled: Optional[bool] = None
    original_audio_enabled: Optional[bool] = None
    captions_enabled: Optional[bool] = None


class CancellationRequest(BaseModel):
    """Request to cancel/flush playback due to speaker interruption or barge-in."""
    room_id: str
    session_id: Optional[str] = None
    speaker_id: Optional[str] = None
    segment_id: Optional[str] = None
    utterance_id: Optional[str] = None
    reason: str = "barge_in_interruption"
    timestamp: float = Field(default_factory=time.time)


class BrainQueryRequest(BaseModel):
    """Query request for Agent 07's intelligent diagnostic brain."""
    query: str
    context: Dict[str, Any] = Field(default_factory=dict)


class BrainQueryResponse(BaseModel):
    """Diagnostic explanation and recommendation from Agent 07 brain."""
    answer: str
    confidence: float = 1.0
    source: str = "expert_engine"
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class IngestionResponse(BaseModel):
    """Response returned upon ingesting an audio chunk."""
    status: str  # queued | scheduled | published | dropped | error
    segment_id: str
    chunk_index: int
    target_lang: str
    action_taken: str
    recipients_count: int = 0
    jitter_buffer_size: int = 0
    latency_ms: float = 0.0
    details: Optional[str] = None


class RoomStatusResponse(BaseModel):
    """Current state of a room session."""
    room_id: str
    tenant_id: str
    participant_count: int
    active_tracks: List[str]
    participants: List[Dict[str, Any]]
    active_utterances: List[str]

