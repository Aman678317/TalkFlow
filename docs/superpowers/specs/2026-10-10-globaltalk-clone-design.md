# GlobalTalk AI Clone Design

## Goal

Build a clean-room clone of the GlobalTalk AI web product in this repo, with the core product loop implemented in a way that is shippable and testable: multilingual text translation, AI writing assistance, document translation, voice translation studio, meetings/chat, and the authenticated workspace shell.

The design intentionally prioritizes product correctness and deployable structure over a literal one-to-one copy of every minor screen or shared-branding detail. The clone must mirror the product's functionality, UX patterns, and data flows without reusing the original app's proprietary content, branding, or closed-source implementation.

## Product scope

### In scope

- Landing page and conversion flow
- Authentication and session handling
- Dashboard with workspaces and navigation
- Text translation workflow with language selection and formality controls
- AI writing assistant with style/tone choice and rewriting/correction
- Real-time voice translation UI and meeting/room flow
- Documents upload and processing flow
- Multilingual chat and meeting room experience
- History archive and glossary/translation-memory management
- API keys, usage tracking, billing, team, admin, settings

### Out of scope for first delivery

- Exact visual parity with every marketing asset
- Proprietary commercial integrations or partner marketplaces
- Deep 3D/VR or highly specialized audio stacks beyond the core translation loop
- Large-scale multi-region production infra beyond the repo's standard backend architecture

## Constraints

- Keep the product implementation in the existing repo structure and current stack conventions.
- Use the repo's existing FastAPI + React + TypeScript foundation rather than a new runtime ecosystem.
- Treat authentication, RBAC, orgs, usage, and billing as first-class product concerns instead of late-stage additions.
- Prefer clean module boundaries and service interfaces over highly coupled page-local logic.
- Preserve a canonical-source model: the original audio/text signal is the truth, and every listener language is derived independently from it.

## Architecture summary

### Frontend

- React 18 + Vite + TypeScript + Tailwind
- Route-based app shell with public routes and authenticated workspace routes
- Zustand stores for auth/session, translation state, workspace context, and UI state
- React Query for API data fetching and cache management
- Reusable UI primitives for form controls, cards, panels, tabs, dialogs, and status badges

### Backend

- Python 3.11 + FastAPI
- Domain-oriented modules for auth, users/orgs, translation, writing, documents, meetings, chat, glossary, usage, billing, admin
- Pydantic v2 schemas for request/response validation and API contracts
- SQLAlchemy 2 models for PostgreSQL-backed persistence
- Redis for queues, caching, and transient session state
- Object storage for uploaded docs, generated translation output, audio assets, and archives

### Realtime and media

- WebSocket-based streaming for live translation and call/session signaling
- WebRTC-style room signaling for join, mute, and participant state
- Audio pipeline split into distinct stages: capture → VAD → STT → language detection → canonical segment → per-target translation → TTS
- Meeting room and chat components share the same message/segment model but are handled by separate service paths

### AI model layer

- Provider abstraction for speech-to-text, language detection, translation, text generation, and TTS
- Capability registry with health checks and failover chains
- Honest degradation for unsupported language pairs and runtime failures
- Translation services run against canonical source segments rather than chained translation loops

## Recommended feature delivery order

### Phase 1 — core SaaS shell

1. Auth, onboarding, dashboard, and workspace shell
2. Text translation workflow and history
3. Writing assistant with style/tone controls
4. Glossaries and translation memory basics
5. Usage + API key surface

### Phase 2 — real-time and documents

1. Voice translation studio and room UI
2. Document upload, status tracking, and processed output retrieval
3. Multilingual chat and transcript/archive view
4. Team/org admin and RBAC checks

### Phase 3 — monetization and ops

1. Billing, plan management, and usage thresholds
2. Admin analytics and auditing
3. Production deployment hardening and observability

This order keeps the core product loop working early while delaying complex real-time and billing detail until the workspace model is stable.

## Detailed module plan

### 1. Auth and tenant model

#### Responsibilities

- Sign up and login flow
- Session refresh and secure auth tokens
- Organization membership and role assignment
- Simple RBAC for admin, member, and owner roles

#### Core entities

- User
- Organization
- OrganizationMembership
- Role
- SessionToken

#### API surface

- `/auth/signup`, `/auth/login`, `/auth/refresh`
- `/me`, `/organizations`, `/members`

### 2. Translation domain

#### Responsibilities

- Source/target language selection
- Auto-detect language support
- Form/tonality options
- Translation job creation and result persistence
- History search and retrieval

#### Core entities

- TranslationJob
- TranslationSegment
- TranslationMemoryEntry
- GlossaryEntry
- LanguagePairConfig

#### API surface

- `/v2/translate`
- `/v3/translation_memories`
- `/v3/glossaries`
- `/history`

### 3. Writing assistant

#### Responsibilities

- Rewrite and refine text according to tone/style
- Grammar / spelling / structure corrections
- Optional personal style profiles

#### Core entities

- WritingRequest
- WritingProfile
- WritingOutput

#### API surface

- `/v2/write/rephrase`
- `/v2/write/correct`
- `/v3/style_rules`

### 4. Document translation

#### Responsibilities

- File upload, validation, and storage
- Async processing status tracking
- Document parsing and translation output reconstruction
- Downloadable translated files in accessible formats

#### Core entities

- DocumentJob
- DocumentAsset
- DocumentResult

#### API surface

- `/v2/document`
- `/v2/document/{id}`
- `/v2/document/{id}/result`

### 5. Voice and meetings

#### Responsibilities

- Create and join room sessions
- Capture / relay participant audio
- Apply translation per listener/muted audio path
- Render captions and live transcript segments

#### Core entities

- MeetingRoom
- MeetingRoomParticipant
- MeetingTranscriptSegment
- VoiceSession

#### API surface

- `/v3/voice/realtime`
- `/meetings`
- `/meeting/:id`
- `/join/:roomId`

### 6. Chat and history

#### Responsibilities

- Message creation, retrieval, sorting, and real-time updates
- Conversation history with transcript/translation metadata
- Search by room, user, or time window

#### Core entities

- ChatRoom
- ChatMessage
- TranscriptSegment

### 7. Usage, API, and admin

#### Responsibilities

- API key issuance and revocation
- Source usage accounting for text, documents, and transcripts
- Admin dashboards and org analytics
- Billing and plan metadata

#### Core entities

- ApiKey
- UsageRecord
- Plan
- BillingInvoice
- AuditLog

## Data model direction

The clone should follow a relational model with a few clear aggregate roots.

### Primary relationships

- User belongs to one or many Organizations
- Organization owns many users, documents, glossary entries, and usage records
- TranslationJob belongs to User and optionally Organization
- DocumentJob belongs to User and Organization
- MeetingRoom belongs to Organization or User depending on room scope
- ChatRoom belongs to Organization or User
- ApiKey belongs to User and Organization

### Design principles

- Keep immutable canonical source segments as the source of truth
- Separate raw source and translated output in schema design
- Track status transitions explicitly: queued, processing, complete, failed
- Store metadata for language pair, formality, glossary use, and model version
- Avoid mixing billing logic directly inside request handlers

## UX and flow design

### Navigation model

- Landing page for public conversion
- Authenticated app shell with a sidebar and topbar
- Feature grouping by workflow: Translate, Write, Voice, Documents, Meetings, Chat, History, Glossaries, API, Usage, Team, Settings, Admin

### State patterns

- Page-level state derived from API data and query cache
- Local optimistic updates for lightweight actions like glossary creation or chat send
- Server-authoritative status for async jobs like translation and document processing
- Error banners and retry affordances for failed translation or document jobs

### Required interaction states

- Idle / empty / loading / ready / error / failed / processed
- Empty state content must be present for all major flows
- All async actions require visible completion or failure states

## Service and communication boundaries

### Frontend to backend

- REST endpoints for CRUD and synchronous actions
- WebSocket or SSE channels for realtime events and room updates
- Shared API client with typed responses and retry strategy

### Backend to AI layer

- Interface-based model adapters
- Capability detection and health checks
- Fallback orchestration for unsupported or degraded scenarios

### Backend to storage and queue

- Document assets stored in object storage
- Jobs sent to async workers or background task queue
- Result artifacts stored back to app records for retrieval

## Risks and mitigations

### Risk: realtime translation complexity

Mitigation: build audio pipeline in phased stages, with a simplified room session model first and audio-specific complexity isolated behind a dedicated service layer.

### Risk: document translation fidelity

Mitigation: implement common file formats sequentially and normalize output reconstruction to the same storage contract.

### Risk: tenant isolation bugs

Mitigation: enforce org-scoped access checks in every domain service and centralize guard utilities.

### Risk: feature bloat

Mitigation: ship only the high-value product flows first; keep admin/billing and advanced inference under feature flags until the core loop is stable.

## Validation plan

### Functional validation

- Auth: sign up, login, refresh, session expiry, role checks
- Text translation: source/target selection, auto-detect, long-form text, unsupported languages
- Writing: tone change, grammar correction, output display
- Documents: upload, status, download, failure handling
- Meetings: create room, join flow, participant state, transcript display
- Admin: org member management, usage visibility, billing plan state

### Technical validation

- Unit tests for domain services and API validation
- Integration tests for auth + translation + document workflows
- End-to-end smoke tests for main user flows
- Oversight for tenant scoping, RBAC enforcement, and queue processing

## Implementation principle

The clone should be built as a coherent platform, not as disconnected feature pages. A small set of well-defined domain modules and explicit API contracts will make the implementation manageable and extensible while preserving the user-facing behavior of the original product.

## Decision summary

Recommended path: implement the product as a modern FastAPI + React SaaS with clear multi-tenant boundaries, a canonical-source translation pipeline, and modular services for translation, documents, meetings, and admin. This is the most realistic clean-room clone of the product's actual value while staying within the repo's existing architecture and delivery constraints.
