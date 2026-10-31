"""Integration tests for Language Intelligence Agent REST endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["agent"] == "language_intelligence_agent"


def test_ready_endpoint():
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json()["ready"] is True


def test_metrics_endpoint():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "talkflow_lang_requests_total" in res.text


def test_agent_info():
    res = client.get("/api/v1/agent/info")
    assert res.status_code == 200
    assert res.json()["name"] == "language_intelligence_agent"


def test_detect_endpoint():
    res = client.post("/api/v1/language/detect", json={"text": "Bonjour tout le monde"})
    assert res.status_code == 200
    assert res.json()["language"] == "fr"


def test_analyze_endpoint_hinglish():
    res = client.post(
        "/api/v1/language/analyze",
        json={
            "text": "Hello everyone, aaj hum artificial intelligence ke baare mein discuss karenge.",
            "session_id": "sess_integration_01",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_multilingual"] is True
    assert len(data["language_spans"]) >= 2
    assert "capability_status" in data


def test_transcript_ingestion_bridge():
    event_payload = {
        "type": "transcript.final",
        "session_id": "sess_agent02",
        "conversation_id": "conv_agent02",
        "speaker_id": "speaker_42",
        "utterance_id": "utt_100",
        "segment_id": "seg_100",
        "seq": 1,
        "text": "नमस्कार मित्रांनो, आपण कसे आहात?",
        "language_hint": "mr",
        "language_probability": 0.90,
        "is_final": True,
        "words": [
            {"word": "नमस्कार", "start": 0.0, "end": 0.5, "confidence": 0.95},
            {"word": "मित्रांनो", "start": 0.5, "end": 1.0, "confidence": 0.92},
        ],
    }
    res = client.post("/api/v1/language/transcript", json=event_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "language.analysis.final"
    assert data["primary_language"] == "mr"
    assert data["session_id"] == "sess_agent02"

