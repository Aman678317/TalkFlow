"""Pydantic REST schemas for Voice Generation Agent."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.voice_profile import VoiceCapability


class SynthesizeRequest(BaseModel):
    """Request model for speech synthesis."""
    text: str = Field(..., min_length=1, description="Approved translated text to synthesize")
    target_language: str = Field(..., description="Target language code, e.g. 'en', 'hi', 'mr', 'ja'")
    target_locale: Optional[str] = Field(None, description="Optional target locale, e.g. 'hi-IN'")
    
    # Translation and session identity
    session_id: str = "sess_default"
    conversation_id: str = "conv_default"
    segment_id: str = "seg_default"
    translation_id: str = "trans_default"
    speaker_id: str = "user_001"
    utterance_id: Optional[str] = None
    
    # Agent 05 Quality Gate Approval
    quality_decision: str = Field("ACCEPT", description="Must be ACCEPT or ACCEPT_WITH_WARNINGS")
    quality_score: float = Field(0.95, ge=0.0, le=1.0)
    
    # Voice preferences (Default TalkFlow Voice Configuration)
    voice_mode: str = Field("expressive", description="expressive | standard | consented_similarity")
    speaking_speed: str = Field("natural", description="natural | fast | slow")
    voice_similarity_enabled: bool = False
    voice_cloning_consent: bool = False  # Frontend claim (never trusted without backend ledger check)
    prosody_preservation: bool = True
    pause_preservation: bool = True
    speaker_consistency: bool = True
    requested_voice_id: Optional[str] = None
    voice_style: str = "natural"
    speaking_rate: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(1.0, ge=0.5, le=1.5)
    volume: float = Field(1.0, ge=0.0, le=2.0)
    
    # Policy controls
    privacy_mode: str = "standard"  # standard | private_only
    offline_only: bool = False
    allow_fallback: bool = True


class AudioChunkSchema(BaseModel):
    """Metadata and binary payload representation of an audio chunk."""
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


class SynthesizeResponse(BaseModel):
    """Complete response for a full synthesized utterance."""
    session_id: str
    conversation_id: str
    segment_id: str
    translation_id: str
    utterance_id: str
    speaker_id: str
    target_language: str
    target_locale: str
    provider: str
    model: str
    voice_id: str
    audio_format: str = "pcm_s16le"
    sample_rate: int = 24000
    channels: int = 1
    duration_ms: float
    chunk_count: int = 1
    audio_base64: str
    synthetic: bool = True
    is_dev: bool = False
    generation_latency_ms: float
    first_audio_chunk_latency_ms: float
    timestamp: float = Field(default_factory=time.time)


class CancellationRequest(BaseModel):
    """Request to cancel ongoing or pending synthesis for an utterance."""
    session_id: str
    segment_id: Optional[str] = None
    utterance_id: Optional[str] = None
    reason: str = "barge_in_interruption"


class CancellationResponse(BaseModel):
    cancelled: bool
    segment_id: Optional[str] = None
    utterance_id: Optional[str] = None
    message: str


class AgentInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    default_provider: str
    active_providers: List[str]
    installed_voices_count: int
    supported_languages: List[str]
    sample_rate: int
    synthetic_guarantee: bool = True
    offline_only: bool
    private_only: bool
    uptime_seconds: float

