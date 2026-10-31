"""Code-switching and mixed-language translation handling (e.g. Hinglish)."""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional
from app.models.events import LanguageSpan

log = logging.getLogger("agent04.translation.codeswitch")

# English technical loanwords frequently retained in Indian business/tech speech
COMMON_TECH_TERMS = {
    "ai", "artificial intelligence", "machine learning", "ml", "project", "architecture",
    "feature", "production", "deploy", "deployment", "report", "meeting", "presentation",
    "dashboard", "database", "backend", "frontend", "server", "api", "code", "model",
    "testing", "quality", "service", "system", "client", "framework", "agent",
}


class CodeSwitchTranslator:
    """Handles mixed-language utterances (e.g. Hinglish) using span awareness and loanword protection."""

    @staticmethod
    def is_code_switched(spans: List[LanguageSpan]) -> bool:
        """Determines if multiple languages were detected across sub-sentence spans."""
        if not spans:
            return False
        langs = set(s.language.lower() for s in spans)
        return len(langs) > 1

    @staticmethod
    def protect_technical_spans(text: str) -> tuple[str, Dict[str, str]]:
        """Protects recognized English tech terms from accidental transliteration/corruption."""
        protected: Dict[str, str] = {}
        counter = 0

        for term in sorted(COMMON_TECH_TERMS, key=len, reverse=True):
            rx = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            def repl(m: re.Match) -> str:
                nonlocal counter
                matched = m.group(0)
                placeholder = f"__TF_TECH_{counter}__"
                protected[placeholder] = matched
                counter += 1
                return placeholder
            text = rx.sub(repl, text)

        return text, protected

    @staticmethod
    def restore_technical_spans(translated_text: str, protected: Dict[str, str]) -> str:
        for placeholder, original in protected.items():
            translated_text = translated_text.replace(placeholder, original)
        return translated_text

