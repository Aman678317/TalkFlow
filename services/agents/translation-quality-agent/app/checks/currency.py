"""Currency integrity and unit preservation check."""
from __future__ import annotations

import re
from typing import List, Set
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

# Currency equivalence groups
CURRENCY_GROUPS = {
    "INR": {"₹", "inr", "rupee", "rupees", "रुपये", "रुपया", "रुपयांचा", "रु."},
    "USD": {"$", "usd", "dollar", "dollars", "डॉलर"},
    "EUR": {"€", "eur", "euro", "euros", "यूरो"},
    "GBP": {"£", "gbp", "pound", "pounds", "पाउंड"},
    "JPY": {"¥", "jpy", "yen", "येन"},
}


def detect_currencies(text: str) -> Set[str]:
    """Detects canonical currency types present in text."""
    found = set()
    low = text.lower()
    for code, aliases in CURRENCY_GROUPS.items():
        for alias in aliases:
            if alias in low or re.search(rf"\b{re.escape(alias)}\b", low):
                found.add(code)
                break
    return found


class CurrencyIntegrityCheck(BaseIntegrityCheck):
    name = "currency_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src_currencies = detect_currencies(request.source_text)
        tgt_currencies = detect_currencies(request.target_text)

        issues: List[QualityIssue] = []

        if not src_currencies:
            return CheckResult(
                name=self.name,
                status="passed",
                message="No currency units detected in source.",
                issues=[],
            )

        # Check for missing currency
        for cur in src_currencies:
            if cur not in tgt_currencies:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.CRITICAL,
                        code="currency_omission",
                        description=f"Source currency '{cur}' was omitted in translation.",
                        source_value=cur,
                    )
                )

        # Check for currency conversion or alteration (e.g., INR turned into USD)
        for cur in tgt_currencies:
            if cur not in src_currencies:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.CRITICAL,
                        code="currency_corruption",
                        description=f"Translation introduced unexpected currency '{cur}' not present in source.",
                        target_value=cur,
                    )
                )

        status = "failed" if issues else "passed"
        return CheckResult(
            name=self.name,
            status=status,
            message="Currency verification completed.",
            issues=issues,
        )

