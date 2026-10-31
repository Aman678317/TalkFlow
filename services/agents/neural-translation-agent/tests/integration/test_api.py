"""Integration tests for Agent 04 REST endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_and_ready():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_health = await client.get("/health")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "ok"
        assert r_health.json()["agent"] == "neural_translation_agent"

        r_ready = await client.get("/ready")
        assert r_ready.status_code == 200
        assert r_ready.json()["ready"] is True


@pytest.mark.asyncio
async def test_agent_info_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agent/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "neural_translation_agent"
        assert data["version"] == "1.0.0"
        assert data["zero_pivot_enforced"] is True
        assert len(data["active_providers"]) > 0


@pytest.mark.asyncio
async def test_translate_single_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "text": "नमस्ते दोस्तों",
            "source_lang": "hi",
            "target_lang": "en",
        }
        resp = await client.post("/api/v1/translation/translate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_lang"] == "hi"
        assert data["target_lang"] == "en"
        assert len(data["text"]) > 0
        assert data["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_translate_batch_fanout_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "text": "नमस्ते दोस्तों",
            "source_lang": "hi",
            "target_langs": ["en", "mr", "ja", "en"],  # duplicate en
        }
        resp = await client.post("/api/v1/translation/batch", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["requested_targets_count"] == 4
        assert data["unique_translation_jobs_count"] == 3
        assert "en" in data["results"]
        assert "mr" in data["results"]
        assert "ja" in data["results"]


@pytest.mark.asyncio
async def test_validate_pair_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"source_lang": "hi", "target_lang": "mr"}
        resp = await client.post("/api/v1/translation/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["supported"] is True
        assert data["status"] in ("PRODUCTION", "SUPPORTED")


@pytest.mark.asyncio
async def test_agent03_event_ingestion_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        event_payload = {
            "version": 1,
            "type": "language.analysis.final",
            "session_id": "test_meeting",
            "conversation_id": "test_conv",
            "speaker_id": "speaker_1",
            "utterance_id": "utt_01",
            "segment_id": "seg_01",
            "seq": 1,
            "original_text": "नमस्ते दोस्तों",
            "primary_language": "hi",
            "secondary_languages": [],
            "is_multilingual": False,
            "confidence": 0.98,
            "target_languages": ["en", "mr"],
        }
        resp = await client.post("/api/v1/translation/agent03/transcript", json=event_payload)
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        tgt_langs = {ev["target_lang"] for ev in events}
        assert tgt_langs == {"en", "mr"}
        for ev in events:
            assert ev["is_final"] is True
            assert ev["segment_id"] == "seg_01"

