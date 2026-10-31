# Speech Recognition Agent (Agent 02) — API Documentation

## REST Endpoints

### 1. Root & Dashboard
- `GET /`: Serves the interactive web control dashboard and browser audio playground.
- `GET /favicon.ico`: Serves SVG favicon.

### 2. Service Telemetry
- `GET /health`: Returns basic JSON health status.
- `GET /ready`: Returns non-blocking provider readiness status.
- `GET /metrics`: Returns Prometheus-compatible latency and throughput metrics.
- `GET /api/v1/agent/info`: Returns agent identity, version, model, device, and active sessions.
- `GET /api/v1/stt/providers`: Returns list of available provider adapters.
- `GET /api/v1/stt/languages`: Returns list of supported Indian and international languages.

### 3. Speech Recognition
- `POST /api/v1/stt/transcribe`:
  - Multipart form upload (`file: UploadFile`).
  - Optional form fields: `session_id`, `speaker_id`, `language_hint`.
  - Returns: `TranscribeResponse` with full text, detected language hint, confidence, and word-level timestamps.
- `POST /api/v1/stt/segment`:
  - Accepts JSON event from Agent 01 (`audio.segment.final` with base64 audio).
  - Returns: `TranscribeResponse`.

## WebSocket Endpoint

### `WS /api/v1/stt/stream/{session_id}`
- Supports streaming 50 ms audio frames (TalkFlow `'O'` binary frame or raw PCM16).
- Emits real-time `transcript.partial` events (JSON) every 500 ms.
- Accepts `{"action": "finalize"}` control messages to commit the utterance.
- Emits immutable `transcript.final` events with word timestamps.

