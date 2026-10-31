"""Terminology compliance verification for glossaries."""
from __future__ import annotations

from typing import Dict, List, Tuple


def verify_glossary_compliance(
    source_text: str,
    translated_text: str,
    active_terms: Dict[str, str],
) -> Tuple[List[str], bool]:
    """Verifies that all applicable glossary target terms are present in the output."""
    flags: List[str] = []
    if not active_terms:
        return flags, False

    lowered_target = translated_text.lower()
    all_matched = True

    for src_term, tgt_term in active_terms.items():
        if tgt_term.lower() not in lowered_target:
            flags.append(f"glossary_term_missing:{tgt_term}")
            all_matched = False

    return flags, all_matched

