"""Integration tests for REST API endpoints using TestClient."""
from pathlib import Path
from starlette.testclient import TestClient
from app.main import app


def test_dashboard_endpoint():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "TalkFlow" in response.text
    assert "Audio Intelligence Agent" in response.text
    assert "text/html" in response.headers["content-type"]


def test_favicon_endpoint():
    client = TestClient(app)
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert "<svg" in response.text


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "agent" in data
    assert "version" in data


def test_ready_endpoint():
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "vad" in data
    assert "noise_suppression" in data


def test_metrics_endpoint():
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "audio_agent_active_sessions" in text or "audio_agent" in text


def test_agent_info_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/agent/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "audio_intelligence_agent"
    assert data["canonical_format"]["sample_rate"] == 16000
    assert "pcm_s16le" in data["supported_formats"]


def test_audio_process_endpoint_with_wav():
    client = TestClient(app)
    sample_file = Path(__file__).parent.parent / "fixtures" / "en_example.wav"
    with open(sample_file, "rb") as f:
        wav_bytes = f.read()

    files = {"file": ("test_speech.wav", wav_bytes, "audio/wav")}
    data = {"speaker_id": "test_speaker", "session_id": "batch_session_101"}

    response = client.post("/api/v1/audio/process", files=files, data=data)
    assert response.status_code == 200
    result = response.json()

    assert result["session_id"] == "batch_session_101"
    assert result["total_audio_duration_ms"] > 1000
    assert result["segments_count"] >= 1
    assert len(result["segments"]) >= 1

    first_segment = result["segments"][0]
    assert first_segment["speaker_id"] == "test_speaker"
    assert first_segment["status"] == "final"
    assert first_segment["duration_ms"] > 0
    assert "quality" in first_segment
