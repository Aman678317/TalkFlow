"""Integration tests for real-time WebSocket audio streaming."""
import json
import time
from pathlib import Path
import soundfile as sf
from starlette.testclient import TestClient
from app.audio.normalization import AudioNormalizer
from app.main import app
from tests.fixtures.audio_fixtures import generate_silence


def test_websocket_streaming_flow():
    client = TestClient(app)
    session_id = "ws_test_sess_01"

    sample_file = Path(__file__).parent.parent / "fixtures" / "en_example.wav"
    data, sr = sf.read(str(sample_file), dtype="int16")
    normalizer = AudioNormalizer()
    real_speech_pcm = normalizer.normalize(data.tobytes(), source_sample_rate=sr)

    with client.websocket_connect(f"/api/v1/audio/stream/{session_id}?speaker_id=user_alice") as ws:
        # 1. Handshake response
        ready_msg = ws.receive_text()
        ready_data = json.loads(ready_msg)
        assert ready_data["event"] == "session.ready"
        assert ready_data["session_id"] == session_id

        # 2. Ping-pong
        ws.send_text(json.dumps({"event": "ping", "timestamp": 123456}))
        pong_msg = ws.receive_text()
        pong_data = json.loads(pong_msg)
        assert pong_data["event"] == "pong"

        # 3. Stream real speech frames (10 frames of 50ms = 500ms)
        offset = 16000
        for i in range(10):
            frame = real_speech_pcm[offset:offset + 1600]
            ws.send_bytes(frame)
            offset += 1600

        # 4. Stream silence frames (12 frames of 50ms = 600ms) to trigger pause and commit
        silence_frame_50ms = generate_silence(50, 16000)
        for i in range(12):
            ws.send_bytes(silence_frame_50ms)

        # 5. Receive emitted events
        events_received = []
        for _ in range(10):
            try:
                msg = ws.receive_text()
                evt = json.loads(msg)
                events_received.append(evt.get("event"))
                if evt.get("event") == "audio.segment.final":
                    # Accompanying binary frame
                    binary = ws.receive_bytes()
                    assert len(binary) > 17
                    break
            except Exception:
                break

        assert "speech.started" in events_received or "audio.segment.final" in events_received
