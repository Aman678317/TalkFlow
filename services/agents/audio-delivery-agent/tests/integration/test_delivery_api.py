"""Integration tests for Agent 07 Audio Delivery REST API endpoints."""
from __future__ import annotations

import base64
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "Agent 07" in data["agent"]


def test_metrics_endpoint():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "talkflow_audio_delivery" in resp.text


def test_register_and_get_room():
    reg_payload = {
        "participant_id": "test_user_01",
        "room_id": "test_room_api",
        "display_name": "Test User",
        "hear_lang": "mr",
        "playback_mode": "translated",
    }
    resp = client.post("/api/v1/rooms/participants", json=reg_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "registered"

    room_resp = client.get("/api/v1/rooms/test_room_api")
    assert room_resp.status_code == 200
    room_data = room_resp.json()
    assert room_data["participant_count"] == 1


def test_ingest_chunk_and_barge_in():
    dummy_audio = base64.b64encode(b"\x00" * 4800).decode()
    chunk_payload = {
        "session_id": "test_room_api",
        "conversation_id": "test_room_api",
        "speaker_id": "speaker_test",
        "segment_id": "seg_api_1",
        "target_lang": "mr",
        "chunk_index": 0,
        "is_final_chunk": False,
        "duration_ms": 100.0,
        "audio_base64": dummy_audio,
        "synthetic": True,
        "audio_origin": "synthetic_tts",
    }
    resp = client.post("/api/v1/delivery/chunks", json=chunk_payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] in ("published", "scheduled")

    # Barge-in cancellation
    cancel_resp = client.post(
        "/api/v1/delivery/cancel",
        json={"room_id": "test_room_api", "reason": "user_interruption"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_brain_query():
    resp = client.post(
        "/api/v1/brain/query",
        json={"query": "Explain TalkFlow 0x54 binary frame layout"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "0x54" in data["answer"]
    assert data["confidence"] > 0.8

