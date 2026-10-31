"""Data models for Multi-Language Meeting Fan-Out Engine (Module A).

Implements Section 3, 5, 6, 9, 14 of the Master Product Specification.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class Participant(BaseModel):
    """Participant in a multi-language meeting room session."""
    participant_id: str
    room_id: str = "default_room"
    name: str = "Participant"
    tenant_id: str = "org_default"
    spoken_language: str = "auto"
    preferred_listen_language: Optional[str] = None
    preferred_language: Optional[str] = None  # Alias for preferred_listen_language
    understood_languages: List[str] = Field(default_factory=list)
    playback_mode: str = "translated"  # 'translated', 'original', 'dual', 'captions_only'
    audio_mode: str = "translated"  # 'translated', 'original', 'dual', 'captions_only'
    voice_profile: str = "default"
    voice_mode: str = "expressive"
    speaking_speed: str = "natural"
    voice_similarity_enabled: bool = False
    voice_cloning_consent: bool = False
    prosody_preservation: bool = True
    pause_preservation: bool = True
    speaker_consistency: bool = True
    voice_speed: float = 1.0
    subtitle_enabled: bool = True
    subtitles_enabled: bool = True
    original_audio_enabled: bool = False
    include_self_translation: bool = False
    original_volume: float = 0.2  # Volume when 'dual' is selected (ducking)
    translated_volume: float = 1.0
    is_active: bool = True
    joined_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class ParticipantLanguagePreference(BaseModel):
    """Explicit persistent participant language & audio preference record (Section 3)."""
    participant_id: str
    room_id: str
    tenant_id: str = "org_default"
    preferred_language: str = "en"
    audio_mode: str = "translated"  # 'translated', 'original', 'dual', 'captions_only'
    voice_profile: str = "default"
    voice_mode: str = "expressive"
    speaking_speed: str = "natural"
    voice_similarity_enabled: bool = False
    voice_cloning_consent: bool = False
    prosody_preservation: bool = True
    pause_preservation: bool = True
    speaker_consistency: bool = True
    voice_speed: float = 1.0
    subtitle_enabled: bool = True
    original_audio_enabled: bool = False
    include_self_translation: bool = False
    understood_languages: List[str] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)


class SourceUtterance(BaseModel):
    """Canonical ingested source speech utterance with VAD boundaries (Section 4, 14)."""
    utterance_id: str
    room_id: str
    tenant_id: str = "org_default"
    source_track_id: str
    source_participant_id: str
    source_participant_name: str = ""
    source_language: str
    transcript: str
    start_time: float
    end_time: float
    duration_ms: int = 0
    status: str = "committed"  # 'partial', 'committed', 'discarded'
    created_at: float = Field(default_factory=time.time)


class TranslationArtifact(BaseModel):
    """Idempotently deduplicated translation result (Section 5, 14)."""
    artifact_id: str
    idempotency_key: str
    utterance_id: str
    room_id: str
    source_language: str
    target_language: str
    translated_text: str
    translation_model: str = "argos_nllb"
    model_version: str = "1.0"
    glossary_version: str = "1.0"
    artifact_status: str = "success"  # 'success', 'failed', 'retrying'
    latency_ms: float = 0.0
    is_cached: bool = False
    created_at: float = Field(default_factory=time.time)


class TTSArtifact(BaseModel):
    """Compatible voice-generated speech artifact (Section 6, 14)."""
    tts_artifact_id: str
    tts_generation_key: str
    utterance_id: str
    target_language: str
    speaker_id: str
    voice_profile_id: str = "default"
    tts_model_version: str = "edge_tts_1.0"
    speech_style: str = "natural"
    audio_artifact_reference: str  # Base64 string or storage URL
    duration_ms: int = 0
    status: str = "success"  # 'success', 'failed', 'retrying'
    latency_ms: float = 0.0
    is_cached: bool = False
    created_at: float = Field(default_factory=time.time)


class FanoutSubscription(BaseModel):
    """Selective subscription binding participant to logical language channels (Section 7, 8)."""
    subscription_id: str
    room_id: str
    participant_id: str
    subscribed_language: str
    audio_mode: str = "translated"
    output_track_reference: str
    status: str = "active"  # 'active', 'paused', 'disconnected'
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class CaptionEvent(BaseModel):
    """Real-time localized subtitle payload delivered to participant (Section 9)."""
    room_id: str
    source_participant_id: str
    source_participant_name: str = ""
    utterance_id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    start_time: float
    end_time: float
    is_final: bool = True
    timestamp: float = Field(default_factory=time.time)


class FanoutDispatchPlan(BaseModel):
    """Calculated minimal translation jobs and participant delivery matrix (Section 5, 7)."""
    room_id: str
    speaker_id: str
    speaker_name: str
    detected_source_lang: str
    text: str
    unique_target_languages: List[str]
    participant_deliveries: Dict[str, Dict[str, Any]]  # participant_id -> delivery details
    deduplication_savings_ratio: float  # (original_needed - unique_jobs) / original_needed
    translation_jobs_needed: int = 0
    listeners_count: int = 0
    created_at: float = Field(default_factory=time.time)


class RoomTelemetryMetrics(BaseModel):
    """Comprehensive observability metrics for meeting quality and resource savings (Section 15, 19)."""
    room_id: str
    tenant_id: str = "org_default"
    active_participants: int = 0
    unique_source_utterances: int = 0
    unique_target_languages: int = 0
    stt_jobs_count: int = 0
    translation_jobs_count: int = 0
    tts_jobs_count: int = 0
    cache_hits_count: int = 0
    audio_fanout_recipients_count: int = 0
    failed_deliveries_count: int = 0
    mean_first_audio_latency_ms: float = 0.0
    mean_utterance_latency_ms: float = 0.0
    deduplication_savings_ratio: float = 0.0
    active_language_channels: List[str] = Field(default_factory=list)


class MeetingRoom(BaseModel):
    """Multi-language meeting room session with participant roster and channels."""
    room_id: str
    tenant_id: str = "org_default"
    title: str = "TalkFlow Multilingual Meeting"
    participants: Dict[str, Participant] = Field(default_factory=dict)
    subscriptions: Dict[str, FanoutSubscription] = Field(default_factory=dict)
    active_speaker_ids: List[str] = Field(default_factory=list)
    active_speaker_id: Optional[str] = None
    telemetry: RoomTelemetryMetrics = Field(default_factory=lambda: RoomTelemetryMetrics(room_id="default"))
    created_at: float = Field(default_factory=time.time)
