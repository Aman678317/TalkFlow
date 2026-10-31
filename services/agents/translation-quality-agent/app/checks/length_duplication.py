"""Length ratio anomalies and repetitive hallucination loop check."""
from __future__ import annotations

import re
from typing import List
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue


class LengthAndDuplicationCheck(BaseIntegrityCheck):
    name = "length_duplication_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src = request.source_text.strip()
        tgt = request.target_text.strip()
        issues: List[QualityIssue] = []

        if not src or not tgt:
            return CheckResult(name=self.name, status="passed", message="Skipped on empty text.", issues=[])

        # 1. Length ratio sanity
        ratio = len(tgt) / max(1, len(src))
        if ratio > 3.8 and len(tgt) > 40:
            issues.append(
                QualityIssue(
                    category=QualityCategory.ACCURACY,
                    severity=IssueSeverity.MAJOR,
                    code="suspiciously_long",
                    description=f"Translation is {ratio:.1f}x longer than source (potential hallucination).",
                )
            )
        elif ratio < 0.18 and len(src) > 40:
            issues.append(
                QualityIssue(
                    category=QualityCategory.ACCURACY,
                    severity=IssueSeverity.MAJOR,
                    code="suspiciously_short",
                    description=f"Translation is only {ratio:.2f}x source length (potential clause omission).",
                )
            )

        # 2. Repetition / stutter loops (e.g., "AI project AI project AI project")
        words = tgt.split()
        if len(words) >= 6:
            # Check for identical adjacent 3-grams
            for i in range(len(words) - 5):
                gram1 = " ".join(words[i:i+3]).lower()
                gram2 = " ".join(words[i+3:i+6]).lower()
                if gram1 == gram2 and len(gram1) > 5:
                    issues.append(
                        QualityIssue(
                            category=QualityCategory.FLUENCY,
                            severity=IssueSeverity.MAJOR,
                            code="repetitive_stutter_loop",
                            description=f"Detected repetitive phrase loop: '{gram1}' repeated verbatim.",
                            target_value=gram1,
                        )
                    )
                    break

        status = "failed" if any(i.severity == IssueSeverity.CRITICAL for i in issues) else ("warning" if issues else "passed")
        return CheckResult(
            name=self.name,
            status=status,
            message="Length ratio and repetition check completed.",
            issues=issues,
        )

