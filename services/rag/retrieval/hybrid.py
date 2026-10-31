"""Hybrid Dense + Lexical Retrieval Engine with Reciprocal Rank Fusion & Reranking."""
from __future__ import annotations

import time
from typing import Optional
from rag.config import settings
from rag.embeddings.base import BaseEmbeddingEngine
from rag.embeddings.bge import BGEM3EmbeddingEngine
from rag.models import RetrievalQuery, RetrievalResponse, RetrievedPassage
from rag.reranker.base import BaseReranker
from rag.reranker.bge_reranker import BGERerankerV2M3, reciprocal_rank_fusion
from rag.retrieval.citation import CitationFormatter
from rag.storage.base import BaseRAGStorage
from rag.storage import get_rag_storage

COMMON_INDIC_CROSS_LINGUAL = {
    "फास्टर": "faster",
    "व्हिस्पर": "whisper",
    "स्पीच": "speech",
    "टेक्स्ट": "text",
    "मॉडल": "model",
    "बेस": "base",
    "ऑडियो": "audio",
    "अनुवाद": "translation",
    "भाषांतर": "translation",
    "गुणवत्ता": "quality",
    "सिंक": "sync",
    "डबिंग": "dubbing",
    "आवाज": "voice",
    "ध्वनि": "audio sound",
}


class HybridRetriever:
    """
    Coordinates multi-stage hybrid retrieval:
    Dense Vector Embedding + FTS5 BM25 Keyword Search
    -> Reciprocal Rank Fusion (RRF)
    -> BGE Cross-Encoder Reranking
    -> Citation & Injection-Shielded Context Assembly.
    """

    def __init__(
        self,
        storage: Optional[BaseRAGStorage] = None,
        embedder: Optional[BaseEmbeddingEngine] = None,
        reranker: Optional[BaseReranker] = None,
    ):
        self.storage = storage or get_rag_storage()
        self.embedder = embedder or BGEM3EmbeddingEngine()
        self.reranker = reranker or BGERerankerV2M3()
        self._cache = {}

    def retrieve(self, request: RetrievalQuery) -> RetrievalResponse:
        """Executes full hybrid search pipeline with latency tracking."""
        start_time = time.time()
        tenant_id = request.tenant_id or settings.default_tenant_id

        # 1. Dense retrieval (if alpha > 0.0)
        dense_results = []
        if request.alpha > 0.0:
            query_vec = self.embedder.embed_text(request.query)
            dense_results = self.storage.search_dense(
                query_vec=query_vec,
                top_k=request.dense_candidates,
                tenant_id=tenant_id,
                agent_scope=request.agent_scope,
                min_trust_tier=request.min_trust_tier,
            )

        # 2. Lexical BM25 retrieval (if alpha < 1.0)
        lexical_results = []
        if request.alpha < 1.0:
            lex_query = request.query
            expanded_terms = [v for k, v in COMMON_INDIC_CROSS_LINGUAL.items() if k in request.query]
            if expanded_terms:
                lex_query = f"{request.query} {' '.join(expanded_terms)}"

            lexical_results = self.storage.search_lexical(
                query=lex_query,
                top_k=request.lexical_candidates,
                tenant_id=tenant_id,
                agent_scope=request.agent_scope,
                min_trust_tier=request.min_trust_tier,
            )

        # 3. Reciprocal Rank Fusion
        fused_candidates = reciprocal_rank_fusion(
            dense_results=dense_results,
            lexical_results=lexical_results,
            k=settings.rrf_k,
            alpha=request.alpha,
        )

        total_candidates = len(fused_candidates)

        # 4. Cross-Encoder / BGE Reranker
        top_passages = self.reranker.rerank(
            query=request.query,
            candidates=fused_candidates,
            top_k=request.top_k,
        )

        # 5. Populate formatted citations
        for idx, p in enumerate(top_passages, start=1):
            p.citation = CitationFormatter.format_citation(p, idx)

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return RetrievalResponse(
            query=request.query,
            total_candidates_examined=total_candidates,
            passages=top_passages,
            latency_ms=latency_ms,
            tenant_id=tenant_id,
        )
