"""Event schemas matching TalkFlow multi-agent specifications for Agent 05."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.schemas import QualityDecision, QualityIssue


class Agent04TranslationFinalEvent(BaseModel):
    """Inbound translation.final event emitted by Agent 04 (MT Agent)."""
    version: int = 1
    type: str = "translation.final"
    session_id: str
    conversation_id: str
    speaker_id: str = "user_001"
    utterance_id: Optional[str] = None
    segment_id: str
    seq: int = 1
    source_lang: str
    target_lang: str
    source_text: str
    text: str
    is_final: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    quality_flags: List[str] = Field(default_factory=list)
    pivoted: bool = False
    source_equals_target: bool = False
    glossary_applied: bool = False
    glossary_terms: Optional[Dict[str, str]] = None
    protected_spans: Optional[List[str]] = None
    timestamp: float = Field(default_factory=time.time)


class QualityAssessmentFinalEvent(BaseModel):
    """Outbound quality.assessment.final event emitted by Agent 05 to Agent 06 (TTS)."""
    version: int = 1
    type: str = "quality.assessment.final"
    evaluation_id: str
    candidate_hash: str
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: Optional[str] = None
    segment_id: str
    translation_id: Optional[str] = None
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    decision: QualityDecision
    quality_status: str  # passed | warning | failed
    overall_score: float
    scores: Dict[str, float] = Field(default_factory=dict)
    checks: Dict[str, str] = Field(default_factory=dict)
    issues: List[QualityIssue] = Field(default_factory=list)
    provider_provenance: Dict[str, Any] = Field(default_factory=dict)
    retry_recommendation: Optional[Dict[str, Any]] = None
    is_final: bool = True
    timestamp: float = Field(default_factory=time.time)


class QualityAssessmentWarningEvent(BaseModel):
    """Outbound quality.assessment.warning event."""
    version: int = 1
    type: str = "quality.assessment.warning"
    evaluation_id: str
    segment_id: str
    translation_id: Optional[str] = None
    decision: QualityDecision = QualityDecision.ACCEPT_WITH_WARNINGS
    quality_status: str = "warning"
    issues: List[QualityIssue] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class QualityAssessmentRetryEvent(BaseModel):
    """Outbound quality.assessment.retry event."""
    version: int = 1
    type: str = "quality.assessment.retry"
    evaluation_id: str
    segment_id: str
    translation_id: Optional[str] = None
    decision: QualityDecision = QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER
    reason_code: str
    issues: List[QualityIssue] = Field(default_factory=list)
    retry_recommendation: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class QualityAssessmentHoldEvent(BaseModel):
    """Outbound quality.assessment.hold event for human review."""
    version: int = 1
    type: str = "quality.assessment.hold"
    evaluation_id: str
    segment_id: str
    translation_id: Optional[str] = None
    decision: QualityDecision = QualityDecision.HOLD_FOR_HUMAN
    reason_code: str
    review_required: bool = True
    timestamp: float = Field(default_factory=time.time)


class QualityAssessmentRejectedEvent(BaseModel):
    """Outbound quality.assessment.rejected event."""
    version: int = 1
    type: str = "quality.assessment.rejected"
    evaluation_id: str
    segment_id: str
    translation_id: Optional[str] = None
    decision: QualityDecision = QualityDecision.REJECT
    quality_status: str = "failed"
    reason_code: str
    issues: List[QualityIssue] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)

