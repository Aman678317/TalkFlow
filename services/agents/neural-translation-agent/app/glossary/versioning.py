"""Glossary version and language-pair integrity models."""
from __future__ import annotations

from typing import Dict, Optional
from pydantic import BaseModel, Field


class GlossaryMetadata(BaseModel):
    glossary_id: str
    org_id: str
    name: str
    source_lang: str
    target_lang: str
    version: int = 1
    terms: Dict[str, str] = Field(default_factory=dict)
    spoken_variants: Dict[str, str] = Field(default_factory=dict)
    case_sensitive: bool = False

    def is_applicable_for_pair(self, src: str, tgt: str) -> bool:
        """Enforces that a glossary for en->hi cannot be applied to en->mr."""
        return self.source_lang.lower() == src.lower() and self.target_lang.lower() == tgt.lower()

