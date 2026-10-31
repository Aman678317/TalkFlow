# TalkFlow Integration Contract & Agent 02 Handoff Guide

## 1. Multi-Agent Topology

In the TalkFlow / GlobalTalk real-time multilingual communication platform, speech flows through specialized autonomous agents:

```
[User Mic] ──► [Agent 01: Audio Intelligence] ──► [Agent 02: STT] ──► [Agent 03: Translation] ──► [Agent 04: TTS]
```

Agent 01 acts as the clean acoustic boundary. It shields Agent 02 from background noise, silence, microphone clipping, and misaligned sample rates.

---

## 2. Event Specification: Agent 01 ──► Agent 02

### 2.1 Final Segment Contract (`audio.segment.final`)
When a natural conversational turn or sentence pause concludes, Agent 01 commits and emits:

```json
{
  "version": 1,
  "event": "audio.segment.final",
  "agent": "audio_intelligence",
  "session_id": "meeting_123",
  "conversation_id": "meeting_123",
  "speaker_id": "user_001",
  "segment_id": "seg_608c94297d90",
  "sequence": 14,
  "start_ms": 1000,
  "end_ms": 4500,
  "duration_ms": 3500,
  "sample_rate": 16000,
  "channels": 1,
  "encoding": "pcm_s16le",
  "quality": {
    "rms": 0.0845,
    "peak": 0.4521,
    "snr_db": 24.5,
    "clipping_ratio": 0.0,
    "silence_ratio": 0.12,
    "speech_duration_ms": 3500,
    "noise_level_db": -48.2,
    "confidence": 0.95,
    "quality_status": "good",
    "issues": []
  },
  "status": "final",
  "storage_ref": null
}
```

### 2.2 Partial Segment Contract (`audio.segment.partial`)
During ongoing speech, provisional chunks are emitted every `vad_partial_interval_ms` (1200 ms default) to power live preview captions:

```json
{
  "version": 1,
  "event": "audio.segment.partial",
  "agent": "audio_intelligence",
  "session_id": "meeting_123",
  "conversation_id": "meeting_123",
  "speaker_id": "user_001",
  "segment_id": "seg_608c94297d90",
  "sequence": 14,
  "start_ms": 1000,
  "end_ms": 2200,
  "duration_ms": 1200,
  "sample_rate": 16000,
  "channels": 1,
  "encoding": "pcm_s16le",
  "quality": {
    "quality_status": "good"
  },
  "status": "partial"
}
```

---

## 3. Audio Binary Transport Format

The binary PCM16 audio data accompanying every segment event is formatted according to TalkFlow's `BinaryFrame` protocol:

```
+------------+-------------------------+--------------------+
| Byte 0     | Bytes 1..16             | Remaining Bytes    |
| 'O' (0x4F) | ASCII Segment Short ID  | Clean PCM16 mono   |
|            | (e.g. seg_608c94297d90) | 16 kHz audio data  |
+------------+-------------------------+--------------------+
```

- Byte count is guaranteed to be `duration_ms * 32` bytes (16 samples/ms * 2 bytes/sample).
- Audio is normalized, DC-filtered, and denoised.

---

## 4. How to Connect Agent 02 (Speech Recognition Agent)

Agent 02 can consume audio from Agent 01 via either of two patterns:

### Pattern A: Direct WebSocket Stream Subscription
Agent 02 establishes a WebSocket client connection to:
```
ws://<agent_01_host>:8001/api/v1/audio/stream/{session_id}
```
1. Receive `session.ready`.
2. As Agent 01 receives microphone frames, Agent 02 listens for `audio.segment.partial` and `audio.segment.final` JSON messages.
3. Upon receiving an `audio.segment.*` event, read the accompanying binary frame containing the clean PCM16 audio.
4. Pass the binary PCM16 payload directly to faster-whisper or IndicConformer for transcription:
```python
import numpy as np

# Convert clean PCM16 payload from Agent 01 to float32 for faster-whisper
audio_float = np.frombuffer(pcm_payload, dtype=np.int16).astype(np.float32) / 32768.0
segments, info = whisper_model.transcribe(audio_float, language="en")
```

### Pattern B: TalkFlow Hub Routing
TalkFlow's central realtime hub (`apps/api/globaltalk/realtime/audio_pipeline.py`) can forward raw mic blocks to Agent 01:
1. Ingest `AudioWorklet` blocks.
2. Delegate VAD, noise suppression, and segmentation to Agent 01.
3. Upon receiving `audio.segment.final`, commit canonical `TranscriptSegment` in TalkFlow database and invoke MT fan-out.

