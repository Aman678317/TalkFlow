"""Multi-dimensional quality scoring with hard safety gating."""
from __future__ import annotations

from typing import Dict, List, Tuple
from app.core.config import settings
from app.models.schemas import IssueSeverity, QualityIssue


class QualityScorer:
    """Calculates multidimensional quality scores and applies hard safety gates."""

    @classmethod
    def calculate_scores(
        cls,
        semantic_score: float,
        data_integrity_score: float,
        issues: List[QualityIssue],
        has_critical_error: bool,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculates composite overall score and dimensional breakdown."""
        weights = settings.scoring_weights

        # 1. Dimensional sub-scores
        terminology_issues = [i for i in issues if i.category == "terminology"]
        term_score = 1.0 - (len(terminology_issues) * 0.25)
        terminology_score = max(0.0, round(term_score, 3))

        fluency_issues = [i for i in issues if i.category in ("fluency", "formatting")]
        fluency_penalty = sum(0.10 if i.severity == IssueSeverity.MAJOR else 0.04 for i in fluency_issues)
        fluency_score = max(0.0, round(1.0 - fluency_penalty, 3))

        completeness_issues = [i for i in issues if "short" in i.code or "omission" in i.code]
        comp_penalty = sum(0.25 if i.severity == IssueSeverity.CRITICAL else 0.12 for i in completeness_issues)
        completeness_score = max(0.0, round(1.0 - comp_penalty, 3))

        # 2. Weighted raw composite
        raw_composite = (
            (semantic_score * weights.semantic_accuracy)
            + (completeness_score * weights.completeness)
            + (data_integrity_score * weights.data_integrity)
            + (terminology_score * weights.terminology)
            + (fluency_score * weights.fluency)
        )

        # 3. HARD SAFETY GATE: If a critical error exists, the composite score CANNOT exceed 0.35!
        # High fluency must never mask a factual/numeric/negation corruption.
        if has_critical_error:
            final_composite = min(0.35, round(raw_composite, 3))
        else:
            final_composite = round(raw_composite, 3)

        scores_dict = {
            "semantic_accuracy": round(semantic_score, 3),
            "completeness": completeness_score,
            "data_integrity": round(data_integrity_score, 3),
            "terminology": terminology_score,
            "fluency": fluency_score,
        }

        return final_composite, scores_dict


quality_scorer = QualityScorer()

