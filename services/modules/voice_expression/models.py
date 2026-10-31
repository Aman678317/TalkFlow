"""Data models for Emotion & Voice-Expression Preservation Engine (Module B).

Defines expressive acoustic features, prosody transfer plans, 3 voice generation modes,
biometric consent records, auditable event logs, and the default TalkFlow voice configuration.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class VoiceGenerationMode(str, Enum):
    """Three official Voice Generation Modes for TalkFlow."""
    STANDARD = "standard"  # Mode 1: Neutral neural synthetic voice, stable baseline
    EXPRESSIVE = "expressive"  # Mode 2: Preserves original prosody, tone, pauses, emphasis without cloning
    CONSENTED_SIMILARITY = "consented_similarity"  # Mode 3: Replicates speaker voice traits with strict consent


class DeliveryTag(str, Enum):
    """Categorical classification of vocal delivery and expressive style."""
    NEUTRAL = "neutral"
    EXCITED = "excited"
    CALM = "calm"
    WHISPERING = "whispering"
    LAUGHING = "laughing"
    SHOUTING = "shouting"
    EMPHATIC = "emphatic"
    HESITANT = "hesitant"
    INQUISITIVE = "inquisitive"


class ConsentAuditEventType(str, Enum):
    """Auditable security event types for biometric voice consent."""
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"
    CONSENT_VERIFIED = "consent_verified"
    CONSENT_REJECTED = "consent_rejected"
    CONSENT_EXPIRED = "consent_expired"
    UNAUTHORIZED_ACCESS_BLOCKED = "unauthorized_access_blocked"
    FAIL_CLOSED_FALLBACK = "fail_closed_fallback"


class TalkFlowVoiceConfig(BaseModel):
    """Canonical default TalkFlow voice configuration."""
    voice_mode: str = "expressive"
    speaking_speed: str = "natural"
    voice_similarity_enabled: bool = False
    voice_cloning_consent: bool = False
    prosody_preservation: bool = True
    pause_preservation: bool = True
    speaker_consistency: bool = True


DEFAULT_VOICE_CONFIG = TalkFlowVoiceConfig(
    voice_mode="expressive",
    speaking_speed="natural",
    voice_similarity_enabled=False,
    voice_cloning_consent=False,
    prosody_preservation=True,
    pause_preservation=True,
    speaker_consistency=True,
)


class VoiceConsentAuditRecord(BaseModel):
    """Auditable log record for biometric consent and access events."""
    event_id: str
    timestamp: float = Field(default_factory=time.time)
    event_type: ConsentAuditEventType
    tenant_id: str
    speaker_id: str
    actor_id: str = "system"
    purpose: str = "realtime_meeting_translation"
    consent_id: Optional[str] = None
    status: str = "SUCCESS"  # SUCCESS | BLOCKED | REJECTED | FALLBACK
    details: Dict[str, Any] = Field(default_factory=dict)


class AcousticFeatures(BaseModel):
    """Acoustic and prosodic features extracted from source human speech."""
    duration_ms: float = 0.0
    mean_pitch_hz: float = 160.0
    pitch_std_hz: float = 20.0
    pitch_min_hz: float = 80.0
    pitch_max_hz: float = 280.0
    pitch_contour: List[float] = Field(default_factory=list, description="Resampled 0-1 normalized F0 curve")
    terminal_pitch_slope: float = 0.0  # > 0 indicates rising question intonation; < 0 indicates falling declaration
    mean_energy_db: float = -20.0
    energy_std_db: float = 5.0
    speaking_rate_cps: float = 15.0  # Characters per second
    speaking_rate_wpm: float = 130.0  # Words per minute
    pause_count: int = 0
    total_pause_duration_ms: float = 0.0
    pause_intervals: List[Tuple[float, float]] = Field(default_factory=list, description="[(start_ms, end_ms), ...]")
    detected_emotion: str = "neutral"
    emotion_confidence: float = 0.90
    is_whisper: bool = False
    has_laughter: bool = False
    non_verbal_events: List[str] = Field(default_factory=list, description="['[laughter]', '[sigh]', ...]")


class ProsodyTransferPlan(BaseModel):
    """Cross-lingual prosody transfer specifications adapted for the target language."""
    source_emotion: str = "neutral"
    target_emotion: str = "neutral"
    source_language: str = "hi"
    target_language: str = "en"
    target_voice_id: str = "en-US-JennyNeural"
    voice_mode: VoiceGenerationMode = VoiceGenerationMode.EXPRESSIVE
    rate_multiplier: float = Field(1.0, ge=0.85, le=1.25, description="Speaking rate multiplier clamped within [0.85, 1.25]")
    pitch_adjustment_pct: float = Field(0.0, ge=-50.0, le=50.0, description="Pitch offset in percentage (-50% to +50%)")
    volume_adjustment_db: float = Field(0.0, description="Volume offset in dB")
    expressive_style: str = "natural"
    ssml_markup: str = ""
    target_pauses_ms: List[Dict[str, Any]] = Field(default_factory=list)
    watermark_id: str = "TF-WATERMARK-EXPR-V1"


class VoiceConsentRecord(BaseModel):
    """Explicit speaker consent ledger record for voice cloning or identity replication."""
    consent_id: str
    tenant_id: str = "org_default"
    speaker_id: str
    speaker_name: str
    purpose: str = "realtime_meeting_translation"
    allowed_languages: List[str] = Field(default_factory=lambda: ["*"])
    consent_statement: str = "I authorize TalkFlow to generate synthetic speech resembling my voice for real-time translation."
    granted_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_revoked: bool = False
    revoked_at: Optional[float] = None
    consent_hash: str = ""
    audio_signature: Optional[str] = None


class PronunciationRule(BaseModel):
    """Custom terminology pronunciation substitution rule."""
    term: str
    spoken_as: str
    language: str = "all"  # 'hi', 'en', 'mr', 'all'
    ipa_or_phonetic: Optional[str] = None


class SpeakerProsodyProfile(BaseModel):
    """Prosody and voice expression attributes for a speaker."""
    speaker_id: str
    tenant_id: str = "org_default"
    assigned_voice_id: str = "en-US-JennyNeural"
    voice_mode: str = "expressive"  # Matches DEFAULT_VOICE_CONFIG
    speaking_speed: str = "natural"
    voice_similarity_enabled: bool = False  # Opt-in only
    has_cloning_consent: bool = False  # Opt-in only, requires backend ledger check
    prosody_preservation: bool = True
    pause_preservation: bool = True
    speaker_consistency: bool = True
    base_speaking_rate: float = 1.0  # 0.8 to 1.3
    pitch_adjustment: float = 0.0  # semitones or Hz
    emotion_style: str = "natural"  # 'natural', 'professional', 'expressive', 'calm'
    preserve_speaking_rate: bool = True
    consent_id: Optional[str] = None
    timbre_embedding: Optional[List[float]] = None


class VoiceEnrollmentRequest(BaseModel):
    """Request to enroll a speaker's voice with explicit biometric consent."""
    speaker_id: str
    speaker_name: str
    consent_statement: str
    purpose: str = "realtime_meeting_translation"
    allowed_languages: List[str] = Field(default_factory=lambda: ["*"])
    expires_in_days: int = 90
    reference_audio_base64: Optional[str] = None


class ExpressiveSynthesisRequest(BaseModel):
    """Request to synthesize expressive speech across Mode 1, Mode 2, or Mode 3."""
    text: str = Field(..., description="Target text to synthesize")
    source_text: Optional[str] = Field(None, description="Original source transcript for prosody alignment")
    source_language: str = "hi"
    target_language: str = "en"
    speaker_id: str = "speaker_001"
    voice_mode: VoiceGenerationMode = VoiceGenerationMode.EXPRESSIVE
    speaking_speed: str = "natural"
    voice_similarity_enabled: bool = False
    voice_cloning_consent: bool = False  # Client claim (never trusted without backend verification)
    prosody_preservation: bool = True
    pause_preservation: bool = True
    speaker_consistency: bool = True
    source_duration_ms: Optional[float] = None
    emotion_override: Optional[str] = None
    tenant_id: str = "org_default"
    purpose: str = "realtime_meeting_translation"
    apply_pronunciation: bool = True


class ExpressiveSynthesisResponse(BaseModel):
    """Result of expressive speech synthesis with telemetry and provenance."""
    session_id: str = "sess_default"
    audio_base64: str = ""
    duration_ms: float = 0.0
    sample_rate: int = 24000
    target_language: str = "en"
    voice_id: str = ""
    voice_mode_used: VoiceGenerationMode
    emotion_applied: str = "neutral"
    rate_multiplier: float = 1.0
    pitch_adjustment_pct: float = 0.0
    ssml_used: str = ""
    consent_verified: bool = False
    fail_closed_fallback: bool = False
    watermark: str = "TF-EXPRESSIVE-V1"
    latency_ms: float = 0.0
