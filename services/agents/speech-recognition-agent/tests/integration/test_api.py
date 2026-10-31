"""Integration tests for Speech Recognition Agent REST API endpoints."""
import json
from pathlib import Path
from starlette.testclient import TestClient
from app.main import app


def test_dashboard_and_favicon():
    client = TestClient(app)
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "TalkFlow Speech Recognition Agent" in r_dash.text
    assert "text/html" in r_dash.headers["content-type"]

    r_fav = client.get("/favicon.ico")
    assert r_fav.status_code == 200
    assert "image/svg+xml" in r_fav.headers["content-type"]


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["agent"] == "speech_recognition_agent"


def test_ready_endpoint():
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert "provider" in data


def test_agent_info_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/agent/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "speech_recognition_agent"
    assert data["canonical_format"]["sample_rate"] == 16000
    assert data["streaming_supported"] is True


def test_languages_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/stt/languages")
    assert resp.status_code == 200
    langs = resp.json()
    assert len(langs) >= 10
    assert any(l["code"] == "hi" for l in langs)
    assert any(l["code"] == "mr" for l in langs)


def test_transcribe_audio_file():
    client = TestClient(app)
    sample_path = Path(__file__).parent.parent / "fixtures" / "en_example.wav"
    with open(sample_path, "rb") as f:
        wav_bytes = f.read()

    files = {"file": ("test.wav", wav_bytes, "audio/wav")}
    data = {"speaker_id": "test_speaker", "session_id": "test_session_101"}

    resp = client.post("/api/v1/stt/transcribe", files=files, data=data)
    assert resp.status_code == 200
    result = resp.json()
    assert result["session_id"] == "test_session_101"
    assert result["text"] != ""
    assert result["language_hint"] == "en"
    assert len(result["words"]) >= 1


def test_transcribe_agent01_segment():
    client = TestClient(app)
    import base64
    from tests.fixtures.audio_fixtures import generate_tone

    tone_pcm = generate_tone(440.0, 0.5, 16000)
    b64_audio = base64.b64encode(tone_pcm).decode()

    event = {
        "version": 1,
        "type": "audio.segment.final",
        "session_id": "agent01_sess",
        "conversation_id": "conv_001",
        "speaker_id": "user_001",
        "utterance_id": "utt_001",
        "segment_id": "seg_001",
        "seq": 1,
        "payload": {
            "segment_id": "seg_001",
            "sequence_number": 1,
            "start_timestamp": 1.5,
            "end_timestamp": 2.0,
            "duration_seconds": 0.5,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm16",
            "audio_data_base64": b64_audio,
            "is_final": True,
        },
    }

    resp = client.post("/api/v1/stt/segment", json=event)
    assert resp.status_code == 200
    data = resp.json()
    assert data["segment_id"] == "seg_001"
    assert data["is_final"] is True

