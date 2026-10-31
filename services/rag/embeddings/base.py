"""Abstract base class for RAG embedding engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingEngine(ABC):
    """Abstract interface for text embedding providers."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate dense vector representation for a single text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vector representations for a batch of texts."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the output embedding vectors."""
        pass

