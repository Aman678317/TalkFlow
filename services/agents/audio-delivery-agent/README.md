# TalkFlow Audio Synchronization & Delivery Agent (Agent 07)

**Agent 07** is the final audio delivery component of the TalkFlow / GlobalTalk AI multilingual communication pipeline. It receives synthesized speech chunks from **Agent 06 (Voice Generation Agent)**, resolves jitter and reordering, synchronizes playback with conversational timelines, fans out translated streams to eligible room participants, and transmits audio over TalkFlow's low-latency binary wire format (`0x54`) and LiveKit WebRTC tracks.

---

## 1. Pipeline Position

```
[Agent 01: Audio Intelligence] (8001)
               │ (WAV / PCM audio)
               ▼
[Agent 02: Speech Recognition (STT)] (8002)
               │ (ASR Transcript)
               ▼
[Agent 03: Language Intelligence (LID)] (8003)
               │ (Language identification & hints)
               ▼
[Agent 04: Neural Machine Translation (MT)] (8004)
               │ (Independent multi-target translations)
               ▼
[Agent 05: Translation Quality (QA)] (8005)
               │ (Accuracy & safety gate)
               ▼
[Agent 06: Voice Generation (TTS)] (8006)
               │ (Synthesized audio chunks)
               ▼
[Agent 07: Audio Synchronization & Delivery] (8007)
               │ (0x54 binary WebSocket & LiveKit WebRTC)
               ▼
       [Meeting Participants]
```

---

## 2. Core Capabilities

- **Jitter Buffering & Reordering**: Reassembles out-of-order chunks via sequence indices, drops duplicates, and skips gaps past the reorder wait deadline (60ms).
- **Conversational Synchronization**: Tracks turn progression via `start_wall_ms` and speaker sequence counters.
- **Stale Utterance Dropping**: Enforces conversational freshness (max 1500ms delay) to prevent stale speech from playing over newer conversation.
- **1-to-N Fan-Out Routing**: Synthesize once per language, fan out to all listeners in that room who configured `hear_lang == target_lang` and `playback_mode in ('translated', 'both')`.
- **Feedback Loop Prevention**: Excludes human speaker from receiving their own microphone input translated back into the room.
- **Dual Transport Delivery**:
  - LiveKit WebRTC synthetic tracks (`gt-translated-{target_lang}`)
  - Binary WebSocket streaming using TalkFlow's `0x54 ('T')` frame format with chunk index extension `0x01`
- **Instant Barge-in Interruption**: Immediately flushes jitter queues and sends `playback.flush` events to client audio players.
- **Audio Ducking**: Attenuates original speaker volume when translated speech is playing concurrently.
- **Diagnostic Brain**: Built-in domain reasoning engine with Ollama LLM integration.

---

## 3. Quickstart

### Starting the Service
```bash
cd audio-delivery-agent
uvicorn app.main:app --host 127.0.0.1 --port 8007
```

### Running Tests
```bash
pytest -v
```

### Running Verification & Benchmark
```bash
python scripts/verify_agent.py
python scripts/benchmark_delivery.py
```

### Interactive Web Dashboard
Open your browser at:
`http://127.0.0.1:8007`

