"""MQM-aligned severity assessment and error classification."""
from __future__ import annotations

from typing import List
from app.models.schemas import IssueSeverity, QualityCategory, QualityIssue


class SeverityClassifier:
    """Classifies issues into MQM severities with strict safety invariants."""

    CRITICAL_CODES = {
        "empty_translation",
        "empty_source",
        "number_mismatch",
        "number_addition",
        "currency_corruption",
        "currency_omission",
        "critical_negation_omission",
        "unprompted_negation_addition",
        "target_script_mismatch",
        "untranslated_foreign_script",
        "unrestored_placeholder_leak",
        "url_loss",
        "email_loss",
    }

    MAJOR_CODES = {
        "ticket_id_loss",
        "protected_span_missing",
        "glossary_term_violation",
        "date_mismatch",
        "temporal_reversal",
        "suspiciously_long",
        "suspiciously_short",
        "repetitive_stutter_loop",
        "insufficient_target_script",
        "untranslated_fallback",
    }

    @classmethod
    def get_max_severity(cls, issues: List[QualityIssue]) -> IssueSeverity:
        """Finds highest severity among all detected issues."""
        if not issues:
            return IssueSeverity.INFO
        if any(i.severity == IssueSeverity.CRITICAL for i in issues):
            return IssueSeverity.CRITICAL
        if any(i.severity == IssueSeverity.MAJOR for i in issues):
            return IssueSeverity.MAJOR
        if any(i.severity == IssueSeverity.MINOR for i in issues):
            return IssueSeverity.MINOR
        return IssueSeverity.INFO

