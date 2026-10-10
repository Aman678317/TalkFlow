# Architecture: TalkFlow (Rebuild of GlobalTalk AI's Core Platform)

## Stack

| layer | choice | why |
| --- | --- | --- |
| web | React 18 + Vite + TypeScript + TailwindCSS | Fast single-page responsiveness, sub-50ms render latency for audio streams |
| backend | FastAPI (Python 3.11) + WebSockets + Uvicorn | Native async I/O required for bi-directional audio streaming and AI model orchestration |
| database | PostgreSQL on Supabase / Neon | Relational integrity for org multi-tenancy, JSONB for glossaries, pgvector-ready |
| realtime / webrtc | LiveKit Server + LiveKit React SDK | Production WebRTC SFU providing decentralized multi-language audio tracks |
| auth | JWT Bearer Auth with bcrypt password hashing | Simple, stateless, self-contained multi-tenant tokens without external auth vendor locks |
| payments | Stripe Checkout + Customer Portal | Industry standard for SaaS subscriptions and usage metering |
| email | Resend API | Reliable transactional delivery for meeting invites and transcript exports |
| jobs | Redis + Celery / ARQ async workers | Non-blocking document conversion (PDF/DOCX) and audio batch processing |
| files | Cloudflare R2 / S3 | S3-compatible, zero-egress cost storage for document jobs and audio assets |
| hosting | Vercel (Web Client) + Render / Fly.io (FastAPI & LiveKit) | High-availability global edge delivery for UI with scalable containerized API |

## Schema

Tables: **10**. Access rules: Data-layer authorization checks scoped by `org_id` and `user_id` enforced in API dependencies (`deps.py`), with optional PostgreSQL Row Level Security (RLS).

Detailed schema definitions, constraints, and foreign key indexes are located in [`replica/schema.sql`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/replica/schema.sql).

- `organizations`: Multi-tenant boundary and subscription tier.
- `users`: Credentials, organization role (owner/admin/member), preferred interface language.
- `api_keys`: Hashed developer API keys with rate-limiting quotas.
- `meetings`: WebRTC video conference rooms with scheduling and configuration.
- `meeting_participants`: Active session participants with selected audio target languages.
- `transcripts`: Timestamped speech segments, original text, and translated outputs.
- `document_jobs`: Async file translation jobs preserving document styling.
- `glossaries`: Custom organization domain terminologies and override rules.
- `translation_memories`: Fuzzy and exact sentence translation cache.
- `subscriptions`: Stripe customer mappings, billing periods, and minute quotas.

## API Specification

| method path | does | who | input | output | flow |
| --- | --- | --- | --- | --- | --- |
| `POST /api/v1/auth/signup` | Creates user & default organization | Public | `{email, password, full_name}` | `{token, user}` | S02 |
| `POST /api/v1/auth/login` | Authenticates user & returns JWT | Public | `{email, password}` | `{token, user}` | S02 |
| `GET /api/v1/users/me` | Fetches active profile & settings | Authed | Headers: Bearer JWT | `UserResponse` | S03 |
| `POST /api/v1/translate/text` | Translates text with formality/tone | Authed | `{text, source_lang, target_lang, formality}` | `{translated_text, detected_lang}` | S05, F04 |
| `POST /api/v1/write/polish` | Rewrites text with target tone | Authed | `{text, tone, instructions}` | `{revised_text, diffs}` | S06, F04 |
| `WS /api/v1/voice/stream` | Bilateral real-time speech translation | Authed | Binary PCM audio chunks + control JSON | Binary audio playback chunks + live transcript JSON | S04, F01 |
| `POST /api/v1/meetings` | Creates scheduled or instant meeting | Authed | `{title, scheduled_at, settings}` | `{meeting_id, room_name, invite_url}` | S07, F02 |
| `POST /api/v1/meetings/:id/token` | Generates LiveKit WebRTC access token | Authed / Guest | `{guest_name?, target_lang}` | `{livekit_token, room_name}` | S08, S09, F02, F05 |
| `GET /api/v1/meetings/:id/transcripts` | Returns bilingual transcript log | Participant | Query params: format (json/srt/vtt) | Transcript array or file stream | S08, S13 |
| `POST /api/v1/documents/upload` | Enqueues async document translation | Authed | Multipart file (PDF/DOCX), target_lang | `{job_id, status: "pending"}` | S10, F03 |
| `GET /api/v1/documents/:id` | Polls document job progress | Authed | `job_id` | `{status, progress_percent, download_url}` | S10, F03 |
| `GET /api/v1/glossaries` | Lists organization domain glossaries | Org Member | - | `Glossary[]` | S12 |
| `POST /api/v1/glossaries` | Creates custom term dictionary | Org Admin | `{name, source_lang, target_lang, terms}` | `Glossary` | S12 |
| `POST /api/v1/billing/checkout` | Creates Stripe customer checkout session | Org Owner | `{price_id, success_url, cancel_url}` | `{checkout_url}` | S14 |

### Webhooks & Background Jobs
- **Webhooks In**:
  - `POST /api/v1/webhooks/stripe`: Handles `customer.subscription.updated`, `invoice.payment_succeeded`, `invoice.payment_failed`.
  - `POST /api/v1/webhooks/livekit`: Handles `room_started`, `room_finished`, `participant_joined`, `participant_left`.
- **Background Jobs**:
  - `process_document_job` (Worker, on-demand): Extracts text layout, batches translation via LLM/NLLB, reassembles document into target format.
  - `cleanup_ephemeral_recordings` (Cron: `0 2 * * *` Daily at 2 AM): Cleans raw meeting audio cache exceeding 30-day retention policies.
  - `reconcile_usage_quotas` (Cron: `0 0 1 * *` 1st of month): Resets monthly translation character counts and audio minutes.

## The Parts That Bite

- **Sub-Second Audio Latency**: Traditional STT → Translation → TTS pipelines take 2.5–4.0s. To achieve sub-second conversational speech-to-speech, streaming VAD (Voice Activity Detection), chunked sentence-level translation, and streaming neural TTS are pipelined concurrently over WebSockets/WebRTC.
- **WebRTC Multi-Track Audio Routing**: In video calls with 5+ speakers of different languages, routing the correct translated audio track per listener requires LiveKit selective subscription and custom audio track publish permissions.
- **Document Layout Drift**: Translated text in Romance/Germanic languages can expand by 20–35% compared to English. PDF and PPTX layout preservation requires font resizing and container reflow calculation during reconstruction.
- **Webhook Idempotency**: Stripe and LiveKit webhooks can be retried multiple times. All incoming webhook events must verify signature and store `event_id` in Redis/Postgres with unique locks.

## Build Order

1. **Vertical Slice (Milestone 1)**:
   - Screens: S02 (Auth), S04 (Live Voice Translation), S05 (Text Translation).
   - Tables: `users`, `organizations`, `transcripts`.
   - Routes: `POST /auth/login`, `POST /translate/text`, `WS /voice/stream`.
   - *Goal: Verify real-time bi-directional audio latency end-to-end.*

2. **Must-Haves (Milestone 2)**:
   - S07 & S08 (Meetings & LiveKit Video Conference Room), S09 (Public Zero-Login Guest Join).
   - S10 (Document Translation Pipeline with PDF/DOCX support).
   - S06 (AI Writing Assistant with tone modification).
   - S13 (Meeting Transcripts & SRT/VTT Exports).
   - Tables: `meetings`, `meeting_participants`, `document_jobs`, `glossaries`.

3. **Should-Haves (Milestone 3)**:
   - S14 (Billing, Quotas, Stripe Webhooks).
   - S15 (Developer API Keys with Rate Limiting).
   - S16 (Team Workspace & Role-based Access Control).
   - S12 (Translation Memory and Domain Glossaries).

4. **Enhancements & Market Differentiation (Milestone 4)**:
   - Incorporated findings from `/replica-entrepreneur` (addressing user complaints with competitor pricing and latency).
