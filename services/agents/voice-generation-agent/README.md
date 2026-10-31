# TalkFlow Agent 06: Voice Generation Agent (TTS)

Production-grade AI Text-to-Speech (TTS) Agent for the **TalkFlow / GlobalTalk AI** multilingual communication platform.

Agent 06 receives finalized translations that have passed **Agent 05 (Translation Quality QA Agent)**'s safety gate and synthesizes natural, low-latency, language-accurate speech for handoff to **Agent 07 (Audio Synchronization & Delivery)**.

---

## 1. Architectural Role in TalkFlow Cascade

```
Agent 01: Audio Intelligence (8001)
   ↓ (VAD, clean audio segments)
Agent 02: Speech Recognition / STT (8002)
   ↓ (human transcript)
Agent 03: Language Intelligence / LID (8003)
   ↓ (language spans, code-switching analysis)
Agent 04: Neural Translation / MT (8004)
   ↓ (independent multi-target fan-out)
Agent 05: Translation Quality / QA (8005)
   ↓ (quality.assessment.final — ACCEPT / ACCEPT_WITH_WARNINGS)
Agent 06: Voice Generation / TTS (8006)
   ↓ (tts.chunk, 0x54 binary PCM frames, synthetic=True)
Agent 07: Audio Synchronization & Delivery (8007)
```

---

## 2. Core Capabilities & Invariants

- **Agent 05 Hard Quality Gate**: Rejects unapproved, held, or retry-recommended translations (`REJECT`, `HOLD_FOR_HUMAN`, `RETRY_WITH_ALTERNATE_PROVIDER`) with HTTP 422 before any audio synthesis begins.
- **Translation Provenance & Identity Validation**: Validates session ID, conversation ID, segment ID, translation ID, target language, and text hash.
- **Language-Aware Voice Selection**: Strict 5-tier fallback:
  1. Participant preferred voice (if compatible with target language and consent active).
  2. Language-native neural model (Kokoro ONNX or Piper ONNX).
  3. System native voice (Windows SAPI via `pyttsx3`).
  4. DevTone deterministic formant tone synthesizer (TalkFlow `dev_tone.py`).
  5. Fail-closed: raises `UnsupportedLanguageError`.
- **Prohibition of Silent Cross-Language Substitution**: Never uses an English voice to speak Hindi or Marathi; returns explicit error.
- **TalkFlow Binary Wire Framing**: Encodes audio chunks with TalkFlow wire format:
  `0x54 ('T')` + 16-byte short ID + 1-byte language length + language bytes + `0x01` + 4-byte big-endian uint32 chunk index + raw PCM16 payload.
- **Synthetic Flag Guarantee**: Every chunk and response is explicitly flagged `synthetic: true`, preventing acoustic feedback loops back into Agent 02 STT.
- **Privacy & Consent Protection**: Generic voices use stock models; cloned or custom voice profiles require explicit opt-in consent. Cloud providers (Azure) are strictly blocked when `private_only` or `offline_only` is active.
- **Barge-in / Utterance Cancellation**: Fast cancellation endpoints stop in-flight streaming synthesis immediately upon speaker interruption.
- **Operational Brain**: Out-of-band reasoning assistant powered by local Ollama (`qwen3.5:4b`).

---

## 3. Quick Start & Execution

### Prerequisites
Python 3.11+ virtual environment with dependencies installed:
```powershell
pip install -r requirements.txt
```

### Running the Agent Service
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8006
```

### Running Test Suites
```powershell
$env:PYTHONPATH="."
pytest -v
```

### Running Verification Script
```powershell
python scripts/verify_agent.py
```

### Running Benchmarks
```powershell
python scripts/benchmark_tts.py
```

---

## 4. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Interactive Web Dashboard with live audio player |
| `GET` | `/api/v1/tts/health` | Health status and provider readiness |
| `GET` | `/api/v1/tts/info` | Agent metadata and configuration envelope |
| `GET` | `/api/v1/tts/voices` | Enumerate registered voice capabilities |
| `GET` | `/api/v1/tts/voices/{id}` | Inspect specific voice profile |
| `POST` | `/api/v1/tts/synthesize` | Direct text synthesis with quality check |
| `POST` | `/api/v1/tts/segment` | Inbound Agent 05 quality approval webhook |
| `POST` | `/api/v1/tts/cancel` | Barge-in cancellation |
| `POST` | `/api/v1/tts/consent` | Register voice cloning consent |
| `POST` | `/api/v1/tts/brain/query` | Operational brain diagnostic query |
| `WS` | `/api/v1/tts/stream` | Real-time streaming WebSocket (JSON + Binary frames) |
| `GET` | `/metrics` | Prometheus telemetry metrics |

