"""Integration tests for Agent 06 FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/api/v1/tts/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["port"] == 8006
    assert data["synthetic_flag_enforced"] is True


def test_info_endpoint():
    resp = client.get("/api/v1/tts/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "TalkFlow Voice Generation Agent" in data["name"]
    assert data["installed_voices_count"] > 0


def test_voices_endpoint():
    resp = client.get("/api/v1/tts/voices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    voices = data["voices"]
    voice_ids = [v["voice_id"] for v in voices]
    assert "dev-tone-neutral" in voice_ids


def test_synthesize_endpoint_success():
    req_body = {
        "text": "TalkFlow speech synthesis test.",
        "target_language": "en",
        "quality_decision": "ACCEPT",
        "quality_score": 0.95,
        "conversation_id": "conv_test_01",
        "segment_id": "seg_test_01",
    }
    resp = client.post("/api/v1/tts/synthesize", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["synthetic"] is True
    assert len(data["audio_base64"]) > 0
    assert data["duration_ms"] > 0


def test_synthesize_endpoint_quality_gate_reject():
    req_body = {
        "text": "Should not synthesize due to rejection.",
        "target_language": "en",
        "quality_decision": "REJECT",
        "quality_score": 0.20,
        "conversation_id": "conv_test_02",
        "segment_id": "seg_test_02",
    }
    resp = client.post("/api/v1/tts/synthesize", json=req_body)
    assert resp.status_code == 422


def test_agent05_webhook_endpoint():
    webhook_payload = {
        "evaluation_id": "eval_001",
        "candidate_hash": "cand_hash_001",
        "session_id": "sess_001",
        "conversation_id": "conv_001",
        "segment_id": "seg_webhook_01",
        "translation_id": "trans_webhook_01",
        "source_lang": "hi",
        "target_lang": "mr",
        "source_text": "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।",
        "target_text": "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करू.",
        "decision": "ACCEPT",
        "overall_score": 0.94,
        "is_safe_for_voice": True,
    }
    resp = client.post("/api/v1/tts/segment", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["synthetic"] is True
    assert data["target_language"] == "mr"


def test_cancellation_endpoint():
    cancel_payload = {
        "session_id": "sess_001",
        "segment_id": "seg_to_cancel",
        "reason": "barge_in_interruption",
    }
    resp = client.post("/api/v1/tts/cancel", json=cancel_payload)
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True


def test_metrics_endpoint():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "talkflow_tts_requests_total" in resp.text

