"""Autonomous 13-Step Research Engine for TalkFlow Multi-Agent Pipeline."""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional
from rag.config import settings
from rag.models import (
    AgentScope,
    ResearchEvidence,
    ResearchNote,
    TrustTier,
)
from rag.research.scopes import AGENT_RESEARCH_TOPICS
from rag.research.tools import ResearchTools
from rag.storage import get_rag_storage


class AutonomousResearchEngine:
    """
    Executes the 13-step evidence-based research procedure.
    Enforces that agents never hallucinate sources or benchmark numbers.
    """

    def __init__(self, tools: Optional[ResearchTools] = None):
        self.tools = tools or ResearchTools()
        self.storage = get_rag_storage()

    def run_research(
        self,
        agent_id: str,
        task_description: str,
        tenant_id: str = "talkflow_enterprise",
        force_external: bool = False,
    ) -> ResearchNote:
        """
        Executes the 13-step autonomous research workflow for an assigned agent task.
        """
        start_time = time.time()
        agent_cfg = AGENT_RESEARCH_TOPICS.get(agent_id, {
            "scope": AgentScope.SHARED_PIPELINE,
            "title": f"Agent {agent_id}",
            "topics": []
        })
        scope = agent_cfg["scope"]

        queries_executed: List[str] = []
        collected_evidence: List[ResearchEvidence] = []
        unresolved: List[str] = []

        # STEP 1: Understand the assigned task
        clean_task = task_description.strip()
        queries_executed.append(clean_task)

        # STEP 2: Determine what knowledge is missing (generate focused query variants)
        query_variants = [clean_task]
        for topic in agent_cfg.get("topics", [])[:2]:
            if any(term in clean_task.lower() for term in topic.split()):
                query_variants.append(f"{clean_task} {topic}")

        # STEP 3: Search the internal knowledge base
        for q in query_variants:
            passages = self.tools.search_internal_knowledge(
                query=q,
                namespace=scope,
                tenant_id=tenant_id,
                limit=3,
            )
            for p in passages:
                # Discard low-confidence semantic noise when query keywords are absent
                if p.final_score < 0.35 and p.dense_score < 0.40 and p.lexical_score == 0.0:
                    continue

                collected_evidence.append(ResearchEvidence(
                    evidence_id=f"ev_int_{p.chunk_id}",
                    source_url_or_path=p.source_path_or_url,
                    source_title=p.title,
                    trust_tier=p.trust_tier,
                    software_version=p.metadata.get("version"),
                    relevant_passage=p.content[:400],
                    extracted_finding=f"Internal TalkFlow implementation ({p.title}) specifies: {p.content[:180]}...",
                    confidence=0.95,
                    agent_that_used_it=agent_id,
                ))

        # STEP 4: Inspect relevant repository code and implementation
        repo_matches = self.tools.search_repository(query=clean_task, limit=2)
        for rm in repo_matches:
            evidence_text = f"Found in {rm['file_path']} (L{rm['matches'][0][0]}): {rm['matches'][0][1]}" if rm['matches'] else ""
            if evidence_text:
                collected_evidence.append(ResearchEvidence(
                    evidence_id=f"ev_repo_{hashlib.md5(rm['file_path'].encode()).hexdigest()[:6]}",
                    source_url_or_path=rm["file_path"],
                    source_title=f"Source Code: {rm['file_path']}",
                    trust_tier=TrustTier.TIER_1_OFFICIAL,
                    relevant_passage=evidence_text,
                    extracted_finding=evidence_text,
                    confidence=0.98,
                    agent_that_used_it=agent_id,
                ))

        # STEP 5: Search approved external technical sources if internal knowledge is sparse or external forced
        if len(collected_evidence) < 2 or force_external:
            ext_results = self.tools.search_external_web(
                query=clean_task,
                agent_id=agent_id,
                max_results=3,
            )
            collected_evidence.extend(ext_results)

        # STEP 6: Validate sources & filter prompt injections & verify topic relevance
        valid_evidence: List[ResearchEvidence] = []
        task_terms = [w.lower() for w in clean_task.split() if len(w) > 3]

        for ev in collected_evidence:
            val = self.tools.validate_source(ev)
            if not val["passed_validation"]:
                continue

            # Ensure evidence actually relates to the task (prevents accepting irrelevant web noise)
            passage_lower = ev.relevant_passage.lower() + " " + ev.source_title.lower()
            if task_terms and not any(term in passage_lower for term in task_terms):
                continue

            valid_evidence.append(ev)

        # STEP 7 & 8: Compare findings and detect version conflicts
        comparison = self.tools.compare_sources(valid_evidence)
        version_notes = ""
        if comparison.get("version_conflict_detected"):
            version_notes = f" Warning: multiple versions detected: {comparison['detected_versions']}."

        # STEP 9: Rerank the evidence by trust tier and relevance
        valid_evidence.sort(key=lambda e: e.trust_tier.trust_score, reverse=True)

        # STEP 10: Create evidence-based research note
        if not valid_evidence:
            synthesized_finding = f"Insufficient authoritative evidence found to verify resolution for '{clean_task}'."
            unresolved.append(f"No Tier 1 or Tier 2 verification available for '{clean_task}'")
        else:
            top_sources_str = ", ".join([e.source_title for e in valid_evidence[:3]])
            findings_summary = " ".join([e.extracted_finding for e in valid_evidence[:2]])
            synthesized_finding = (
                f"Verified based on {top_sources_str}. Key engineering evidence: {findings_summary}{version_notes}"
            )

        citations = self.tools.cite_research_evidence(valid_evidence[:5])

        # STEP 11 & 12: Construct note & save verified findings
        research_id = f"res_{agent_id}_{int(time.time())}"
        note = ResearchNote(
            research_id=research_id,
            agent_id=agent_id,
            agent_scope=scope,
            tenant_id=tenant_id,
            task_description=clean_task,
            queries_executed=queries_executed,
            evidence_items=valid_evidence[:5],
            synthesized_finding=synthesized_finding,
            citations=citations,
            unresolved_questions=unresolved,
            verified=len(valid_evidence) > 0,
            created_at=time.time(),
        )

        # Save to storage (Step 12)
        self.tools.save_verified_research(note)

        # STEP 13: Pass findings and source references to agent context
        return note
