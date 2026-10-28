import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_google_meet_connect_invalid_url():
    resp = client.post("/api/v1/google-meet/connect", json={
        "meet_url": "https://invalid-meeting.com/xyz",
        "bot_name": "TalkFlow Subtitle Companion",
    })
    assert resp.status_code == 400
    assert "Invalid Google Meet URL" in resp.json()["error"]["message"]

def test_google_meet_connect_and_disconnect_lifecycle():
    meet_code = "itg-pefc-aef"
    meet_url = f"https://meet.google.com/{meet_code}"
    
    # 1. Connect Google Meet bridge
    resp = client.post("/api/v1/google-meet/connect", json={
        "meet_url": meet_url,
        "bot_name": "TalkFlow Subtitle Companion",
        "source_language": "auto",
        "target_languages": ["hi", "en"],
        "enable_audio_interpretation": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["meet_code"] == meet_code
    assert data["status"] == "active"
    assert "room_id" in data
    assert "session_ticket" in data
    bridge_id = data["id"]
    
    # 2. Re-connect returns existing active session
    re_resp = client.post("/api/v1/google-meet/connect", json={
        "meet_url": meet_url,
        "bot_name": "TalkFlow Subtitle Companion",
    })
    assert re_resp.status_code == 200
    assert re_resp.json()["id"] == bridge_id

    # 3. Get session details
    get_resp = client.get(f"/api/v1/google-meet/sessions/{bridge_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == bridge_id

    # 4. Disconnect session
    disc_resp = client.post(f"/api/v1/google-meet/sessions/{bridge_id}/disconnect")
    assert disc_resp.status_code == 200
    assert disc_resp.json()["session_id"] == bridge_id
