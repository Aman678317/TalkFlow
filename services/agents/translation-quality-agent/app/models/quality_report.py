"""Comprehensive immutable Quality Report data model for Agent 05."""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.schemas import CheckResult, QualityDecision, QualityIssue


class QualityReport(BaseModel):
    """Complete, reproducible audit report for a translation evaluation."""

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

    overall_score: float = Field(..., ge=0.0, le=1.0)
    semantic_score: float = Field(default=1.0, ge=0.0, le=1.0)
    data_integrity_score: float = Field(default=1.0, ge=0.0, le=1.0)
    completeness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    terminology_score: float = Field(default=1.0, ge=0.0, le=1.0)
    fluency_score: float = Field(default=1.0, ge=0.0, le=1.0)

    checks: List[CheckResult] = Field(default_factory=list)
    issues: List[QualityIssue] = Field(default_factory=list)
    has_critical_error: bool = False

    provider: str = "unknown"
    model: str = "unknown"
    evaluator_version: str = "agent05-v1.0.0"
    evaluation_latency_ms: float = 0.0
    created_at: float = Field(default_factory=time.time)

    retry_recommendation: Optional[Dict[str, Any]] = None

    @staticmethod
    def compute_candidate_hash(source: str, target: str, src_lang: str, tgt_lang: str) -> str:
        """Computes deterministic SHA256 candidate fingerprint to ensure immutability."""
        payload = f"{src_lang}:{source.strip()}->{tgt_lang}:{target.strip()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

