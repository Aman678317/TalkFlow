# REST & WebSocket API Specification: Agent 03

## 1. REST Endpoints

### `GET /`
Interactive Control Dashboard and Visual Code-Switching Playground.

### `GET /health`
Returns basic microservice health status.
```json
{
  "status": "ok",
  "agent": "language_intelligence_agent",
  "version": "1.0.0",
  "timestamp": 1793437148.26
}
```

### `GET /ready`
Readiness probe validating underlying LID models.
```json
{
  "ready": true,
  "providers": [
    {"name": "fasttext", "model": "fasttext-lid-176", "healthy": true},
    {"name": "langdetect", "model": "langdetect-indic-heuristics", "healthy": true},
    {"name": "whisper-lid", "model": "whisper-base-lid", "healthy": true}
  ],
  "active_sessions": 1
}
```

### `POST /api/v1/language/detect`
Fast stateless text language detection.
```json
// Request
{
  "text": "Hello world"
}

// Response
{
  "language": "en",
  "confidence": 0.9999,
  "provider": "fasttext",
  "alternatives": []
}
```

### `POST /api/v1/language/analyze`
Full multi-signal analysis with sub-sentence code-switching and script segmentation.
```json
// Request
{
  "text": "Hello everyone, aaj hum artificial intelligence ke baare mein discuss karenge.",
  "session_id": "sess_123"
}

// Response
{
  "session_id": "sess_123",
  "conversation_id": "sess_123",
  "speaker_id": "user_001",
  "original_text": "Hello everyone, aaj hum artificial intelligence ke baare mein discuss karenge.",
  "primary_language": "en",
  "primary_language_script": "Latn",
  "secondary_languages": ["hi"],
  "is_multilingual": true,
  "detection_status": "success",
  "confidence": 0.85,
  "language_spans": [
    {
      "language": "en",
      "script": "Latn",
      "text": "Hello everyone",
      "text_start_offset": 0,
      "text_end_offset": 14,
      "confidence": 0.95
    },
    {
      "language": "hi",
      "script": "Latn",
      "text": "aaj hum",
      "text_start_offset": 16,
      "text_end_offset": 23,
      "confidence": 0.92
    }
  ],
  "capability_status": {
    "language": "en",
    "capability": "production",
    "routing_recommendation": "direct_translation"
  },
  "analysis_latency_ms": 1.48
}
```

### `POST /api/v1/language/transcript`
Direct event bridge consuming Agent 02 `transcript.final` events and outputting Agent 04 `language.analysis.final` events.

---

## 2. Streaming WebSocket API

### `WS /api/v1/language/stream/{session_id}`
Bi-directional real-time transcript streaming.

**Inbound (Agent 02 -> Agent 03):**
```json
{
  "type": "transcript.partial",
  "session_id": "sess_001",
  "speaker_id": "spk_1",
  "text": "Hello everyone aaj hum"
}
```

**Outbound (Agent 03 -> Client / Agent 04):**
```json
{
  "type": "language.analysis.partial",
  "session_id": "sess_001",
  "speaker_id": "spk_1",
  "text": "Hello everyone aaj hum",
  "primary_language": "en",
  "confidence": 0.85,
  "is_multilingual": true,
  "spans_count": 2
}
```

