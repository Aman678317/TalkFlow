"""Tenant terminology and glossary compliance check."""
from __future__ import annotations

import re
from typing import Dict, List
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue


class GlossaryComplianceCheck(BaseIntegrityCheck):
    name = "glossary_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        glossary: Dict[str, str] = request.glossary or {}
        if not glossary:
            return CheckResult(
                name=self.name,
                status="passed",
                message="No tenant glossary configured for this request.",
                issues=[],
            )

        src_low = request.source_text.lower()
        tgt_low = request.target_text.lower()

        issues: List[QualityIssue] = []
        checked_terms = 0
        passed_terms = 0

        for src_term, preferred_tgt in glossary.items():
            if re.search(rf"\b{re.escape(src_term.lower())}\b", src_low) or src_term.lower() in src_low:
                checked_terms += 1
                if preferred_tgt.lower() in tgt_low:
                    passed_terms += 1
                else:
                    issues.append(
                        QualityIssue(
                            category=QualityCategory.TERMINOLOGY,
                            severity=IssueSeverity.MAJOR,
                            code="glossary_term_violation",
                            description=f"Glossary mandated term '{src_term}' -> '{preferred_tgt}' was not used.",
                            source_value=src_term,
                            target_value=preferred_tgt,
                        )
                    )

        status = "failed" if any(i.severity == IssueSeverity.CRITICAL for i in issues) else ("warning" if issues else "passed")
        compliance_pct = (passed_terms / checked_terms * 100) if checked_terms else 100.0
        msg = f"Glossary checked {checked_terms} active terms: {passed_terms} passed ({compliance_pct:.0f}% compliance)."

        return CheckResult(
            name=self.name,
            status=status,
            message=msg,
            issues=issues,
        )

