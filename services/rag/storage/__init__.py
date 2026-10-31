"""Storage backends for TalkFlow Agentic RAG."""
from rag.storage.base import BaseRAGStorage
from rag.storage.sqlite_store import SQLiteRAGStorage

_instance: SQLiteRAGStorage = None


def get_rag_storage() -> BaseRAGStorage:
    """Singleton provider for active RAG storage engine."""
    global _instance
    if _instance is None:
        _instance = SQLiteRAGStorage()
    return _instance


__all__ = ["BaseRAGStorage", "SQLiteRAGStorage", "get_rag_storage"]

