"""Critical negation reversal and instruction directionality check."""
from __future__ import annotations

import re
from typing import List
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

NEGATION_PATTERNS = {
    "en": re.compile(r"\b(?:not|never|no|none|neither|nor|don'?t|doesn'?t|didn'?t|won'?t|cannot|can'?t|shouldn'?t)\b", re.I),
    "hi": re.compile(r"(?:नहीं|मत|ना|कदापि नहीं)"),
    "mr": re.compile(r"(?:नाही|नको|नये|नसेल|नसते)"),
    "bn": re.compile(r"(?:না|নয়|নেই|কখনও না)"),
    "ja": re.compile(r"(?:ない|ません|ず|ぬ)"),
}


def has_negation(text: str, lang: str) -> bool:
    """Checks whether the text contains an active grammatical negation particle."""
    pattern = NEGATION_PATTERNS.get(lang.lower())
    if pattern:
        return bool(pattern.search(text))
    # Fallback check across standard English / Latin forms
    return bool(NEGATION_PATTERNS["en"].search(text))


class NegationIntegrityCheck(BaseIntegrityCheck):
    name = "negation_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src_lang = request.source_lang.lower()
        tgt_lang = request.target_lang.lower()

        src_has_neg = has_negation(request.source_text, src_lang)
        tgt_has_neg = has_negation(request.target_text, tgt_lang)

        issues: List[QualityIssue] = []

        # 1. Source had negation, but translation omitted it (Critical Negation Reversal)
        if src_has_neg and not tgt_has_neg:
            issues.append(
                QualityIssue(
                    category=QualityCategory.ACCURACY,
                    severity=IssueSeverity.CRITICAL,
                    code="critical_negation_omission",
                    description="Source contains negation, but translation candidate omitted negative instruction (polarity flip).",
                )
            )

        # 2. Source was affirmative, but translation added unprompted negation
        elif not src_has_neg and tgt_has_neg:
            issues.append(
                QualityIssue(
                    category=QualityCategory.ACCURACY,
                    severity=IssueSeverity.CRITICAL,
                    code="unprompted_negation_addition",
                    description="Affirmative source was converted into a negative statement in translation (polarity flip).",
                )
            )

        status = "failed" if issues else "passed"
        return CheckResult(
            name=self.name,
            status=status,
            message="Negation and instruction directionality check completed.",
            issues=issues,
        )

