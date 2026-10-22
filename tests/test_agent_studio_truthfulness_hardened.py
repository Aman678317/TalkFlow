"""The Agent Studio must not present placeholders as real results.

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding B-2):

``app/routers/agent_studio.py`` runs a real multi-agent bridge when the
portfolio is present, and falls back to in-process placeholders when it is
not. The placeholders used to look exactly like real results:

* the research fallback returned a hard-coded "Comprehensive Research
  Report" with a roster of three agents all marked ``completed`` and
  ``"verified": True`` — a verification that never happened;
* the content fallback returned a hard-coded draft, a ``9.2`` quality
  score, a fake critique history, a ``published_path`` for a file that was
  never written, and ``"status": "published"``;
* the triage fallback claimed a ``0.94`` confidence for a keyword
  heuristic, and its customer-facing reply stated that a refund had been
  initiated;
* ``GET /status`` always answered ``"ready"``.

The web page compounded it: a hard-coded ``94 / 100`` score when no score
existed, a hard-coded two-pass critique history, ``output.md`` as the
publication path, and a "QUALITY GATE PASSED" badge on a run that never
happened.

Pinned here: every fallback says what it is, and the client renders only
what the server actually reported.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.routers import agent_studio

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "apps" / "web" / "src" / "pages" / "AgentStudio.tsx"


# --------------------------------------------------------------------------- #
# 1. the research fallback must not claim a verification
# --------------------------------------------------------------------------- #
def test_the_research_fallback_is_not_verified():
    out = agent_studio._fallback_research("anything")
    assert out["verified"] is False, (
        "a report that was never researched must not be reported as verified")
    assert out["mode"] == "unavailable"
    assert out.get("note"), "the honest reason must be stated"
    assert all(a["status"] != "completed" for a in out["agents"]), (
        "an agent that never ran must not be marked completed")
    assert "verified production-grade output" not in out["report"]


# --------------------------------------------------------------------------- #
# 2. the content fallback must not claim a score or a publication
# --------------------------------------------------------------------------- #
def test_the_content_fallback_claims_nothing():
    out = agent_studio._fallback_content("anything")
    assert out["score"] is None, "a score nobody assigned must not be invented"
    assert out["published_path"] is None, "no file was written, so no path exists"
    assert out["status"] != "published"
    assert out["final_content"] is None
    assert out["feedback"] == [], "a critique that never happened must not be listed"
    assert out["loops"] == 0
    assert out.get("note"), "the honest reason must be stated"


# --------------------------------------------------------------------------- #
# 3. the triage fallback is a keyword guess, and its reply is a draft
# --------------------------------------------------------------------------- #
def test_the_triage_fallback_states_its_confidence_and_marks_the_draft():
    out = agent_studio._fallback_triage("I was charged twice, please refund order ord_101")
    assert out["confidence"] <= 0.6, (
        "a keyword heuristic must not claim a high confidence")
    assert out["source"] == "fallback"
    assert out["response_is_draft"] is True
    assert "heuristic" in out["reasoning"].lower()
    # the reply must not state that a refund was initiated (it never was)
    assert "has been initiated" not in (out["response"] or "").lower()


# --------------------------------------------------------------------------- #
# 4. the status endpoint reports the real availability
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_status_reports_whether_the_bridge_can_run(monkeypatch):
    monkeypatch.setattr(agent_studio, "_find_portfolio_root",
                        lambda: Path("/nonexistent-portfolio"))
    out = await agent_studio.get_studio_status()
    assert out["status"] != "ready", (
        "the studio is not ready when the agent bridge is absent")
    assert out["bridge_available"] is False
    assert out.get("note")


# --------------------------------------------------------------------------- #
# 5. the client renders only what the server reported
# --------------------------------------------------------------------------- #
def test_the_page_invents_no_score_publication_or_verification():
    src = PAGE.read_text(encoding="utf-8")
    assert "'94'" not in src, (
        "the page must not fall back to an invented quality score")
    assert "|| 'output.md'" not in src, (
        "the page must not invent a publication path")
    assert "Score 0.72" not in src and "Score 0.94" not in src, (
        "the page must not narrate a critique history that never happened")
    assert "Fact-Check: Verified" in src, (
        "the verified badge must still exist — for the runs that verified")
    assert "researchResult.verified" in src, (
        "the research badge must follow the server's verification flag")
    assert "contentResult.published_path ?" in src, (
        "the published-artifact block must be conditional on a real path")
