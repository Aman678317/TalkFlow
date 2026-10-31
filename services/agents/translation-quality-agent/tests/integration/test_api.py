"""Integration tests for Translation Quality Agent REST API and Webhooks."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_and_ready():
    """Verify health and readiness probes."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "agent" in data

    resp_ready = client.get("/ready")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["status"] == "ready"


def test_agent_info():
    """Verify Agent 05 capabilities and metadata endpoint."""
    resp = client.get("/api/v1/agent/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "ACCEPT" in data["decision_outcomes"]
    assert "RETRY_WITH_ALTERNATE_PROVIDER" in data["decision_outcomes"]


def test_evaluate_single_clean_translation():
    """Verify evaluation of a faithful English to Hindi translation."""
    payload = {
        "source_text": "The project meeting starts at 3:00 PM today.",
        "target_text": "परियोजना बैठक आज दोपहर 3:00 बजे शुरू होगी।",
        "source_lang": "en",
        "target_lang": "hi",
        "session_id": "test_sess_01",
        "tenant_id": "org_default",
    }
    resp = client.post("/api/v1/quality/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] in ("ACCEPT", "ACCEPT_WITH_WARNINGS")
    assert data["has_critical_error"] is False
    assert data["overall_score"] >= 0.70


def test_evaluate_single_critical_number_corruption():
    """Verify hard gate triggers when numbers or currencies are corrupted."""
    payload = {
        "source_text": "Your total invoice amount is $500.",
        "target_text": "आपका कुल इनवॉइस 50 रुपये है।",  # Corrupted number 50 and currency
        "source_lang": "en",
        "target_lang": "hi",
        "session_id": "test_sess_02",
        "tenant_id": "org_default",
    }
    resp = client.post("/api/v1/quality/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_critical_error"] is True
    assert data["decision"] in ("RETRY_WITH_ALTERNATE_PROVIDER", "REJECT")
    assert data["overall_score"] <= 0.35  # Hard safety gate ceiling enforced


def test_evaluate_batch():
    """Verify concurrent batch evaluation endpoint."""
    payload = {
        "candidates": [
            {
                "source_text": "Good morning everyone.",
                "target_text": "सभी को शुभ प्रभात।",
                "source_lang": "en",
                "target_lang": "hi",
            },
            {
                "source_text": "Welcome to our conference.",
                "target_text": "हमारे सम्मेलन में आपका स्वागत है।",
                "source_lang": "en",
                "target_lang": "hi",
            },
        ]
    }
    resp = client.post("/api/v1/quality/evaluate/batch", json=payload)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 2
    assert all("decision" in r for r in results)


def test_reference_evaluation_sacrebleu():
    """Verify reference-based evaluation endpoint."""
    payload = {
        "source_text": "Thank you very much.",
        "hypothesis_text": "आपका बहुत-बहुत धन्यवाद।",
        "reference_text": "आपका बहुत-बहुत धन्यवाद।",
        "source_lang": "en",
        "target_lang": "hi",
    }
    resp = client.post("/api/v1/quality/evaluate/reference", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "reference_metrics" in data
    assert data["reference_metrics"]["bleu"] >= 90.0


def test_agent04_transcript_inbound_webhook():
    """Verify inbound event ingestion from Agent 04 Neural Translation Agent."""
    event = {
        "version": 1,
        "type": "translation.final",
        "session_id": "sess_live_integration_1",
        "conversation_id": "conv_live_1",
        "speaker_id": "spk_host",
        "segment_id": "seg_001",
        "seq": 1,
        "source_lang": "en",
        "target_lang": "hi",
        "source_text": "We are deploying the software now.",
        "text": "हम अभी सॉफ़्टवेयर परिनियोजित कर रहे हैं।",
        "is_final": True,
        "provider": "argos",
    }
    resp = client.post("/api/v1/quality/agent04/transcript", json=event)
    assert resp.status_code == 200
    data = resp.json()
    assert "decision" in data
    assert "evaluation_id" in data
    assert data["quality_status"] in ("passed", "warning")
