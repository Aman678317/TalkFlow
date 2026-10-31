"""Deterministic decision engine for translation quality gating."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings
from app.models.schemas import IssueSeverity, QualityDecision, QualityIssue
from app.quality.severity import SeverityClassifier


class DecisionEngine:
    """Evaluates findings against strict quality gates to produce one immutable decision."""

    @classmethod
    def resolve_decision(
        cls,
        overall_score: float,
        issues: List[QualityIssue],
        has_critical_error: bool,
        current_retry_count: int = 0,
        current_provider: Optional[str] = None,
        source_lang: str = "en",
        target_lang: str = "hi",
    ) -> Tuple[QualityDecision, str, Optional[Dict[str, Any]]]:
        """Resolves (decision, quality_status, retry_recommendation)."""
        max_severity = SeverityClassifier.get_max_severity(issues)
        thresholds = settings.thresholds

        retry_recommendation: Optional[Dict[str, Any]] = None

        # 1. Critical Errors (Hard Gate)
        if has_critical_error or max_severity == IssueSeverity.CRITICAL:
            # Check if retry budget remains and an alternate provider can be recommended
            if current_retry_count < thresholds.retry_budget:
                alt_provider = cls._suggest_alternate_provider(current_provider, source_lang, target_lang)
                retry_recommendation = {
                    "alternate_provider_required": True,
                    "recommended_provider": alt_provider,
                    "reason": "Critical integrity failure (number, currency, script, or negation mismatch)",
                    "current_retry_count": current_retry_count + 1,
                    "max_retries": thresholds.retry_budget,
                }
                return QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER, "failed", retry_recommendation

            # If retries exhausted or catastrophic, reject immediately
            return QualityDecision.REJECT, "failed", None

        # 2. Major Errors (Glossary / Terminology / Truncation)
        if max_severity == IssueSeverity.MAJOR:
            if current_retry_count < thresholds.retry_budget:
                alt_provider = cls._suggest_alternate_provider(current_provider, source_lang, target_lang)
                retry_recommendation = {
                    "alternate_provider_required": True,
                    "recommended_provider": alt_provider,
                    "reason": "Major quality issue detected (terminology violation or truncation)",
                    "current_retry_count": current_retry_count + 1,
                    "max_retries": thresholds.retry_budget,
                }
                return QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER, "warning", retry_recommendation

            # Route to human review if retries exhausted
            return QualityDecision.HOLD_FOR_HUMAN, "warning", None

        # 3. Score-based gating
        if overall_score >= thresholds.quality_threshold:
            if max_severity == IssueSeverity.MINOR:
                return QualityDecision.ACCEPT_WITH_WARNINGS, "warning", None
            return QualityDecision.ACCEPT, "passed", None

        if overall_score >= thresholds.warning_threshold:
            return QualityDecision.ACCEPT_WITH_WARNINGS, "warning", None

        # 4. Low confidence score fallback
        return QualityDecision.HOLD_FOR_HUMAN, "warning", None

    @staticmethod
    def _suggest_alternate_provider(current: Optional[str], src: str, tgt: str) -> str:
        """Heuristic alternate provider recommendation for Agent 04 orchestrator."""
        cur = (current or "").lower()
        if "argos" in cur:
            return "marian"
        elif "marian" in cur:
            return "neural_online"
        elif "madlad" in cur:
            return "argos"
        return "argos"


decision_engine = DecisionEngine()

