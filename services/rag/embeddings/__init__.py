"""Embedding engines for TalkFlow Agentic RAG."""
from rag.embeddings.base import BaseEmbeddingEngine
from rag.embeddings.bge import BGEM3EmbeddingEngine

__all__ = ["BaseEmbeddingEngine", "BGEM3EmbeddingEngine"]

