"""Common Research Tools for TalkFlow Autonomous Agents."""
from __future__ import annotations

import hashlib
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import httpx

from rag.config import settings
from rag.models import (
    AgentScope,
    DocumentChunk,
    ResearchEvidence,
    ResearchNote,
    RetrievalQuery,
    RetrievedPassage,
    TrustTier,
)
from rag.research.web_search import WebSearchProvider
from rag.retrieval.citation import CitationFormatter
from rag.retrieval.hybrid import HybridRetriever
from rag.security import SecuritySanitizer
from rag.storage import get_rag_storage


class ResearchTools:
    """Standardized toolsuite exposed to all 7 TalkFlow autonomous agents."""

    def __init__(self):
        self.storage = get_rag_storage()
        self.retriever = HybridRetriever(storage=self.storage)
        self.web_search = WebSearchProvider()
        self.root_dir = Path("I:/vioces agent")

    def search_internal_knowledge(
        self,
        query: str,
        namespace: Optional[AgentScope] = None,
        tenant_id: str = "talkflow_enterprise",
        limit: int = 5,
    ) -> List[RetrievedPassage]:
        """Searches indexed internal TalkFlow code, docs, schemas, and configurations."""
        req = RetrievalQuery(
            query=query,
            agent_scope=namespace,
            tenant_id=tenant_id,
            top_k=limit,
            alpha=0.5,
        )
        resp = self.retriever.retrieve(req)
        return resp.passages

    def search_repository(
        self,
        query: str,
        file_pattern: str = "*.py",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Directly scans repo files for matching symbols, function names, or terms."""
        matches = []
        q_lower = query.lower()

        target_dirs = [
            self.root_dir / "audio-intelligence-agent",
            self.root_dir / "speech-recognition-agent",
            self.root_dir / "language-intelligence-agent",
            self.root_dir / "neural-translation-agent",
            self.root_dir / "translation-quality-agent",
            self.root_dir / "voice-generation-agent",
            self.root_dir / "audio-delivery-agent",
            self.root_dir / "orchestrator",
            self.root_dir / "docs",
        ]

        for tdir in target_dirs:
            if not tdir.exists():
                continue
            for p in tdir.rglob(file_pattern):
                if any(ign in str(p) for ign in [".venv", "__pycache__", ".git", ".pytest_cache"]):
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    if q_lower in text.lower():
                        lines = text.splitlines()
                        matching_lines = [
                            (idx + 1, line.strip())
                            for idx, line in enumerate(lines)
                            if q_lower in line.lower()
                        ][:3]

                        rel_path = str(p.relative_to(self.root_dir)).replace("\\", "/")
                        matches.append({
                            "file_path": rel_path,
                            "matches": matching_lines,
                            "line_count": len(lines),
                        })
                        if len(matches) >= limit:
                            return matches
                except Exception:
                    continue

        return matches

    def search_external_web(
        self,
        query: str,
        agent_id: str = "agent_researcher",
        max_results: int = 5,
    ) -> List[ResearchEvidence]:
        """Searches external approved technical sources for specifications and benchmarks."""
        return self.web_search.search(query=query, max_results=max_results, agent_id=agent_id)

    def fetch_source(self, url: str) -> str:
        """Fetches raw text content from a source URL or local path."""
        if not url.startswith("http"):
            local_path = self.root_dir / url if not Path(url).is_absolute() else Path(url)
            if local_path.exists() and local_path.is_file():
                return local_path.read_text(encoding="utf-8", errors="ignore")
            return ""

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return SecuritySanitizer.scrub_secrets(res.text[:10000])
        except Exception:
            pass
        return ""

    def compare_sources(self, sources: List[ResearchEvidence]) -> Dict[str, Any]:
        """Compares multiple independent sources to evaluate consistency and version conflicts."""
        if not sources:
            return {"status": "no_sources", "consensus": "insufficient_data"}

        versions = [s.software_version for s in sources if s.software_version]
        trust_scores = [s.trust_tier.trust_score for s in sources]
        avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 0.5

        conflict_detected = len(set(versions)) > 1 if versions else False

        return {
            "source_count": len(sources),
            "average_trust_score": round(avg_trust, 2),
            "highest_trust_source": max(sources, key=lambda s: s.trust_tier.trust_score).source_url_or_path,
            "version_conflict_detected": conflict_detected,
            "detected_versions": list(set(versions)),
        }

    def validate_source(self, evidence: ResearchEvidence) -> Dict[str, Any]:
        """Validates that a source does not contain prompt injection and ranks its trust tier."""
        has_injection = "[FILTERED_POTENTIAL_PROMPT_INJECTION]" in SecuritySanitizer.sanitize_untrusted_content(evidence.relevant_passage)
        return {
            "source": evidence.source_url_or_path,
            "trust_tier": evidence.trust_tier.value,
            "is_trusted": evidence.trust_tier in (TrustTier.TIER_1_OFFICIAL, TrustTier.TIER_2_RESEARCH),
            "prompt_injection_detected": has_injection,
            "passed_validation": not has_injection and evidence.trust_tier.trust_score >= 0.50,
        }

    def save_verified_research(self, note: ResearchNote) -> None:
        """Persists verified research note in shared RAG store."""
        self.storage.save_research_note(note)

    def retrieve_agent_memory(
        self,
        query: str,
        tenant_id: str = "talkflow_enterprise",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieves long-term memory entries and verified findings for the agent."""
        results = self.storage.search_long_term_memory(
            query=query,
            query_vec=[],
            tenant_id=tenant_id,
            top_k=limit,
        )
        return [
            {
                "memory_id": item.memory_id,
                "title": item.title,
                "content": item.content,
                "citations": item.source_citations,
                "score": round(score, 3),
            }
            for item, score in results
        ]

    def cite_research_evidence(self, evidence_list: List[ResearchEvidence]) -> List[str]:
        """Constructs formal citations for collected evidence."""
        citations = []
        for idx, ev in enumerate(evidence_list, start=1):
            tier_str = ev.trust_tier.value.replace("_", " ").title()
            citations.append(f"[{idx}] {ev.source_title} ({ev.source_url_or_path}) — {tier_str}")
        return citations
