# TalkFlow Audio Intelligence Agent (Agent 01) — API Specification

The Audio Intelligence Agent exposes a FastAPI HTTP/REST and WebSocket interface operating on port `8001` by default.

---

## 1. REST Endpoints

### 1.1 Health Check
- **Route:** `GET /health`
- **Description:** Verifies service liveness.
- **Response (200 OK):**
```json
{
  "status": "ok",
  "agent": "audio_intelligence_agent",
  "version": "1.0.0",
  "timestamp": 1730372000.123
}
```

---

### 1.2 Readiness Check
- **Route:** `GET /ready`
- **Description:** Verifies operational readiness of audio processing dependencies (VAD provider, noise suppressor, models).
- **Response (200 OK):**
```json
{
  "ready": true,
  "vad": {
    "provider": "silero",
    "available": true
  },
  "noise_suppression": {
    "provider": "spectral",
    "available": true
  },
  "active_sessions": 0
}
```
- **Error Response (503 Service Unavailable):** Returned if a required model or provider backend is unavailable.

---

### 1.3 Agent Telemetry & Prometheus Metrics
- **Route:** `GET /metrics`
- **Description:** Exports Prometheus metrics for Prometheus scrapers and observability dashboards.
- **Key Metrics:**
  - `audio_agent_frames_processed_total{session_id="..."}`
  - `audio_agent_frames_dropped_total{reason="..."}`
  - `audio_agent_segments_total{status="partial|final"}`
  - `audio_agent_active_sessions`
  - `audio_agent_frame_latency_ms_bucket`
  - `audio_agent_vad_latency_ms_bucket`
  - `audio_agent_denoise_latency_ms_bucket`
  - `audio_agent_snr_db_bucket`

---

### 1.4 Agent Identity & Capabilities
- **Route:** `GET /api/v1/agent/info`
- **Description:** Returns agent identity, supported audio specifications, and configuration parameters.
- **Response (200 OK):**
```json
{
  "name": "audio_intelligence_agent",
  "version": "1.0.0",
  "description": "TalkFlow Audio Intelligence Agent (Agent 01)",
  "canonical_format": {
    "sample_rate": 16000,
    "channels": 1,
    "encoding": "pcm_s16le",
    "frame_duration_ms": 50
  },
  "supported_formats": ["pcm_s16le", "wav"],
  "vad_provider": "silero",
  "noise_suppression_provider": "spectral",
  "llm_agent_enabled": true,
  "llm_model": "qwen3.5:4b",
  "active_sessions": 2,
  "uptime_seconds": 124.5
}
```

---

### 1.5 Batch Audio Processing
- **Route:** `POST /api/v1/audio/process`
- **Content-Type:** `multipart/form-data`
- **Parameters:**
  - `file`: Audio file (WAV or raw PCM16)
  - `session_id` (optional): Session tracking identifier
  - `conversation_id` (optional): Conversation / meeting identifier
  - `speaker_id` (optional, default `"user_001"`): Speaker identifier
- **Response (200 OK):**
```json
{
  "session_id": "batch_session_101",
  "total_audio_duration_ms": 60000,
  "speech_duration_ms": 42500,
  "segments_count": 5,
  "segments": [
    {
      "session_id": "batch_session_101",
      "conversation_id": "batch_session_101",
      "speaker_id": "test_speaker",
      "segment_id": "seg_608c94297d90",
      "sequence": 1,
      "start_ms": 500,
      "end_ms": 4850,
      "duration_ms": 4350,
      "sample_rate": 16000,
      "channels": 1,
      "encoding": "pcm_s16le",
      "quality": {
        "rms": 0.0845,
        "peak": 0.4521,
        "snr_db": 24.5,
        "clipping_ratio": 0.0,
        "silence_ratio": 0.12,
        "speech_duration_ms": 4350,
        "noise_level_db": -48.2,
        "confidence": 0.95,
        "quality_status": "good",
        "issues": []
      },
      "status": "final",
      "storage_ref": null
    }
  ],
  "overall_quality": {
    "rms": 0.0782,
    "peak": 0.5120,
    "snr_db": 25.1,
    "clipping_ratio": 0.0,
    "silence_ratio": 0.15,
    "speech_duration_ms": 42500,
    "noise_level_db": -49.0,
    "confidence": 0.95,
    "quality_status": "good",
    "issues": []
  },
  "processing_time_ms": 412.3
}
```

---

## 2. Real-Time Streaming WebSocket

- **Endpoint:** `WebSocket /api/v1/audio/stream/{session_id}`
- **Query Parameters:**
  - `conversation_id` (optional): Defaults to `session_id`
  - `speaker_id` (optional): Defaults to `"user_001"`
  - `sample_rate` (optional): Incoming sample rate (default `16000`)
  - `channels` (optional): Channel count (default `1`)

### Handshake & Lifecycle
1. **Server Welcome:** Upon connection, server sends:
```json
{
  "version": 1,
  "event": "session.ready",
  "session_id": "meeting_123",
  "conversation_id": "meeting_123",
  "speaker_id": "user_001",
  "canonical_sample_rate": 16000,
  "canonical_channels": 1
}
```

2. **Client Streaming:** Client sends continuous 50 ms audio frames:
   - **Binary Frames:** 1600 bytes PCM16 mono 16 kHz little-endian audio. (TalkFlow `'O'` binary frames also supported).
   - **Heartbeat:** `{"event": "ping", "timestamp": 123456}` -> server replies with `{"event": "pong", "timestamp": 123456}`.
   - **Stream End:** `{"event": "audio.stopped"}`.

3. **Server Streaming Outbound Events:**
   - `speech.started`
   - `audio.segment.partial` (accompanied by binary audio chunk)
   - `speech.ended`
   - `audio.segment.final` (accompanied by binary audio chunk)

