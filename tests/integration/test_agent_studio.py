"""Integration tests for Agent Studio multi-agent endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.mark.asyncio
async def test_agent_studio_status():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/agent-studio/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert len(data["systems"]) == 3
        ids = [s["id"] for s in data["systems"]]
        assert "system-01" in ids
        assert "system-02" in ids
        assert "system-03" in ids


@pytest.mark.asyncio
async def test_agent_studio_triage_billing():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"ticket": "I was charged twice this month for my subscription order ord_101. Please refund me."}
        res = await client.post("/api/v1/agent-studio/triage", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["category"] == "billing"
        assert data["route"] == "billing"
        assert data["escalated"] is False
        assert "refund" in data["response"].lower() or "ord_101" in data["response"]


@pytest.mark.asyncio
async def test_agent_studio_triage_escalation():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"ticket": "This is ridiculous and unacceptable, your platform is a scam, get a human now!"}
        res = await client.post("/api/v1/agent-studio/triage", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["sentiment"] == "angry"
        assert data["escalated"] is True


@pytest.mark.asyncio
async def test_agent_studio_research_crew():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"topic": "Multi-agent LangGraph architectures"}
        res = await client.post("/api/v1/agent-studio/research-crew", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["verified"] is True
        assert len(data["agents"]) >= 3
        assert "report" in data
