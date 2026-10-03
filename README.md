# GlobalTalk AI

<div align="center">

> **One shared conversation. Every participant speaks and hears their own language.**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![React](https://img.shields.io/badge/react-18-61DAFB)
![FastAPI](https://img.shields.io/badge/fastapi-0.100%2B-009688)
![TypeScript](https://img.shields.io/badge/typescript-strict-3178C6)
![Status](https://img.shields.io/badge/status-active-brightgreen)

</div>

---

## 🌍 What is GlobalTalk AI?

**GlobalTalk AI** is a production-ready, open-source multilingual AI communication platform.  
Break language barriers in real-time — everyone in a conversation speaks their own language and hears the others in theirs.

**Core capabilities:**

| Feature | Description |
|---|---|
| 🎙️ **Real-Time Voice Translation** | WebRTC / WebSocket PCM stream → VAD → STT → NMT → TTS, per-listener, <1 s end-to-end |
| 📝 **Text Translation** | Standard Desi-compatible v2 API: formality, glossaries, tag handling, context |
| ✍️ **AI Writing Assistant** | Style/tone adaptation (Business, Academic, Casual) + grammar/spelling corrections |
| 📄 **Document Translation** | DOCX, PPTX, XLSX, PDF, TXT, HTML — layout-preserving, async jobs |
| 💬 **Multilingual Chat** | Per-listener translated chat in real-time meetings |
| 🎬 **Transcript & Subtitle Exporter** | Export live speech & meetings in `.srt`, `.vtt`, `.txt`, and `.json` with standard timecodes |
| 🌐 **SEO & AI Search (GEO) Ready** | Schema.org `WebApplication` JSON-LD, OpenGraph, `sitemap.xml`, `robots.txt`, and `llms.txt` |
| 📚 **Glossaries & Translation Memory** | Custom term pairs, fuzzy TM matching, bilingual export |
| 🔑 **Developer API** | v2 + v3 conformant REST API with auth, metering, usage analytics, webhooks |
| 🛡️ **Teams / RBAC / Admin** | Organizations, roles, audit logs, API key scopes, admin dashboard |

---

## 🏛️ Core Architectural Rule — The Canonical Source

```
Human mic → WebRTC/LiveKit or WS audio → VAD → streaming STT → language ID
        → CANONICAL SOURCE SEGMENT (immutable)
        → Translation fan-out (dedup per target language)
        → per-language TTS → Listener Router → each participant hears their language
```

**Human speech or text is the only semantic source of truth.**  
Translation chains (Hindi → English → Japanese) are **forbidden by design**.  
Each listener language is translated independently from the canonical source (Hindi → {English, Japanese, Marathi}).

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 · Vite · TypeScript (strict) · Tailwind CSS · TanStack Query · Zustand |
| **Backend** | Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic |
| **Database** | PostgreSQL (prod) / SQLite (dev), pgvector-ready |
| **Cache / Queue** | Redis (prod) / in-process (dev) |
| **Storage** | S3/MinIO (prod) / local FS (dev) |
| **Realtime Media** | LiveKit SFU (prod) / WebSocket PCM (dev, fully functional) |
| **AI (self-hosted)** | faster-whisper · Argos NMT · Kokoro-ONNX TTS · Silero VAD · fastlangid |

All AI providers are behind **protocol interfaces + a model router** with capability registry,  
fallback chains, and honest health reporting. **No closed-LLM hard dependency.**

---

## 🚀 Quick Start (Local — No Docker Required)

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/globaltalk-ai.git
cd globaltalk-ai
```

### 2. Backend (Python)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r services/api/requirements.txt
cp .env.example .env          # edit API keys as needed
python run_api.py              # starts on http://127.0.0.1:8088
```

> **API Docs:** http://127.0.0.1:8088/api/docs (Swagger UI)

### 3. Frontend (Node.js)

```bash
cd apps/web
npm install
npm run dev                    # starts on http://localhost:5173
```

### 4. One-Click Launcher (Windows)

```bat
.\START_ALL.bat
```

Launches both backend and frontend in separate terminal windows.

---

## 🖥️ Application Pages

| Route | Feature |
|---|---|
| `/` | Landing page |
| `/translate` | Text translator (language auto-detect, formality, glossaries) |
| `/write` | GlobalTalk Write — AI writing assistant |
| `/voice` | GlobalTalk Voice Studio — real-time speech-to-speech translation |
| `/documents` | Document translation upload/download |
| `/meetings` | Virtual multilingual meetings |
| `/meeting/:id` | Live meeting room (WebRTC + live captions) |
| `/glossaries` | Glossary manager |
| `/history` | Translation history & transcript archive |
| `/usage` | API usage dashboard |

---

## 🔌 API Reference (Desi v2/v3 Standard Conformance)

GlobalTalk AI implements full drop-in compatibility with the official `desi-python` SDK / Desi wire protocol:

```python
import gt_ai as desi

client = desi.Client("gtk_live_api_key", server_url="http://127.0.0.1:8088")
result = client.translate_text("Hello world!", target_lang="DE")
print(result.text)  # "Hallo Welt!"
```

| Endpoint | Method | Description |
|---|---|---|
| `/v2/translate` | `POST` | Text translation (formality, glossaries, TM, context, tag-handling) |
| `/v2/write/rephrase` | `POST` | AI writing assistant: style & tone improvement |
| `/v2/write/correct` | `POST` | AI writing assistant: grammar & spelling correction (v1.32.0) |
| `/v2/document` | `POST` | Upload document for async translation |
| `/v2/document/{id}` | `GET`, `POST` | Poll document translation status |
| `/v2/document/{id}/result` | `GET`, `POST` | Download translated document file |
| `/v2/languages` | `GET` | Supported source & target languages |
| `/v2/usage` | `GET` | Character, document, and team document quotas & usage |
| `/v2/glossary-language-pairs` | `GET` | Supported language pairs for glossaries |
| `/v2/glossaries` | `POST`, `GET`, `DELETE` | v2 Monolingual glossaries |
| `/v3/glossaries` | `POST`, `GET`, `PATCH`, `DELETE` | v3 Multilingual glossaries & dictionary management |
| `/v3/style_rules` | `POST`, `GET`, `PATCH`, `DELETE` | v3 Style rules & custom instructions |
| `/v3/translation_memories` | `GET`, `DELETE` | v3 Translation memories listing & segments |
| `/v3/translation_memories/import` | `POST`, `PUT` | v3 TMX translation memory import jobs |
| `/v3/translation_memories/export` | `POST`, `GET` | v3 TMX translation memory export & download |
| `/v3/voice/realtime` | `POST`, `GET` | Request & reconnect real-time voice streaming sessions |
| `/v3/spoken-terms` | `POST`, `GET` | Domain vocabulary collections for speech recognition |
| `/v2/admin/analytics/custom-tags` | `GET` | Tag-based usage analytics |

Full interactive OpenAPI documentation available at **http://127.0.0.1:8088/api/docs**.

---

## ✅ Verified Capability Status (CPU Sandbox — 2 cores / 1 GiB RAM)

| Capability | Status |
|---|---|
| Auth (signup / login / token refresh / sessions), orgs, RBAC, tenant isolation | ✅ |
| Text translation with real offline NMT, TM, glossaries, styles, metering | ✅ |
| Language detection (audio: Whisper LID · text: langid+script fusion) | ✅ |
| Documents: TXT/DOCX/PDF translated & reconstructed (headings/tables kept) | ✅ |
| Realtime golden call: 5 WS participants, real speech → canonical transcript → fan-out → TTS | ✅ |
| Honest degradation for unsupported pairs (`translation.failed`, recoverable) | ✅ |
| Agent-to-agent bridge (canonical source → independent per-agent projections) | ✅ |
| BLEU/WER/CER evaluation gates | ✅ |
| LiveKit, pgvector, vLLM, Kokoro, Docling, Seamless | 🔌 adapters present; configure via `.env` |

---

## 🎬 Golden Demo

Open `/meetings` → Create a meeting → Open in 3 browser tabs:

| Participant | Speaks | Hears |
|---|---|---|
| A | Hindi | English |
| B | English | Hindi |
| C | Japanese | Marathi (captions) |

A speaks Hindi → B hears English, C sees Marathi captions, transcripts stored, chat translated per-listener, state survives reconnect, AI can summarize.

---

## 📖 Documentation

| Document | Description |
|---|---|
| [`developer-docs/`](developer-docs/) | Mintlify interactive developer portal |
| [`api-specs/`](api-specs/) | Public OpenAPI 3.1.0 & AsyncAPI 3.0.0 authoritative specification mirror |
| [`cli/desi-cli/`](cli/desi-cli/) | Official Desi CLI: 100+ global & 22 Indic languages, honorifics, sync, write, voice |
| [`sdk/README.md`](sdk/README.md) | Official Client SDKs Directory & Parity Matrix |
| [`sdk/python/desi-python/`](sdk/python/desi-python/) | Official Desi Python SDK (Python 3.9+, sync & async `httpx`) |
| [`sdk/typescript/`](sdk/typescript/) | Official GlobalTalk & Desi TypeScript / Node.js SDK (`@globaltalk/sdk`) |
| [`sdk/java/desi-java/`](sdk/java/desi-java/) | Official Desi Java SDK (Java 11+, zero runtime dependencies) |
| [`sdk/dotnet/Desi/`](sdk/dotnet/Desi/) | Official Desi .NET C# SDK (`netstandard2.0`, `net6.0`, `net8.0`) |
| [`mcp/desi-mcp-server/`](mcp/desi-mcp-server/) | Stdio MCP Server for Claude Code, Cursor, and VS Code |
| [`plugins/desi-claude-plugin/`](plugins/desi-claude-plugin/) | Official Claude Plugin exposing Desi translation, writing, glossaries, and docs |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture & design decisions |
| [`docs/api.md`](docs/api.md) | Internal API reference |
| [`docs/AI.md`](docs/AI.md) | AI provider system, model router, fallback chains |
| [`docs/REALTIME.md`](docs/REALTIME.md) | WebSocket protocol & realtime pipeline |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Schema & migration guide |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Docker, k8s, cloud deployment |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Security model |
| [`docs/LOCAL_DEVELOPMENT.md`](docs/LOCAL_DEVELOPMENT.md) | Full local dev setup |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy & running tests |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Common issues & fixes |

---

## 🤝 Contributing

Contributions are welcome! Please read [`CONTRIBUTING.md`](.github/CONTRIBUTING.md) and our [Code of Conduct](.github/CODE_OF_CONDUCT.md) before opening a PR.

---

## 📦 Packaging

To create a complete full-stack ZIP archive (excluding `node_modules` and caches):

```bat
.\CREATE_ZIP.bat
```

Output: `globaltalk-ai-fullstack.zip`

---

## 📄 License

This project is licensed under the **MIT License** — see the [`LICENSE`](LICENSE) file for details.