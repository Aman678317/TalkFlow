"""Translation Memory (TM) and Approved Glossary Store."""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional
from rag.models import TranslationMemoryEntry
from rag.storage.base import BaseRAGStorage
from rag.storage import get_rag_storage


class TranslationMemoryManager:
    """Manages high-precision verified source-to-target translation pairs and glossaries."""

    def __init__(self, storage: Optional[BaseRAGStorage] = None):
        self.storage = storage or get_rag_storage()

    def lookup(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        tenant_id: str = "talkflow_enterprise",
    ) -> Optional[TranslationMemoryEntry]:
        """
        Fast zero-latency translation memory lookup.
        Returns verified target text if an approved translation exists.
        """
        if not source_text or not source_text.strip():
            return None

        return self.storage.lookup_translation_memory(
            source_text=source_text.strip(),
            source_lang=source_lang.lower().strip(),
            target_lang=target_lang.lower().strip(),
            tenant_id=tenant_id,
        )

    def record_approved_translation(
        self,
        source_text: str,
        source_lang: str,
        target_text: str,
        target_lang: str,
        tenant_id: str = "talkflow_enterprise",
        org_id: str = "org_talkflow",
        domain: str = "general",
        glossary_terms: Optional[Dict[str, str]] = None,
        quality_score: float = 1.0,
        user_approved: bool = True,
    ) -> TranslationMemoryEntry:
        """Stores a user-approved or high-confidence translation pair in Translation Memory."""
        clean_src = source_text.strip()
        clean_tgt = target_text.strip()
        s_lang = source_lang.lower().strip()
        t_lang = target_lang.lower().strip()

        entry_id = f"tm_{s_lang}_{t_lang}_{hashlib.md5(clean_src.encode('utf-8')).hexdigest()[:10]}"

        entry = TranslationMemoryEntry(
            entry_id=entry_id,
            tenant_id=tenant_id,
            org_id=org_id,
            source_lang=s_lang,
            target_lang=t_lang,
            source_text=clean_src,
            target_text=clean_tgt,
            domain=domain,
            glossary_terms=glossary_terms or {},
            quality_score=quality_score,
            user_approved=user_approved,
            usage_count=1,
            created_at=time.time(),
        )

        self.storage.save_translation_memory(entry)
        return entry

