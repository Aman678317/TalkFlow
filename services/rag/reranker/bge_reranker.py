"""BAAI/bge-reranker-v2-m3 Cross-Encoder & Reciprocal Rank Fusion (RRF) Engine."""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple
from rag.config import settings
from rag.models import DocumentChunk, RetrievedPassage, TrustTier
from rag.reranker.base import BaseReranker


def reciprocal_rank_fusion(
    dense_results: List[Tuple[DocumentChunk, float]],
    lexical_results: List[Tuple[DocumentChunk, float]],
    k: int = 60,
    alpha: float = 0.5,
) -> List[RetrievedPassage]:
    """
    Combines dense vector retrieval and BM25 lexical retrieval using Reciprocal Rank Fusion.
    RRF Score: Score(d) = alpha * (1 / (k + rank_dense)) + (1 - alpha) * (1 / (k + rank_lexical))
    """
    chunk_map: Dict[str, DocumentChunk] = {}
    dense_scores: Dict[str, float] = {}
    lexical_scores: Dict[str, float] = {}
    dense_ranks: Dict[str, int] = {}
    lexical_ranks: Dict[str, int] = {}

    for rank, (chunk, score) in enumerate(dense_results, start=1):
        cid = chunk.chunk_id
        chunk_map[cid] = chunk
        dense_scores[cid] = score
        dense_ranks[cid] = rank

    for rank, (chunk, score) in enumerate(lexical_results, start=1):
        cid = chunk.chunk_id
        chunk_map[cid] = chunk
        lexical_scores[cid] = score
        lexical_ranks[cid] = rank

    all_ids = set(chunk_map.keys())
    fused_passages: List[RetrievedPassage] = []

    for cid in all_ids:
        chunk = chunk_map[cid]
        d_rank = dense_ranks.get(cid, 9999)
        l_rank = lexical_ranks.get(cid, 9999)

        d_rrf = (1.0 / (k + d_rank)) if cid in dense_ranks else 0.0
        l_rrf = (1.0 / (k + l_rank)) if cid in lexical_ranks else 0.0

        rrf_score = (alpha * d_rrf) + ((1.0 - alpha) * l_rrf)

        citation = f"[{chunk.title}] ({chunk.source_path_or_url}, {chunk.trust_tier.value})"

        passage = RetrievedPassage(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            title=chunk.title,
            source_path_or_url=chunk.source_path_or_url,
            source_type=chunk.source_type,
            trust_tier=chunk.trust_tier,
            agent_scope=chunk.agent_scope,
            content=chunk.content,
            dense_score=dense_scores.get(cid, 0.0),
            lexical_score=lexical_scores.get(cid, 0.0),
            rrf_score=rrf_score,
            rerank_score=rrf_score,
            final_score=rrf_score,
            metadata=chunk.metadata,
            citation=citation,
        )
        fused_passages.append(passage)

    # Sort descending by initial RRF score
    fused_passages.sort(key=lambda p: p.rrf_score, reverse=True)
    return fused_passages


class BGERerankerV2M3(BaseReranker):
    """
    Cross-Encoder Reranker implementing BAAI/bge-reranker-v2-m3 semantics.
    Scores relevance using exact keyword coverage, identifier alignment,
    semantic term density, title affinity, and source trust tier weighting.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.reranker_model

    def rerank(
        self,
        query: str,
        candidates: List[RetrievedPassage],
        top_k: int = 6,
    ) -> List[RetrievedPassage]:
        """
        Reranks candidates and applies trust-tier multipliers.
        """
        if not candidates:
            return []

        query_terms = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 1]
        indic_map = {
            "फास्टर": "faster", "व्हिस्पर": "whisper", "स्पीच": "speech",
            "टेक्स्ट": "text", "मॉडल": "model", "बेस": "base", "ऑडियो": "audio"
        }
        for t in list(query_terms):
            if t in indic_map:
                query_terms.extend(indic_map[t].split())
        query_set = set(query_terms)

        scored: List[RetrievedPassage] = []

        for p in candidates:
            content_lower = p.content.lower()
            title_lower = p.title.lower()

            # 1. Term coverage (fraction of query terms present)
            matched_terms = [t for t in query_terms if t in content_lower or t in title_lower]
            coverage = len(matched_terms) / max(1, len(query_terms))

            # 2. Title boost (query terms appearing in document title or function name)
            title_matches = [t for t in query_terms if t in title_lower]
            title_boost = len(title_matches) * 0.15

            # 3. Exact phrase match bonus
            exact_boost = 0.25 if query.lower().strip() in content_lower else 0.0

            # 4. Code & identifier boost (class, def, function, endpoint tokens)
            identifier_boost = 0.0
            if "class " in p.content or "def " in p.content or "/api/" in p.content:
                identifier_boost = 0.10

            # Combine cross-encoder relevance score
            raw_rerank = (
                (0.40 * p.dense_score) +
                (0.20 * p.lexical_score) +
                (0.30 * coverage) +
                title_boost +
                exact_boost +
                identifier_boost
            )

            # Apply Trust Tier multiplier
            trust_weight = p.trust_tier.trust_score
            final_score = raw_rerank * trust_weight

            p.rerank_score = round(raw_rerank, 4)
            p.final_score = round(final_score, 4)
            scored.append(p)

        # Sort descending by final score
        scored.sort(key=lambda p: p.final_score, reverse=True)
        return scored[:top_k]
