"""SQLAlchemy ORM models — tenant-aware, UUID primary keys, created_at/updated_at everywhere.

All business tables carry org_id (tenant). Derivative artifacts (translations, TTS audio,
AI summaries) always reference source_segment_id — the canonical human source is immutable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from globaltalk.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GUID(String):
    """UUID stored as CHAR(36): identical behaviour on SQLite and PostgreSQL."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 server_default=func.now(), onupdate=_now)


# ----------------------------------------------------------------------------- identity & tenancy

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                      nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # architecture-ready
    default_language: Mapped[str] = mapped_column(String(16), default="en")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["OrganizationMember"]] = relationship(back_populates="user")


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free|pro|business|enterprise
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    retention_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="org")


class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_user"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                                        index=True)
    user_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner|admin|manager|member|viewer
    user: Mapped[User] = relationship(back_populates="memberships")
    org: Mapped[Organization] = relationship(back_populates="members")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                                        index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


class UserSession(Base, TimestampMixin):
    """Device/session tracking for login sessions."""
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("sessions.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    replaced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                                        index=True)
    user_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ----------------------------------------------------------------------------- language & model registry

class LanguageCapability(Base, TimestampMixin):
    """Registry-driven truth about what each language can actually do (validated, not claimed)."""
    __tablename__ = "language_capabilities"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. hi, en, mr
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str] = mapped_column(String(100), default="")
    speech_input_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    speech_output_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    translation_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    realtime_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    document_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    stt_status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL")
    tts_status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL")
    mt_status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL")
    stt_provider: Mapped[str] = mapped_column(String(60), default="")
    tts_provider: Mapped[str] = mapped_column(String(60), default="")
    mt_provider: Mapped[str] = mapped_column(String(60), default="")
    tts_voices: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class LanguagePairValidation(Base, TimestampMixin):
    """Each direction of each pair is independently validated (never assumed from model metadata)."""
    __tablename__ = "language_pair_validations"
    __table_args__ = (UniqueConstraint("source", "target", "task", name="uq_pair_task"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(16), index=True)
    target: Mapped[str] = mapped_column(String(16), index=True)
    task: Mapped[str] = mapped_column(String(20), default="mt")  # mt|stt|tts
    status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL")
    provider: Mapped[str] = mapped_column(String(60), default="")
    metric_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelRegistry(Base, TimestampMixin):
    __tablename__ = "model_registry"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    task: Mapped[str] = mapped_column(String(30), index=True)  # stt|mt|tts|vad|llm|embedding|langid
    provider: Mapped[str] = mapped_column(String(60), index=True)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[str] = mapped_column(String(80), default="pinned")
    languages: Mapped[list] = mapped_column(JSON, default=list)
    hardware: Mapped[str] = mapped_column(String(20), default="cpu")  # cpu|gpu
    quantization: Mapped[str] = mapped_column(String(20), default="")
    license: Mapped[str] = mapped_column(String(80), default="")
    license_review_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    production_status: Mapped[str] = mapped_column(String(20), default="EXPERIMENTAL")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    latency_p50_ms: Mapped[float] = mapped_column(Float, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    gpu_required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")


# ----------------------------------------------------------------------------- meetings & realtime

class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                                        index=True)
    project_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    created_by: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id"))
    room_name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    join_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # derivative artifact
    participants: Mapped[list["Participant"]] = relationship(back_populates="meeting")


class Participant(Base, TimestampMixin):
    __tablename__ = "participants"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("meetings.id", ondelete="CASCADE"),
                                            index=True)
    user_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    identity: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member")  # host|member|agent
    status: Mapped[str] = mapped_column(String(20), default="joined", index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting: Mapped[Meeting] = relationship(back_populates="participants")
    preferences: Mapped["ParticipantPreference | None"] = relationship(
        back_populates="participant", uselist=False, cascade="all, delete-orphan")


class ParticipantPreference(Base, TimestampMixin):
    """Per-listener routing truth: 'I speak X / I want to hear Y / audio mode'."""
    __tablename__ = "participant_preferences"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    participant_id: Mapped[str] = mapped_column(
        GUID(36), ForeignKey("participants.id", ondelete="CASCADE"), unique=True, index=True)
    speaking_language: Mapped[str] = mapped_column(String(16), default="AUTO")
    listening_language: Mapped[str] = mapped_column(String(16), default="en")
    audio_mode: Mapped[str] = mapped_column(String(16), default="translated")  # original|translated|mixed
    captions_language: Mapped[str] = mapped_column(String(16), default="")  # '' = follow listening
    caption_mode: Mapped[str] = mapped_column(String(16), default="both")  # original|translated|both
    latency_mode: Mapped[str] = mapped_column(String(24), default="balanced")
    participant: Mapped[Participant] = relationship(back_populates="preferences")


class AudioSession(Base, TimestampMixin):
    __tablename__ = "audio_sessions"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("meetings.id", ondelete="CASCADE"),
                                            index=True)
    participant_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("participants.id",
                                                                     ondelete="CASCADE"), index=True)
    transport: Mapped[str] = mapped_column(String(20), default="websocket")  # websocket|livekit
    status: Mapped[str] = mapped_column(String(20), default="active")
    stt_provider: Mapped[str] = mapped_column(String(60), default="")
    latency_mode: Mapped[str] = mapped_column(String(24), default="balanced")
    audio_seconds: Mapped[float] = mapped_column(Float, default=0)
    dropouts: Mapped[int] = mapped_column(Integer, default=0)
    reconnects: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class TranscriptSegment(Base, TimestampMixin):
    """CANONICAL HUMAN SOURCE. Immutable after is_final=true (no UPDATEs to text/language)."""
    __tablename__ = "transcript_segments"
    __table_args__ = (Index("ix_transcript_meeting_seq", "meeting_id", "sequence"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    meeting_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("meetings.id", ondelete="CASCADE"),
                                            index=True)
    participant_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("participants.id",
                                                                     ondelete="CASCADE"), index=True)
    audio_session_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_id: Mapped[str] = mapped_column(String(60), default="")  # diarization label, optional
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    stt_provider: Mapped[str] = mapped_column(String(60), default="")
    stt_model: Mapped[str] = mapped_column(String(120), default="")
    started_at_ms: Mapped[int] = mapped_column(Integer, default=0)
    ended_at_ms: Mapped[int] = mapped_column(Integer, default=0)
    audio_key: Mapped[str | None] = mapped_column(String(300), nullable=True)  # original audio object
    latency: Mapped[dict] = mapped_column(JSON, default=dict)
    correction_status: Mapped[str] = mapped_column(String(20), default="none")  # none|corrected


class TranslationSegment(Base, TimestampMixin):
    """Derivative artifact. Always references source_segment_id. Never a semantic source."""
    __tablename__ = "translation_segments"
    __table_args__ = (
        UniqueConstraint("source_segment_id", "target_language", name="uq_source_target"),
        Index("ix_translation_meeting", "meeting_id", "target_language"),
    )
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    meeting_id: Mapped[str | None] = mapped_column(GUID(36),
                                                   ForeignKey("meetings.id", ondelete="CASCADE"),
                                                   nullable=True, index=True)
    source_segment_id: Mapped[str] = mapped_column(GUID(36), index=True, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), default="transcript")  # transcript|chat|document
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(60), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    glossary_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    style_profile_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_translation_memory: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    tts_audio_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tts_provider: Mapped[str] = mapped_column(String(60), default="")
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)


class ChatMessage(Base, TimestampMixin):
    """Original text is immutable; per-language translations live in translation_segments."""
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    meeting_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("meetings.id", ondelete="CASCADE"),
                                            index=True)
    participant_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("participants.id",
                                                                     ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str] = mapped_column(String(16), default="")
    kind: Mapped[str] = mapped_column(String(20), default="message")  # message|system


class VoiceConsent(Base, TimestampMixin):
    """AI voice safety: explicit, revocable, audited consent for voice preservation."""
    __tablename__ = "voice_consents"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    purpose: Mapped[str] = mapped_column(String(40), default="voice_preservation")
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_audio_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    synthetic_flag_metadata: Mapped[bool] = mapped_column(Boolean, default=True)


# ----------------------------------------------------------------------------- documents

class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    user_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    source_language: Mapped[str] = mapped_column(String(16), default="AUTO")
    detected_language: Mapped[str] = mapped_column(String(16), default="")
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    glossary_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    style_profile_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    domain: Mapped[str] = mapped_column(String(40), default="general")
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    source_key: Mapped[str] = mapped_column(String(300), default="")
    output_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    segments_total: Mapped[int] = mapped_column(Integer, default=0)
    segments_done: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    versions_used: Mapped[dict] = mapped_column(JSON, default=dict)  # model/glossary/style versions


class DocumentJob(Base, TimestampMixin):
    __tablename__ = "document_jobs"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("documents.id", ondelete="CASCADE"),
                                             index=True)
    stage: Mapped[str] = mapped_column(String(30), default="queued")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0)
    log: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentSegment(Base, TimestampMixin):
    __tablename__ = "document_segments"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("documents.id", ondelete="CASCADE"),
                                             index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(30), default="text")  # text|heading|table_cell|caption
    page: Mapped[int] = mapped_column(Integer, default=0)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, default="")
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    translatable: Mapped[bool] = mapped_column(Boolean, default=True)


# ----------------------------------------------------------------------------- glossary / TM / style

class Glossary(Base, TimestampMixin):
    __tablename__ = "glossaries"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|active|archived
    domain: Mapped[str] = mapped_column(String(40), default="general")
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    terms: Mapped[list["GlossaryTerm"]] = relationship(back_populates="glossary",
                                                       cascade="all, delete-orphan")


class GlossaryTerm(Base, TimestampMixin):
    __tablename__ = "glossary_terms"
    __table_args__ = (Index("ix_gterm_lookup", "glossary_id", "source_lower"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    glossary_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("glossaries.id", ondelete="CASCADE"),
                                             index=True)
    source_term: Mapped[str] = mapped_column(String(400), nullable=False)
    source_lower: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    target_term: Mapped[str] = mapped_column(String(400), nullable=False)
    part_of_speech: Mapped[str] = mapped_column(String(30), default="")
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    do_not_translate: Mapped[bool] = mapped_column(Boolean, default=False)
    spoken_variants: Mapped[list] = mapped_column(JSON, default=list)  # spoken term normalization
    glossary: Mapped[Glossary] = relationship(back_populates="terms")


class StyleProfile(Base, TimestampMixin):
    __tablename__ = "style_profiles"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str | None] = mapped_column(GUID(36), index=True, nullable=True)  # NULL = system
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="custom")
    version: Mapped[int] = mapped_column(Integer, default=1)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_fragment: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class TranslationMemory(Base, TimestampMixin):
    __tablename__ = "translation_memories"
    __table_args__ = (Index("ix_tm_lookup", "org_id", "source_language", "target_language",
                            "source_norm_hash"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    tm_namespace: Mapped[str] = mapped_column(String(120), default="default")
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_norm_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    domain: Mapped[str] = mapped_column(String(40), default="general")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)  # pgvector in prod
    version: Mapped[int] = mapped_column(Integer, default=1)


# ----------------------------------------------------------------------------- translation history

class TranslationHistory(Base, TimestampMixin):
    __tablename__ = "translation_history"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    user_id: Mapped[str | None] = mapped_column(GUID(36), index=True, nullable=True)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="")
    provider: Mapped[str] = mapped_column(String(60), default="")
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)
    glossary_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    style_profile_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    domain: Mapped[str] = mapped_column(String(40), default="general")
    intent: Mapped[str] = mapped_column(String(30), default="quality_optimized")
    from_tm: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(20), default="text")  # text|batch|realtime


# ----------------------------------------------------------------------------- metering & billing

class UsageRecord(Base, TimestampMixin):
    """Immutable usage events. Billing is computed FROM metering, never the reverse."""
    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_org_time", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    user_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    dimension: Mapped[str] = mapped_column(String(40), index=True)
    # characters|tokens|audio_seconds|video_minutes|translation_requests|document_pages|
    # gpu_seconds|storage_bytes|api_requests
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    meeting_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    document_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                                        unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")
    status: Mapped[str] = mapped_column(String(20), default="active")
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)


class BillingEvent(Base, TimestampMixin):
    __tablename__ = "billing_events"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # invoice|threshold|plan_change
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")


# ----------------------------------------------------------------------------- platform ops

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_time", "org_id", "created_at"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str | None] = mapped_column(GUID(36), index=True, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    actor_api_key_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(60), default="")
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str] = mapped_column(String(32), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Integration(Base, TimestampMixin):
    __tablename__ = "integrations"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # zoom|teams|gmeet|slack|crm|helpdesk|cms|webhook|mcp
    name: Mapped[str] = mapped_column(String(120), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)  # never plaintext
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Webhook(Base, TimestampMixin):
    __tablename__ = "webhooks"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list)
    signing_secret: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(String(300), default="")


class WebhookDelivery(Base, TimestampMixin):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    webhook_id: Mapped[str] = mapped_column(GUID(36), ForeignKey("webhooks.id", ondelete="CASCADE"),
                                            index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|delivered|failed
    last_error: Mapped[str] = mapped_column(Text, default="")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    org_id: Mapped[str | None] = mapped_column(GUID(36), index=True, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(300), default="")


class AgentSession(Base, TimestampMixin):
    """Agent-to-agent language bridge sessions. Human source stays canonical."""
    __tablename__ = "agent_sessions"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    meeting_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    human_source_language: Mapped[str] = mapped_column(String(16), default="")
    agents: Mapped[list] = mapped_column(JSON, default=list)  # [{name, language, role}]
    status: Mapped[str] = mapped_column(String(20), default="active")
    turns: Mapped[list] = mapped_column(JSON, default=list)


class MemoryItem(Base, TimestampMixin):
    """Seven logical memory classes; retrieval-scoped, tenant-aware."""
    __tablename__ = "memory_items"
    __table_args__ = (Index("ix_memory_scope", "org_id", "memory_class", "scope_id"),)
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(GUID(36), index=True)
    memory_class: Mapped[str] = mapped_column(String(24))
    # working|semantic|episodic|procedural|retrieval|parametric|prospective
    scope: Mapped[str] = mapped_column(String(24), default="meeting")  # meeting|org|user
    scope_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="")
    source_segment_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    org_id: Mapped[str | None] = mapped_column(GUID(36), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(GUID(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # translation|stt|tts|meeting|document
    target_id: Mapped[str] = mapped_column(String(64), default="")
    rating: Mapped[int] = mapped_column(Integer, default=0)  # -1..1 or 1..5
    comment: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class QualityEvaluation(Base, TimestampMixin):
    __tablename__ = "quality_evaluations"
    id: Mapped[str] = mapped_column(GUID(36), primary_key=True, default=_uuid)
    task: Mapped[str] = mapped_column(String(20))  # stt|mt|tts|langid
    dataset: Mapped[str] = mapped_column(String(120), default="")
    source_language: Mapped[str] = mapped_column(String(16), default="")
    target_language: Mapped[str] = mapped_column(String(16), default="")
    provider: Mapped[str] = mapped_column(String(60), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # wer|cer|bleu|comet|latency...
    samples: Mapped[int] = mapped_column(Integer, default=0)
    passed_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
