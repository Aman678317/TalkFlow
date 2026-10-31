"""Abstract Reranker Interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple
from rag.models import DocumentChunk, RetrievedPassage


class BaseReranker(ABC):
    """Abstract interface for passage reranking engines."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[RetrievedPassage],
        top_k: int = 6,
    ) -> List[RetrievedPassage]:
        """Rerank candidate passages based on cross-entropy relevance to query."""
        pass

