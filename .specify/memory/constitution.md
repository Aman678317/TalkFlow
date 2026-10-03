# GlobalTalk AI / TalkFlow Constitution

## Core Principles

### I. Immutable Canonical Source of Truth
Human speech or direct user text is the **only** semantic source of truth.
- When speech is captured and transcribed, it forms an immutable canonical source segment.
- Transcripts, translations, TTS audio, summaries, and AI agent projections are derivative artifacts.
- The final source segment is immutable, ensuring transcript consistency, data integrity, and compliance auditability.

### II. Translate Once, Fan Out (No Translation Chains)
Translation chains (e.g., Hindi → English → Japanese) are strictly forbidden at the architectural level.
- Translations fan out independently and concurrently from the canonical source segment to each listener's selected target language.
- Duplicate requests for the same target language within a room are deduplicated.
- TTS output is never re-transcribed as new source speech, completely eliminating audio feedback loops.

### III. Honest Degradation & Explicit Failure
When AI pipeline components (VAD, STT, MT, TTS, or network transport) experience degraded performance or errors:
- Failures must degrade honestly and explicitly rather than failing silently or hallucinating.
- If STT fails, raw original audio remains accessible to listeners.
- If MT fails for an unsupported or degraded language pair, an explicit recoverable error is emitted.
- If TTS fails or is delayed, translated captions are delivered immediately as fallback text.

### IV. Provider & Model Abstraction
Business logic must remain completely isolated from vendor-specific model implementations.
- All AI services (STT: faster-whisper, MT: Argos/neural/online, TTS: Kokoro-ONNX/Piper, VAD: Silero) are accessed via standard provider interfaces.
- Switching between local offline models (CPU/GPU) and remote providers requires no business logic changes.

### V. Strict Architecture & Modern Stack
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 (async + sync support), SQLite (dev) / PostgreSQL (prod, pgvector-ready).
- **Frontend**: React 18, Vite, TypeScript strict mode (`tsc -b`), Tailwind CSS, TanStack Query, Zustand.
- **Realtime**: Binary PCM16 16kHz audio over WebSocket (dev/edge) and LiveKit WebRTC SFU (production).
- **Caching & Queue**: Redis in production with in-process ThreadPool fallback for single-node development and isolated tests.
- **Storage**: Local filesystem storage (dev) and S3/MinIO (prod).

### VI. Tenant Isolation & Security by Default
- Strict multi-tenancy enforced by `org_id` and role-based access control (RBAC). Cross-tenant access must return 404 (not 403) to prevent enumeration.
- Passwords hashed with bcrypt; JWT access tokens short-lived (30 min) with refresh token rotation and replay detection.
- File uploads validated with magic-byte MIME detection, size limits, and malware scanning hooks.
- No hardcoded production secrets in Git; credentials and tokens rotatable via environment variables.

### VII. Comprehensive Quality Gates
Every pull request or release gate must pass:
1. Backend Unit Tests (`tests/unit`)
2. Backend Integration Tests (`tests/integration`)
3. Realtime Golden Call Tests (`tests/realtime`)
4. Frontend Strict Typecheck (`npx tsc -b`)
5. Frontend Vitest Suite (`npx vitest run`)
6. Production Bundle Build (`npm run build`)
7. Health & Readiness Probe Validation (`/health`, `/ready`)

## Governance
This constitution governs all feature specifications, plans, tasks, and code modifications in GlobalTalk AI / TalkFlow. Working modules must be preserved and reused; refactoring must maintain full test-gate compliance.

**Version**: 1.0.0 | **Ratified**: 2026-10-04 | **Status**: Active
