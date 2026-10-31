"""TalkFlow Shared Agentic RAG and Autonomous Research Configuration."""
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class RAGSettings(BaseSettings):
    """Central configuration for TalkFlow RAG, Vector Storage, Research Engine & Memory."""

    # Storage & Database
    storage_dir: Path = Field(default=Path("I:/vioces agent/storage/rag"))
    sqlite_db_path: Path = Field(default=Path("I:/vioces agent/storage/rag/talkflow_rag.db"))
    database_url: str = Field(default=os.getenv("DATABASE_URL", ""))  # If postgresql:// is provided

    # Tenant Isolation
    default_tenant_id: str = "talkflow_enterprise"
    default_org_id: str = "org_talkflow"
    enforce_tenant_isolation: bool = True

    # Embedding Configuration
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "qwen3.5:4b"

    # Reranking Configuration
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rrf_k: int = 60  # Standard Reciprocal Rank Fusion constant
    dense_candidates_count: int = 25
    lexical_candidates_count: int = 25
    final_top_k: int = 6  # Recommended passages passed to agent token budget

    # Document Chunking
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 80
    min_chunk_tokens: int = 30

    # Web & External Research
    search_provider: str = os.getenv("SEARCH_PROVIDER", "duckduckgo")  # duckduckgo, searxng, offline
    searxng_url: str = os.getenv("SEARXNG_URL", "http://localhost:8080")
    web_search_timeout_sec: float = 10.0
    max_external_results: int = 5
    allow_external_research: bool = True

    # Security & Prompt Injection Defense
    scrub_secrets: bool = True
    sanitize_external_documents: bool = True

    class Config:
        env_prefix = "TALKFLOW_RAG_"
        arbitrary_types_allowed = True


settings = RAGSettings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)

