# TalkFlow Multi-Agent Integration Guide (Agent 01 -> Agent 02 -> Agent 03)

## 1. Connecting Agent 01 to Agent 02

Agent 01 emits clean, denoised 16 kHz Mono PCM16 audio chunks. You can forward them to Agent 02 via two methods:

### Method A: REST Webhook / Event (`POST /api/v1/stt/segment`)
When Agent 01 finalizes a speech segment:
```json
POST http://127.0.0.1:8002/api/v1/stt/segment
Content-Type: application/json

{
  "version": 1,
  "type": "audio.segment.final",
  "session_id": "meeting_123",
  "conversation_id": "meeting_123",
  "speaker_id": "user_001",
  "utterance_id": "utt_101",
  "segment_id": "seg_101",
  "seq": 1,
  "payload": {
    "segment_id": "seg_101",
    "sequence_number": 1,
    "start_timestamp": 0.5,
    "end_timestamp": 2.8,
    "sample_rate": 16000,
    "audio_data_base64": "<base64_encoded_pcm16>"
  }
}
```

### Method B: Streaming WebSocket (`WS /api/v1/stt/stream/{session_id}`)
When streaming live microphone frames from Agent 01, send TalkFlow binary frames:
- Byte 0: `'O'` (0x4F)
- Bytes 1..16: 16-char ASCII segment ID
- Bytes 17..N: 50 ms PCM16 audio samples (1600 bytes)

---

## 2. Connecting Agent 02 to Agent 03 (Language Intelligence Agent)

Agent 02 produces `transcript.final` events containing:
1. Canonical transcribed text preserving the original spoken words (including Hinglish and code-switching).
2. Detected language hint (e.g. `hi`, `en`, `mr`) and confidence score.
3. Word-level timestamps (`[{"word": "aaj", "start": 0.5, "end": 0.8}, ...]`).

### Outbound Event Example:
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
  "quality_flags": [],
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
Agent 03 ingests this transcript to perform language confirmation, translation routing, and glossary adaptation!

