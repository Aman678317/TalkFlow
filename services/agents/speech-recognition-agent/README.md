# TalkFlow Speech Recognition Agent (Agent 02)

Production-oriented, independent AI Speech Recognition (STT) microservice for the **TalkFlow / GlobalTalk** real-time multilingual communication platform.

Agent 02 receives clean, timestamped audio chunks from **Agent 01 (Audio Intelligence Agent)**, transcribes spoken words using real speech recognition models (`faster-whisper`), and emits structured partial captions and final transcripts with word-level timestamps and language hints for **Agent 03 (Language Intelligence Agent)**.

---

## Key Capabilities

- **Real Speech Recognition Engine**: Powered by `faster-whisper` and `CTranslate2` (INT8/FP16 precision) with cache-first weight loading.
- **Multilingual & Indian Languages**: High-accuracy recognition for English, Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Punjabi, Urdu, and 25+ international languages.
- **Hinglish & Code-Switching**: Preserves mixed-language speech without forcing translation into English or Hindi.
- **Streaming Partials & Word Timestamps**: Emits incremental partial captions every 500 ms with monotonic revision tracking and word-level timing.
- **Anti-Hallucination Filter**: Automatically detects and drops Whisper repetition loops and silence hallucinations.
- **Out-of-Band Operational Intelligence**: Uses the official **OpenAI Agents SDK** with local Ollama (`qwen3.5:4b`) for operational diagnostics, service health, and profile recommendations.
- **Interactive Web Control Dashboard**: Gorgeous dark-mode browser playground with real-time microphone streaming and WAV file analysis at `http://127.0.0.1:8002/`.

---

## Quick Start (Windows PowerShell)

```powershell
# 1. Navigate to service directory
cd "i:\vioces agent\speech-recognition-agent"

# 2. Run automated component verification (VAD, STT, Brain)
& "i:\vioces agent\.venv\Scripts\python.exe" scripts/verify_agent.py

# 3. Run real-time speech recognition demo on real speech audio
& "i:\vioces agent\.venv\Scripts\python.exe" scripts/test_audio.py

# 4. Run concurrency & latency benchmark
& "i:\vioces agent\.venv\Scripts\python.exe" scripts/benchmark_stt.py

# 5. Start the FastAPI REST & WebSocket server (Port 8002)
& "i:\vioces agent\.venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8002 --reload
```

---

## Running the Automated Test Suite

```powershell
& "i:\vioces agent\.venv\Scripts\pytest.exe" "i:\vioces agent\speech-recognition-agent\tests" -v
```

---

## API Endpoints Overview

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| **`/`** | `GET` | Interactive Web Control Dashboard & Audio Playground |
| **`/favicon.ico`** | `GET` | SVG Service Favicon |
| **`/health`** | `GET` | Basic service health |
| **`/ready`** | `GET` | Non-blocking provider readiness check |
| **`/metrics`** | `GET` | Prometheus-compatible metrics |
| **`/api/v1/agent/info`** | `GET` | Full agent metadata and active session stats |
| **`/api/v1/stt/languages`** | `GET` | List of supported Indian and international languages |
| **`/api/v1/stt/transcribe`** | `POST` | Transcribe complete WAV or PCM file |
| **`/api/v1/stt/segment`** | `POST` | Ingest and transcribe Agent 01 `audio.segment.final` event |
| **`/api/v1/stt/stream/{id}`** | `WS` | Real-time bi-directional streaming WebSocket |

---

## Downstream Integration Contract with Agent 03

Finalized transcript event emitted by Agent 02:
```json
{
  "version": 1,
  "type": "transcript.final",
  "session_id": "meeting_123",
  "conversation_id": "meeting_123",
  "speaker_id": "user_001",
  "utterance_id": "utt_101",
  "segment_id": "seg_101",
  "sequence_hint": 1,
  "text": "Hello everyone aaj meeting mein AI discuss karenge.",
  "language": "hi",
  "language_probability": 0.94,
  "confidence": 0.92,
  "is_final": true,
  "provider": "faster-whisper",
  "model": "whisper-base",
  "recognition_latency_ms": 280.5,
  "words": [
    {"word": "Hello", "start": 0.50, "end": 0.85, "confidence": 0.98},
    {"word": "everyone", "start": 0.86, "end": 1.25, "confidence": 0.96},
    {"word": "aaj", "start": 1.28, "end": 1.55, "confidence": 0.94},
    {"word": "meeting", "start": 1.58, "end": 1.95, "confidence": 0.95},
    {"word": "mein", "start": 1.98, "end": 2.15, "confidence": 0.91},
    {"word": "AI", "start": 2.18, "end": 2.40, "confidence": 0.97},
    {"word": "discuss", "start": 2.42, "end": 2.75, "confidence": 0.95},
    {"word": "karenge", "start": 2.78, "end": 3.10, "confidence": 0.93}
  ]
}
```

