"""Translation finalizer performing span restoration, glossary enforcement, and QA verification."""
from __future__ import annotations

from typing import Dict, List, Tuple
from app.quality.integrity_checks import check_translation_integrity
from app.quality.protected_spans import SpanProtector
from app.glossary.glossary_manager import glossary_manager


def finalize_translation(
    source_text: str,
    raw_translated: str,
    source_lang: str,
    target_lang: str,
    span_protector: SpanProtector,
    glossary_protected: Dict[int, str],
    tech_protected: Dict[str, str],
    existing_flags: List[str],
) -> Tuple[str, List[str]]:
    """Restores all protected placeholders and executes output integrity pre-checks."""
    import re
    # 1. Restore technical term placeholders (tolerant to model spacing and casing)
    text = raw_translated
    for placeholder, original in tech_protected.items():
        num_m = re.search(r"\d+", placeholder)
        if num_m:
            idx = num_m.group(0)
            pattern = re.compile(rf"__\s*TF_TECH_{idx}\s*__", re.IGNORECASE)
            text = pattern.sub(original, text)
        else:
            text = text.replace(placeholder, original)

    # 2. Restore glossary target terms
    if glossary_protected:
        text = glossary_manager.restore_glossary_terms(text, glossary_protected)

    # 3. Restore immutable entities (URLs, emails, numbers, code)
    if span_protector.span_count > 0:
        text = span_protector.restore(text)

    # 4. Run post-generation integrity pre-checks
    qa_flags = check_translation_integrity(source_text, text, source_lang, target_lang)

    # Combine unique flags
    combined_flags = list(dict.fromkeys(existing_flags + qa_flags))
    return text.strip(), combined_flags
