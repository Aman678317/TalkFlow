# TalkFlow Audio Intelligence Agent (Agent 01) — Architecture

## 1. System Overview & Purpose

The **Audio Intelligence Agent (Agent 01)** is the ingestion and acoustic preprocessing gateway of the TalkFlow / GlobalTalk real-time multilingual communication platform.

Its primary responsibility is to receive raw, continuous microphone audio from diverse clients (Web Audio AudioWorklet, LiveKit WebRTC, mobile browsers, PSTN), validate and normalize the stream, eliminate background acoustic noise, reliably detect speech vs. silence boundaries, intelligently segment continuous speech into coherent conversational utterances, compute acoustic quality telemetry, and emit cleanly formatted, timestamped audio chunks for **Agent 02: Speech Recognition Agent (STT)**.

```
+-------------------------------------------------------------------------+
|                           CLIENT TIER                                   |
|   Web Browser (AudioWorklet) / LiveKit WebRTC / Mobile / Local WAV      |
+-------------------------------------------------------------------------+
                                    │
                                    │ PCM16 16 kHz (50 ms blocks) / TalkFlow BinaryFrame
                                    ▼
+─────────────────────────────────────────────────────────────────────────+
|                  AGENT 01: AUDIO INTELLIGENCE AGENT                     |
|                                                                         |
|  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   |
|  │ Audio Ingestion  │───►│ Format           │───►│ Real-Time        │   |
|  │ & Validation     │    │ Normalizer       │    │ Noise Gate & DSP │   |
|  └──────────────────┘    └──────────────────┘    └──────────────────┘   |
|                                                            │            |
|                                                            ▼            |
|  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   |
|  │ Chunk Lifecycle  │◄───│ Intelligent      │◄───│ VAD Engine       │   |
|  │ & Ephemeral Store│    │ Speech Segmenter │    │ (Silero/WebRTC)  │   |
|  └──────────────────┘    └──────────────────┘    └──────────────────┘   |
|           │                       │                                     |
|           ▼                       ▼                                     |
|  ┌──────────────────┐    ┌──────────────────────────────────────────┐   |
|  │ Acoustic Quality │    │ OpenAI Agents SDK Advisory Agent (Async) │   |
|  │ Analyzer         │    │ (Ollama qwen3.5:4b / OpenAI-compatible)  │   |
|  └──────────────────┘    └──────────────────────────────────────────┘   |
+─────────────────────────────────────────────────────────────────────────+
                                    │
                                    │ audio.segment.partial / audio.segment.final
                                    │ + Clean PCM16 mono audio payload
                                    ▼
+-------------------------------------------------------------------------+
|                  AGENT 02: SPEECH RECOGNITION AGENT (STT)               |
|      (faster-whisper / IndicConformer streaming transcription)          |
+-------------------------------------------------------------------------+
```

---

## 2. Audio Pipeline Stages (50 ms Processing Loop)

Every incoming 50 ms audio block traverses the following stages within a strict < 5 ms compute budget:

1. **Ingestion & Validation (`app/audio/validation.py`):**
   - Frame length and multi-channel byte alignment enforcement (`len % (channels * 2) == 0`).
   - Monotonic sequence verification (`current_seq > last_seq`) with duplicate and out-of-order rejection.
   - Bounded frame size limits (up to 8192 bytes).
2. **Format Normalization (`app/audio/normalization.py`):**
   - Canonical format target: **16000 Hz, mono (1 channel), signed 16-bit little-endian PCM (`pcm_s16le`)**.
   - Polyphase resampler (`scipy.signal.resample_poly`) converts non-standard rates (48 kHz, 44.1 kHz, 8 kHz) to 16 kHz without spectral distortion.
   - Stereo to mono downmixing (`(L + R) / 2`).
   - DC offset subtraction (mean removal) to prevent DC bias from corrupting zero-crossing and VAD models.
3. **Voice Activity Detection (`app/providers/vad/`):**
   - Pluggable provider architecture:
     - **Silero VAD (Default):** Deep neural network VAD via ONNX runtime, processing stateful 512-sample windows with temporal LSTM memory.
     - **WebRTC VAD:** Multi-rate statistical GMM VAD evaluating 10ms and 20ms sub-frames across aggressiveness modes 0 to 3.
     - **Energy VAD:** Real DSP RMS calculation with continuous adaptive noise floor tracking (`noise_floor = 0.95 * noise_floor + 0.05 * rms`).
4. **Noise Detection & Suppression (`app/providers/noise_suppression/`):**
   - Pluggable suppressors:
     - **Spectral Gating (Default):** Real-time STFT spectral subtraction and Wiener filtering (`gain = psd / (psd + oversub * noise_psd)`). Smooths stationary hiss and fans without cutting low-energy consonants.
     - **Noisereduce:** Stationary spectral gating using the `noisereduce` library.
     - **Passthrough:** Transparent bypass for raw baseline benchmarking.
5. **Intelligent Speech Segmentation (`app/audio/segmentation.py`):**
   - State machine tracking `IDLE`, `IN_SPEECH`, and `IN_HANGOVER`.
   - Natural pause detection (configurable silence hangover, default 400 ms).
   - Minimum speech duration filter (default 200 ms) discarding clicks, bumps, and coughs.
   - Maximum utterance duration enforcement (default 15 s) force-committing long monologues to ensure continuous translation.
   - Mid-speech phrase boundary detection (commits at natural energy dips after phrase intervals).
   - Incremental partial chunk emission (default every 1200 ms).
6. **Acoustic Quality Analysis (`app/audio/quality.py`):**
   - Computes RMS volume, peak amplitude, estimated SNR in dB, clipping percentage, and silence ratio.
   - Classifies quality status into `good`, `fair`, or `poor` with descriptive diagnostic issue codes.
7. **Chunk Persistence & Delivery (`app/audio/chunk_manager.py` & `app/integration/`):**
   - Assigns unique, monotonic segment identifiers (`seg_<uuid>`).
   - Packages metadata according to TalkFlow protocol contracts.
   - Delivers payloads via WebSocket binary frames or ephemeral memory/disk storage references.

---

## 3. High-Level AI Intelligence (OpenAI Agents SDK)

To combine deterministic low-latency DSP with model-based reasoning, the agent employs the **OpenAI Agents SDK (`openai-agents`)**:

- **Decoupled Execution:** The LLM agent runs completely out-of-band in an asynchronous task triggered upon segment commitment. It **never runs inside the 50 ms real-time audio loop**, guaranteeing **0 ms latency impact** on streaming audio.
- **Tools Attached to Agent:**
  - `assess_acoustic_environment`: Evaluates SNR, clipping, noise floor, and speech envelope.
  - `recommend_tuning_action`: Formulates dynamic DSP tuning recommendations (e.g., increase spectral attenuation, decrease mic gain).
  - `flag_segment_for_review`: Flags compromised audio segments for quality audit.
- **Provider Agnostic & Offline-First:** Configured via `.env` with `LLM_MODEL=qwen3.5:4b` and `LLM_BASE_URL=http://localhost:11434/v1` for local Ollama deployment.
- **Honest Degradation:** If Ollama or the configured LLM endpoint is unreachable, the agent falls back to a deterministic expert heuristic diagnostic system without failing the meeting.

---

## 4. Multi-Tenant Safety & Privacy Invariants

- **Zero Unnecessary Audio Retention:** Default retention policy is `ephemeral`. Audio buffers are held in memory during the utterance and freed immediately upon delivery to Agent 02.
- **Sanitized Temporary Files:** In `debug_disk` mode, audio files are isolated in `temp_audio/<session_id>/` and completely removed upon session termination.
- **Tenant Isolation:** Every event, segment, log, and metric carries strict session and speaker scoping (`session_id`, `conversation_id`, `speaker_id`).
- **Credential Protection:** Secrets and tokens are loaded strictly from `.env` and are never logged or exposed in client payloads.

