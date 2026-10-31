"""Pattern matching and term extraction for multilingual glossaries."""
from __future__ import annotations

import re
from typing import Dict, Optional


def build_glossary_pattern(terms: Dict[str, str], case_sensitive: bool = False) -> Optional[re.Pattern]:
    """Compiles an optimized regex matching terms in reverse length order."""
    if not terms:
        return None
    # Sort terms longest first to ensure greedy multi-word match (e.g. "artificial intelligence" before "intelligence")
    sorted_terms = sorted(terms.keys(), key=len, reverse=True)
    escaped = [re.escape(t) for t in sorted_terms]
    flags = re.UNICODE if case_sensitive else (re.IGNORECASE | re.UNICODE)
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", flags)


def extract_active_terms(source_text: str, glossary: Dict[str, str], case_sensitive: bool = False) -> Dict[str, str]:
    """Finds glossary entries that appear in the source text."""
    if not glossary:
        return {}
    pattern = build_glossary_pattern(glossary, case_sensitive=case_sensitive)
    if pattern is None:
        return {}

    hits: Dict[str, str] = {}
    for m in pattern.finditer(source_text):
        matched = m.group(0)
        matched_cmp = matched if case_sensitive else matched.lower()
        for k, v in glossary.items():
            k_cmp = k if case_sensitive else k.lower()
            if k_cmp == matched_cmp:
                hits[k] = v
                break
    return hits

