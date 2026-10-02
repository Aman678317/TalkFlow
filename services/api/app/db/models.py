"""Full GlobalTalk AI schema (PDD §27 + §7).

Rules honored here:
- UUID primary keys everywhere
- created_at / updated_at on every mutable table
- real foreign keys + intentional indexes (integrity is NOT app-only)
- tenant_id (org) on every business row — queries always filter by it
- immutable ledger tables (usage_records, billing_events, audit_logs,
  transcript_segments source rows) are insert-only by convention
  (enforced in services + DB-level checks where practical)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, TZDateTime, UUIDPkMixin

# --------------------------------------------------------------------------- #
# Identity & tenancy (CONTROL PLANE)
# --------------------------------------------------------------------------- #


class User(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    locale: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    speak_lang: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    hear_lang: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|suspended|deleted
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    memberships: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin")


class Organization(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="free", nullable=False)  # free|pro|business|enterprise
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retention_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


class OrganizationMember(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_user"),
        CheckConstraint(
            "role IN ('owner','admin','manager','member','viewer')",
            name="ck_member_role"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships", lazy="selectin")
    org: Mapped[Organization] = relationship(lazy="selectin")


class Project(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "projects"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_glossary_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    default_style_profile_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Session(Base, UUIDPkMixin, TimestampMixin):
    """Login session / device tracking (PDD §24)."""
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_info: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


class RefreshToken(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    replaced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ApiKey(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "api_keys"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|revoked
    last_used_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


# --------------------------------------------------------------------------- #
# Language capability registry & model registry (CONTROL PLANE)
# --------------------------------------------------------------------------- #


class LanguageCapability(Base, TimestampMixin):
    """PDD §8 — DB-driven capability registry; frontend dropdowns come from here."""
    __tablename__ = "language_capabilities"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    script: Mapped[str] = mapped_column(String(16), default="Latn", nullable=False)
    rtl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    translation_status: Mapped[str] = mapped_column(String(16), default="SUPPORTED", nullable=False)
    speech_input_status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL", nullable=False)
    speech_output_status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL", nullable=False)
    realtime_status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL", nullable=False)
    document_status: Mapped[str] = mapped_column(String(16), default="SUPPORTED", nullable=False)
    stt_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    mt_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    tts_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    tts_voices: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    wer_benchmark: Mapped[float | None] = mapped_column(Float, nullable=True)
    mt_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class LanguagePairCapability(Base, TimestampMixin):
    """Per-pair validation state — a pair is enabled only after evaluation."""
    __tablename__ = "language_pair_capabilities"

    source_lang: Mapped[str] = mapped_column(String(16), primary_key=True)
    target_lang: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL", nullable=False)
    domain: Mapped[str] = mapped_column(String(32), default="general", primary_key=True)
    bleu_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    eval_report_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ModelRegistry(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "model_registry"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    task: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # stt|mt|tts|...
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), default="1", nullable=False)
    quality_tier: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    cost_tier: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    latency_class: Mapped[str] = mapped_column(String(16), default="fast", nullable=False)
    private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_gpu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    languages_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    validated_pairs_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    domains_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    org_overrides_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


# --------------------------------------------------------------------------- #
# Customization assets (CONTROL PLANE)
# --------------------------------------------------------------------------- #


class Glossary(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "glossaries"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|active|archived
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    terms: Mapped[list["GlossaryTerm"]] = relationship(
        back_populates="glossary", cascade="all, delete-orphan", lazy="selectin")


class GlossaryTerm(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "glossary_terms"
    __table_args__ = (
        UniqueConstraint("glossary_id", "source_text", name="uq_glossary_term"),
    )

    glossary_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("glossaries.id", ondelete="CASCADE"), index=True, nullable=False)
    source_text: Mapped[str] = mapped_column(String(500), nullable=False)
    target_text: Mapped[str] = mapped_column(String(500), nullable=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: spoken variants for STT normalization ("see pee you" -> "CPU")
    spoken_variants_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    glossary: Mapped[Glossary] = relationship(back_populates="terms")


class StyleProfile(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "style_profiles"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)  # NULL = system default
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="custom", nullable=False)  # formal|casual|technical|legal|finance|support|education|sales|custom
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class TranslationMemory(Base, UUIDPkMixin, TimestampMixin):
    """One TM = a named collection; entries live in TranslationMemoryEntry."""
    __tablename__ = "translation_memories"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TranslationMemoryEntry(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "translation_memory_entries"
    __table_args__ = (
        Index("ix_tme_lookup", "tm_id", "source_lang", "target_lang"),
    )

    tm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("translation_memories.id", ondelete="CASCADE"), index=True, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_normalized: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # sha256 prefix for exact match
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# --------------------------------------------------------------------------- #
# Meetings & realtime conversation (DATA PLANE artifacts)
# --------------------------------------------------------------------------- #


class Meeting(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "meetings"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="Untitled meeting")
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    # scheduled|live|ended|archived
    mode: Mapped[str] = mapped_column(String(20), default="ws", nullable=False)  # ws|livekit
    room_name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retention_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    next_seq: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)


class Participant(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", "guest_key", name="uq_meeting_user"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    guest_key: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)  # host|member|ai_agent
    status: Mapped[str] = mapped_column(String(20), default="invited", nullable=False)  # invited|joined|left
    joined_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    livekit_identity: Mapped[str] = mapped_column(String(120), default="", nullable=False)


class ParticipantPreference(Base, UUIDPkMixin, TimestampMixin):
    """PDD §12 — the personalized routing state, one row per participant."""
    __tablename__ = "participant_preferences"
    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_pref_participant"),
        CheckConstraint(
            "audio_mode IN ('original','translated','mixed','captions_only')",
            name="ck_audio_mode"),
    )

    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True, nullable=False)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False)
    speak_lang: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    hear_lang: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    audio_mode: Mapped[str] = mapped_column(String(20), default="translated", nullable=False)
    captions_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ducking_level: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)


class AudioSession(Base, UUIDPkMixin, TimestampMixin):
    """A WebSocket/media session bound to a participant (control-plane record
    of data-plane sessions)."""
    __tablename__ = "audio_sessions"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True, nullable=False)
    session_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    transport: Mapped[str] = mapped_column(String(16), default="ws", nullable=False)  # ws|livekit
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|closed
    sample_rate: Mapped[int] = mapped_column(Integer, default=16000, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    audio_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latency_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TranscriptSegment(Base, UUIDPkMixin, TimestampMixin):
    """CANONICAL human source (PDD §11.1). Immutable after is_final=true.
    Translated outputs live in TranslationSegment and NEVER feed back here."""
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("meeting_id", "seq", name="uq_meeting_seq"),
        Index("ix_segments_meeting_created", "meeting_id", "created_at"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), nullable=True)
    speaker_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    stt_model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    stt_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    audio_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correction_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    translations: Mapped[list["TranslationSegment"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan", lazy="selectin")


class TranslationSegment(Base, UUIDPkMixin, TimestampMixin):
    """Fan-out result: (segment, target_lang) unique per glossary/style version."""
    __tablename__ = "translation_segments"
    __table_args__ = (
        UniqueConstraint("segment_id", "target_lang", name="uq_segment_target"),
        Index("ix_translation_product_created", "product", "created_at"),
    )

    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=True, index=True)
    # standalone text/document/chat translations reuse this table:
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    product: Mapped[str] = mapped_column(String(20), default="realtime", nullable=False)
    # text|document|realtime|chat
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    intent: Mapped[str] = mapped_column(String(32), default="quality_optimized", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quality_flags_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    glossary_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("glossaries.id", ondelete="SET NULL"), nullable=True)
    glossary_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    style_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("style_profiles.id", ondelete="SET NULL"), nullable=True)
    tm_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("translation_memories.id", ondelete="SET NULL"), nullable=True)
    tm_match_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # exact|fuzzy|semantic|None
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    segment: Mapped[TranscriptSegment | None] = relationship(back_populates="translations")


class ChatMessage(Base, UUIDPkMixin, TimestampMixin):
    """Original message is immutable; translations attach separately."""
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_meeting_created", "meeting_id", "created_at"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    detected_lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="message", nullable=False)  # message|system
    seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    translations_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # {target_lang: {text, model, flags[]}} — never overwrites original_text


# --------------------------------------------------------------------------- #
# Documents (DATA PLANE artifacts, CONTROL PLANE metadata)
# --------------------------------------------------------------------------- #


class Document(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "documents"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    detected_lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    glossary_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("glossaries.id", ondelete="SET NULL"), nullable=True)
    style_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("style_profiles.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="uploaded", index=True, nullable=False)
    # uploaded|scanning|parsing|translating|reconstructing|quality_check|ready|failed|deleted
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    output_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    glossary_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    style_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


class DocumentJob(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "document_jobs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(30), default="translate", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


class DocumentSegment(Base, UUIDPkMixin, TimestampMixin):
    """Layout-aware unit: text block with geometry (PDD §15)."""
    __tablename__ = "document_segments"
    __table_args__ = (
        Index("ix_docseg_doc_idx", "document_id", "block_index"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    # text|heading|table_cell|caption|non_translatable
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [x0,y0,x1,y1] normalized
    font_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


# --------------------------------------------------------------------------- #
# Conversation intelligence & memory (PDD §21, §23)
# --------------------------------------------------------------------------- #


class AgentSession(Base, UUIDPkMixin, TimestampMixin):
    """Agent-to-agent bridge session (PDD §22): tracks which agent consumed
    which canonical segment in which agent-language. Translated outputs passed
    to agents are recorded as derived, never promoted to source."""
    __tablename__ = "agent_sessions"

    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    bridge_state_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    consumed_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


class MemoryItem(Base, UUIDPkMixin, TimestampMixin):
    """Seven logical memory classes (PDD §23)."""
    __tablename__ = "memory_items"
    __table_args__ = (
        CheckConstraint(
            "memory_class IN ('working','semantic','episodic','procedural',"
            "'retrieval','parametric','prospective')", name="ck_memory_class"),
        Index("ix_memory_scope", "org_id", "meeting_id", "memory_class"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    memory_class: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(300), default="", nullable=False, index=True)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    embedding_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="system", nullable=False)
    # human_source|derived_translation|assistant — canonical-source guard
    source_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Feedback(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "feedback"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # translation|segment|document|summary|tts
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # -1|1 thumb
    correction_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)


class QualityEvaluation(Base, UUIDPkMixin, TimestampMixin):
    """Eval-harness runs & human evaluations (PDD §43)."""
    __tablename__ = "quality_evaluations"

    pair: Mapped[str] = mapped_column(String(40), index=True, nullable=False)  # hi->en
    domain: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    dataset: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    method: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)  # auto|human
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    n_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bleu_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    wer_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    cer_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed_gates: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evaluated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


# --------------------------------------------------------------------------- #
# Platform: usage, billing, audit, integrations, webhooks
# --------------------------------------------------------------------------- #


class UsageRecord(Base, UUIDPkMixin):
    """IMMUTABLE usage ledger (PDD §21.1). No updated_at by design."""
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_org_time", "org_id", "created_at"),
        Index("ix_usage_product", "product", "unit_type"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    request_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    product: Mapped[str] = mapped_column(String(20), nullable=False)
    # text|voice|meeting|document|api|storage
    unit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # characters|tokens|audio_seconds|video_minutes|translation_requests|
    # document_pages|gpu_seconds|storage_bytes|api_requests
    units: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, index=True)


class Subscription(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # active|trialing|past_due|canceled
    current_period_start: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    quota_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provider_ref: Mapped[str] = mapped_column(String(120), default="", nullable=False)


class BillingEvent(Base, UUIDPkMixin):
    """IMMUTABLE billing ledger derived from usage (never the other way)."""
    __tablename__ = "billing_events"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # invoice_created|payment_succeeded|payment_failed|plan_changed|quota_warning
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    period: Mapped[str] = mapped_column(String(10), default="", nullable=False)  # YYYY-MM
    lines_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)


class AuditLog(Base, UUIDPkMixin):
    """IMMUTABLE audit trail (PDD §20)."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_org_time", "org_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    # user|api_key|system
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    request_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)


class Integration(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "integrations"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # zoom|teams|google_meet|slack|crm|helpdesk|cms|webhook|mcp
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="disconnected", nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    credentials_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # pointer into secret manager, NEVER the secret itself
    last_sync_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


class WebhookEndpoint(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "webhook_endpoints"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    secret: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class WebhookDelivery(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending|delivered|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)


# --------------------------------------------------------------------------- #
# Telephony, Global Calling & AI Agent Models
# --------------------------------------------------------------------------- #


class PhoneNumber(Base, UUIDPkMixin, TimestampMixin):
    """Registered or provisioned caller ID phone numbers (E.164 format)."""
    __tablename__ = "phone_numbers"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    e164_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), default="US", nullable=False)  # ISO 3166-1 alpha-2 (e.g. IN, US, JP)
    friendly_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="twilio", nullable=False)  # twilio|telnyx|livekit_sip|custom
    provider_sid: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|pending|released
    capabilities_json: Mapped[dict] = mapped_column(JSON, default=lambda: {"voice": True, "sms": False}, nullable=False)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class CallSession(Base, UUIDPkMixin, TimestampMixin):
    """PSTN / VoIP Call Session for International Calling with Realtime AI Translation."""
    __tablename__ = "call_sessions"
    __table_args__ = (
        Index("ix_call_org_created", "org_id", "created_at"),
        Index("ix_call_sid", "call_sid"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    call_sid: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="outbound", nullable=False)  # outbound|inbound
    from_number: Mapped[str] = mapped_column(String(32), nullable=False)
    to_number: Mapped[str] = mapped_column(String(32), nullable=False)
    caller_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    # Language Configuration
    caller_language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    receiver_language: Mapped[str] = mapped_column(String(16), default="ja", nullable=False)

    # State Machine: idle|initiating|connecting|ringing|connected|translating|ending|ended|busy|declined|no_answer|failed
    status: Mapped[str] = mapped_column(String(32), default="initiating", index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="human_to_human", nullable=False)  # human_to_human|ai_agent|call_center
    provider: Mapped[str] = mapped_column(String(32), default="twilio", nullable=False)
    stream_sid: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Agent / Prompt integration
    agent_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # Optional bound Meeting for realtime pipeline reuse
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)

    # Timing & Metrics
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Cost metering (independent breakdown)
    telephony_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stt_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mt_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tts_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Privacy & Recording (Phase 12 & 13: Recording OFF by default)
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Status / Failure diagnostics
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CallEvent(Base, UUIDPkMixin):
    """Immutable audit ledger for Call lifecycle events."""
    __tablename__ = "call_events"
    __table_args__ = (
        Index("ix_call_event_call_time", "call_id", "created_at"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)  # status_change|dtmf|media_start|media_stop|translation_error
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)


class AgentPrompt(Base, UUIDPkMixin, TimestampMixin):
    """AI Voice Agent configuration with versioned prompt management."""
    __tablename__ = "agent_prompts"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    agent_role: Mapped[str] = mapped_column(String(120), default="customer_support", nullable=False)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # draft|testing|active|archived
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PromptVersion(Base, UUIDPkMixin, TimestampMixin):
    """Versioned prompt record with Platform + Custom prompt merge history."""
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("agent_prompt_id", "version", name="uq_agent_version"),
    )

    agent_prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_prompts.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|testing|active|archived

    original_platform_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    original_custom_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    project_context: Mapped[str] = mapped_column(Text, default="", nullable=False)
    merged_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    conflicts_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="valid", nullable=False)  # valid|needs_review
    validation_errors_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
