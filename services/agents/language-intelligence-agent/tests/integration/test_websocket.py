"""Integration tests for Language Intelligence Agent WebSocket streaming endpoint."""
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_websocket_streaming_partial_and_final():
    with client.websocket_connect("/api/v1/language/stream/sess_ws_test") as ws:
        # 1. Send partial transcript
        partial_msg = {
            "type": "transcript.partial",
            "session_id": "sess_ws_test",
            "speaker_id": "user_001",
            "text": "Hello everyone aaj hum",
        }
        ws.send_text(json.dumps(partial_msg))
        resp1 = json.loads(ws.receive_text())
        assert resp1["type"] == "language.analysis.partial"
        assert "primary_language" in resp1

        # 2. Send final transcript
        final_msg = {
            "type": "transcript.final",
            "session_id": "sess_ws_test",
            "speaker_id": "user_001",
            "utterance_id": "utt_ws_01",
            "segment_id": "seg_ws_01",
            "text": "Hello everyone aaj hum discuss karenge",
        }
        ws.send_text(json.dumps(final_msg))
        resp2 = json.loads(ws.receive_text())
        assert resp2["type"] == "language.analysis.final"
        assert "primary_language" in resp2
        assert "language_spans" in resp2

