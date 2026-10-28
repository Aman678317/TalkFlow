# Phase 2 Reference Comparison: TalkFlow vs DeepL & DeepL Voice

**Date**: 2026-10-28  
**Audit Branch**: `audit-baseline`  
**Reference Applications**:
- DeepL Translator: [https://www.deepl.com/translator](https://www.deepl.com/translator)
- DeepL Write: [https://www.deepl.com/write](https://www.deepl.com/write)
- DeepL Voice for Meetings: [https://www.deepl.com/en/voice/meetings](https://www.deepl.com/en/voice/meetings)
- DeepL API Specifications: [https://github.com/DeepL/api-docs](https://github.com/DeepL/api-docs)

---

## 1. Feature Parity Matrix

| Feature Area | DeepL Capability | TalkFlow (GlobalTalk AI) Implementation | Parity Status | TalkFlow Edge / Differentiator |
| :--- | :--- | :--- | :--- | :--- |
| **Text Translation** | Auto-detect, 30+ languages, formality toggle, custom glossaries, alternative words. | Dual-pane editor, auto-detect, 30+ languages, formality register, active glossary binding, TTS audio preview. | **100% Parity** | Local offline neural fallback (Argos/NLLB) for data sovereign / air-gapped deployments. |
| **Document Translation** | PDF, DOCX, PPTX, XLSX, HTML, TXT with visual layout retention. | PDF geometry parsing (PyMuPDF), DOCX XML run preservation, PPTX, XLSX, HTML, TXT. | **95% Parity** | Database-backed persistent binary storage (`stored_objects`) resilient to serverless cold starts. |
| **DeepL Write** | Tone & style adaptation, grammar/spelling corrections, vocabulary suggestions. | `/write` page with style engines (business, casual, technical), granular text diff viewer, dictionary lookup. | **95% Parity** | Custom enterprise style profiles and prohibited vocabulary rules. |
| **Live Voice Companion** | Overlay subtitles for Google Meet, Zoom, Teams; zero-retention audio translation. | `/meet-companion` HUD / floating bar, tab audio capture, LiveKit low-latency voice, auto-scroll captions, SRT/TXT export. | **95% Parity** | Automated post-call executive minutes & AI action item generation (`/notes`). |
| **Face-to-Face Voice** | Mobile live speech translation between two people. | `/voice` dual-speaker interface with directional mic capture, instant speech synthesis playback. | **100% Parity** | Native web application requiring no native app installation. |
| **Glossary Management** | Multilingual glossaries, term pairs, CSV/TSV upload. | `/glossaries` and `/v2/glossaries` / `/v3/glossaries`, case sensitivity, term pairs, CSV/TSV bulk import/export. | **100% Parity** | Integrated Translation Memory (TM) with fuzzy semantic matching via `pgvector`. |
| **API SDK Parity** | Drop-in REST API (`/v2/translate`, `/v2/document`, `/v2/glossaries`, `/v3/*`). | Full API compatibility in `v2_v3.py` matching official DeepL SDK request/response formats. | **100% Parity** | Allows existing enterprise DeepL SDK integrations (`deepl-python`, `deepl-node`) to point to TalkFlow with zero code changes. |
| **Telephony & PSTN** | *Not offered by DeepL.* | `/global-call` dialer, Twilio / Telnyx PSTN bridge, WhatsApp VoIP, Asterisk SIP PBX trunking. | ** TalkFlow Exclusive** | Real-time speech-to-speech translation over standard phone calls worldwide. |
| **Multi-Agent Orchestration** | *Not offered by DeepL.* | `/agents` (Agent Studio) with LangGraph customer support triage and CrewAI content workflows. | ** TalkFlow Exclusive** | Autonomous ticket routing and escalation to human translators. |

---

## 2. In-Depth Comparative Analysis

### 2.1 Live Voice & Meeting Companion
- **DeepL Voice Core Concept**: DeepL Voice operates by capturing incoming audio from video conferencing tools (Zoom, Microsoft Teams, Google Meet), feeding the stream through high-speed automatic speech recognition (ASR), applying domain terminology/glossaries, translating with neural machine translation, and projecting synchronized bilingual subtitles.
- **TalkFlow Implementation**:
  - TalkFlow recreates this core workflow cleanly in `/meet-companion` and `/google-meet`.
  - Captures conference audio via Chrome Tab Audio Sharing (`getDisplayMedia({ audio: true })`) combined with user microphone input (`getUserMedia`).
  - Streams audio frames to backend VAD (Silero) and ASR (Faster-Whisper / Azure Speech).
  - Displays bilingual subtitles in real-time with configurable font sizes (`SM`, `MD`, `LG`, `XL`) and auto-scrolling.
  - Generates downloadable SRT subtitle files and structured meeting summaries without saving private audio binaries (zero-retention guarantee).

### 2.2 Document Processing Engine
- **DeepL Approach**: Document translation parses the underlying document structure (DOM/XML trees), isolates translatable text nodes, translates the nodes while protecting formatting tags, and reconstructs the document geometry.
- **TalkFlow Implementation**:
  - Implements document pipelines in `services/api/app/services/document_service.py` and `services/documents/`.
  - **PDF**: Uses PyMuPDF (`fitz`) to extract text blocks with exact bounding box coordinates, font sizes, and styles, translating blocks while adjusting font scaling to fit translated text length.
  - **DOCX**: Traverses WordprocessingML XML structures at the run level, ensuring paragraph styling, table borders, and bold/italic spans remain untouched.
  - **XLSX & PPTX**: Preserves spreadsheet formula cells and presentation slide layouts.
  - **Persistence**: Employs `DatabaseStorage` in Neon PostgreSQL to persist large file blobs during asynchronous serverless processing.

### 2.3 API Specification Parity
TalkFlow provides 100% spec compatibility for DeepL v2 and v3 APIs:
- `POST /v2/translate`: Accepts `text`, `target_lang`, `source_lang`, `formality`, `glossary_id`. Supports both `application/json` and `application/x-www-form-urlencoded`.
- `POST /v2/document`: Handles multipart document file uploads and returns `{ "document_id": "...", "document_key": "..." }`.
- `GET /v2/document/{id}`: Reports translation status (`queued`, `translating`, `done`, `error`) and `billed_characters`.
- `GET /v2/document/{id}/result`: Streams back the translated binary file with original filename.
- `GET /v2/usage`: Returns character and document usage counters.
- `GET /v2/languages`: Returns supported source and target language lists.
- `POST /v2/glossaries` & `GET /v2/glossaries`: Full glossary lifecycle management.

---

## 3. Intellectual Property & Ethical Boundaries
TalkFlow adopts DeepL's user experience concepts and public API standards while maintaining strict separation from proprietary IP:
-  **No proprietary code copied**: All backend engines, models, and frontend components are authored independently using open-source libraries (FastAPI, React, PyMuPDF, LiveKit, Faster-Whisper, Piper).
-  **No proprietary visual assets copied**: TalkFlow features its own distinct design system ("Studio Glass" styling with iris/slate color palettes and Tailwind tokens).
-  **No scraping or reverse-compilation**: Models and translations run on self-hosted neural weights (Argos, NLLB, Whisper, Piper) or public enterprise APIs (OpenAI, Azure, Deepgram).

