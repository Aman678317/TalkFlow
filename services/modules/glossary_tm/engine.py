"""Glossary, Terminology & Translation Memory Engine (Module E).

Provides domain-specific glossaries, proper name dictionaries, regional terminology,
and user correction workflows with strict tenant separation and SQLite persistence.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

from modules.glossary_tm.models import (
    GlossaryLookupResult,
    GlossaryTerm,
    UserCorrectionSubmission,
)
from rag.memory.translation_memory import TranslationMemoryManager
from rag.models import TranslationMemoryEntry

tm_manager = TranslationMemoryManager()
logger = logging.getLogger("talkflow.modules.glossary_tm")


class GlossaryAndTMEngine:
    """Manages custom terminology libraries, user correction workflows, and TM reuse."""

    def __init__(self) -> None:
        # (tenant_id, term_id) -> GlossaryTerm
        self._glossary_terms: Dict[Tuple[str, str], GlossaryTerm] = {}
        # (tenant_id, correction_id) -> UserCorrectionSubmission
        self._corrections: Dict[Tuple[str, str], UserCorrectionSubmission] = {}
        self._seed_default_glossary()

    def _seed_default_glossary(self) -> None:
        """Seed high-priority product terms and regional dialect idioms."""
        defaults = [
            GlossaryTerm(
                term_id="term_talkflow_hi",
                tenant_id="org_default",
                source_term="TalkFlow",
                target_term="टॉकफ्लो",
                source_lang="en",
                target_lang="hi",
                category="proper_name",
                pronunciation_guide="टॉक-फ्लो",
            ),
            GlossaryTerm(
                term_id="term_talkflow_mr",
                tenant_id="org_default",
                source_term="TalkFlow",
                target_term="टॉकफ्लो",
                source_lang="en",
                target_lang="mr",
                category="proper_name",
                pronunciation_guide="टॉक-फ्लो",
            ),
            GlossaryTerm(
                term_id="term_agentic_hi",
                tenant_id="org_default",
                source_term="Agentic AI",
                target_term="एजेंटिक एआई",
                source_lang="en",
                target_lang="hi",
                category="terminology",
                domain="engineering",
            ),
            GlossaryTerm(
                term_id="term_rag_hi",
                tenant_id="org_default",
                source_term="Retrieval-Augmented Generation",
                target_term="रिट्रीवल-ऑगमेंटेड जनरेशन",
                source_lang="en",
                target_lang="hi",
                category="terminology",
                domain="engineering",
            ),
        ]
        for term in defaults:
            self._glossary_terms[(term.tenant_id, term.term_id)] = term

    def add_term(self, term: GlossaryTerm) -> GlossaryTerm:
        """Adds or updates a terminology rule for a tenant."""
        if not term.term_id:
            term.term_id = f"term_{hashlib.md5(f'{term.source_term}_{term.source_lang}_{term.target_lang}'.encode()).hexdigest()[:10]}"
        self._glossary_terms[(term.tenant_id, term.term_id)] = term
        logger.info(f"Added glossary term '{term.source_term}' -> '{term.target_term}' for tenant '{term.tenant_id}'")
        return term

    def list_terms(
        self,
        tenant_id: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> List[GlossaryTerm]:
        """Filters glossary terms with multi-tenant isolation."""
        results = []
        for (t_id, _), term in self._glossary_terms.items():
            if t_id != tenant_id and t_id != "org_default":
                continue
            if source_lang and term.source_lang != source_lang.lower().split("-")[0]:
                continue
            if target_lang and term.target_lang != target_lang.lower().split("-")[0]:
                continue
            if domain and term.domain != domain.lower():
                continue
            results.append(term)
        return results

    def submit_user_correction(self, sub: UserCorrectionSubmission) -> UserCorrectionSubmission:
        """Ingests and approves user corrections, saving directly into Translation Memory."""
        if not sub.correction_id:
            sub.correction_id = f"corr_{hashlib.md5(f'{sub.tenant_id}_{sub.source_text}_{time.time()}'.encode()).hexdigest()[:12]}"

        sub.status = "approved"
        self._corrections[(sub.tenant_id, sub.correction_id)] = sub

        # Store into persistent Translation Memory (SQLite) for reuse across future translation jobs
        tm_manager.record_approved_translation(
            source_text=sub.source_text.strip(),
            source_lang=sub.source_lang.lower().split("-")[0],
            target_text=sub.corrected_translation.strip(),
            target_lang=sub.target_lang.lower().split("-")[0],
            tenant_id=sub.tenant_id,
            domain=sub.domain,
            quality_score=1.0,
            user_approved=True,
        )
        logger.info(f"Committed user correction '{sub.correction_id}' to persistent Translation Memory for tenant '{sub.tenant_id}'")
        return sub

    def lookup(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        tenant_id: str = "org_default",
        domain: str = "general",
    ) -> GlossaryLookupResult:
        """Evaluates text against approved Translation Memory and applies glossary rules."""
        src_clean = source_lang.lower().split("-")[0].strip()
        tgt_clean = target_lang.lower().split("-")[0].strip()

        # 1. Check exact Translation Memory
        exact_entry = tm_manager.lookup(
            source_text=text,
            source_lang=src_clean,
            target_lang=tgt_clean,
            tenant_id=tenant_id,
        )

        has_exact = exact_entry is not None
        exact_trans = exact_entry.target_text if exact_entry else None
        fuzzy_match = None

        # 3. Apply glossary terms
        active_terms = self.list_terms(tenant_id, source_lang=src_clean, target_lang=tgt_clean, domain=domain)
        applied = []
        processed_text = text

        for term in active_terms:
            flags = 0 if term.case_sensitive else re.IGNORECASE
            pattern = r"\b" + re.escape(term.source_term) + r"\b"
            if re.search(pattern, processed_text, flags=flags):
                applied.append(term)
                # Protected placeholder
                processed_text = re.sub(pattern, term.target_term, processed_text, flags=flags)

        return GlossaryLookupResult(
            original_text=text,
            preprocessed_text=processed_text,
            applied_terms=applied,
            has_exact_tm_match=has_exact,
            exact_tm_translation=exact_trans,
            fuzzy_tm_match=fuzzy_match,
        )


# Global Engine Instance
glossary_tm_engine = GlossaryAndTMEngine()
