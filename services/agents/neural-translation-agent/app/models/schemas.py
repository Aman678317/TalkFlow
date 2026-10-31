"""Pydantic request and response schemas for REST endpoints."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TranslationIntent(StrEnum):
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_OPTIMIZED = "quality_optimized"
    COST_OPTIMIZED = "cost_optimized"
    PRIVATE_ONLY = "private_only"
    OFFLINE_ONLY = "offline_only"
    EXPERIMENTAL = "experimental"


class TranslationRequestSchema(BaseModel):
    """Single-target translation request schema."""
    text: str = Field(..., min_length=1, max_length=50000, description="Canonical source text")
    source_lang: str = Field(..., min_length=2, max_length=16, description="ISO 639-1 code or 'auto'")
    target_lang: str = Field(..., min_length=2, max_length=16, description="Target ISO 639-1 code")
    session_id: Optional[str] = Field(None, description="Meeting or session identifier")
    conversation_id: Optional[str] = Field(None, description="Conversation identifier")
    speaker_id: Optional[str] = Field("user_001", description="Speaker identity")
    utterance_id: Optional[str] = Field(None, description="Turn identifier")
    segment_id: Optional[str] = Field(None, description="Canonical segment identifier from Agent 01/02")
    domain: str = Field("general", description="Domain context (e.g. general, technical, legal)")
    intent: TranslationIntent = Field(TranslationIntent.QUALITY_OPTIMIZED, description="Routing intent")
    context: List[str] = Field(default_factory=list, description="Recent conversation turns (bounded)")
    glossary: Optional[Dict[str, str]] = Field(None, description="Term mappings {source_term: target_term}")
    glossary_id: Optional[str] = Field(None, description="ID of stored glossary")
    style_profile_id: Optional[str] = Field(None, description="ID of style profile")
    tm_id: Optional[str] = Field(None, description="Translation memory ID")
    tenant_private_only: bool = Field(False, description="Strict local-only policy")
    formality: str = Field("neutral", description="neutral, formal, or informal")


class TranslationResponseSchema(BaseModel):
    """Single-target translation response schema."""
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    speaker_id: Optional[str] = None
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    source_lang: str
    target_lang: str
    text: str
    is_final: bool = True
    provider: str
    model: str
    latency_ms: float
    confidence: Optional[float] = None
    quality_flags: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    tm_match: Optional[str] = None
    glossary_applied: bool = False
    pivoted: bool = False
    source_equals_target: bool = False


class BatchTranslationRequestSchema(BaseModel):
    """Multi-target translation request schema (one source segment -> N targets)."""
    text: str = Field(..., min_length=1, max_length=50000)
    source_lang: str = Field(..., min_length=2, max_length=16)
    target_langs: List[str] = Field(..., min_length=1, description="List of target ISO language codes")
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    speaker_id: Optional[str] = "user_001"
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    domain: str = "general"
    intent: TranslationIntent = TranslationIntent.QUALITY_OPTIMIZED
    context: List[str] = Field(default_factory=list)
    glossary: Optional[Dict[str, str]] = None
    tenant_private_only: bool = False
    formality: str = "neutral"


class BatchTargetResult(BaseModel):
    target_lang: str
    text: str
    status: str = "success"  # success | failed | identity
    provider: str
    model: str
    latency_ms: float
    quality_flags: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    pivoted: bool = False


class BatchTranslationResponseSchema(BaseModel):
    """Multi-target translation response schema."""
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    speaker_id: Optional[str] = None
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    source_lang: str
    source_text: str
    requested_targets_count: int
    unique_translation_jobs_count: int
    results: Dict[str, BatchTargetResult]
    total_latency_ms: float


class ValidatePairRequestSchema(BaseModel):
    source_lang: str
    target_lang: str
    tenant_private_only: bool = False


class ValidatePairResponseSchema(BaseModel):
    source_lang: str
    target_lang: str
    supported: bool
    status: str  # PRODUCTION | SUPPORTED | EXPERIMENTAL | UNSUPPORTED
    recommended_provider: Optional[str] = None
    recommended_model: Optional[str] = None
    direct_translation_supported: bool
    pivot_required: bool
    notes: str = ""


class LanguagePairInfo(BaseModel):
    source_lang: str
    target_lang: str
    status: str
    provider: str
    model: str
    direct: bool


class AgentInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    primary_provider: str
    default_model: str
    device: str
    compute_type: str
    active_providers: List[str]
    supported_pairs_count: int
    zero_pivot_enforced: bool
    agent_brain_enabled: bool
    agent_brain_model: Optional[str] = None
    active_sessions: int
    uptime_seconds: float

