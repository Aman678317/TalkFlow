"""Empty text and unchanged fallback checks."""
from __future__ import annotations

from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue


class EmptyTranslationCheck(BaseIntegrityCheck):
    name = "empty_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src = request.source_text.strip()
        tgt = request.target_text.strip()

        issues = []
        if not src:
            issues.append(
                QualityIssue(
                    category=QualityCategory.ACCURACY,
                    severity=IssueSeverity.CRITICAL,
                    code="empty_source",
                    description="Source text is empty or contains only whitespace.",
                )
            )

        if not tgt:
            issues.append(
                QualityIssue(
                    category=QualityCategory.ACCURACY,
                    severity=IssueSeverity.CRITICAL,
                    code="empty_translation",
                    description="Translation candidate is empty.",
                )
            )

        # Check for untranslated unchanged fallback across different languages
        if src and tgt and src.lower() == tgt.lower() and request.source_lang != request.target_lang:
            # If both are non-ascii (like Devanagari) and different languages, unchanged is usually an untranslated drop
            if not src.isascii():
                issues.append(
                    QualityIssue(
                        category=QualityCategory.LANGUAGE,
                        severity=IssueSeverity.MAJOR,
                        code="untranslated_fallback",
                        description=f"Output is identical to source for cross-language pair {request.source_lang}->{request.target_lang}.",
                    )
                )

        status = "failed" if any(i.severity == IssueSeverity.CRITICAL for i in issues) else ("warning" if issues else "passed")
        return CheckResult(
            name=self.name,
            status=status,
            message="Empty or unchanged text check completed.",
            issues=issues,
        )

