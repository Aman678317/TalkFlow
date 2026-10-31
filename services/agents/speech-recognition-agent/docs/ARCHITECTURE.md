# TalkFlow Speech Recognition Agent (Agent 02) — Architecture Document

## 1. System Overview

Agent 02 is responsible for transcribing clean, timestamped audio segments produced by Agent 01 (Audio Intelligence Agent) and emitting structured partial and final transcript events for Agent 03 (Language Intelligence Agent).

### Key Architectural Boundaries:
1. **Deterministic Speech-to-Text Pipeline**: The speech recognition pipeline (`faster-whisper` + CTranslate2) processes audio deterministically without any LLM in the audio inference path.
2. **Out-of-Band Operational Intelligence**: The OpenAI Agents SDK coupled with local Ollama (`qwen3.5:4b`) runs as an operational control-plane assistant to diagnose service health, analyze latency metrics, and recommend hardware-tuned model configurations.
3. **Decoupled Identity Management**: Agent 02 preserves session, speaker, utterance, and segment IDs received from Agent 01 without inventing conflicting global event sequences.

```mermaid
flowchart TD
    subgraph Inbound ["Inbound from Agent 01"]
        A[Clean 16kHz PCM16 Chunks\nFrom Agent 01 /audio/stream or /segment] --> B[Audio Ingestion & Sequence Guard]
    end

    subgraph CoreEngine ["Speech Recognition Core Engine"]
        B --> C{Streaming or Batch?}
        C -->|Streaming| D[Partial Manager\n500ms sliding window\nRevision tracking]
        C -->|Final Segment| E[Finalizer Engine\nCTranslate2 Whisper / Mock]
        D --> F[Anti-Hallucination & Repetition Filter]
        E --> F
        F --> G[Word-Level Alignment & Timeline Conversion]
        G --> H[Language Hint Extraction]
    end

    subgraph Outbound ["Outbound to TalkFlow & Agent 03"]
        H -->|transcript.partial| I[TalkFlow Realtime Captions]
        H -->|transcript.final| J[Agent 03: Language Intelligence Agent]
    end

    subgraph OutOfBand ["Out-of-Band Control Plane"]
        K[OpenAI Agents SDK Brain\nOllama qwen3.5:4b] -.->|Operational Diagnostics| L[Prometheus Metrics & Health]
    end
```

