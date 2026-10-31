"""Integration tests for STT WebSocket streaming endpoint."""
import json
from starlette.testclient import TestClient
from app.main import app
from tests.fixtures.audio_fixtures import generate_tone


def test_websocket_streaming_flow():
    client = TestClient(app)

    with client.websocket_connect("/api/v1/stt/stream/ws_test_sess") as ws:
        # Stream 3 50ms frames of tone audio (prefixed with 'O' TalkFlow header)
        for _ in range(3):
            pcm16 = generate_tone(440.0, 0.05, 16000)
            frame = bytearray(17 + len(pcm16))
            frame[0] = ord("O")
            frame[1:17] = b"seg_test_0000000"
            frame[17:] = pcm16
            ws.send_bytes(bytes(frame))

        # Send control finalize message
        ws.send_text(json.dumps({"action": "finalize", "seq": 1}))

        # Receive final event
        resp_text = ws.receive_text()
        data = json.loads(resp_text)
        assert data["type"] == "transcript.final"
        assert data["session_id"] == "ws_test_sess"
        assert data["is_final"] is True

