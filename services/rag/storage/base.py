"""Abstract Storage Engine for TalkFlow Shared RAG, Vector Index & Memory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from rag.models import (
    AgentScope,
    DocumentChunk,
    DocumentRecord,
    LongTermMemoryItem,
    ResearchNote,
    ShortTermMemoryItem,
    TranslationMemoryEntry,
    TrustTier,
)


class BaseRAGStorage(ABC):
    """Abstract storage backend managing vector embeddings, BM25 indexing, and agent memories."""

    @abstractmethod
    def insert_document(self, doc: DocumentRecord) -> None:
        pass

    @abstractmethod
    def get_document(self, document_id: str, tenant_id: str) -> Optional[DocumentRecord]:
        pass

    @abstractmethod
    def insert_chunk(self, chunk: DocumentChunk) -> None:
        pass

    @abstractmethod
    def insert_chunks(self, chunks: List[DocumentChunk]) -> None:
        pass

    @abstractmethod
    def search_dense(
        self,
        query_vec: List[float],
        top_k: int,
        tenant_id: str,
        agent_scope: Optional[AgentScope] = None,
        min_trust_tier: Optional[TrustTier] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        pass

    @abstractmethod
    def search_lexical(
        self,
        query: str,
        top_k: int,
        tenant_id: str,
        agent_scope: Optional[AgentScope] = None,
        min_trust_tier: Optional[TrustTier] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        pass

    @abstractmethod
    def save_research_note(self, note: ResearchNote) -> None:
        pass

    @abstractmethod
    def get_research_note(self, research_id: str, tenant_id: str) -> Optional[ResearchNote]:
        pass

    @abstractmethod
    def list_research_notes(self, tenant_id: str, agent_id: Optional[str] = None) -> List[ResearchNote]:
        pass

    @abstractmethod
    def save_short_term_memory(self, item: ShortTermMemoryItem) -> None:
        pass

    @abstractmethod
    def get_short_term_memory(self, job_id: str, tenant_id: str) -> Optional[ShortTermMemoryItem]:
        pass

    @abstractmethod
    def save_long_term_memory(self, item: LongTermMemoryItem) -> None:
        pass

    @abstractmethod
    def search_long_term_memory(
        self,
        query: str,
        query_vec: List[float],
        tenant_id: str,
        top_k: int = 5,
    ) -> List[Tuple[LongTermMemoryItem, float]]:
        pass

    @abstractmethod
    def save_translation_memory(self, entry: TranslationMemoryEntry) -> None:
        pass

    @abstractmethod
    def lookup_translation_memory(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        tenant_id: str,
    ) -> Optional[TranslationMemoryEntry]:
        pass

