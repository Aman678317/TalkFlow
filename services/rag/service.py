"""FastAPI HTTP REST endpoints for TalkFlow Shared RAG, Research & Memory."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from rag.config import settings
from rag.ingestion.indexer import TalkFlowIndexer
from rag.memory.long_term import LongTermMemoryManager
from rag.memory.short_term import ShortTermMemoryManager
from rag.memory.translation_memory import TranslationMemoryManager
from rag.models import (
    AgentScope,
    ResearchNote,
    RetrievalQuery,
    RetrievalResponse,
    TranslationMemoryEntry,
    TrustTier,
)
from rag.research.engine import AutonomousResearchEngine
from rag.retrieval.hybrid import HybridRetriever
from rag.storage import get_rag_storage

router = APIRouter(tags=["RAG, Autonomous Research & Long-Term Memory"])

storage = get_rag_storage()
retriever = HybridRetriever(storage=storage)
indexer = TalkFlowIndexer(storage=storage)
research_engine = AutonomousResearchEngine()
ltm = LongTermMemoryManager(storage=storage)
stm = ShortTermMemoryManager(storage=storage)
tm = TranslationMemoryManager(storage=storage)


# --- Request/Response Schemas ---

class SearchRequest(BaseModel):
    query: str
    agent_id: Optional[str] = None
    namespace: Optional[AgentScope] = None
    tenant_id: str = "talkflow_enterprise"
    top_k: int = 6
    alpha: float = 0.5
    min_trust_tier: Optional[TrustTier] = None


class IngestRequest(BaseModel):
    tenant_id: str = "talkflow_enterprise"
    org_id: str = "org_talkflow"
    force_reindex: bool = False
    include_seed_knowledge: bool = True


class ResearchRunRequest(BaseModel):
    agent_id: str
    task_description: str
    tenant_id: str = "talkflow_enterprise"
    force_external: bool = False


class MemorySearchRequest(BaseModel):
    query: str
    tenant_id: str = "talkflow_enterprise"
    top_k: int = 5


class TranslationLookupRequest(BaseModel):
    source_text: str
    source_lang: str
    target_lang: str
    tenant_id: str = "talkflow_enterprise"


class TranslationSaveRequest(BaseModel):
    source_text: str
    source_lang: str
    target_text: str
    target_lang: str
    domain: str = "general"
    glossary_terms: Dict[str, str] = Field(default_factory=dict)
    tenant_id: str = "talkflow_enterprise"
    org_id: str = "org_talkflow"
    user_approved: bool = True


# --- Endpoints ---

@router.post("/api/v1/rag/search", response_model=RetrievalResponse)
@router.post("/api/rag/search", response_model=RetrievalResponse)
async def search_rag(req: SearchRequest):
    """Executes hybrid dense vector + BM25 keyword search with BGE reranking."""
    query = RetrievalQuery(
        query=req.query,
        agent_id=req.agent_id,
        agent_scope=req.namespace,
        tenant_id=req.tenant_id,
        top_k=req.top_k,
        alpha=req.alpha,
        min_trust_tier=req.min_trust_tier,
    )
    return retriever.retrieve(query)


@router.post("/api/v1/rag/ingest")
@router.post("/api/rag/ingest")
async def trigger_ingestion(req: IngestRequest):
    """Incrementally indexes internal codebase, documentation, and external knowledge."""
    indexed_docs, total_chunks = indexer.index_codebase(
        tenant_id=req.tenant_id,
        org_id=req.org_id,
        force=req.force_reindex,
    )

    seed_chunks = 0
    if req.include_seed_knowledge:
        seed_chunks = indexer.ingest_seed_external_knowledge(
            tenant_id=req.tenant_id,
            org_id=req.org_id,
        )

    return {
        "status": "success",
        "tenant_id": req.tenant_id,
        "indexed_documents": indexed_docs,
        "code_chunks": total_chunks,
        "seed_knowledge_chunks": seed_chunks,
        "total_new_chunks": total_chunks + seed_chunks,
    }


@router.post("/api/v1/research/run", response_model=ResearchNote)
@router.post("/api/research/run", response_model=ResearchNote)
async def run_autonomous_research(req: ResearchRunRequest):
    """Executes the 13-step autonomous research procedure for an assigned agent task."""
    try:
        note = research_engine.run_research(
            agent_id=req.agent_id,
            task_description=req.task_description,
            tenant_id=req.tenant_id,
            force_external=req.force_external,
        )
        return note
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research procedure failed: {str(e)}")


@router.get("/api/v1/research/{research_id}", response_model=ResearchNote)
@router.get("/api/research/{research_id}", response_model=ResearchNote)
async def get_research_result(
    research_id: str,
    tenant_id: str = Query("talkflow_enterprise")
):
    """Retrieves an existing verified research note by ID."""
    note = storage.get_research_note(research_id, tenant_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Research note '{research_id}' not found.")
    return note


@router.post("/api/v1/agents/{agent_id}/memory/search")
@router.post("/api/agents/{agent_id}/memory/search")
async def search_agent_memory(agent_id: str, req: MemorySearchRequest):
    """Searches long-term knowledge memory for an agent."""
    results = ltm.search_knowledge(
        query=req.query,
        tenant_id=req.tenant_id,
        top_k=req.top_k,
    )
    return {
        "agent_id": agent_id,
        "query": req.query,
        "matches": [
            {
                "memory_id": item.memory_id,
                "title": item.title,
                "content": item.content,
                "tags": item.tags,
                "citations": item.source_citations,
                "score": round(score, 3),
            }
            for item, score in results
        ]
    }


@router.post("/api/v1/memory/translation/lookup")
async def lookup_translation(req: TranslationLookupRequest):
    """Checks Translation Memory for verified existing translations."""
    entry = tm.lookup(
        source_text=req.source_text,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        tenant_id=req.tenant_id,
    )
    if not entry:
        return {"found": False, "entry": None}
    return {"found": True, "entry": entry.model_dump()}


@router.post("/api/v1/memory/translation/save")
async def save_translation(req: TranslationSaveRequest):
    """Saves user-approved translation pair into Translation Memory."""
    entry = tm.record_approved_translation(
        source_text=req.source_text,
        source_lang=req.source_lang,
        target_text=req.target_text,
        target_lang=req.target_lang,
        domain=req.domain,
        glossary_terms=req.glossary_terms,
        tenant_id=req.tenant_id,
        org_id=req.org_id,
        user_approved=req.user_approved,
    )
    return {"status": "saved", "entry": entry.model_dump()}


@router.get("/api/v1/rag/stats")
async def get_rag_stats(tenant_id: str = Query("talkflow_enterprise")):
    """Returns RAG index metrics, chunk counts, and memory statistics."""
    conn = storage._get_connection()
    doc_count = conn.execute("SELECT count(*) FROM rag_documents WHERE tenant_id = ?", (tenant_id,)).fetchone()[0]
    chunk_count = conn.execute("SELECT count(*) FROM rag_chunks WHERE tenant_id = ?", (tenant_id,)).fetchone()[0]
    res_count = conn.execute("SELECT count(*) FROM rag_research_notes WHERE tenant_id = ?", (tenant_id,)).fetchone()[0]
    tm_count = conn.execute("SELECT count(*) FROM rag_translation_memory WHERE tenant_id = ?", (tenant_id,)).fetchone()[0]
    ltm_count = conn.execute("SELECT count(*) FROM rag_long_term_memory WHERE tenant_id = ?", (tenant_id,)).fetchone()[0]

    return {
        "tenant_id": tenant_id,
        "indexed_documents": doc_count,
        "indexed_chunks": chunk_count,
        "research_notes": res_count,
        "translation_memory_entries": tm_count,
        "long_term_memories": ltm_count,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
    }

