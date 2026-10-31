"""Date and temporal integrity verification check."""
from __future__ import annotations

import re
from typing import List, Set
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
]

# High-impact temporal markers whose corruption alters meaning
TEMPORAL_PAIRS = [
    ({"next month", "अगले महीने", "पुढील महिन्यात"}, {"next year", "अगले साल", "पुढील वर्षी"}),
    ({"yesterday", "कल (बीता)", "काल"}, {"tomorrow", "कल (आने वाला)", "उद्या"}),
    ({"today", "आज", "आजच"}, {"tomorrow", "कल", "उद्या"}),
]


class DatesTimesIntegrityCheck(BaseIntegrityCheck):
    name = "dates_times_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src = request.source_text.lower()
        tgt = request.target_text.lower()
        issues: List[QualityIssue] = []

        # 1. Exact numeric date formats (e.g. 15/08/1947)
        src_dates = set()
        for rx in _DATE_PATTERNS:
            src_dates.update(rx.findall(request.source_text))

        tgt_dates = set()
        for rx in _DATE_PATTERNS:
            tgt_dates.update(rx.findall(request.target_text))

        for d in src_dates:
            if d not in tgt_dates:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.MAJOR,
                        code="date_mismatch",
                        description=f"Source date '{d}' was altered or missing in translation.",
                        source_value=d,
                    )
                )

        # 2. Time anchor corruption (e.g. next month -> next year)
        for group_a, group_b in TEMPORAL_PAIRS:
            a_in_src = any(m in src for m in group_a)
            b_in_tgt = any(m in tgt for m in group_b)
            if a_in_src and b_in_tgt:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.CRITICAL,
                        code="temporal_reversal",
                        description="Temporal anchor corrupted (e.g. month vs year mismatch).",
                    )
                )

        status = "failed" if any(i.severity == IssueSeverity.CRITICAL for i in issues) else ("warning" if issues else "passed")
        return CheckResult(
            name=self.name,
            status=status,
            message="Date and time integrity check completed.",
            issues=issues,
        )

