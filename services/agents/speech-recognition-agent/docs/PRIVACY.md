# Privacy & Security Policy — Speech Recognition Agent (Agent 02)

## 1. Zero External Audio Leakage
All speech recognition runs entirely on-premise / locally via `faster-whisper` (CTranslate2) or local ONNX runtime. Audio frames are never forwarded to third-party public clouds or unauthenticated endpoints.

## 2. Ephemeral In-Memory Buffering
- Audio frames received via streaming WebSocket or REST are held in memory only for the duration of the utterance.
- Upon utterance finalization or disconnect, audio buffers are cleared (`del` + garbage collection).

## 3. Operational Reasoning Privacy
- The OpenAI Agents SDK operational brain connects to your locally hosted Ollama instance (`qwen3.5:4b`) by default.
- Operational telemetry queries only inspect metadata (latency, queue depth, CPU threads, model availability). Raw speech transcripts and private audio are NEVER passed to the reasoning LLM.

