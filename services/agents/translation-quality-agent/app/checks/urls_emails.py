"""Verbatim entity preservation check for URLs, emails, and ticket IDs."""
from __future__ import annotations

import re
from typing import List, Set
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ID_RE = re.compile(r"\b(?:SKU|TICKET|CASE|INC|ORD|INV)-[A-Z0-9-]+\b", re.IGNORECASE)


class URLsEmailsIntegrityCheck(BaseIntegrityCheck):
    name = "urls_emails_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        src = request.source_text
        tgt = request.target_text

        issues: List[QualityIssue] = []

        # 1. URLs
        src_urls = set(m.group(0).rstrip(".,;:)") for m in _URL_RE.finditer(src))
        tgt_urls = set(m.group(0).rstrip(".,;:)") for m in _URL_RE.finditer(tgt))
        for url in src_urls:
            if url not in tgt_urls:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.FORMATTING,
                        severity=IssueSeverity.CRITICAL,
                        code="url_loss",
                        description=f"Source URL '{url}' was not preserved in translation.",
                        source_value=url,
                    )
                )

        # 2. Emails
        src_emails = set(m.group(0).lower() for m in _EMAIL_RE.finditer(src))
        tgt_emails = set(m.group(0).lower() for m in _EMAIL_RE.finditer(tgt))
        for email in src_emails:
            if email not in tgt_emails:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.FORMATTING,
                        severity=IssueSeverity.CRITICAL,
                        code="email_loss",
                        description=f"Source email '{email}' was lost or corrupted in translation.",
                        source_value=email,
                    )
                )

        # 3. Ticket / SKU IDs
        src_ids = set(m.group(0).upper() for m in _ID_RE.finditer(src))
        tgt_ids = set(m.group(0).upper() for m in _ID_RE.finditer(tgt))
        for tid in src_ids:
            if tid not in tgt_ids:
                issues.append(
                    QualityIssue(
                        category=QualityCategory.ACCURACY,
                        severity=IssueSeverity.MAJOR,
                        code="ticket_id_loss",
                        description=f"System identifier '{tid}' was omitted or modified.",
                        source_value=tid,
                    )
                )

        status = "failed" if issues else "passed"
        return CheckResult(
            name=self.name,
            status=status,
            message="URLs, emails, and identifiers verification completed.",
            issues=issues,
        )

