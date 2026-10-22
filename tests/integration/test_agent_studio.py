"""Integration tests for Agent Studio multi-agent endpoints.

Phase 3: all endpoints require an authenticated org user (router-level
require_org_user). Anonymous callers get 401 — the /status payload no longer
leaks the server interpreter path and the bridge subprocess is not reachable
without credentials.
"""
import pytest


def test_agent_studio_requires_auth(services_app_client):
    res = services_app_client.get("/api/v1/agent-studio/status")
    assert res.status_code == 401
    assert "interpreter" not in res.json()


def test_agent_studio_status(services_app_client, user):
    res = services_app_client.get("/api/v1/agent-studio/status", headers=user["headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert len(data["systems"]) == 3
    ids = [s["id"] for s in data["systems"]]
    assert "system-01" in ids
    assert "system-02" in ids
    assert "system-03" in ids


def test_agent_studio_triage_billing(services_app_client, user):
    payload = {"ticket": "I was charged twice this month for my subscription order ord_101. Please refund me."}
    res = services_app_client.post("/api/v1/agent-studio/triage", json=payload, headers=user["headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "billing"
    assert data["route"] == "billing"
    assert data["escalated"] is False
    assert "refund" in data["response"].lower() or "ord_101" in data["response"]


def test_agent_studio_triage_escalation(services_app_client, user):
    payload = {"ticket": "This is ridiculous and unacceptable, your platform is a scam, get a human now!"}
    res = services_app_client.post("/api/v1/agent-studio/triage", json=payload, headers=user["headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["sentiment"] == "angry"
    assert data["escalated"] is True


def test_agent_studio_research_crew(services_app_client, user):
    payload = {"topic": "Multi-agent LangGraph architectures"}
    res = services_app_client.post("/api/v1/agent-studio/research-crew", json=payload, headers=user["headers"])
    assert res.status_code == 200
    data = res.json()
    # The fallback placeholder must NOT claim a verified report (issue #109
    # class 3, day-2 finding B-2): nothing was researched and nothing was
    # fact-checked, so the honest answer is "not verified" + the reason. On a
    # deployment where the real bridge runs, a verification IS true — but then
    # the mode says so and no placeholder note is present.
    if data["mode"] == "unavailable":
        assert data["verified"] is False, (
            "a research result that was never produced must not be reported as verified")
        assert data.get("note"), "the honest reason must be stated"
    else:
        assert data["verified"] is True
    assert len(data["agents"]) >= 3
    assert "report" in data
