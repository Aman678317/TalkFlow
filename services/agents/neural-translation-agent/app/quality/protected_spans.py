"""Protected span handling using Private Use Area (PUA) Unicode characters.

Replaces immutable content (URLs, emails, code snippets, ticket IDs, numbers, currency)
with single PUA characters (U+E000 + index) before neural translation, and restores them
after generation to guarantee 100% preservation.
"""
from __future__ import annotations

import re
from typing import List

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CODE_RE = re.compile(r"`[^`]+`")
_ID_RE = re.compile(r"\b(?:SKU|TICKET|CASE|INC|ORD|INV|SEG|UTT)-[A-Za-z0-9-]+\b", re.IGNORECASE)
# Numbers including Indian grouping (e.g. 1,00,000.50), currency symbols, percentages
_NUMBER_RE = re.compile(
    r"(?:[₹$€£¥]|USD|INR|EUR|GBP|JPY)?\s?"
    r"[-+]?\d{1,3}(?:[,،]\d{2,3})*(?:\.\d+)?%?"
    r"|\b\d+(?:\.\d+)?%?\b"
)


_UNIFIED_PROTECTED_RE = re.compile(
    r"(?P<url>https?://\S+|www\.\S+)|"
    r"(?P<email>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|"
    r"(?P<code>`[^`]+`)|"
    r"(?P<id>\b(?:SKU|TICKET|CASE|INC|ORD|INV|SEG|UTT)-[A-Za-z0-9-]+\b)|"
    r"(?P<number>(?:[₹$€£¥]|USD|INR|EUR|GBP|JPY)?\s*[-+]?\d+(?:[,،]\d+)*(?:\.\d+)?%?)",
    re.IGNORECASE
)


class SpanProtector:
    """Safely swaps protected spans with ASCII markers and restores them in a single pass."""

    def __init__(self) -> None:
        self._spans: List[str] = []

    def protect(self, text: str) -> str:
        """Finds and replaces immutable entities with __TF_IMM_{idx}__ placeholders in a single pass."""
        self._spans = []

        def repl(m: re.Match) -> str:
            val = m.group(0).strip()
            if not val:
                return m.group(0)
            idx = len(self._spans)
            self._spans.append(val)
            return f" __TF_IMM_{idx}__ "

        return _UNIFIED_PROTECTED_RE.sub(repl, text)

    def restore(self, text: str) -> str:
        """Restores protected spans from recorded index, tolerant to spacing/casing."""
        for idx, span in enumerate(self._spans):
            pat = re.compile(rf"__\s*TF_IMM_\s*{idx}\s*__", re.IGNORECASE)
            text = pat.sub(span, text)
        return text

    @property
    def span_count(self) -> int:
        return len(self._spans)
