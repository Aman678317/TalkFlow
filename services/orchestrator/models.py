"""Data models, state definitions, and handoff contracts for TalkFlow Central Orchestrator."""
from __future__ import annotations

import enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PipelineStage(str, enum.Enum):
    AUDIO_INGESTION = "agent_01_audio"
    SPEECH_RECOGNITION = "agent_02_stt"
    LANGUAGE_INTELLIGENCE = "agent_03_lid"
    NEURAL_TRANSLATION = "agent_04_mt"
    TRANSLATION_QUALITY = "agent_05_qa"
    VOICE_GENERATION = "agent_06_tts"
    AUDIO_DELIVERY = "agent_07_delivery"


class PipelineState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    AUDIO_PROCESSING = "AUDIO_PROCESSING"
    AUDIO_VALIDATED = "AUDIO_VALIDATED"
    STT_PROCESSING = "STT_PROCESSING"
    TRANSCRIPT_READY = "TRANSCRIPT_READY"
    LANGUAGE_ANALYSIS = "LANGUAGE_ANALYSIS"
    LANGUAGE_READY = "LANGUAGE_READY"
    TRANSLATION_PROCESSING = "TRANSLATION_PROCESSING"
    TRANSLATION_READY = "TRANSLATION_READY"
    QUALITY_VALIDATION = "QUALITY_VALIDATION"
    QUALITY_APPROVED = "QUALITY_APPROVED"
    TTS_PROCESSING = "TTS_PROCESSING"
    AUDIO_GENERATED = "AUDIO_GENERATED"
    DELIVERY_QUEUED = "DELIVERY_QUEUED"
    DELIVERY_SYNCHRONIZED = "DELIVERY_SYNCHRONIZED"
    AUDIO_PUBLISHED = "AUDIO_PUBLISHED"
    PLAYBACK_CONFIRMED = "PLAYBACK_CONFIRMED"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class QAGateDecision(str, enum.Enum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_WARNINGS = "ACCEPT_WITH_WARNINGS"
    RETRY_WITH_ALTERNATE_PROVIDER = "RETRY_WITH_ALTERNATE_PROVIDER"
    HOLD_FOR_HUMAN = "HOLD_FOR_HUMAN"
    REJECT = "REJECT"


class DeliveryStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SYNCHRONIZED = "SYNCHRONIZED"
    PUBLISHED = "PUBLISHED"
    SUBSCRIBED = "SUBSCRIBED"
    PLAYBACK_STARTED = "PLAYBACK_STARTED"
    COMPLETED = "COMPLETED"
    EXCLUDED_LOOP = "EXCLUDED_LOOP"


class HandoffEnvelope(BaseModel):
    """Canonical handoff envelope passed and validated between every sequential agent stage."""
    pipeline_id: str
    conversation_id: str
    room_id: str
    source_segment_id: str
    translation_id: Optional[str] = None
    utterance_id: Optional[str] = None
    speaker_id: str
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    agent_from: str
    agent_to: str
    stage: str
    attempt: int = 1
    status: str
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    payload_reference: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1.0"


class AudioChunkDescriptor(BaseModel):
    """Metadata and execution state for an individual sliced audio chunk in a full recording."""
    chunk_index: int
    total_chunks: int
    start_ms: int
    end_ms: int
    duration_ms: int
    status: str = "PENDING"
    source_transcript: Optional[str] = None
    source_language: Optional[str] = None
    per_language_translations: Dict[str, str] = Field(default_factory=dict)
    per_language_qa: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    per_language_audio_durations_ms: Dict[str, int] = Field(default_factory=dict)
    per_language_audio_paths: Dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None


class FullLanguageResult(BaseModel):
    """Complete synthesized and reassembled audio result for a specific target language."""
    target_language: str
    voice_id: str
    full_text: str
    chunk_count: int
    total_synthesized_duration_ms: int
    total_synthesis_time_ms: float
    output_audio_path: str
    output_audio_size_bytes: int
    output_audio_base64: Optional[str] = None
    delivery_status: str
    rtf: float


class RecordingManifest(BaseModel):
    """Full-length audio recording processing manifest tracking all chunks and reassembly."""
    recording_id: str
    session_id: str
    conversation_id: str
    speaker_id: str
    source_audio_duration_ms: int
    chunk_count: int
    chunks: List[AudioChunkDescriptor] = Field(default_factory=list)
    source_language: str
    target_languages: List[str]
    start_time: float
    end_time: Optional[float] = None
    wall_clock_time_sec: float = 0.0
    rtf: float = 0.0
    status: str = "PROCESSING"
    full_source_transcript: str = ""
    per_language_results: Dict[str, FullLanguageResult] = Field(default_factory=dict)
    completeness_metrics: Dict[str, Any] = Field(default_factory=dict)

