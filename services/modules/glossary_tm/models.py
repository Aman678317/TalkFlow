"""Data models for Translation Memory, Terminology & Glossaries (Module E)."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    """An individual glossary or terminology entry."""
    term_id: str
    tenant_id: str = "org_default"
    source_term: str
    target_term: str
    source_lang: str
    target_lang: str
    domain: str = "general"  # 'engineering', 'finance', 'medical', 'legal', 'general'
    category: str = "terminology"  # 'proper_name', 'terminology', 'regional_idiom'
    pronunciation_guide: Optional[str] = None
    case_sensitive: bool = False
    created_at: float = Field(default_factory=time.time)


class UserCorrectionSubmission(BaseModel):
    """User submission to correct a machine translation."""
    correction_id: str = ""
    tenant_id: str = "org_default"
    source_text: str
    original_translation: str
    corrected_translation: str
    source_lang: str
    target_lang: str
    domain: str = "general"
    user_id: str = "user_reviewer"
    reason: Optional[str] = None
    status: str = "approved"  # 'pending', 'approved', 'rejected'
    created_at: float = Field(default_factory=time.time)


class GlossaryLookupResult(BaseModel):
    """Result of glossary and TM evaluation for a segment."""
    original_text: str
    preprocessed_text: str
    applied_terms: List[GlossaryTerm] = Field(default_factory=list)
    has_exact_tm_match: bool = False
    exact_tm_translation: Optional[str] = None
    fuzzy_tm_match: Optional[Dict[str, Any]] = None
