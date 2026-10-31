"""Deterministic integrity check orchestrator."""
from __future__ import annotations

import time
from typing import List, Tuple
from app.checks.base import BaseIntegrityCheck
from app.checks.currency import CurrencyIntegrityCheck
from app.checks.dates_times import DatesTimesIntegrityCheck
from app.checks.empty import EmptyTranslationCheck
from app.checks.glossary import GlossaryComplianceCheck
from app.checks.language_script import LanguageScriptIntegrityCheck
from app.checks.length_duplication import LengthAndDuplicationCheck
from app.checks.negation import NegationIntegrityCheck
from app.checks.numbers import NumberIntegrityCheck
from app.checks.protected_spans import ProtectedSpansIntegrityCheck
from app.checks.urls_emails import URLsEmailsIntegrityCheck
from app.core.config import settings
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityIssue


class IntegrityCheckRunner:
    """Executes all enabled deterministic checks in a single high-speed pass (<10ms)."""

    def __init__(self) -> None:
        self.checks: List[BaseIntegrityCheck] = [
            EmptyTranslationCheck(),
            NumberIntegrityCheck(),
            CurrencyIntegrityCheck(),
            DatesTimesIntegrityCheck(),
            URLsEmailsIntegrityCheck(),
            ProtectedSpansIntegrityCheck(),
            GlossaryComplianceCheck(),
            LanguageScriptIntegrityCheck(),
            NegationIntegrityCheck(),
            LengthAndDuplicationCheck(),
        ]

    def run_all(self, request: EvaluationRequestSchema) -> Tuple[List[CheckResult], List[QualityIssue], float, bool]:
        """Runs all checks and returns (results, all_issues, data_integrity_score, has_critical_error)."""
        results: List[CheckResult] = []
        all_issues: List[QualityIssue] = []
        has_critical = False

        for check in self.checks:
            try:
                res = check.run(request)
                results.append(res)
                all_issues.extend(res.issues)
                if any(i.severity == IssueSeverity.CRITICAL for i in res.issues):
                    has_critical = True
            except Exception as e:
                # Fail-safe reporting: a check error must register as a warning
                results.append(
                    CheckResult(
                        name=check.name,
                        status="warning",
                        message=f"Check encountered runtime error: {e}",
                        issues=[],
                    )
                )

        # Calculate data integrity score (penalizing for errors)
        critical_count = sum(1 for i in all_issues if i.severity == IssueSeverity.CRITICAL)
        major_count = sum(1 for i in all_issues if i.severity == IssueSeverity.MAJOR)
        minor_count = sum(1 for i in all_issues if i.severity == IssueSeverity.MINOR)

        penalty = (critical_count * 0.40) + (major_count * 0.15) + (minor_count * 0.05)
        data_integrity_score = max(0.0, round(1.0 - penalty, 3))

        return results, all_issues, data_integrity_score, has_critical


integrity_runner = IntegrityCheckRunner()

