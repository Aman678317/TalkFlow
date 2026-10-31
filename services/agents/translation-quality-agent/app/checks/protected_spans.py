"""Protected spans and opaque placeholder integrity check."""
from __future__ import annotations

import re
from typing import List
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

_LEAKED_PLACEHOLDER_RE = re.compile(r"__(?:TF_IMM|PUA)_[0-9]+__|[\uE000-\uE0FF]")


class ProtectedSpansIntegrityCheck(BaseIntegrityCheck):
    name = "protected_spans_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        tgt = request.target_text
        issues: List[QualityIssue] = []

        # 1. Check for unrestored placeholder leak in final translation
        leaked = _LEAKED_PLACEHOLDER_RE.findall(tgt)
        if leaked:
            issues.append(
                QualityIssue(
                    category=QualityCategory.FORMATTING,
                    severity=IssueSeverity.CRITICAL,
                    code="unrestored_placeholder_leak",
                    description=f"Raw internal placeholder tokens leaked into final output: {leaked[:3]}",
                    target_value=str(leaked[:3]),
                )
            )

        # 2. Check explicitly provided protected spans
        if request.protected_spans:
            for span in request.protected_spans:
                if span.lower() not in tgt.lower():
                    issues.append(
                        QualityIssue(
                            category=QualityCategory.DATA_INTEGRITY,
                            severity=IssueSeverity.MAJOR,
                            code="protected_span_missing",
                            description=f"Protected entity '{span}' was omitted in translation candidate.",
                            source_value=span,
                        )
                    )

        status = "failed" if any(i.severity == IssueSeverity.CRITICAL for i in issues) else ("warning" if issues else "passed")
        return CheckResult(
            name=self.name,
            status=status,
            message="Protected span verification completed.",
            issues=issues,
        )

