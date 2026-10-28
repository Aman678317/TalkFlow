# Phase 0 Baseline Audit: TalkFlow (GlobalTalk AI)

**Date**: 2026-10-28  
**Audit Branch**: `audit-baseline` (branched from `main` at `1ee5c36`)  
**Base Commit SHA**: `1ee5c3689968e49485b1ec7aa38b7c4a42fec0d1`  
**Repository**: [https://github.com/Aman678317/TalkFlow](https://github.com/Aman678317/TalkFlow)  
**Deployed Staging/Production**: [https://feat-vercel-multi-service.vercel.app/](https://feat-vercel-multi-service.vercel.app/)  
**Operating Environment**: Windows 11 (64-bit)  
**Runtimes**:
- **Node.js**: `v26.12.1`
- **npm**: `11.20.0`
- **Python**: `3.14.2`
- **pip**: `25.0.1`
- **Git**: `2.52.0.windows.1`

---

## 1. System Inventory

TalkFlow is a multi-service, multi-tenant enterprise real-time speech-to-speech, text, and document translation platform designed with a DeepL / DeepL Voice core concept parity model.

### 1.1 Components & Services
| Subsystem | Location | Technologies / Framework | Purpose |
| :--- | :--- | :--- | :--- |
| **Frontend SPA** | `apps/web` | React 18, Vite 5, Tailwind CSS, TanStack Query, Lucide, LiveKit Client SDK | User-facing dashboard, text/web translation, write assistant, document translation, live voice companion, meetings studio, telephony dialer, admin and developer keys. |
| **Canonical API Backend** | `services/api` | FastAPI 0.115+, SQLAlchemy 2.0 (async), Pydantic v2, PostgreSQL / SQLite | Multi-tenant REST & WebSocket API, auth, billing, glossaries, translation memory, meetings, telephony, document parsing, v2/v3 DeepL parity. |
| **Legacy Bridge API** | `apps/api` | FastAPI | Separate legacy migration lineage and compatibility endpoints. |
| **AI Subsystem** | `ai/` (`gt-ai`) | Argos Translate, NLLB, OpenAI, Azure, DeepL Parity, Groq, Piper TTS, Whisper STT | Unified provider abstraction layer, fallback cascades, prompt templating, and model caching. |
| **V2V Connect Webapp** | `apps/amazon-connect-v2v` | Vite, React | Telephony & Amazon Connect agent voice-to-voice stream bridge. |
| **Workers** | `workers/` | Python Background Workers | Document worker, inference worker, metering worker, cleanup worker. |
| **Multi-Agent Portfolio** | `multi-agent-portfolio` | LangGraph, CrewAI | Multi-agent studio triage, content pipeline, and research crew engines. |

### 1.2 Data Tier & Cloud Storage
- **Relational Database**: PostgreSQL 16 with `pgvector` extension (Hosted on Neon serverless PostgreSQL at `ep-calm-hill-ao5en1qf-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?ssl=require`). Fallback to local SQLite in local test environments.
- **Storage Subsystem**: `DatabaseStorage` storing file binaries and metadata persistently in `stored_objects` table in Neon PostgreSQL with local `/tmp` caching for serverless execution.
- **Cache & Message Broker**: Redis 7 / in-memory fallback for local dev.
- **Media & Signaling**: LiveKit Cloud / self-hosted LiveKit WebRTC server, Asterisk ARI / SIP telephony integration, baresip.

---

## 2. Baseline Test Execution Results

All tests executed from the baseline commit prior to making audit remediations.

### 2.1 Frontend (`apps/web`)
- **Unit & Component Tests (`vitest run`)**:
  - Test Files: **39 passed** (39 total)
  - Tests: **307 passed** (307 total)
  - Duration: **47.96s**
  - Result: **100% PASS**
- **TypeScript Typecheck (`npx tsc -b`)**:
  - Command: `npx --node-options=--max-old-space-size=4096 tsc -b`
  - Output: Clean exit code 0, 0 type errors.
- **Production Build (`vite build`)**:
  - Output: 2,456 modules transformed, 30 SPA static route stubs generated + `404.html`.
  - Build Duration: **12.01s**
  - Bundle size: Vendor bundle 157.15 kB (gzip 51.45 kB), LiveKit bundle 561.71 kB (gzip 147.25 kB).

### 2.2 Python Backend (`services/api` & `tests/`)
- **Static Code Analysis (`ruff check`)**:
  - Command: `python -m ruff check apps/api ai services scripts --select E9,F --ignore F401,F841,F541`
  - Result: **All checks passed (0 errors)**.
- **Fast Unit Tests (`tests/unit`)**:
  - Command: `python -m pytest tests/unit -q`
  - Result: **320 passed in 64.14s (0 failures)**.
- **Integration Tests (`tests/integration`)**:
  - Command: `python -m pytest tests/integration -q`
  - Result: **48 passed, 2 skipped in 58.27s (0 failures)**.
- **Total Test Inventory**:
  - Command: `python -m pytest --collect-only -q`
  - Total collected tests across all suites: **1,105 tests**.

---

## 3. Known Pre-Existing Failures & Anomalies

1. **Storage Mock Mismatch in Hardened Test Suite**:
   - `tests/test_production_readiness_hardened.py::test_readiness_probe_fails_closed_on_dependency_failure`
   - *Failure*: Line 74 `assert resp.status_code == 503` (received 200).
   - *Root Cause*: The test mocked `app.storage.LocalStorage.ping`, but `init_storage()` initialized `DatabaseStorage` when a database connection string was present. The mock did not affect `DatabaseStorage.ping()`.
2. **SQLite Contention in Concurrency Tests**:
   - `tests/test_realtime_security_hardened.py` produces `sqlite3.OperationalError: database is locked` when run against SQLite due to parallel connection contention. Documented in CI configuration to run strictly against PostgreSQL.
3. **Vercel Ephemeral Lifecycle**:
   - Long-lived background loops freeze when serverless HTTP responses complete. Resolved for document translation by combining `DatabaseStorage` with FastAPI `BackgroundTasks` and client polling kickstarters.

---

## 4. Audit Baseline Sign-off
- Repository is clean, builds pass, and all baseline test metrics are recorded.
- Fixes and enhancements will be executed strictly on dedicated branches with reviewable diffs and test verification.
