"""Multi-tenant Translation Memory service with exact and fuzzy matching."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.memory.lookup import compute_normalized_hash, calculate_lexical_similarity


class TMEntry(BaseModel):
    entry_id: str
    tm_id: str
    org_id: str
    source_text: str
    target_text: str
    source_lang: str
    target_lang: str
    domain: str = "general"
    approved: bool = True
    confidence: float = 1.0


class TMQueryResult(BaseModel):
    entry: TMEntry
    match_type: str  # exact | fuzzy
    score: float


class TranslationMemoryService:
    """Manages tenant-isolated Translation Memory collections."""

    def __init__(self) -> None:
        # key: (org_id, tm_id, source_lang, target_lang, norm_hash) -> TMEntry
        self._exact_index: Dict[Tuple[str, str, str, str, str], TMEntry] = {}
        # key: (org_id, tm_id, source_lang, target_lang) -> List[TMEntry]
        self._pair_entries: Dict[Tuple[str, str, str, str], List[TMEntry]] = {}

    def add_entry(self, entry: TMEntry) -> None:
        """Stores an approved translation memory entry."""
        if not entry.approved:
            return  # Never store unapproved draft machine outputs

        norm_hash = compute_normalized_hash(entry.source_text)
        exact_key = (entry.org_id, entry.tm_id, entry.source_lang, entry.target_lang, norm_hash)
        self._exact_index[exact_key] = entry

        pair_key = (entry.org_id, entry.tm_id, entry.source_lang, entry.target_lang)
        if pair_key not in self._pair_entries:
            self._pair_entries[pair_key] = []
        self._pair_entries[pair_key].append(entry)

    def lookup(
        self,
        org_id: str,
        tm_id: str,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str = "general",
        fuzzy_threshold: float = 0.85,
    ) -> Optional[TMQueryResult]:
        """Performs exact lookup, falling back to lexical fuzzy match."""
        # 1. Exact normalized hash match
        norm_hash = compute_normalized_hash(source_text)
        exact_key = (org_id, tm_id, source_lang, target_lang, norm_hash)
        exact_entry = self._exact_index.get(exact_key)
        if exact_entry:
            return TMQueryResult(entry=exact_entry, match_type="exact", score=1.0)

        # 2. Fuzzy match within same language pair and tenant
        pair_key = (org_id, tm_id, source_lang, target_lang)
        candidates = self._pair_entries.get(pair_key, [])
        best_entry: Optional[TMEntry] = None
        best_score = 0.0

        for cand in candidates:
            score = calculate_lexical_similarity(source_text, cand.source_text)
            if score > best_score:
                best_score = score
                best_entry = cand

        if best_entry and best_score >= fuzzy_threshold:
            return TMQueryResult(entry=best_entry, match_type="fuzzy", score=best_score)

        return None


translation_memory_service = TranslationMemoryService()

