"""Voice capability profiles and consent models."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VoiceCapability(BaseModel):
    """Metadata tracking a specific voice in the capability registry."""
    voice_id: str
    name: str
    provider: str
    model: str
    language: str
    locale: str
    gender: Optional[str] = "neutral"
    supported_styles: List[str] = Field(default_factory=lambda: ["natural", "neutral"])
    sample_rate: int = 24000
    audio_formats: List[str] = Field(default_factory=lambda: ["pcm_s16le", "wav"])
    streaming_supported: bool = True
    is_local: bool = True
    requires_gpu: bool = False
    is_available: bool = True
    license: str = "open"
    commercial_use: bool = True
    attribution_required: bool = False
    notes: Optional[str] = None


class VoiceConsentRecord(BaseModel):
    """Explicit recorded opt-in consent for voice cloning / personalization."""
    consent_id: str
    speaker_id: str
    user_id: str
    tenant_id: str = "org_default"
    voice_profile_name: str
    purpose: str = "realtime_speech_translation"
    granted_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_revoked: bool = False
    revoked_at: Optional[float] = None
    audit_hash: str = ""

