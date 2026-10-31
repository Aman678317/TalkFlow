"""Data models and schemas for Translation Quality Agent."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QualityDecision(str, Enum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_WARNINGS = "ACCEPT_WITH_WARNINGS"
    RETRY_WITH_ALTERNATE_PROVIDER = "RETRY_WITH_ALTERNATE_PROVIDER"
    HOLD_FOR_HUMAN = "HOLD_FOR_HUMAN"
    REJECT = "REJECT"


class IssueSeverity(str, Enum):
    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class QualityCategory(str, Enum):
    ACCURACY = "accuracy"
    FLUENCY = "fluency"
    TERMINOLOGY = "terminology"
    LOCALE = "locale"
    FORMATTING = "formatting"
    LANGUAGE = "language"
    DATA_INTEGRITY = "data_integrity"


class QualityIssue(BaseModel):
    category: QualityCategory
    severity: IssueSeverity
    code: str
    description: str
    source_value: Optional[str] = None
    target_value: Optional[str] = None


class CheckResult(BaseModel):
    name: str
    status: str  # passed | warning | failed | not_applicable
    message: str
    issues: List[QualityIssue] = Field(default_factory=list)


class EvaluationRequestSchema(BaseModel):
    source_text: str = Field(..., description="Canonical source human speech transcript")
    target_text: str = Field(..., description="Candidate translation from Agent 04")
    source_lang: str = Field(..., description="Source language ISO code (e.g., 'hi')")
    target_lang: str = Field(..., description="Target language ISO code (e.g., 'en')")
    session_id: str = "sess_qa_default"
    conversation_id: str = "conv_qa_default"
    speaker_id: str = "user_001"
    utterance_id: Optional[str] = None
    segment_id: str = "seg_qa_default"
    translation_id: Optional[str] = None
    provider: Optional[str] = "agent04_neural"
    model: Optional[str] = "unknown"
    glossary: Optional[Dict[str, str]] = None
    protected_spans: Optional[List[str]] = None
    mode: str = "final"  # final | partial | reference


class BatchEvaluationRequestSchema(BaseModel):
    candidates: List[EvaluationRequestSchema]


class PartialEvaluationRequestSchema(BaseModel):
    source_text: str
    target_text: str
    source_lang: str
    target_lang: str
    segment_id: Optional[str] = "partial_seg"


class ReferenceEvaluationRequestSchema(BaseModel):
    source_text: str
    hypothesis_text: str
    reference_text: str
    source_lang: str
    target_lang: str


class EvaluationResponseSchema(BaseModel):
    evaluation_id: str
    candidate_hash: str
    session_id: str
    segment_id: str
    translation_id: Optional[str] = None
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    decision: QualityDecision
    quality_status: str  # passed | warning | failed
    overall_score: float = Field(..., ge=0.0, le=1.0)
    scores: Dict[str, float] = Field(default_factory=dict)
    issues: List[QualityIssue] = Field(default_factory=list)
    checks: Dict[str, str] = Field(default_factory=dict)
    provider_provenance: Dict[str, Any] = Field(default_factory=dict)
    retry_recommendation: Optional[Dict[str, Any]] = None
    evaluation_latency_ms: float
    timestamp: float = Field(default_factory=time.time)


class HumanReviewSubmissionSchema(BaseModel):
    evaluation_id: str
    reviewer_id: str
    human_decision: QualityDecision
    corrected_translation: Optional[str] = None
    comments: Optional[str] = None
    labels: List[str] = Field(default_factory=list)


class HumanReviewItem(BaseModel):
    evaluation_id: str
    segment_id: str
    source_text: str
    target_text: str
    source_lang: str
    target_lang: str
    suggested_decision: QualityDecision
    reasons: List[str]
    created_at: float = Field(default_factory=time.time)
    reviewed: bool = False
    review_result: Optional[HumanReviewSubmissionSchema] = None


class AgentInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    primary_evaluator: str
    active_evaluators: List[str]
    supported_metrics: List[str]
    decision_outcomes: List[str]
    agent_brain_enabled: bool
    agent_brain_model: Optional[str] = None
    pending_human_reviews: int
    uptime_seconds: float

