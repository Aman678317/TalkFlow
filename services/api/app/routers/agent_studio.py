"""Agent Studio Router — Interactive Multi-Agent Systems Integration.

Exposes REST endpoints to trigger and visualize the 3 Multi-Agent architectures:
1. Research Assistant Crew (CrewAI Hub & Spoke)
2. Customer Support Triage Graph (LangGraph State Machine)
3. Autonomous Content Pipeline (LangGraph + CrewAI Hybrid Loop)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_org_user

log = logging.getLogger("app.routers.agent_studio")

# Phase 3: every Agent Studio endpoint requires an authenticated org user —
# previously all routes (including bridge.py subprocess execution) were anonymous.
router = APIRouter(prefix="/api/v1/agent-studio", tags=["agent-studio"],
                   dependencies=[Depends(require_org_user)])

# Paths to multi-agent portfolio
def _find_portfolio_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "multi_agent_portfolio",
        Path(__file__).resolve().parent.parent.parent / "multi-agent-portfolio",
        Path(__file__).resolve().parent / "multi_agent_portfolio",
    ]
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        candidates.append(curr / "multi_agent_portfolio")
        candidates.append(curr / "multi-agent-portfolio")
        curr = curr.parent

    for cand in candidates:
        if cand.exists() and (cand / "bridge.py").exists():
            return cand
    return Path(__file__).resolve().parent

_PORTFOLIO_ROOT = _find_portfolio_root()
_BRIDGE_SCRIPT = _PORTFOLIO_ROOT / "bridge.py"

# Preferred python interpreter in dedicated venv
if os.name == "nt":
    _VENV_PYTHON = _PORTFOLIO_ROOT / ".venv" / "Scripts" / "python.exe"
else:
    _VENV_PYTHON = _PORTFOLIO_ROOT / ".venv" / "bin" / "python"

if not _VENV_PYTHON.exists():
    _PYTHON_BIN = sys.executable
else:
    _PYTHON_BIN = str(_VENV_PYTHON)


def _exec_bridge_sync(cmd: List[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def _fallback_triage(ticket: str) -> Dict[str, Any]:
    """The in-process fallback classifier.

    HONEST CONTRACT (issue #109 class 3, day-2 finding B-2): a heuristic
    guess is labelled as one. It does not claim a confidence it did not
    measure, and the customer-facing reply is a DRAFT — it promises no
    refund that never happened.
    """
    lower = ticket.lower()
    angry_words = ["unacceptable", "scam", "ridiculous", "human", "angry", "terrible", "worst", "fraud"]
    is_angry = any(w in lower for w in angry_words)
    sentiment = "angry" if is_angry else "neutral"

    if any(w in lower for w in ["charge", "refund", "bill", "subscription", "payment", "ord_"]):
        category = "billing"
        route = "billing"
        escalated = is_angry
        response = (f"Your billing inquiry regarding order '{ticket}' has been recorded "
                    f"and a refund review has been queued for our billing team. You will "
                    f"hear back once the review is complete.") if not is_angry else None
        escalation_reason = "Customer expressed high dissatisfaction regarding billing" if is_angry else None
    elif any(w in lower for w in ["error", "bug", "crash", "failed", "broken", "500"]):
        category = "technical"
        route = "engineering"
        escalated = is_angry
        response = "We have recorded the technical issue and our engineering team is reviewing it." if not is_angry else None
        escalation_reason = "Urgent technical failure requiring immediate human review" if is_angry else None
    else:
        category = "general"
        route = "general_support"
        escalated = is_angry
        response = "Thank you for reaching out. We have recorded your inquiry and a support specialist will follow up." if not is_angry else None
        escalation_reason = "Customer requested human escalation" if is_angry else None

    return {
        "ticket": ticket,
        "category": category,
        # A keyword heuristic: the confidence is NOT measured, so it is not
        # dressed up as 0.94.
        "confidence": 0.5,
        "reasoning": (f"Heuristic classifier parsed intent as {category}. "
                      f"This is a keyword guess, not a verified classification."),
        "route": route,
        "sentiment": sentiment,
        "response": response,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
        "source": "fallback",
        "response_is_draft": True,
    }


def _fallback_research(topic: str) -> Dict[str, Any]:
    """The placeholder report shown when the research crew cannot run.

    It is NOT a research result: nothing was researched, nothing was
    verified, and no agent ran. The previous version claimed
    ``"verified": True`` and a roster of "completed" agents — a fabricated
    result presented as real (issue #109 class 3, day-2 finding B-2).
    """
    return {
        "topic": topic,
        "mode": "unavailable",
        "agents": [
            {"role": "Lead Researcher", "model": "gpt-4o", "status": "unavailable"},
            {"role": "Domain Specialist", "model": "claude-3-5-sonnet", "status": "unavailable"},
            {"role": "Fact Checker & Synthesizer", "model": "gemini-1.5-pro", "status": "unavailable"},
        ],
        "report": (
            f"# Research unavailable\n\nThe research crew could not run for "
            f"\"{topic}\" in this environment, so no research was performed and "
            f"nothing here is verified. This is a placeholder, not a report."
        ),
        "verified": False,
        "note": ("The research crew was unavailable — no sources were gathered and "
                 "nothing was verified."),
    }


def _fallback_content(topic: str) -> Dict[str, Any]:
    """The placeholder shown when the content pipeline cannot run.

    The previous version claimed a 9.2/10 quality score, a fake critique
    history, a publication path and a "published" status for a document that
    was never written (issue #109 class 3, day-2 finding B-2).
    """
    return {
        "topic": topic,
        "research": "",
        "draft": "",
        "score": None,
        "feedback": [],
        "loops": 0,
        "final_content": None,
        "published_path": None,
        "status": "not_published",
        "note": ("The content pipeline was unavailable — nothing was drafted, "
                 "scored or published."),
    }


async def _run_bridge(action: str, input_text: str = "") -> Dict[str, Any]:
    """Execute bridge.py or fallback gracefully in constrained serverless environments."""
    root = _find_portfolio_root()
    bridge_script = root / "bridge.py"

    if bridge_script.exists():
        cmd = [_PYTHON_BIN, str(bridge_script), "--action", action]
        if input_text:
            cmd.extend(["--input", input_text])

        try:
            proc = await asyncio.to_thread(_exec_bridge_sync, cmd, str(root))
            raw_output = proc.stdout
            err_output = proc.stderr

            if "__JSON_START__" in raw_output and "__JSON_END__" in raw_output:
                json_part = raw_output.split("__JSON_START__")[1].split("__JSON_END__")[0].strip()
                return json.loads(json_part)

            if proc.returncode == 0 and raw_output.strip():
                return json.loads(raw_output.strip())

            log.warning("Bridge returned code %s, trying in-process / fallback", proc.returncode)
        except Exception as exc:
            log.warning("Subprocess bridge failed (%s), falling back to in-process execution", exc)

    # Serverless fallback handlers
    if action == "triage":
        return _fallback_triage(input_text or "General support ticket")
    elif action in ("research", "research-crew"):
        return _fallback_research(input_text or "State of agentic AI, 2026")
    elif action in ("content", "content-pipeline"):
        return _fallback_content(input_text or "Why agentic AI needs typed tool calls")

    raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")



# --- Request & Response Schemas ---

class TriageRequest(BaseModel):
    ticket: str = Field(
        default="I was charged twice this month for my subscription order ord_101. Please refund me.",
        description="Raw customer inquiry or support ticket"
    )

class TriageResponse(BaseModel):
    ticket: str
    category: str
    confidence: float
    reasoning: str
    route: str
    sentiment: str
    response: Optional[str]
    escalated: bool
    escalation_reason: Optional[str]
    #: "bridge" (the real agent ran) or "fallback" (the in-process heuristic)
    source: str = "bridge"
    #: the reply is a draft for a human to send, not a sent message
    response_is_draft: bool = False

class ContentPipelineRequest(BaseModel):
    topic: str = Field(
        default="Why agentic AI needs typed tool calls",
        description="Content brief or technical topic"
    )

class ContentPipelineResponse(BaseModel):
    topic: str
    research: str
    draft: str
    #: None when nothing was scored — the pipeline never ran
    score: Optional[float] = None
    feedback: List[str]
    loops: int
    final_content: Optional[str]
    #: the path of a file that actually exists, or None
    published_path: Optional[str] = None
    status: str
    #: the honest reason, when the pipeline could not run
    note: Optional[str] = None

class ResearchCrewRequest(BaseModel):
    topic: str = Field(
        default="State of agentic AI, 2026",
        description="Research topic for multi-agent delegation"
    )

class ResearchCrewResponse(BaseModel):
    topic: str
    mode: str
    agents: List[Dict[str, Any]]
    report: str
    #: True only when a real crew verified the report
    verified: bool = False
    note: Optional[str] = None


# --- Endpoints ---

@router.get("/status")
async def get_studio_status():
    """Retrieve health and metadata of all 3 Multi-Agent Systems.

    The status reports whether the agent bridge can actually run here — the
    previous version always answered "ready" even when the portfolio was
    absent and every request silently fell back to the placeholder
    (issue #109 class 3, day-2 finding B-2).
    """
    root = _find_portfolio_root()
    bridge_script = root / "bridge.py"
    return {
        "status": "ready" if bridge_script.exists() else "unavailable",
        "bridge_available": bridge_script.exists(),
        "note": None if bridge_script.exists() else (
            "The multi-agent bridge is not present in this deployment, so the "
            "studio answers with honest placeholders instead of results."),
        "systems": [
            {
                "id": "system-01",
                "name": "Research Assistant Crew",
                "framework": "CrewAI",
                "architecture": "Hub & Spoke Delegation",
                "agents": [
                    "Senior Research Librarian",
                    "Critical Research Analyst",
                    "Technical Report Writer",
                    "Independent Fact-Checker",
                ],
                "description": "Delegates web discovery, claims extraction, and synthesis across 4 specialized personas."
            },
            {
                "id": "system-02",
                "name": "Customer Support Triage Graph",
                "framework": "LangGraph",
                "architecture": "Conditional State Machine",
                "nodes": ["Classifier", "Billing Specialist", "Tech Support Specialist", "Human Escalation Queue"],
                "description": "Classifies intent, sentiment, routes deterministically, and escalates to human on low confidence."
            },
            {
                "id": "system-03",
                "name": "Autonomous Content Pipeline",
                "framework": "LangGraph + CrewAI Hybrid",
                "architecture": "Self-Correcting Feedback Loop",
                "nodes": ["CrewAI Sub-Crew", "Draft Node", "Critique Node", "Quality Gate", "Publish Node"],
                "description": "Drafts from research, critiques against strict rubrics, and iterates until passing >= 0.8 quality threshold."
            }
        ]
    }


@router.post("/triage", response_model=TriageResponse)
async def triage_ticket(body: TriageRequest):
    """Run System 02: Customer Support Triage Graph."""
    data = await _run_bridge("triage", body.ticket)
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data


@router.post("/content-pipeline", response_model=ContentPipelineResponse)
async def run_content_pipeline_endpoint(body: ContentPipelineRequest):
    """Run System 03: Autonomous Content Pipeline."""
    data = await _run_bridge("content-pipeline", body.topic)
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data


@router.post("/research-crew", response_model=ResearchCrewResponse)
async def run_research_crew_endpoint(body: ResearchCrewRequest):
    """Run System 01: Research Assistant Crew."""
    data = await _run_bridge("research-crew", body.topic)
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data
