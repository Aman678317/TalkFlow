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
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("app.routers.agent_studio")

router = APIRouter(prefix="/api/v1/agent-studio", tags=["agent-studio"])

# Paths to multi-agent portfolio
curr = Path(__file__).resolve()
_PORTFOLIO_ROOT = curr.parent
while curr != curr.parent:
    if (curr / "multi-agent-portfolio").exists():
        _PORTFOLIO_ROOT = curr / "multi-agent-portfolio"
        break
    curr = curr.parent

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


async def _run_bridge(action: str, input_text: str = "") -> Dict[str, Any]:
    """Execute bridge.py asynchronously and parse delimited JSON output."""
    cmd = [_PYTHON_BIN, str(_BRIDGE_SCRIPT), "--action", action]
    if input_text:
        cmd.extend(["--input", input_text])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_PORTFOLIO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        raw_output = stdout.decode("utf-8", errors="replace")
        err_output = stderr.decode("utf-8", errors="replace")

        if "__JSON_START__" in raw_output and "__JSON_END__" in raw_output:
            json_part = raw_output.split("__JSON_START__")[1].split("__JSON_END__")[0].strip()
            return json.loads(json_part)

        if proc.returncode != 0:
            log.error("Bridge exited with code %s: %s | %s", proc.returncode, raw_output, err_output)
            raise HTTPException(status_code=500, detail=f"Bridge error: {err_output or raw_output}")

        return json.loads(raw_output.strip())
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to execute agent bridge: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Agent bridge execution failed: {str(exc)}"
        )


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

class ContentPipelineRequest(BaseModel):
    topic: str = Field(
        default="Why agentic AI needs typed tool calls",
        description="Content brief or technical topic"
    )

class ContentPipelineResponse(BaseModel):
    topic: str
    research: str
    draft: str
    score: float
    feedback: List[str]
    loops: int
    final_content: Optional[str]
    published_path: Optional[str]
    status: str

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
    verified: bool


# --- Endpoints ---

@router.get("/status")
async def get_studio_status():
    """Retrieve health and metadata of all 3 Multi-Agent Systems."""
    return {
        "status": "ready",
        "interpreter": _PYTHON_BIN,
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
