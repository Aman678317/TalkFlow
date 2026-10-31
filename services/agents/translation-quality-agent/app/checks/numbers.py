"""Multi-locale number extraction, normalization, and integrity check."""
from __future__ import annotations

import re
from typing import List, Set
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

# Devanagari digit translation table
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize_number_string(num_str: str) -> str:
    """Normalizes script digits and removes comma separators (e.g. '12,50,000' -> '1250000')."""
    s = num_str.translate(DEVANAGARI_DIGITS).translate(BENGALI_DIGITS)
    # Remove commas and non-breaking spaces used as grouping separators
    s = re.sub(r"[,،\s]", "", s)
    # Remove trailing dot or leading plus
    s = s.rstrip(".").lstrip("+")
    return s


def extract_normalized_numbers(text: str) -> List[str]:
    """Extracts all numbers (integers, floats, percentages) with multi-locale digit support."""
    # Matches sequences of digits with optional decimals and commas
    pattern = re.compile(r"[-+]?[0-9०-९০-৯]+(?:[,،\s][0-9०-९০-৯]+)*(?:\.[0-9०-९০-৯]+)?%?")
    matches = pattern.findall(text)
    normalized = []
    for m in matches:
        clean = normalize_number_string(m.strip())
        if clean and any(ch.isdigit() for ch in clean):
            normalized.append(clean)
    return normalized


class NumberIntegrityCheck(BaseIntegrityCheck):
    name = "number_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src_nums = extract_normalized_numbers(request.source_text)
        tgt_nums = extract_normalized_numbers(request.target_text)

        issues: List[QualityIssue] = []

        if not src_nums and not tgt_nums:
            return CheckResult(
                name=self.name,
                status="passed",
                message="No numbers present in source or target.",
                issues=[],
            )

        # Check for missing source numbers
        tgt_set = set(tgt_nums)
        for num in src_nums:
            if num not in tgt_set:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.CRITICAL,
                        code="number_mismatch",
                        description=f"Source number '{num}' was omitted or modified in translation.",
                        source_value=num,
                    )
                )

        # Check for fabricated target numbers
        src_set = set(src_nums)
        for num in tgt_nums:
            if num not in src_set:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.CRITICAL,
                        code="number_addition",
                        description=f"Translation contains fabricated or altered number '{num}' not in source.",
                        target_value=num,
                    )
                )

        status = "failed" if issues else "passed"
        msg = f"Number verification completed: {len(src_nums)} source, {len(tgt_nums)} target."
        return CheckResult(name=self.name, status=status, message=msg, issues=issues)

