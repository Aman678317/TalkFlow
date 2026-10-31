# TalkFlow Neural Translation Agent (Agent 04)

> **Agent 04** in the TalkFlow Real-Time Multilingual Communication Platform.  
> Translates canonical human speech transcripts into requested target languages independently with zero translation chains.

---

## 1. Role in the Multi-Agent Architecture

```
Agent 01: Audio Intelligence Agent (Port 8001)
   │
   ▼ [ audio.segment.final ]
Agent 02: Speech Recognition Agent (Port 8002)
   │
   ▼ [ transcript.final ]
Agent 03: Language Intelligence Agent (Port 8003)
   │
   ▼ [ language.analysis.final ]
Agent 04: Neural Translation Agent (Port 8004)  ◄── (THIS AGENT)
   │
   ▼ [ translation.final ]
Agent 05: Translation Quality Agent (Port 8005)
   │
   ▼
Agent 06: Voice Generation Agent (Port 8006)
   │
   ▼
Agent 07: Audio Synchronization & Delivery Agent (Port 8007)
```

Agent 04 ingests the canonical speech transcript and source-language analysis from **Agent 03**, validates language pairs, executes zero-pivot multi-target translation, restores protected spans and glossaries, and emits `translation.final` events to **Agent 05**.

---

## 2. Core Architectural Features

1. **Zero-Pivot Multi-Target Translation**: Every listener language is translated directly and independently from the canonical human source transcript. Never chained (`hi -> en -> mr`).
2. **Listener Deduplication**: If multiple meeting participants listen in the same language (e.g. 5 listeners in English), only **1** MT inference job is executed and shared.
3. **Same-Language Identity Rule**: If `source_lang == target_lang`, the original text is returned verbatim with `source_equals_target`, incurring zero MT model cost.
4. **Hinglish & Code-Switching Handling**: Understands mixed-language speech (e.g. *"Aaj hum new AI project discuss karenge"*) and preserves English technical terms while translating the matrix language.
5. **SpanProtector**: Reversible placeholders prevent URLs, emails, code blocks, ticket IDs, numbers, and currencies from being corrupted during seq2seq generation.
6. **Multi-Tenant Glossaries & Translation Memory**: Approved exact matches and fuzzy matches bypass MT generation; tenant terminology is enforced.
7. **Operational Reasoning Brain**: Uses the OpenAI Agents SDK and local Ollama (`qwen3.5:4b`) for out-of-band diagnostics and telemetry monitoring without sitting in the real-time path.

---

## 3. Quick Start

### A. Windows PowerShell
```powershell
# Navigate to agent directory
cd "i:\vioces agent\neural-translation-agent"

# Run tests
& "i:\vioces agent\.venv\Scripts\pytest.exe" -v

# Start the agent service on Port 8004
& "i:\vioces agent\.venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8004 --reload
```

### B. Linux / macOS
```bash
cd neural-translation-agent
pytest -v
uvicorn app.main:app --host 127.0.0.1 --port 8004 --reload
```

### C. Web Dashboard
Open your browser at:
```
http://127.0.0.1:8004
```
Features an interactive test console for Single-Target MT, Multi-Target Fan-Out, Hinglish Code-Switching, and Language Pair Capability inspections.

---

## 4. REST & WebSocket API Specification

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Basic service liveness |
| `/ready` | GET | Provider readiness |
| `/metrics` | GET | Prometheus telemetry metrics |
| `/api/v1/agent/info` | GET | Metadata, active models, uptime |
| `/api/v1/translation/translate` | POST | Single-target translation |
| `/api/v1/translation/batch` | POST | Multi-target independent fan-out |
| `/api/v1/translation/validate` | POST | Language pair readiness check |
| `/api/v1/translation/agent03/transcript` | POST | Webhook for Agent 03 transcript events |
| `/api/v1/translation/stream/{session_id}` | WebSocket | Real-time provisional & final streaming |

---

## 5. Evaluation & Benchmarking

```powershell
# Run language pair quality evaluation (BLEU, chrF++, entity preservation)
& "i:\vioces agent\.venv\Scripts\python.exe" scripts/evaluate_language_pairs.py

# Run latency and multi-target fan-out benchmarks
& "i:\vioces agent\.venv\Scripts\python.exe" scripts/benchmark_translation.py

# Run CLI translation test
& "i:\vioces agent\.venv\Scripts\python.exe" scripts/test_translation.py --text "नमस्ते दोस्तों" --source hi --target en
```

---

## 6. Model Licenses & Production Guidelines

- **Argos Translate**: MIT License (Code), Creative Commons (OpenNMT models). Completely offline CPU translation.
- **MarianMT / OPUS-MT**: MIT License (Code), CC BY 4.0 (Pretrained Checkpoints). Direct en<->mr pairs.
- **MADLAD-400**: Apache 2.0 (Google). 400+ languages, recommended on GPU.
- **NLLB-200**: **CC BY-NC 4.0 (Non-Commercial Research Only)**. Must NOT be deployed commercially without explicit licensing approval.
- **DeepL / Azure Translator**: Commercial cloud APIs. Disabled when `tenant_private_only=True`.

