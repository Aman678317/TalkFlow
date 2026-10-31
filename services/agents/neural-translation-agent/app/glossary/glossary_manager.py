"""In-memory multi-tenant glossary manager with PUA pre-substitution and post-enforcement."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from app.glossary.matcher import build_glossary_pattern, extract_active_terms
from app.glossary.versioning import GlossaryMetadata


class GlossaryManager:
    """Manages tenant glossaries, protects source terms, and enforces target terms."""

    def __init__(self) -> None:
        # (org_id, glossary_id) -> GlossaryMetadata
        self._glossaries: Dict[Tuple[str, str], GlossaryMetadata] = {}

    def register_glossary(self, glossary: GlossaryMetadata) -> None:
        """Registers or updates a tenant glossary."""
        key = (glossary.org_id, glossary.glossary_id)
        self._glossaries[key] = glossary

    def get_glossary(self, org_id: str, glossary_id: str) -> Optional[GlossaryMetadata]:
        return self._glossaries.get((org_id, glossary_id))

    def apply_spoken_variants(self, text: str, variants: Dict[str, str]) -> str:
        """Rewrites STT speech variants into written canonical forms (e.g. 'C P U' -> 'CPU')."""
        if not variants:
            return text
        for var, canon in variants.items():
            text = re.sub(rf"\b{re.escape(var)}\b", canon, text, flags=re.IGNORECASE)
        return text

    def protect_glossary_terms(
        self,
        source_text: str,
        terms: Dict[str, str],
        case_sensitive: bool = False,
    ) -> Tuple[str, Dict[int, str]]:
        """Replaces matched source terms with PUA placeholder characters before translation."""
        protected: Dict[int, str] = {}
        if not terms:
            return source_text, protected

        pattern = build_glossary_pattern(terms, case_sensitive=case_sensitive)
        if pattern is None:
            return source_text, protected

        counter = 0

        def repl(m: re.Match) -> str:
            nonlocal counter
            matched = m.group(0)
            matched_cmp = matched if case_sensitive else matched.lower()
            for k, v in terms.items():
                k_cmp = k if case_sensitive else k.lower()
                if k_cmp == matched_cmp:
                    token = chr(0xE100 + counter)
                    protected[counter] = v
                    counter += 1
                    return token
            return matched

        return pattern.sub(repl, source_text), protected

    def restore_glossary_terms(self, translated_text: str, protected: Dict[int, str]) -> str:
        """Restores PUA placeholder characters with the preferred target terms."""
        for idx, target_term in protected.items():
            translated_text = translated_text.replace(chr(0xE100 + idx), target_term)
        # Clear any dangling PUA codes
        translated_text = re.sub(r"[\uE100-\uE1FF]", "", translated_text)
        return translated_text


glossary_manager = GlossaryManager()

