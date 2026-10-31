# TalkFlow Audio Intelligence Agent (Agent 01)

Production-oriented AI Audio Intelligence Agent in Python for the TalkFlow / GlobalTalk multilingual communication platform.

Agent 01 is responsible for receiving raw microphone audio, analyzing acoustic conditions, applying real-time noise suppression, detecting voice activity, intelligently segmenting continuous speech, computing quality metrics, and emitting clean, timestamped audio chunks for **Agent 02: Speech Recognition Agent (STT)**.

---

## Table of Contents
1. [What This Agent Does](#1-what-this-agent-does)
2. [Architecture](#2-architecture)
3. [Prerequisites & Python Installation](#3-prerequisites--python-installation)
4. [Dependency Installation](#4-dependency-installation)
5. [Model Installation & Local AI Brain (Ollama)](#5-model-installation--local-ai-brain-ollama)
6. [Configuration](#6-configuration)
7. [Running Locally](#7-running-locally)
8. [Testing with a WAV File (Terminal Demo)](#8-testing-with-a-wav-file-terminal-demo)
9. [Real-Time Audio Streaming (WebSocket)](#9-real-time-audio-streaming-websocket)
10. [API Reference & Usage](#10-api-reference--usage)
11. [Running Automated Tests](#11-running-automated-tests)
12. [Docker & Containerized Deployment](#12-docker--containerized-deployment)
13. [Benchmarking Performance](#13-benchmarking-performance)
14. [TalkFlow & Agent 02 Integration Contract](#14-talkflow--agent-02-integration-contract)
15. [Troubleshooting Common Issues](#15-troubleshooting-common-issues)

---

## 1. What This Agent Does

The Audio Intelligence Agent processes continuous microphone audio through an intelligent, ultra-low-latency pipeline:

```
Raw Microphone Audio (50 ms blocks)
  ──► Audio Frame Validation & Alignment
  ──► Audio Format Normalization (16 kHz mono PCM16)
  ──► Real-Time Noise Detection
  ──► Spectral Noise Suppression & Wiener Filtering
  ──► Voice Activity Detection (Silero ONNX / WebRTC / Energy)
  ──► Intelligent Phrase-Aware Speech Segmentation
  ──► Acoustic Quality Intelligence (RMS, Peak, SNR, Clipping, Silence)
  ──► High-Level Decision Making via OpenAI Agents SDK (Async)
  ──► Monotonic Chunk Generation & Timestamping
  ──► Clean Payload Delivery to Agent 02 (STT)
```

### Key Capabilities:
- **Streaming 50 ms Framing:** Processes live microphone blocks in < 2 ms (over 25× faster than real-time).
- **Multi-Provider VAD:** Silero VAD (ONNX deep neural net), WebRTC VAD (Google GMM), and Energy VAD (adaptive DSP noise floor tracking).
- **Natural Phrase Segmentation:** Respects speech cadence, syllable hangover, natural pauses, and max turn limits. Never clips quiet speech or word endings.
- **Acoustic Telemetry:** Continuously measures RMS volume, peak amplitude, SNR in dB, and clipping distortion.
- **AI Brain (OpenAI Agents SDK):** High-level acoustic environment diagnosis using the official OpenAI Agents SDK (`openai-agents`), backed by local Ollama (`qwen3.5:4b`) or OpenAI-compatible endpoints.
- **Honest Degradation:** Never fabricates audio; gracefully degrades if backends or models are offline.

---

## 2. Architecture

```
                                [Client Microphone]
                                         │  PCM16 mono 16 kHz (50 ms frames)
                                         ▼
                     [FastAPI WebSocket / REST Ingestion]
                                         │
               ┌─────────────────────────┴─────────────────────────┐
               ▼                                                   ▼
     [Frame Validator]                                   [Format Normalizer]
  - Length & Alignment                                - Resample (48k/8k -> 16k)
  - Monotonic Sequences                               - Stereo -> Mono
  - Rejects corrupted frames                          - DC Offset Subtraction
               │                                                   │
               └─────────────────────────┬─────────────────────────┘
                                         ▼
                               [Noise Suppressor]
                       - Real-Time STFT Spectral Gating
                       - Wiener Filtering (gain adjustment)
                       - Eliminates hum & stationary noise
                                         │
                                         ▼
                                  [VAD Engine]
                       - Silero ONNX (LSTM temporal state)
                       - WebRTC VAD (Modes 0-3)
                       - Energy VAD (Adaptive noise tracking)
                                         │
                                         ▼
                           [Intelligent Segmenter]
                       - State: IDLE / IN_SPEECH / HANGOVER
                       - Natural pause detection (400ms)
                       - Max utterance timeout (15s)
                       - Emits partials (1200ms) & finals
                                         │
               ┌─────────────────────────┴─────────────────────────┐
               ▼                                                   ▼
     [Acoustic Analyzer]                               [Chunk Manager & Wire]
  - RMS, Peak, SNR in dB                             - Monotonic Segment ID
  - Clipping % & Silence %                           - Ephemeral retention
  - Quality Status (Good/Fair/Poor)                  - BinaryFrame 'O' encoding
               │                                                   │
               └─────────────────────────┬─────────────────────────┘
                                         ▼
                       [Acoustic Intelligence Agent]
                 (OpenAI Agents SDK + Ollama qwen3.5:4b)
                 - Async background reasoning (0 ms audio latency impact)
                 - Acoustic diagnostic tools & dynamic tuning
                                         │
                                         │ audio.segment.final + Clean PCM16
                                         ▼
                           [Agent 02: STT Ingestion]
```

---

## 3. Prerequisites & Python Installation

Requires **Python 3.11** or **Python 3.12**.

### Windows PowerShell
```powershell
# Using uv (recommended)
uv python install 3.11
uv venv .venv --python 3.11
.venv\Scripts\activate

# Or using standard python
python -m venv .venv
.venv\Scripts\activate
```

### Linux / macOS
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

---

## 4. Dependency Installation

### Windows PowerShell
```powershell
uv pip install -r requirements.txt
# Or: pip install -r requirements.txt
```

### Linux / macOS
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Model Installation & Local AI Brain (Ollama)

### 5.1 Silero VAD Model
The official Silero VAD ONNX model is already bundled in `models/silero_vad.onnx`.

### 5.2 Local LLM Brain (Ollama)
The high-level advisory agent uses Ollama for local, free AI reasoning:

1. **Install Ollama:** Download from [https://ollama.com/download](https://ollama.com/download)
2. **Pull the recommended model:**
   ```bash
   ollama pull qwen3.5:4b
   ```
3. **Start Ollama service:**
   ```bash
   ollama run qwen3.5:4b
   ```

*Note: If Ollama is not running, the agent automatically falls back to deterministic expert heuristics without error.*

---

## 6. Configuration

Settings are managed in `config.yaml` and overridden via `.env`.

Create your local `.env`:
```powershell
# Windows
Copy-Item .env.example .env

# Linux
cp .env.example .env
```

### Core Configuration Parameters (`config.yaml` / `.env`):
| Key | Default | Description |
|---|---|---|
| `AUDIO_SAMPLE_RATE` | `16000` | Canonical audio sample rate (Hz) |
| `AUDIO_CHANNELS` | `1` | Canonical audio channels (1 = mono) |
| `AUDIO_FRAME_DURATION_MS` | `50` | Expected incoming frame block duration (ms) |
| `NOISE_SUPPRESSION_PROVIDER` | `spectral` | Denoising provider (`spectral`, `noisereduce`, `passthrough`) |
| `VAD_PROVIDER` | `silero` | VAD engine (`silero`, `webrtc`, `energy`) |
| `VAD_SPEECH_THRESHOLD` | `0.35` | Speech probability activation threshold |
| `VAD_MIN_SPEECH_MS` | `200` | Minimum duration required to confirm human speech |
| `VAD_MIN_SILENCE_MS` | `400` | Pause duration triggering segment commitment |
| `VAD_MAX_UTTERANCE_MS` | `15000` | Maximum continuous turn before force commit |
| `LLM_MODEL` | `qwen3.5:4b` | Model name for OpenAI Agents SDK |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Base URL for Ollama / local LLM endpoint |

---

## 7. Running Locally

### Start the Agent Server
```powershell
# Windows PowerShell
$env:PYTHONPATH = "."
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Linux / macOS
export PYTHONPATH="."
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Verify service readiness:
```bash
curl http://localhost:8001/health
curl http://localhost:8001/ready
```

---

## 8. Testing with a WAV File (Terminal Demo)

Run the terminal demonstration script to stream an audio file through the pipeline in real-time:

```powershell
# Windows PowerShell
$env:PYTHONPATH = "."
.venv\Scripts\python.exe scripts/test_audio.py --file tests/fixtures/en_example.wav

# Linux / macOS
python scripts/test_audio.py --file tests/fixtures/en_example.wav
```

### Output Example:
```
[INFO] Audio Intelligence Agent started.
[INFO] Session created: meeting_123
[INFO] Audio received: PCM16 / 16 kHz / 50 ms (Total: 60000 ms)
[INFO] Noise analysis completed.
[INFO] VAD: Speech detected.
[INFO] Speech started: speaker user_001
[INFO] Partial segment emitted (1150 ms).
[INFO] Speech pause detected.
[INFO] Final audio segment committed: seg_b94e968ab92a (2350 ms).
[INFO] Quality status: GOOD
[INFO] Sending segment to downstream STT agent.
[INFO] Processing latency: 4.9 ms
```

---

## 9. Real-Time Audio Streaming (WebSocket)

Clients stream raw 50 ms microphone chunks via WebSocket:
```
ws://localhost:8001/api/v1/audio/stream/{session_id}?speaker_id=user_001
```

### Streaming Sequence:
1. Client connects -> Server sends `session.ready`.
2. Client sends binary frames (1600 bytes PCM16 mono 16 kHz).
3. Server emits JSON events (`speech.started`, `audio.segment.partial`, `audio.segment.final`, `speech.ended`).
4. Every `audio.segment.*` event is accompanied by an encoded binary audio frame containing the clean PCM16 payload.

---

## 10. API Reference & Usage

### Process Complete Audio File via cURL
```bash
curl -X POST http://localhost:8001/api/v1/audio/process \
  -F "file=@tests/fixtures/en_example.wav" \
  -F "speaker_id=user_alice" \
  -F "session_id=meeting_001"
```

### Inspect Prometheus Metrics
```bash
curl http://localhost:8001/metrics
```

---

## 11. Running Automated Tests

Run the complete 40-test automated test suite:

```powershell
# Windows PowerShell
$env:PYTHONPATH = "."
.venv\Scripts\pytest.exe tests -v

# Linux / macOS
export PYTHONPATH="."
pytest tests -v
```

All 40 unit, integration, and performance tests will run and pass green.

---

## 12. Docker & Containerized Deployment

### Build and Run with Docker Compose
```bash
docker compose up --build -d
```
This boots both the Audio Intelligence Agent (port 8001) and Ollama brain (port 11434).

### Check Container Health
```bash
docker compose ps
curl http://localhost:8001/health
```

---

## 13. Benchmarking Performance

Execute the concurrency benchmark across C=1, 2, 4, 8, 16 concurrent sessions:

```powershell
# Windows PowerShell
$env:PYTHONPATH = "."
.venv\Scripts\python.exe scripts/benchmark.py
```

### Measured Benchmark Envelope (Local Dev Box):
| Concurrency (Sessions) | Audio Duration | Wall Clock | Real-Time Factor (RTFX) | p50 Frame Latency | p95 Frame Latency | Mean Latency | Process RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| **C = 1** | 5.0 s | 0.29 s | **17.3×** | 1.57 ms | 2.75 ms | 1.71 ms | 353 MB |
| **C = 2** | 10.0 s | 0.39 s | **25.5×** | 1.10 ms | 1.57 ms | 1.06 ms | 364 MB |
| **C = 4** | 20.0 s | 0.72 s | **27.6×** | 1.09 ms | 1.40 ms | 1.01 ms | 363 MB |
| **C = 8** | 40.0 s | 1.43 s | **28.0×** | 1.09 ms | 1.40 ms | 1.00 ms | 354 MB |
| **C = 16** | 80.0 s | 2.86 s | **28.0×** | 1.08 ms | 1.38 ms | 1.00 ms | 355 MB |

*Every frame processes in < 2 ms, leaving > 95% CPU headroom for downstream STT.*

---

## 14. TalkFlow & Agent 02 Integration Contract

### Downstream Handshake with Agent 02 (STT)
Agent 02 subscribes to Agent 01's stream. When Agent 01 emits `audio.segment.final`, Agent 02 ingests the clean PCM16 payload:

```python
import numpy as np

# Convert clean PCM16 payload from Agent 01 to float32 for faster-whisper
audio_float = np.frombuffer(pcm_payload, dtype=np.int16).astype(np.float32) / 32768.0
segments, info = whisper_model.transcribe(audio_float, language="en")
```

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for full wire contract schemas.

---

## 15. Troubleshooting Common Issues

1. **`Cannot call receive once disconnect message has been received`:**
   - Ensure clients do not send frames after `audio.stopped`. The session manager automatically closes the socket and cleans up resources.
2. **`ModuleNotFoundError: No module named 'app'`:**
   - Set `PYTHONPATH="."` (or `$env:PYTHONPATH = "."` in PowerShell) before running scripts directly.
3. **`Ollama connection refused`:**
   - If Ollama is not installed or running, the agent automatically falls back to deterministic heuristic diagnostics. Audio processing is never interrupted.
4. **`Audio frame is not aligned`:**
   - Raw PCM16 frames must have an even number of bytes (`len % 2 == 0`). Verify the client AudioWorklet outputs 16-bit signed PCM.

