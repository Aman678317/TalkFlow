"""Pydantic schemas (API contracts). Versioned under /api/v1. SDK-generation friendly:
flat request/response models, explicit enums, no ORM leakage."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ------------------------------------------------------------------ auth

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=200)
    organization_name: str = Field(default="", max_length=200)

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        if v.lower() in ("password", "password123", "12345678"):
            raise ValueError("password is too common")
        has_alpha = any(c.isalpha() for c in v)
        has_num = any(c.isdigit() for c in v)
        if not (has_alpha and has_num):
            raise ValueError("password must contain letters and numbers")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str
    is_platform_admin: bool
    email_verified: bool
    default_language: str
    created_at: datetime


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    plan: str


class MembershipOut(BaseModel):
    org: OrgOut
    role: str


class AuthResponse(BaseModel):
    tokens: TokenPair
    user: UserOut
    membership: MembershipOut | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class SessionOut(BaseModel):
    id: str
    user_agent: str
    ip_address: str
    created_at: datetime
    last_seen_at: datetime
    revoked: bool


# ------------------------------------------------------------------ translate

class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    source_language: str = "AUTO"
    target_language: str
    glossary_id: str | None = None
    style_profile_id: str | None = None
    translation_memory_id: str | None = None
    domain: str = "general"
    intent: Literal["quality_optimized", "latency_optimized", "cost_optimized",
                    "private_only", "offline_only", "experimental"] = "quality_optimized"


class TranslateResponse(BaseModel):
    translation_id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    model: str
    provider: str
    latency_ms: float
    quality_flags: list[str] = []
    from_translation_memory: bool = False
    detected_confidence: float = 0.0


class BatchTranslateRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)
    source_language: str = "AUTO"
    target_language: str
    glossary_id: str | None = None
    style_profile_id: str | None = None
    domain: str = "general"
    intent: str = "quality_optimized"


class BatchTranslateResponse(BaseModel):
    translations: list[TranslateResponse]


class DetectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class DetectResponse(BaseModel):
    language: str
    confidence: float
    provider: str
    alternatives: list[dict[str, Any]] = []


class HistoryItem(BaseModel):
    id: str
    created_at: datetime
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    model: str
    provider: str
    latency_ms: float
    quality_flags: list[str]
    kind: str
    from_tm: bool


# ------------------------------------------------------------------ languages

class LanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    native_name: str
    speech_input_supported: bool
    speech_output_supported: bool
    translation_supported: bool
    realtime_supported: bool
    document_supported: bool
    stt_status: str
    tts_status: str
    mt_status: str
    stt_provider: str
    tts_provider: str
    mt_provider: str


# ------------------------------------------------------------------ glossary / TM / style

class GlossaryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_language: str
    target_language: str
    domain: str = "general"
    description: str = ""


class GlossaryTermIn(BaseModel):
    source_term: str = Field(min_length=1, max_length=400)
    target_term: str = Field(min_length=1, max_length=400)
    part_of_speech: str = ""
    case_sensitive: bool = False
    do_not_translate: bool = False
    spoken_variants: list[str] = []


class GlossaryOut(BaseModel):
    id: str
    name: str
    source_language: str
    target_language: str
    version: int
    status: str
    domain: str
    term_count: int
    created_at: datetime


class TmEntryIn(BaseModel):
    source_text: str = Field(min_length=1, max_length=5000)
    target_text: str = Field(min_length=1, max_length=5000)
    source_language: str
    target_language: str
    domain: str = "general"
    approved: bool = False


class TmEntryOut(BaseModel):
    id: str
    source_text: str
    target_text: str
    source_language: str
    target_language: str
    domain: str
    approved: bool
    confidence: float
    usage_count: int
    version: int
    created_at: datetime


class StyleProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "custom"
    rules: dict[str, Any] = {}
    prompt_fragment: str = ""


class StyleProfileOut(BaseModel):
    id: str
    name: str
    kind: str
    version: int
    rules: dict[str, Any]
    prompt_fragment: str
    is_system: bool


# ------------------------------------------------------------------ documents

class DocumentOut(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    source_language: str
    detected_language: str
    target_language: str
    status: str
    pages: int
    segments_total: int
    segments_done: int
    error: str | None
    created_at: datetime
    versions_used: dict[str, Any]


class DocumentStatusOut(BaseModel):
    document_id: str
    status: str
    stage: str
    progress: float
    segments_total: int
    segments_done: int
    error: str | None
    log: list[dict]


# ------------------------------------------------------------------ meetings

class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    settings: dict[str, Any] = {}


class MeetingOut(BaseModel):
    id: str
    title: str
    status: str
    room_name: str
    join_token: str
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    has_summary: bool = False
    transport: str = "websocket"
    livekit_url: str | None = None


class PreferenceIn(BaseModel):
    speaking_language: str = "AUTO"
    listening_language: str = "en"
    audio_mode: Literal["original", "translated", "mixed"] = "translated"
    caption_mode: Literal["original", "translated", "both"] = "both"
    latency_mode: Literal["ultra_low_latency", "balanced", "high_accuracy"] = "balanced"


class ParticipantOut(BaseModel):
    id: str
    display_name: str
    status: str
    speaking_language: str
    listening_language: str
    audio_mode: str
    caption_mode: str


class TranscriptItem(BaseModel):
    id: str
    sequence: int
    speaker: str
    participant_id: str
    language: str
    text: str
    confidence: float
    stt_provider: str
    stt_model: str
    created_at: str
    latency: dict[str, Any]
    translations: list[dict[str, Any]]


class SummaryOut(BaseModel):
    summary: str = ""
    key_points: list[str] = []
    decisions: list[str] = []
    action_items: list[dict[str, Any]] = []
    unanswered_questions: list[str] = []
    topics: list[str] = []
    follow_up_suggestions: list[str] = []
    method: str = "none"
    message: str = ""
    segments_used: int = 0
    generated_at: str = ""


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


# ------------------------------------------------------------------ platform

class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = ["translate", "detect", "documents", "glossaries"]


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class ApiKeyCreated(ApiKeyOut):
    key: str  # shown exactly once


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = []
    description: str = ""


class WebhookOut(BaseModel):
    id: str
    url: str
    events: list[str]
    enabled: bool
    description: str
    created_at: datetime


class UsageOut(BaseModel):
    totals: dict[str, float]
    plan: str
    limits: dict[str, Any]
    period_start: datetime | None = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["owner", "admin", "manager", "member", "viewer"] = "member"


class MemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    joined_at: datetime


class FeedbackIn(BaseModel):
    kind: Literal["translation", "stt", "tts", "meeting", "document"]
    target_id: str = ""
    rating: int = Field(ge=-1, le=5)
    comment: str = ""
    context: dict[str, Any] = {}


class BridgeTurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    source_language: str = "AUTO"


class BridgeAgentOut(BaseModel):
    agent: str
    language: str
    text: str
    provider: str
    from_canonical_source: bool = True
