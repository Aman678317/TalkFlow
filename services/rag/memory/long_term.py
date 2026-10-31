"""Long-Term Knowledge Memory Manager for verified engineering findings and model configurations."""
from __future__ import annotations

import hashlib
import time
from typing import List, Optional, Tuple
from rag.embeddings.base import BaseEmbeddingEngine
from rag.embeddings.bge import BGEM3EmbeddingEngine
from rag.models import AgentScope, LongTermMemoryItem
from rag.storage.base import BaseRAGStorage
from rag.storage import get_rag_storage


class LongTermMemoryManager:
    """Stores and retrieves verified technical knowledge, model benchmarks, and engineering decisions."""

    def __init__(
        self,
        storage: Optional[BaseRAGStorage] = None,
        embedder: Optional[BaseEmbeddingEngine] = None,
    ):
        self.storage = storage or get_rag_storage()
        self.embedder = embedder or BGEM3EmbeddingEngine()

    def save_knowledge(
        self,
        title: str,
        content: str,
        agent_scope: AgentScope = AgentScope.SHARED_PIPELINE,
        tenant_id: str = "talkflow_enterprise",
        org_id: str = "org_talkflow",
        tags: Optional[List[str]] = None,
        source_citations: Optional[List[str]] = None,
        verified_by_user: bool = False,
    ) -> LongTermMemoryItem:
        """Saves a verified engineering or operational finding into long-term memory."""
        mem_id = f"mem_{hashlib.md5(f'{title}_{content}'.encode()).hexdigest()[:12]}"
        embedding = self.embedder.embed_text(f"{title}\n{content}")

        item = LongTermMemoryItem(
            memory_id=mem_id,
            tenant_id=tenant_id,
            org_id=org_id,
            agent_scope=agent_scope,
            title=title,
            content=content,
            tags=tags or [],
            source_citations=source_citations or [],
            verified_by_user=verified_by_user,
            embedding=embedding,
            created_at=time.time(),
        )

        self.storage.save_long_term_memory(item)
        return item

    def search_knowledge(
        self,
        query: str,
        tenant_id: str = "talkflow_enterprise",
        top_k: int = 5,
    ) -> List[Tuple[LongTermMemoryItem, float]]:
        """Searches long-term verified memory by hybrid semantic + keyword matching."""
        query_vec = self.embedder.embed_text(query)
        return self.storage.search_long_term_memory(
            query=query,
            query_vec=query_vec,
            tenant_id=tenant_id,
            top_k=top_k,
        )

