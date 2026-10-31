"""Pydantic schemas and data contracts for TalkFlow Shared RAG, Research & Memory."""
from __future__ import annotations

from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TrustTier(str, Enum):
    """Hierarchy of source trust for evidence and citations."""
    TIER_1_OFFICIAL = "tier_1_official"         # Official repo code, RFCs, official framework documentation, model cards
    TIER_2_RESEARCH = "tier_2_research"         # Peer-reviewed papers, arXiv publications, technical benchmarks
    TIER_3_REPUTABLE = "tier_3_reputable"       # Established engineering blogs, developer documentation
    TIER_4_COMMUNITY = "tier_4_community"       # Community forums, GitHub issues, discussions, unverified blog posts

    @property
    def trust_score(self) -> float:
        weights = {
            TrustTier.TIER_1_OFFICIAL: 1.0,
            TrustTier.TIER_2_RESEARCH: 0.85,
            TrustTier.TIER_3_REPUTABLE: 0.70,
            TrustTier.TIER_4_COMMUNITY: 0.50,
        }
        return weights.get(self, 0.5)


class SourceType(str, Enum):
    """Classification of ingested knowledge sources."""
    INTERNAL_CODE = "internal_code"
    INTERNAL_DOC = "internal_doc"
    EXTERNAL_DOC = "external_doc"
    RESEARCH_PAPER = "research_paper"
    LEARNING_DATA = "learning_data"
    USER_FEEDBACK = "user_feedback"


class AgentScope(str, Enum):
    """Explicit namespace and assigned research responsibility for each agent."""
    AGENT_01_AUDIO_INTEL = "agent_01_audio_intel"
    AGENT_02_SPEECH_RECOG = "agent_02_speech_recognition"
    AGENT_03_LANG_INTEL = "agent_03_language_intel"
    AGENT_04_NEURAL_MT = "agent_04_neural_translation"
    AGENT_05_QUALITY_GATE = "agent_05_quality_gate"
    AGENT_06_VOICE_GEN = "agent_06_voice_generation"
    AGENT_07_DELIVERY_SYNC = "agent_07_audio_delivery"
    SHARED_PIPELINE = "shared_pipeline"
    GLOBAL = "global"


class DocumentChunk(BaseModel):
    """A semantic chunk of code or documentation indexed in the RAG store."""
    chunk_id: str
    document_id: str
    tenant_id: str = "talkflow_enterprise"
    org_id: str = "org_talkflow"
    agent_scope: AgentScope = AgentScope.SHARED_PIPELINE
    source_type: SourceType = SourceType.INTERNAL_DOC
    source_path_or_url: str
    title: str
    content: str
    token_count: int = 0
    trust_tier: TrustTier = TrustTier.TIER_1_OFFICIAL
    software_version: Optional[str] = None
    checksum: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: float = Field(default_factory=time.time)


class DocumentRecord(BaseModel):
    """High-level document record tracking file checksum and indexing timestamp."""
    document_id: str
    tenant_id: str
    org_id: str
    title: str
    source_path_or_url: str
    source_type: SourceType
    trust_tier: TrustTier
    checksum: str
    chunk_count: int
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class RetrievalQuery(BaseModel):
    """Structured query contract for hybrid dense + lexical search."""
    query: str
    agent_id: Optional[str] = None
    agent_scope: Optional[AgentScope] = None
    tenant_id: str = "talkflow_enterprise"
    org_id: str = "org_talkflow"
    top_k: int = 6
    dense_candidates: int = 25
    lexical_candidates: int = 25
    alpha: float = 0.5  # 1.0 = dense only, 0.0 = BM25 only, 0.5 = balanced hybrid
    min_trust_tier: Optional[TrustTier] = None
    filter_metadata: Dict[str, Any] = Field(default_factory=dict)
    include_external: bool = True


class RetrievedPassage(BaseModel):
    """A single retrieved passage with fusion scoring and citation details."""
    chunk_id: str
    document_id: str
    title: str
    source_path_or_url: str
    source_type: SourceType
    trust_tier: TrustTier
    agent_scope: AgentScope
    content: str
    dense_score: float = 0.0
    lexical_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    citation: str = ""


class RetrievalResponse(BaseModel):
    """Full hybrid retrieval response with execution latency and citations."""
    query: str
    total_candidates_examined: int
    passages: List[RetrievedPassage]
    latency_ms: float
    tenant_id: str


class ResearchEvidence(BaseModel):
    """Evidence item collected during autonomous research."""
    evidence_id: str
    source_url_or_path: str
    source_title: str
    trust_tier: TrustTier
    software_version: Optional[str] = None
    published_date: Optional[str] = None
    relevant_passage: str
    extracted_finding: str
    confidence: float = 0.90
    agent_that_used_it: str


class ResearchNote(BaseModel):
    """Evidence-based research synthesis produced by an agent."""
    research_id: str
    agent_id: str
    agent_scope: AgentScope
    tenant_id: str
    task_description: str
    queries_executed: List[str]
    evidence_items: List[ResearchEvidence]
    synthesized_finding: str
    citations: List[str]
    unresolved_questions: List[str] = Field(default_factory=list)
    verified: bool = True
    created_at: float = Field(default_factory=time.time)


class ShortTermMemoryItem(BaseModel):
    """Active in-flight context and chunk state for a processing job."""
    job_id: str
    agent_id: str
    tenant_id: str
    stage: str
    chunk_states: Dict[str, Any] = Field(default_factory=dict)
    intermediate_outputs: Dict[str, Any] = Field(default_factory=dict)
    active_errors: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class LongTermMemoryItem(BaseModel):
    """Persistent verified technical knowledge, model benchmark or configuration."""
    memory_id: str
    tenant_id: str
    org_id: str
    agent_scope: AgentScope
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    source_citations: List[str] = Field(default_factory=list)
    verified_by_user: bool = False
    embedding: Optional[List[float]] = None
    created_at: float = Field(default_factory=time.time)


class TranslationMemoryEntry(BaseModel):
    """High-precision approved translation pair for instant zero-latency retrieval."""
    entry_id: str
    tenant_id: str
    org_id: str
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    domain: str = "general"
    glossary_terms: Dict[str, str] = Field(default_factory=dict)
    quality_score: float = 1.0
    user_approved: bool = True
    usage_count: int = 1
    created_at: float = Field(default_factory=time.time)

