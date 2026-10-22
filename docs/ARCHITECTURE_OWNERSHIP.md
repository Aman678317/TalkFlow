# Architecture & Ownership Matrix

**Roadmap Day 2 (P0) — "Full repository architecture and ownership map".**

The point of this document is one question, asked of every part of the repository:
**for this feature, which file is authoritative, what does it depend on, who tests it, what does it need at runtime, and what can go wrong?**

Everything below was **read out of the code** on the commit named in the header — not inferred from the docs, which is precisely why a few of them turned out to be wrong (§11).

| | |
|---|---|
| Repository | `Aman678317/TalkFlow` |
| Map taken at | `017be8f` (main, after #115) — with #116 (class-1 contract shapes) open |
| How it was produced | four parallel read-only code sweeps (frontend · canonical backend · duplicate/legacy trees · test ownership) + direct verification of the deployment topology, the CI lanes and the sharpest risk claims |
| Rule of the day | **flag stale, duplicate and unreachable paths — do not delete them blindly** |

---

## 0. How to read this document

1. **The API is the contract.** Where the client and the server disagree, the server wins — the client is what gets fixed (see #116).
2. **The canonical backend is `services/api`.** `apps/api` is a legacy compatibility tree with its own Alembic lineage; the deployed image runs `app.main:app` from `services/api` (§1). The `ai/` tree at the repo root is the *legacy lane* provider package set; `services/api/gt_ai/` is the canonical one; the root-level `gt_ai/` is a **separate public SDK** that can shadow the canonical package on `sys.path` (§8).
3. **"Test owner" means the file that fails when the area breaks.** An area with no test owner is an area with no safety net.
4. **"Known risk" is a verified observation**, not a worry: each one names the file and the line, and says what could go wrong.

---

## 1. The deployed topology (verified)

| Piece | Where it is defined | What it actually runs |
|---|---|---|
| API image | `infrastructure/docker/Dockerfile.api` | `PYTHONPATH=/app/services/api:/app/apps/api:/app/ai:/app`, `APP_MODULE=app.main:app`, `WORKDIR /app/services/api` → **the canonical backend** |
| Worker image | `infrastructure/docker/Dockerfile.worker` | copies `ai/`, `services/api/`, `workers/`; dispatches on `WORKER_KIND` |
| Web image | `infrastructure/docker/Dockerfile.web` | the SPA in `apps/web` |
| Compose topology | `docker-compose.yml` | `postgres · redis · minio · minio-init · livekit · api · worker · web` (+ the `pgdata` / `redisdata` / `miniodata` / `modelcache` / `apidata` volumes) |
| Runtime env (compose) | the `x-api-env` anchor | `APP_ENV=development`, Postgres (`asyncpg`), Redis cache, MinIO (`S3_*`), `LIVEKIT_*`, `MODEL_CACHE_PATH=/models`, `WEB_ORIGIN` |
| Deployment config | `deploy/gcp` | the GCP target for the compose topology |

**Consequence for the docs:** `docs/ARCHITECTURE.md` §4 still lists `apps/api` as the "FastAPI control+data plane" — the deployed plane is `services/api` (§11, D-1).

---

## 2. Frontend ownership (`apps/web`)

React 18 + Vite 5 + TS strict · react-router 6 · react-query 5 · zustand 4 · livekit-client 2.22 · motion 14.

### 2.1 Routing — the live router is `src/main.tsx`, and there is a second one that is dead

| Path (live, `src/main.tsx:101-141`) | Page | Wrapper | Note |
|---|---|---|---|
| `/` | `RootGate` → `Landing` | — | `main.tsx:81-88` |
| `/login`, `/signup`, `/auth/callback/:provider` | `Login`, `Signup`, `AuthCallback` | — | public |
| `/join/:roomId`, `/meeting/:id` | `JoinCall`, `MeetingRoom` | — | public by link |
| `/agents`, `/agent-studio`, `/docs`, `/api/docs` | `AgentStudio`, `AgentStudio`, `DocsPage`, `DocsPage` | `AppShell` | public chrome |
| `/dashboard`, `/translate`, `/translate/page`, `/write`, `/voice`, `/documents`, `/meetings`, `/chat`, `/history`, `/glossaries`, `/translation-memory`, `/style-profiles`, `/api`, `/usage`, `/billing`, `/team`, `/settings`, `/admin`, `/admin/telephony`, `/agent/calls` | the matching page | `RequireAuth` + `Layout` | `/chat` → `ChatRooms` |
| `*` | redirect to `/` | — | `main.tsx:140` |

**`src/App.tsx` is a complete duplicate router that nothing imports** (`index.html:103` loads `/src/main.tsx`). It maps `/chat` to a *different* page (`ChatPage`, dead), leaves `/translate`, `/write`, `/dashboard` **ungated**, and is the only place `CopilotKit` / `CopilotSidebar` (`App.tsx:75,121`) and the `VITE_COPILOTKIT_RUNTIME_URL` / `VITE_CPK_INTELLIGENCE_API_KEY` env vars (`App.tsx:71-72`) are referenced — the live app has no CopilotKit at all.

**`/admin` and `/admin/telephony` have no role guard on the route** (`main.tsx:136-137`); only the nav links are filtered (`Layout.tsx:120-121`, `AppShell.tsx:72-75`). The server still enforces its own permissions — the risk is the page shell, not access.

### 2.2 The API client — one wrapper, and what owns what

`lib/api.ts` (504 lines) is the single fetch wrapper: base-URL resolution with https-upgrade and same-origin for preview/staging (`api.ts:98-222`), bearer token **in memory only** (`api.ts:27,35-37,385-386`), double-submit CSRF (`api.ts:40-44,395-399`), `credentials: "include"`, a 401 → refresh → retry-once path with dedupe (`api.ts:289-374,428-458`), cross-tab auth broadcast (`api.ts:46-88`), per-request timeouts (15 s / 60 s for `FormData`, `api.ts:390,400-427`), and `ApiError`/`friendlyMessage` normalizing the backend's error envelope (`api.ts:7-25,464,480-504`).

| Lib module | Owns | Network |
|---|---|---|
| `lib/translation.ts` | detect + translate calls, the envelope normalizer, the honesty gate `isUsableTranslation` | REST |
| `lib/contacts.ts` | the contacts/campaigns **envelope** helper (#116) | REST — no page consumes it yet |
| `lib/ws.ts` | **the meeting event protocol client** (resume by `last_sequence`, 20 s heartbeat, 65 s liveness, binary frames, 64 KB backpressure, single-use ticket minting) | REST + WS |
| `lib/realtime.ts` | a **second, older** WS client (`/ws/realtime?ticket=`) — superseded, only a test imports it | WS (test-only) |
| `lib/audio.ts` | capture (AudioWorklet, 16 kHz mono PCM16) and **playback** (WAV queue, raw PCM relay, cross-transport dedup, barge-in) | none |
| `lib/captions.ts` | pure caption reducer over realtime events | none |
| `lib/webrtc.ts` | the P2P video mesh (perfect-negotiation, one ICE restart, grace windows); signalling rides the meeting WS | none |
| `lib/mediaRecovery.ts` | the LiveKit recovery policy (a connected spell counts only after 10 s) | none |
| `lib/stageStatus.ts` | the pipeline-chip reducer (stt/mt/tts/media/mic) | none |
| `lib/adaptivePolling.ts`, `lib/documentMeta.ts`, `lib/pageUrl.ts`, `lib/shortcuts.ts`, `lib/selection.ts`, `lib/languagePicker.ts`, `lib/writeDiff.ts`, `lib/transcriptExporter.ts`, `lib/agentConsole.ts`, `lib/utils.ts`, `lib/motion.ts` | pure helpers | none |
| `lib/twilioVoice.ts`, `lib/socialProviders.ts`, `lib/virtualCamera.ts`, `lib/recentTranslations.ts` | Twilio SDK, OAuth IdP scripts, virtual camera, localStorage recents | external / none |

### 2.3 The canonical playback path (one true path)

```
backend WS /ws/meetings/{id}
  → lib/ws.ts:188 JSON.parse | lib/ws.ts:184 decodeBinaryFrame()
      ├─ binary "original" → MeetingRoom.tsx:451 player.enqueuePcm16(...)   (original-audio relay)
      ├─ binary "tts"      → MeetingRoom.tsx:468 player.deliver(wavBytes, tag, {source:"binary"})
      ├─ JSON "tts.chunk" / "tts.completed" → MeetingRoom.tsx:734/755 player.deliver(...)
      ├─ JSON "playback.flush" → player.stopAll() (recipients) / cancelSpeaker() (barge-in)
      └─ transcript/translation/latency events → lib/captions.ts reduceCaptions()
lib/audio.ts AudioPlayer.deliver()  → binary wins immediately; JSON waits 350 ms → dedup key `${tag}:${chunkIndex}`
  → queue ordered by (sequence, chunkIndex, arrival) → AudioBufferSourceNode.start()
  → onPlaybackState(turn, playing|played|dropped) → captions.setPlayback()
```
The identity rule that makes cross-transport dedup work is `normId()` (`lib/ws.ts:56`): the binary frame's short id and the JSON event id are normalized to the same string. **Caption state comes from the player, not from the events** (`lib/captions.ts:252-256`).

### 2.4 Frontend risk register (verified)

| # | Risk | Evidence | What could go wrong |
|---|---|---|---|
| F-1 | a whole duplicate router is dead | `src/App.tsx` (124 lines) imported by nothing; `index.html:103` loads `main.tsx` | someone edits the wrong route table; the CopilotKit wiring and two env vars live only there |
| F-2 | dead code with no importers | `pages/ChatPage.tsx` (only `App.tsx` imports it), `components/meeting/ShareInviteModal.tsx`, `stores/toast.tsx` (shadowed by `stores/toast.ts`), `src/test/setup.ts` (vite registers `test-setup.ts` instead) | stale behavior re-enters the build; `toast.tsx`'s `ToastHost` is never mounted |
| F-3 | production-dead modules | `lib/realtime.ts` (only `src/test/ui.test.tsx` imports it), `lib/contacts.ts` (only its own test) | a second WS client and a whole API area look alive but never run |
| F-4 | duplicated chrome/primitive layers | `components/ui.tsx` vs `components/ui/index.tsx` (the index still carries a full shadow copy of Button/Spinner/Badge/Card/Input/Select/Textarea/Modal/EmptyState/ErrorState/Skeleton), `Layout.tsx` vs `layout/AppShell.tsx` (two `Logo`s, two `ErrorBoundary`s), three toast modules | a fix lands in the copy that is not imported |
| F-5 | admin routes are not role-guarded in the router | `main.tsx:136-137` vs the filtered nav links `Layout.tsx:120-121` | an ordinary authenticated user loads the admin shell (the server still guards the data) |
| F-6 | large commented-out legacy translators | `pages/Translate.tsx:185-245,246-416` (232 lines, two `fetch("")`), `pages/Voice.tsx:60-195` (136 lines, `fetch("")` at `:168`) | the commented code looks like the current path and gets "restored" |
| F-7 | no frontend page owns the CRM area | `lib/contacts.ts` has no importer; there is no contacts/campaigns page | the API area is unexercised end to end from the UI |
| F-8 | most pages have no test | the pages listed as uncovered in §2.5 | a UI regression is found by a user, not by a lane |

### 2.5 Frontend test ownership (the safety net that exists)

`lib/api.test.ts` (origin/WS/token/refresh/ticket), `lib/__tests__/protocol.test.ts` (binary frames, dedup identity, `ApiError`), `lib/__tests__/mediaResilience.test.ts` (heartbeat, mic loss), `lib/__tests__/mediaRecovery.test.ts` (the 10 s recovery window), `lib/__tests__/audioPlayer.test.ts` (queue, dedup, JSON fallback, barge-in, playback state), `lib/__tests__/captions.test.ts` (one line per turn, failure recorded once, 80-line bound), `lib/__tests__/stageStatus.test.ts`, `lib/__tests__/webrtc.test.ts`, `lib/__tests__/meetingRoomIce.test.ts`, `lib/__tests__/adaptivePolling.test.ts`, `hooks/__tests__/useRosterQuery.test.tsx`, `lib/translation.test.ts`, `lib/__tests__/writeDiff.test.ts`, `lib/__tests__/shortcuts.test.ts`, `components/__tests__/SelectionTranslate.test.tsx`, `lib/__tests__/languagePicker.test.ts`, `lib/__tests__/pageUrl.test.ts`, `lib/__tests__/documentMeta.test.ts`, `lib/recentTranslations.test.ts`, `lib/transcriptExporter.test.ts`, `lib/agentConsole.test.ts`, `pages/Meetings.test.tsx`, `pages/ApiKeys.test.tsx`, `pages/AgentCalls.test.tsx`, `pages/AdminTelephony.test.tsx`, `stores/auth.test.ts`, `test/phase14_frontend_hardening.test.tsx`, `test/ui.test.tsx`, `test/videoTileChips.test.tsx`, `lib/__tests__/postcssVendorCss.test.ts`.

**Uncovered pages:** Translate, TranslateWebPage, Write, Voice, Documents, MeetingRoom, ChatRooms, History, Glossaries, TranslationMemory, StyleProfiles, Billing, Usage, Team, Settings, Dashboard, AgentStudio, JoinCall, DocsPage · **uncovered components:** all of `components/voice/*`, `components/LanguagePicker.tsx`, `components/Layout.tsx`, `components/layout/AppShell.tsx` · **uncovered hooks:** `useLiveKitRoom`, `useDocumentsQuery`, `useLanguages`.

---

## 3. Worked example — the text-translation request path (traced end to end)

One path, every layer, with the line it happens on. This is the chain the Day-2 map is supposed to make obvious: **route → service → provider interface → model router → provider → ledger → response.**

| # | Layer | Where | What happens there |
|---|---|---|---|
| 1 | HTTP route | `services/api/app/routers/translate.py:44` | `POST /api/v1/translate`; the per-request context (org, glossary, style, TM, domain, intent) is built by `_ctx()` (`:33`) |
| 2 | quota pre-checks | `routers/translate.py:75,80` | the character allowance and the translation-request allowance are checked **before** the expensive work (the units are the ledger's own — #115) |
| 3 | domain service | `services/api/app/services/translation_service.py:217` | `translate_text()` — language detection, pair validation, the TM lookup, the glossary/style load, the usage record |
| 4 | request build | `translation_service.py:291-301` | the `TranslationRequest` carries the intent **and** the tenant-private flag |
| 5 | AI facade | `services/api/app/ai.py:561` | the tenant flag becomes `intent=PRIVATE_ONLY` when set (`:561-575`); the stream variant is `:591` |
| 6 | chain builder | `app/ai.py:358` → `:380` | `_ordered_candidates()` asks the router for a decision, marks the picked provider unavailable and asks again — the private pool running dry **ends** the chain instead of failing it (`:373-380`) |
| 7 | model router | `services/api/gt_ai/model_router/router.py:87` | the hard filter drops non-private providers for a private_only intent (`:99-100`); the score picks the winner; `provider_is_private()` (`:62`) is the shared classification |
| 8 | provider factory | `services/api/gt_ai/registry.py:33` | `create(task, name, **kwargs)` builds the concrete provider (e.g. `NeuralOnlineTranslationProvider`, `gt_ai/translation/neural_online.py:505`) |
| 9 | provider | `gt_ai/translation/*.py` | the actual inference; the local providers are cache-first and load only from the provisioned cache |
| 10 | ledger | `translation_service.py:373,380` | the characters and the translation-request count are written to the immutable ledger |
| 11 | response | `routers/translate.py:85-100` | the flat `TranslationOut` rows; the **envelope** (`{translations, request_id}`) is assembled at the route boundary — the client type now mirrors it (#116) |

**Every ledger write site in the canonical tree** (the metering surface the plan limits are checked against):

| Site | Dimension |
|---|---|
| `services/api/app/services/translation_service.py:373,380` | `characters`, `translation_requests` |
| `services/api/app/services/document_service.py:694,699` | `characters`, `document_pages` |
| `services/api/app/routers/documents.py:226` | `api_requests` (document uploads) |
| `services/api/app/routers/translate.py:172` | `api_requests` (language detection) |
| `services/api/app/telephony/call_service.py:297` | `telephony_minutes` |
| `services/api/app/realtime/pipeline.py:680` | `audio_seconds` (the realtime path — metered by #115) |

---

## 4. The canonical backend (`services/api`)

### 4.1 Entry points and processes

| Process | Where | What it runs |
|---|---|---|
| API (dev) | `run_api.py:29` | `uvicorn app.main:app` on `:8088`; puts `services/api` and `ai` on `sys.path` (`:14-15`) and `chdir`s into `services/api` (`:18`) |
| API (prod) | `infrastructure/docker/Dockerfile.api:36` | `python -m uvicorn ${APP_MODULE}` → `app.main:app`, `--workers 1`; `PYTHONPATH=/app/services/api:/app/apps/api:/app/ai:/app` (`:19`) |
| App factory | `app/main.py:43` `create_app()`; module-level `app = create_app()` at `:387` | middleware `:61-74`, routers `:83-111`, CopilotKit mount `:113-118` |
| Lifespan | `main.py:138` startup / `:336` shutdown | DB `:141`, cache `:143`, queue `:145`, storage `:147`, schema gate `:151`, seed `:154`, AI registry `:158-161`, warmup task `:167-174`, 3 in-process workers `:177-192`, ARI consumer `:198-239`, call-job worker+ticker `:245-258`, escalation rewire `:265-278`, sweeper `:281-282`, retention loop `:283` |
| Standalone workers | `workers/{document,inference,cleanup,metering}-worker/main.py` | documents `:22`, inference `:27`, cleanup `:17`, metering `:22`; dispatched by `WORKER_KIND` (`Dockerfile.worker:28-33`, `docker-compose.yml:115-125`) |
| Migrations | `services/api/alembic/env.py` | head `f4e2a9c1d8b7`; **the prod boot fails closed on a head mismatch** (`main.py:320-333`) |

### 4.2 Routers — who owns which path

| Module | Prefix | The routes | Auth | Calls |
|---|---|---|---|---|
| `health.py` | none | `/health`, `/healthz`, `/ready`, `/readyz`, `/version`, `/metrics`, `/api/v1/system/diagnostics` | **public** (the metrics token gates in prod, `:117-123`) | `app.ai.ai`, `livekit_bridge`, `app.metrics` |
| `auth.py` | `/api/v1/auth` | signup/login/social-login/refresh/logout/sessions/identities/password-reset/me | `rl_auth` on the auth routes; `get_principal` on the identity routes | `social_auth_service`, `audit_service`, `billing_service` |
| `orgs.py` | `/api/v1` | `/organizations`, `/organizations/current`, `/members`, `/projects`, `/roles` | `require_org_user` | `audit_service`, `billing_service` |
| `translate.py` | `/api/v1` | `/translate`, `/translate/page`, `/detect-language`, `/voice/transcribe`, `/voice/tts`, `/languages`, `/history` | `rl_translate` + `require_scope("detect")` + `use_voice` | `translation_service`, `page_fetch`, `usage_service`, `app.ai.ai`, `model_fetch` |
| `write.py` | `/api/v1` | `/write`, `/dictionary` | `get_principal` | `write_service` |
| `customization.py` | `/api/v1` | glossaries, translation memories, style profiles (CRUD) | `require_org_user` | `audit_service`, `translation_service.tm_store` |
| `documents.py` | `/api/v1/documents` | upload, list, status, segments, original, download, retry, delete | `require_org_user` + `require_scope("documents")` | `document_service`, `usage_service`, `audit_service` |
| `meetings.py` | `/api/v1` (+ a voice alias router) | create/join/join-ticket/leave/tokens/media-token/end + list/detail/ice-servers/participants/transcript/export/preferences/delete | `require_org_user` on the mutating routes; `get_principal_optional` on the read routes | `meeting_service`, `webhook_service`, `audit_service`, `livekit_bridge` |
| `assistant.py` | `/api/v1` (chat + assistant) | chat, chat translate, summary, ask, memory, memory retrieve, bridge, source segments, respond | `require_org_user` | `assistant_service`, `chat_service`, `translation_service` |
| `agent_studio.py` | `/api/v1/agent-studio` | `/status`, `/triage`, `/content-pipeline`, `/research-crew` | `require_org_user` | **a subprocess**, `bridge.py` (`:64-73`) — with hard-coded fallbacks (`:76-139`) |
| `contacts.py` | `/api/v1/contacts` + `/api/v1/campaigns` | CRM CRUD, consent, documents, `/call`, jobs, campaigns | `require_org_user` | `contacts_service`, `call_jobs` |
| `platform.py` | 8 sub-routers | api-keys, usage/billing, webhooks, search, feedback, flags, integrations, admin | `require_org_user`; `_require_platform_admin` on `/admin/*` (`:393-397`) | `usage_service`, `billing_service`, `audit_service`, `webhook_service`, `search_service`, `app.ai.ai` |
| `telephony.py` | `/api/v1/telephony` | calls, peer-calls, transcripts, escalations, phone numbers, provider status, carrier webhooks, agent prompts + 3 WS routes | `require_org_user`; the carrier webhooks are **signature-gated** instead (`:928,951`) | `CallService`, `call_transcript`, `escalation`, `media_stream_service`, `phone_number_service`, `twilio_token`, `prompt_composer` |
| `v2_v3.py` | **root** (`/v2/*`, `/v3/*`, `:48`) | ~60 legacy-compat routes | mostly `get_principal_optional` (public by default) | `write_service`, `meeting_service`, `translation_service` |
| `app/realtime/ws.py:38` | — | WS `/ws/meetings/{id}`, `/ws/realtime` | ticket/JWT verified **inside** the handler | `app.realtime.pipeline`, `chat_service`, `meeting_service` |
| `app/agent.py:61` | `/api/copilotkit` | `/info`, `/agent/{name}/run`, threads | **no auth** | a `ChatOpenAI` call (`:104`) |

### 4.3 Services — the domain layer

| Service | Responsibility | Tables | Called by |
|---|---|---|---|
| `assistant_service.py` | transcript load, summary, Q&A, memory | `Meeting`, `TranscriptSegment`, `MemoryItem` | `routers/assistant.py` |
| `audit_service.py` | the audit ledger | `AuditLog` | 7 routers |
| `billing_service.py` | plan catalog, subscription, invoice, events | `Subscription`, `BillingEvent`, `UsageRecord`, `Organization` | `platform`, `auth`, `orgs`, the billing job, the metering worker |
| `chat_service.py` | meeting chat | `ChatMessage`, `Meeting`, `Participant` | `routers/assistant.py`, `realtime/ws.py` |
| `contacts_service.py` | CRM + consent ledger | `Contact`, `ContactConsent`, `ContactDocument`, `Document` | `routers/contacts.py`, `routers/telephony.py` |
| `document_service.py` | the document pipeline (parse → translate → reconstruct) | `Document`, `DocumentJob`, `DocumentSegment`, `UsageRecord` | `routers/documents.py`, the documents worker |
| `meeting_service.py` | meeting/participant lifecycle, preferences | `Meeting`, `Participant`, `ParticipantPreference`, `AudioSession`, `User` | 4 routers + the WS |
| `page_fetch.py` | SSRF-guarded page fetch + text extraction | — | `routers/translate.py` |
| `retention_service.py` | retention policy + sweep | 9 tables | the retention job, the cleanup worker |
| `search_service.py` | cross-entity search | 8 tables | `routers/platform.py` |
| `social_auth_service.py` | Google/Apple/GitHub ID-token verification | `User`, `UserIdentity` | `routers/auth.py` |
| `translation_service.py` | translate orchestration (TM → glossary → style → provider) | 6 tables | 6 routers |
| `usage_service.py` | the ledger, the period usage, the quota limits | `UsageRecord`, `Subscription` | 4 routers + the realtime pipeline |
| `webhook_service.py` | org webhooks: CRUD, signed dispatch, delivery, SSRF guard | `WebhookEndpoint`, `WebhookDelivery` | 3 routers + the metering worker |
| `write_service.py` | the tiered writing service (rules → neural) | — (stateless) | `routers/write.py`, `v2_v3.py` |

## 5. The provider layer and the model router

### 5.1 The provider layer (`services/api/gt_ai/`)

| Contract | Where |
|---|---|
| `BaseProvider` (name/task/private/quality/cost/latency + `warmup`/`healthcheck`/`runtime_ready`) | `gt_ai/base.py:20-42`; the task protocols at `:57-106` |
| The value types (`Task`, `Intent`, the request/result shapes, `ProviderUnavailable`, `NoPrivateProviderAvailable`) | `gt_ai/types.py:14-131` |
| The registry (`register`, `create` with an instance cache, the adapter import map) | `gt_ai/registry.py:19,33,55-77` |
| The model router (hard filters, the `PRIVATE_ONLY` refusal, the scoring, the health EWMA) | `gt_ai/model_router/router.py:25,75,87,127-137,153-194,210-226` |
| The privacy classification | `gt_ai/model_router/router.py:52,62` (`NON_PRIVATE_PROVIDER_NAMES`, `provider_is_private`) |
| The app-facing facade (the only entry into the provider layer) | `app/ai.py:84` (`AIFacade`), the singleton `ai = AIFacade()` at `:855` |

| Family | Class | Load or probe |
|---|---|---|
| MT | `madlad400` (`:28`) · `nllb_ct2` (`:38`) · `argos` (`:27`) · `airllm` (`:29`) | **load** the model (all cache-first since #112) |
| MT | `neural_online`/`deepl` (`:505`) · `azure_translator` (`:30`) · `mt_http` (`:26`) · `dev_echo` (`:112`) | **probe only** (HTTP) |
| STT | `faster_whisper` (`:26`) | **loads**; its `healthcheck` never loads (`:109`) |
| STT | `azure_speech` (`:72`) · `stt_http` (`:17`) · `dev_text` (`:25`) | probe only / no model |
| TTS | `kokoro` (`:26`) · `piper` (`:21`) | **load** the voice |
| TTS | `azure_speech_tts` (`:49`) · `tts_http` (`:17`) · `dev_tone` (`:61`) | probe only / synthesised |
| Detect | `fasttext` (`:16`) loads · `langdetect` (`:97`) pure python | — |
| Summarize | `extractive` (`:81`) pure python · `llm_http` (`:22`) probe only | — |
| Embed | `hash_tfidf` (`:47`) pure python · `sentence_transformers` (`:23`) loads | — |
| VAD | `EnergyVAD` (`:34`) no model · `SileroVAD` (`:131`) torch-hub, cache-first since #113 | — |

## 6. Realtime, telephony, data, queue and workers

### 6.1 Data, queue, workers

`app/db/models.py` (1127 lines) holds 16 model families, each with one owning service (identity, tenancy, developer platform, capability/routing, localization, meeting/realtime, document, agent/memory, feedback/quality, billing, platform ops, telephony, CRM, escalation).

| Piece | Where | Behaviour |
|---|---|---|
| The job contract | `app/queue.py:29` `Job` | id/type/payload/attempts/backoff envelope |
| The queue interface | `app/queue.py:43` `JobQueue` | push/pop/ack/nack/depth/DLQ/ping/close |
| The memory queue | `app/queue.py:80` | delayed requeue via a task (`:139-156`) |
| The Redis queue | `app/queue.py:190` | `gt:queue:{q}` (`:198`), `:processing` (`:201`), `:delayed` (`:204`), `:dlq` (`:207`), a stale-processing sweep (`:306`) |
| The selection | `app/queue.py:338` | Redis if it answers, else memory; **production raises without Redis** (`:349-358`) |
| The worker | `app/queue.py:379` | exponential backoff (`:443`), DLQ after the attempt cap (`:448-453`), graceful stop (`:477`) |
| The in-process registrations | `main.py:180-192` | `documents` → `document_service.process_document_job`; `webhooks` → `webhook_service.deliver_job`; `default` → `retention.sweep` + `billing.finalize` |
| The call-job worker | `main.py:245-258` (opt-in `CALL_WORKER_ENABLED`) | a `WorkerRunner` on the `telephony` queue + a `CallJobTicker` |
| The background loops | `main.py:167` (warmup), `:257` (ticker), `:282` (session sweeper), `:283`/`:380` (retention, 3600 s), `realtime/ws.py:553` (session sweeper, 60 s tick, a hard-coded 300 s grace at `:550`) | |

### 6.2 Realtime and telephony

| Piece | Where | Note |
|---|---|---|
| The event protocol | `realtime/protocol.py:20` `ServerEventType` (39 types), `:62` `ClientEventType` (11), `PROTOCOL_VERSION=1` (`:76`), the JSON envelope (`:79-113`) | the client mirrors it in `apps/web/src/lib/ws.ts` |
| Sessions | `realtime/session_manager.py:35,53,79` | create/close, attach/detach, `listeners_for_language` (`:156`), `required_target_languages` (`:175`), broadcast (`:195`), replay (`:233`), the original-audio relay (`:246`) |
| The pipeline | `realtime/pipeline.py:98` | `_make_vad` (`:195`), the speaker loop (`:356`), `_finalize_utterance` (`:635`), `_commit_segment` (`:789`), `_start_fanout` (`:894`), `_translate_and_synthesize` (`:940`), the staleness check (`:1241`) |
| The agent graph | `realtime/agents/__init__.py:1-53` | listening / translation / voice / supervisor over an `AgentBus` (`agents/bus.py:33`) |
| The stage deadlines | `agents/listening.py:130` (STT), `agents/translation.py:87` (MT), `agents/voice.py:70` (TTS) + the shared `InferenceGate` (`agents/inference_gate.py:20`) | `RT_*_DEADLINE_MS` + `RT_INFERENCE_CONCURRENCY` |
| The provider link | `pipeline.py:28` `from app.ai import ai` | every STT/MT/TTS call goes through the facade → the router → a provider |
| The telephony lane | `app/telephony/*` | the provider adapters (`providers/{twilio,telnyx,asterisk,simulated}_provider.py`), the outbound gate (`gate.py:63` — campaign → DNC → AI → consent → backoff → window → attempts → concurrency), the bridge (`bidirectional_bridge.py:156`), the media gateway (`media_stream_service.py:37,329`), the webhook security (`security.py:22,91`), the call lifecycle (`call_service.py:30`), the jobs (`call_jobs.py:36`), the transcript + sha256 citations (`call_transcript.py:73,171`), the escalation queue/store (`escalation.py:69`, `escalation_store.py:31`), the agent graph (`ai_agent_graph.py:180`), the ARI client/consumer/inbound (`ari_client.py:86`, `ari_events.py:181`, `ari_inbound.py:60`) |

---

## 7. Test ownership and the CI gates

### 7.1 The lanes

| Lane | Invocation | Env | Needs |
|---|---|---|---|
| unit + integration (SQLite) | `pytest tests/unit tests/integration -q` (`ci.yml:51`) | `APP_ENV=test`, `CACHE_BACKEND=memory`, `REDIS_URL=""`, `JWT_SECRET`, `RATE_LIMIT_*` | a DB (SQLite) |
| **hardened lane** | `pytest <46 flat files> -q` (`ci.yml:68-114`) | same as above | a DB |
| integration (Postgres + pgvector + Redis) | `pytest tests/integration -q` (`ci.yml:126`) | `DATABASE_URL=postgresql+psycopg://…`, `CACHE_BACKEND=redis` | Postgres + pgvector + Redis |
| migrations | `alembic upgrade head` / `check` / `downgrade base` in **both** trees (`ci.yml:159-177`) + `test_database_migrations_hardened.py` | per-tree DB URLs | Postgres |
| realtime-golden | seed the models (`scripts/download_models.sh`, `MODEL_PROFILE=CPU STT_SIZE=small`), `pytest tests/realtime -q -rs` (`ci.yml:214`), then `scripts/verify_ai_stack.py` (`ci.yml:217`) | `MODEL_CACHE_PATH=${{ runner.temp }}/models` | **model weights** |
| frontend | `npx tsc -b` · `npx vitest run` · `npx vite build` (`ci.yml:230-234`) | — | node |
| docker | builds `Dockerfile.api` + `Dockerfile.web` (`ci.yml:242-244`) | — | docker |
| e2e (separate workflow) | `npx playwright test` in `apps/web` (`e2e.yml:84`) against a compose stack | `LIVEKIT_PUBLIC_URL` | docker + livekit |

### 7.2 The boundary

`tests/unit` = pure logic, no models · `tests/integration` = the real app against a real DB/storage/queue (model assertions **skip** when the weights are absent, `tests/integration/test_api.py:166,193`) · `tests/realtime` = the golden multilingual call, needs weights, and **skips** without them (`tests/realtime/test_golden_call.py:104`) · the flat `tests/test_*.py` suites = phase-level proof.

**There are two conftest files, for two different trees, and both are loaded for any `pytest tests/...` run:**

| File | Tree | DB | Notes |
|---|---|---|---|
| `conftest.py` (repo root) | the **legacy** `globaltalk.*` tree (`apps/api`) | **fixed** on-disk files `data/globaltalk_test.db`, `data/services_test.db` — deleted at session start | the legacy lane's fixtures |
| `tests/conftest.py` | the **canonical** `app.*` tree (`services/api`) | a per-session **temp dir** SQLite | forces the dev providers (`tests/conftest.py:45-47`) |

`AGENTS.md` says "Tests use `services/api/conftest.py` fixtures" — **that file does not exist** (the fixtures live in `tests/conftest.py`) — a stale doc line (risk D-4).

### 7.3 Verified gap: **9 test suites (102 test functions) run in no CI job**

| Suite | Tests | Area it owns |
|---|---|---|
| `tests/test_tenant_security_extended.py` | 18 | tenant isolation & BOLA/IDOR |
| `tests/test_ai_agent_graph.py` | 17 | AI-agent graph hard guards — **wired** |
| `tests/test_meeting_media_contract.py` | 15 | the web ↔ API media contract — **wired** |
| `tests/test_realtime_security_hardened.py` | 12 | realtime/WS session authorization — **excluded on purpose** (`ci.yml:56-59`, SQLite lock contention) |
| `tests/test_auth_full_flow.py` | 10 | end-to-end auth + refresh-rotation flow — **wired** |
| `tests/test_cross_tenant_security.py` | 9 | cross-tenant isolation — **wired** |
| `tests/test_social_real_verification.py` | 9 | real signed social-provider verification — **wired** |
| `tests/test_storage_webhooks.py` | 5 | object storage + webhook SSRF protection — **wired** |
| `tests/test_deployment_and_devops_alignment.py` | 5 | compose/k8s/nginx/Dockerfile alignment — **wired** |

`tests/deployment/` (2 files, 9 tests) and `tests/browser_e2e/` (1 file, 1 test) are **orphaned directories** — no CI lane references them.

**What it means:** a green CI does **not** mean the repository's tests pass. The suites that are not wired up are disproportionately the *security* ones (tenant isolation, BOLA/IDOR, WS authorization) — that is the wrong end of the spectrum to leave unwired.

### 7.4 Coverage gaps (no test references the module at all)

`services/api/app/mcp/indic_server.py` and the Node MCP server (`mcp/desi-mcp-server/`) · `telephony/audio_codec.py` · `telephony/sentence_chunker.py` · `telephony/twilio_token.py` · `telephony/media_stream_service.py` · `services/search_service.py` · `services/audit_service.py` · `services/assistant_service.py` · `agents/prompt_composer.py` · `globaltalk_client.py` · the org-management routes (`/organizations`, `/roles`, `/projects`) · the assistant memory API · the chat HTTP endpoints · the billing events endpoint.

### 7.5 Gate fragility (the landmines that make a green run non-deterministic)

| # | Landmine | Where | Effect |
|---|---|---|---|
| T-1 | **`app.config` is reloaded by a session fixture, forking the module-owned `settings` singleton** | `tests/conftest.py:94-102` (`get_settings.cache_clear()` + `importlib.reload(cfg)`) vs `app/config.py:507-514` (`settings = get_settings()`) | every `from app.config import settings` in already-imported modules keeps the **old** object — a `monkeypatch.setattr(settings, …)` can silently miss the binding the code reads. Self-documented at `tests/test_asterisk_ari_adapter.py:46-67` and `tests/test_telephony_webhook_security.py:7-11`, which force the value onto every binding. A **second** reload site exists in `tests/integration/test_desi_compatibility.py:24,27` |
| T-2 | one shared SQLite engine for the whole session | `tests/conftest.py:17-28` | a test holding a write transaction makes others hit "database is locked" |
| T-3 | the root conftest writes to **fixed** files under `data/` | `conftest.py:13-14,35-41` | state leaks between runs and workers; `make clean` removes them |
| T-4 | the operator's `MODEL_CACHE_PATH` leaks into the session | `tests/conftest.py:44` | the same commit passes on a box with weights and **skips** on CI (the backend job does not set it; the realtime job does) |
| T-5 | weights-dependent skips inside the integration lane | `tests/integration/test_api.py:166,193,174,197` | real-MT assertions vanish when the packs are absent |
| T-6 | the golden call **skips** without weights or on a busy port | `tests/realtime/test_golden_call.py:104,107`, fixed port `8765` (`:45`) | the realtime acceptance test can be green without running |
| T-7 | a **network-dependent** test in a unit file | `tests/unit/test_translation_pipeline.py:392` | pass/fail depends on sandbox egress |
| T-8 | optional-dependency skips | `tests/unit/test_document_pdf_geometry_and_ocr.py:27,65,91` | PDF/OCR coverage disappears without PyMuPDF |
| T-9 | wall-clock timing assertions | `tests/test_performance_and_load_hardened.py:45,55,62,64`; `tests/test_provider_chain_hardened.py:111-117`; `tests/test_queue_and_workers_hardened.py:126-132`; `tests/test_agent_media_session.py:291-292` | a loaded runner flips green→red |
| T-10 | process-global Prometheus counters shared by suites | `tests/test_telemetry_tracing_hardened.py:141-144`; `tests/test_observability_and_metrics_hardened.py` | label values accumulate across suites in one process (order-dependent) |
| T-11 | `monkeypatch.setattr(os, "environ", dict(os.environ))` | `tests/test_model_fetch_gates_hardened.py:377` | the env object itself is replaced |
| T-12 | stale `__pycache__` for deleted test modules | `tests/__pycache__/` holds `test_zz_probe`, `zz_scratch_diag*`, `test_settings_probe_tmp`, … | a stale `.pyc` can be collected and report phantom tests |

### 7.6 The "AI truthfulness" suites (what the repo actually holds itself to)

| Suite | Invariant it pins |
|---|---|
| `test_audit_round3_truthfulness.py` | a `private_only` request never downloads a 3B model, never falls through to an online provider, keeps the parser's own "no translatable text" reason, reports a gate block as HTTP 409, and covers the `componay` spelling variant |
| `test_private_only_guarantee_hardened.py` | the tenant `private_only` flag reaches the router as `intent=PRIVATE_ONLY` on **every** task (#114) |
| `test_model_fetch_gates_hardened.py` | every loader checks the cache first, fails honestly when the weights are absent, and no health probe loads or downloads (#112) |
| `test_provider_chain_hardened.py` | a hung attempt is cut at the deadline and the chain fails over; a not-ready candidate never enters the chain; Argos resolves packs cache-only (#111) |
| `test_realtime_translation_invariant_hardened.py` | a production meeting never receives a synthetic stand-in translation; `untranslated_fallback` is a failure; every fan-out translation cites its canonical segment |
| `test_glossary_mismatch_note_hardened.py` | a glossary whose language pair does not match is reported honestly via `glossary_note` |
| `test_usage_billing_units_hardened.py` | one canonical unit vocabulary across ledger/limits/pricing/client; limits that trip; an invoice that prices the translation volume and discloses what it does not (#115) |
| `test_ai_agent_graph.py` | disclosure is mandatory, identity is verified before any account statement, citations are limited to permitted documents, escalation triggers are exhaustive, the machine terminates on `END` — **not in CI** |
| `test_asterisk_ari_adapter.py` | the allowlist is enforced *before* any ARI action, an unreachable ARI is an honest unavailable outcome, terminal outcomes are claimed once, the simulated provider stays the default |
| `test_agent_turn_loop.py` | the turn loop derives no identity from text, fingerprints with sha256, and swallows sink failures |
| `test_production_telephony_gates.py` | production telephony fails closed at boot and stays honest at runtime |
| `test_telephony_privacy_abuse_gates.py` | PII handling, webhook rate limits and signature verification stay enforced in production posture |

---

## 8. The parallel trees: canonical, legacy lane, shared lane and the public SDK

The repository has **four** Python trees that answer to similar names. Knowing which one the deployed system loads is the single most useful thing this map records.

| Tree | What it is | Who loads it |
|---|---|---|
| `services/api/gt_ai/` | the **canonical** provider package (46 modules): the base protocol, the registry, the model router, every provider family | the API image (`Dockerfile.api:19` puts `services/api` first), the pytest config (`pyproject.toml:3`), the dev server (`run_api.py:18` chdirs into it) |
| `ai/gt_ai/` | the **legacy lane's** copy of the same package (43 modules) — the mirror the legacy `apps/api` server imports | the legacy lane; **and the inference worker**, which puts `ai/` first on `sys.path` (`workers/inference-worker/main.py:20-21`) — so the GPU worker resolves the *older* provider tree |
| `apps/api/globaltalk/` | the **legacy backend** (its own models, its own Alembic lineage, its own `globaltalk.*` package) | the legacy deployment only; `docs/DATABASE.md` records that it is never run alongside the canonical API |
| `gt_ai/` (repo root) | the **public SDK** for external consumers (7 files: the client, the HTTP transport, the shared types) — *not* a server package: it has no `model_router/`, no providers | external consumers; the risk is that it **shadows** the canonical package when it lands first on `sys.path` |

### 8.1 The mirror drift (measured file by file)

Of the 46 canonical modules, **35 are byte-identical** to their `ai/gt_ai/` twin. Eleven are not:

| Module | Relationship | Why it matters |
|---|---|---|
| `registry.py` | differs | the mirror's adapter map omits `gt_ai.translation.airllm` → `create("mt", "airllm")` raises `KeyError` in the lane that resolves the mirror |
| `translation/neural_online.py` | differs | the mirror lacks the DeepL source-text validation the canonical copy has (`services/api/gt_ai/translation/neural_online.py:282-300`) |
| `vad.py` | differs | the mirror lacks the cache-first Silero gate the canonical copy has (`services/api/gt_ai/vad.py:123-160`) — so a process that imports the mirror can still clone silero-vad from GitHub |
| `stt/azure_speech.py`, `tts/azure_speech.py`, `translation/azure_translator.py` | differ | the Azure adapters have diverged between the lanes |
| `stt/__init__.py`, `translation/__init__.py` | differ | the package exports differ (the canonical exports the adapters the mirror does not have) |
| `stt/recognizer.py`, `translation/translator.py`, `translation/airllm.py` | **canonical only** | `translator.py` and `recognizer.py` are imported **only by tests** (O-7) — production code that only tests reach |

**The rule this map proposes:** the canonical copy is the one that answers "what is authoritative", and the mirror is kept honest by *copying* it (the pattern this session used: `model_router/router.py`, `translation/madlad400.py` and `translation/nllb_ct2.py` were re-mirrored byte-identically in #113/#114/#115), never by re-implementing. Where the two must differ (the legacy lane's own semantics), the difference belongs in the mirror and is listed here.

<<<<<<< Updated upstream
### 8.2 The shadowing hazard (a name collision, not a bug)

`gt_ai/` at the repo root and `services/api/gt_ai/` are different packages with the same import name. Which one wins is decided by `sys.path` order, and the order is set differently per entry point:

| Entry point | `sys.path` order | resolves |
|---|---|---|
| the API image | `services/api` first (`Dockerfile.api:19`) | the **canonical** package ✓ |
| the dev server | `chdir` into `services/api` + `services/api` inserted at 0 (`run_api.py:14-18`) | the canonical package ✓ |
| pytest | `pythonpath = ["services/api", "apps/api", "ai", "."]` (`pyproject.toml:3`) | the canonical package ✓ (the root SDK is last) |
| the **inference worker** | `services/api` inserted, then `ai` inserted at 0 again (`workers/inference-worker/main.py:20-21`) | the **legacy mirror** ✗ |
| a plain `python` from the repo root | the cwd (the root) is `sys.path[0]` | the **root SDK** ✗ — this is why running a script from the repo root without an explicit `PYTHONPATH` imports the SDK, not the server package |

### 8.3 The scripts inventory
=======
### 8.2 The shadowing hazard (a name collision, plus two entry points that pick the wrong copy)

`gt_ai/` at the repo root and `services/api/gt_ai/` are different packages with the same import name. Which one wins is decided by `sys.path` order, and the order is set differently per entry point:

| Entry point | `gt_ai` resolves to | How |
|---|---|---|
| the API image | the **canonical** package ✓ | `PYTHONPATH=/app/services/api:…` (`Dockerfile.api:19`); the root SDK is not even copied into the image |
| the Render deploy | the **canonical** package ✓ | `services/api/start.sh` runs from the service directory |
| pytest | the **canonical** package ✓ | `pyproject.toml:3` puts `services/api` first; `tests/conftest.py:14-15` re-inserts it at index 0 |
| **the documented dev server** | ✓ the **canonical** package (fixed) | `run_api.py` now inserts the canonical path last, so it wins. It used to insert `ai/` last — the last insert lands at `sys.path[0]` — and the dev server ran the stale mirror |
| **the GPU inference worker** | ✓ the **canonical** package (fixed) | `workers/inference-worker/main.py` now inserts the canonical path last. It used to insert `ai/` last, so the GPU worker ran the stale mirror *and* the canonical app in one process |
| a plain `python` from the repo root | ✗ the **root SDK** | the cwd is `sys.path[0]`, and the root SDK defines the same 11 class names with an incompatible `Intent` base and **no** `NoPrivateProviderAvailable` — if it ever wins, `app/ai.py:32-35` raises `ImportError` and the whole AI facade dies at startup. The hazard is already acknowledged in `scripts/bench_tts_voices.py:4-7` |

### 8.3 The deployment that overwrote the canonical tree

`vercel.json`'s API install command used to run

```
pip install ../../ai && python -c "shutil.copytree('../../ai/gt_ai', './gt_ai', dirs_exist_ok=True); …"
```

The service root is `services/api`, so **`./gt_ai` *is* the canonical provider tree** — the copy merged the legacy lane's mirror over it. Harmless while the two trees were identical (they were, when the command was written); now it reverts the eight diverging canonical files in the serverless build — including the cache-first Silero gate (#113), the `neural_online` echo guard, the AirLLM registration and the `gt_ai.stt` / `gt_ai.translation` exports. `pip install ../../ai` put the same stale package into site-packages under the name `gt_ai` (the mirror's `ai/pyproject.toml` declares `include = ["gt_ai*"]`), even though nothing in `services/api` imports the legacy `ai` package.

**This is finding #1 in the risk register, and it has its own PR** (the install command no longer writes into the canonical tree).

### 8.4 Which entry point is "the app"?

| Command | What it actually starts |
|---|---|
| `make dev` (`Makefile:22` → `scripts/run_dev.sh:7`) | the **legacy** backend (`uvicorn globaltalk.main:app`, `PYTHONPATH=apps/api:.`) — not the canonical one |
| `python run_api.py` (`AGENTS.md` "Local Dev", `START_ALL.bat:11`) | the canonical app **and** the canonical provider tree (fixed) |
| `docker compose up` | the canonical app, the canonical providers ✓ |
| Render / Vercel | the canonical app ✓ — the Vercel build additionally overwrote the provider tree (§8.3) |

So there are four different "run the app" paths and **no two of them resolve the same code** — a green local run does not mean the deployed behaviour, and a green Docker run does not mean the local one.


### 8.5 The scripts inventory
>>>>>>> Stashed changes

| Script | Referenced by | Note |
|---|---|---|
| `scripts/download_models.sh` | CI (`ci.yml:205`), docs | the operator/CI model seeding path (`MODEL_PROFILE`, `STT_SIZE`) |
| `scripts/verify_ai_stack.py` | CI (`ci.yml:217`), docs | the AI-stack verification step — it inherits the `ai/bootstrap` cache policy since #112 |
| `scripts/bench_tts_voices.py`, `scripts/run_evaluation.py`, `scripts/run_dev.sh` | docs only | operator tools |
| `scripts/download_models.ps1` | **nothing** | the PowerShell twin of a CI-referenced script — a Windows-operator gap |
| `scripts/bootstrap_full_ai.{sh,ps1}` | nothing | a one-shot bootstrap with no owner |
| `scripts/apply_phase4_hardening.py` | nothing | **mutates source in place** (`app/realtime/livekit_bridge.py`) — a one-shot migration script that is not idempotent-safe and is referenced by nothing |
| `scripts/benchmark_translation_fanout.py`, `scripts/probe_e2e_features.py`, `scripts/update_cross_tests.py` | nothing | unreferenced tools |

---

## 9. The runtime environment

`services/api/app/config.py` (514 lines) — pydantic-settings; the env name is the upper-cased field name; `extra="ignore"`; the env file is resolved by `_find_env_file` (`:17-27`). The table below is grouped by what the setting actually controls, and the last column says whether **anything reads it** (§10.3 C-1 lists the ones nothing does).

| Area | Settings | Read by |
|---|---|---|
| Core | `APP_ENV` `APP_NAME` `VERSION` `API_PORT` `WEB_ORIGIN` `LOG_LEVEL` | `main.py:44,123`, `is_production` (`config.py:350`), the webhook base URL (`call_service.py:118`, `twilio_token.py:97`) |
| Secrets | `SECRET_KEY` `JWT_SECRET` `JWT_ALGORITHM` `JWT_ACCESS_TTL_MINUTES` `JWT_REFRESH_TTL_DAYS` `BCRYPT_ROUNDS` | `deps.py:106`, `security.py`; prod forces ≥32 chars (`config.py:364,368`) |
| Datastores | `DATABASE_URL` `DB_POOL_SIZE` `DB_MAX_OVERFLOW` `DB_ECHO` `REDIS_URL` `CACHE_BACKEND` | `app/db/session.py`, `app/cache.py:133`, `app/queue.py:338-358`; prod forbids SQLite (`:376`) and requires Redis (`:372`) |
| Storage | `S3_ENABLED` `S3_ENDPOINT` `S3_BUCKET` `S3_ACCESS_KEY` `S3_SECRET_KEY` `S3_REGION` `LOCAL_STORAGE_PATH` `MAX_UPLOAD_MB` | `app/storage.py:55`; the local root becomes `/tmp/storage` serverless (`:84,482`) |
| LiveKit | `LIVEKIT_ENABLED` `LIVEKIT_URL` `LIVEKIT_PUBLIC_URL` `LIVEKIT_API_KEY` `LIVEKIT_API_SECRET` `WEBRTC_ICE_SERVERS_JSON` | `realtime/livekit_bridge.py:34-39`; prod requires the URL and a `wss://` public URL (`:452,458`) and validates the TURN list (`:462-474`) |
| Telephony | `TELEPHONY_PROVIDER` `TWILIO_*` `TELNYX_*` `TELEPHONY_WEBHOOK_BASE_URL` `TELEPHONY_HUMAN_MOBILE_NUMBER` | `app/telephony/service.py:50-91`, the provider adapters; prod requires the credential sets (`:416-426,445`) |
| Asterisk | `ASTERISK_TELEPHONY_ENABLED` `ASTERISK_ARI_*` `ASTERISK_ALLOWED_EXTENSIONS` `ASTERISK_REQUEST_TIMEOUT_SECONDS` `ASTERISK_EVENT_RETRY_SECONDS` `ASTERISK_WS_RECONNECT_SECONDS` `ASTERISK_INBOUND_ENABLED` `ASTERISK_INBOUND_ORG_ID` | `app/telephony/providers/asterisk_provider.py:87`, `ari_client.py`, `ari_events.py`; the inbound org must be explicit (empty = fail closed) |
| Call worker / agent media | `CALL_WORKER_ENABLED` `CALL_WORKER_INTERVAL_SECONDS` `CALL_WORKER_BATCH_SIZE` `ASTERISK_MEDIA_ENABLED` `ASTERISK_MEDIA_BIND_HOST` `ASTERISK_MEDIA_BIND_PORT` `ASTERISK_MEDIA_EXTERNAL_HOST` `ASTERISK_AGENT_PERMITTED_DOCUMENTS` `ASTERISK_AGENT_SEGMENT_WAIT_SECONDS` | `main.py:208,245-258`, the media server, the agent graph |
| MT providers | `TRANSLATION_PROVIDER` `TRANSLATION_MODEL` `AIRLLM_*` `DEEPL_API_KEY` `DEEPL_API_URL` `MT_HTTP_URL` `MT_HTTP_STYLE` **`MT_HTTP_PRIVATE`** | `app/ai.py:154-216`; the privacy flags are the #114 opt-ins |
| STT / TTS | `STT_PROVIDER` `STT_MODEL` `STT_DEVICE` `STT_COMPUTE_TYPE` `STT_HTTP_URL` **`STT_HTTP_PRIVATE`** `TTS_PROVIDER` `TTS_MODEL` `TTS_HTTP_URL` **`TTS_HTTP_PRIVATE`** `TTS_VOICE_MAP` `LANG_DETECT_PROVIDER` `FASTTEXT_LID_MODEL` `SUMMARIZATION_PROVIDER` `LLM_HTTP_URL` `LLM_MODEL` **`LLM_HTTP_PRIVATE`** `EMBEDDING_PROVIDER` `EMBEDDING_MODEL` `MODEL_CACHE_PATH` `VAD_PROVIDER` `GPU_AVAILABLE` `PROVIDER_ATTEMPT_TIMEOUT_S` `DOCUMENT_TRANSLATION_CONCURRENCY` `WRITE_NEURAL_TIMEOUT_S` | the provider layer + `app/ai.py`; `TTS_VOICE_MAP` decides which voice speaks which language (`realtime/voices.py:30`) |
| Turn segmentation | `VAD_MIN_SPEECH_MS` `VAD_MIN_SILENCE_MS` `VAD_MAX_SPEECH_MS` `VAD_PARTIAL_INTERVAL_MS` `VAD_PHRASE_COMMIT_MS` | `realtime/pipeline.py:195-210,430,441` — the one source of truth for when a turn ends |
| Realtime deadlines | `RT_STT_DEADLINE_MS` `RT_MT_DEADLINE_MS` `RT_TTS_TTFB_DEADLINE_MS` `RT_INFERENCE_CONCURRENCY` `RT_RESUME_BUFFER_SIZE` `RT_TARGET_LATENCY_MS` | the three agents + the shared inference gate (`agents/inference_gate.py:55-60`), the replay buffer (`session_manager.py:61`) |
| Rate limits | `RATE_LIMIT_TRANSLATE` `RATE_LIMIT_AUTH` `RATE_LIMIT_DEFAULT` | `app/deps.py:274,279,283` |
| Security | `CLAMAV_HOST` `CLAMAV_PORT` `CORS_ORIGINS` `SECURE_COOKIES` `COOKIE_SAMESITE` `COOKIE_DOMAIN` `REFRESH_GRACE_SECONDS` `GOOGLE_CLIENT_ID` `GOOGLE_CLIENT_SECRET` `GITHUB_CLIENT_ID` `GITHUB_CLIENT_SECRET` `APPLE_CLIENT_ID` `ALLOW_SEED` `ALLOW_TEST_AUTH` | the CORS/security middleware, the social login, the seed gate (`seed.py:243`), the wildcard test key (`deps.py:186`) |
| Retention | `RETENTION_AUDIO_DAYS` `RETENTION_TRANSCRIPT_DAYS` `RETENTION_DOCUMENT_DAYS` `RETENTION_USAGE_DAYS` `RETENTION_ESCALATION_DAYS` | `app/services/retention_service.py:23` |
| Observability | `METRICS_ENABLED` `METRICS_TOKEN` | `app/routers/health.py:112-123` |
| Feature flags | `FF_VOICE_TRANSLATION` `FF_DOCUMENT_TRANSLATION` `FF_AGENT_BRIDGE` `FF_VOICE_PRESERVATION` `FF_NEW_TRANSLATION_MODEL` `FF_EXPERIMENTAL_LANGUAGE` `FF_ENTERPRISE_SSO` | the DB `FeatureFlag` defaults (`app/deps.py:302-308`), seeded at `app/seed.py:44-52` |

**The composite rules that matter for a deployment** (all in `config.py`): production forbids SQLite (`:376`) and requires Redis (`:372`), forbids a `*` CORS origin (`:380`), forces secure cookies (`:386`), demands ≥32-char secrets (`:364,368`), requires the LiveKit URL to be `wss://` (`:458`), requires the complete carrier credential set (`:416-426`), blocks `TELEPHONY_PROVIDER=auto` when carrier credentials exist (`:392-403`), and blocks the Asterisk lane unless it is explicitly admitted (`:436`).

---

## 10. The consolidated risk register

Every row is verified with a file + line. **Nothing here was deleted or "fixed"** — the roadmap's rule for the day is to flag, and several of these deserve their own PR and their own decision.

### 10.1 The ones that are live bugs (verified by reading the code path)

| # | Risk | Evidence | What goes wrong |
|---|---|---|---|
<<<<<<< Updated upstream
| **B-1** | **The metering worker dies on every pass after the first quota threshold.** The threshold markers are written *inside* `quota_json`; the next pass iterates them, so `limit` becomes a dict and `used / limit` raises `TypeError`, which the blanket `except` swallows as "metering pass failed". | `workers/metering-worker/main.py:65-66` writes `qj["_thresholds"] = state`; `:50` iterates `quota.items()`; `:53` divides by `limit`; `:68-69` catches everything | After the first 80 %/100 % threshold crossing the worker never finalizes an invoice and never dispatches a threshold webhook again. The invoice line the page claims comes "from real metering" stops moving |
=======
| **B-0** | **The Vercel build overwrites the canonical provider tree with the stale mirror.** `vercel.json`'s install command copied `../../ai/gt_ai` over `./gt_ai` — and the service root is `services/api`, so `./gt_ai` **is** the canonical tree. | `vercel.json` (`services.api.installCommand`), the eight diverging pairs in §8.1 | The serverless deploy silently reverts the cache-first Silero gate (#113), the `neural_online` echo guard, the AirLLM registration and the `gt_ai.stt` / `gt_ai.translation` exports. **Fixed in its own PR** (the install command no longer writes into the canonical tree) |
| **B-1** | **The metering worker dies on every pass after the first quota threshold.** The threshold markers are written *inside* `quota_json`; the next pass iterates them, so `limit` becomes a dict and `used / limit` raises `TypeError`, which the blanket `except` swallows as "metering pass failed". | `workers/metering-worker/main.py:65-66` writes `qj["_thresholds"] = state`; `:50` iterates `quota.items()`; `:53` divides by `limit`; `:68-69` catches everything | After the first 80 %/100 % threshold crossing the worker never finalizes an invoice and never dispatches a threshold webhook again. The invoice line the page claims comes "from real metering" stops moving. **Fixed in its own PR** |
>>>>>>> Stashed changes
| **B-2** | **Agent Studio returns fabricated results as if they were real.** The fallback (used whenever the `bridge.py` subprocess is missing or fails) returns a hard-coded report with `"verified": True`, and a hard-coded draft with `"score": 9.2`, `"published_path": "content/published/article.md"`, `"status": "published"`. | `services/api/app/routers/agent_studio.py:114-125` (`_fallback_research`), `:128-139` (`_fallback_content`), used at `:147-166`; `/status` always reports `"ready"` (`:236`) | A caller cannot tell a fabricated "verified" report or a claimed publication from a real one — the exact failure mode the rest of the repo refuses |
| **B-3** | **The CopilotKit agent endpoints have no auth** and swallow every failure into a canned greeting. | `services/api/app/agent.py:64-74` (no `Depends`), `:115-119` (the catch-all) | An unauthenticated LLM proxy; and a failure is indistinguishable from a success to the caller |
| **B-4** | **The legacy `/v2/*` and `/v3/*` surface is mounted at the root** and most of its routes use `get_principal_optional` — anonymous by default. | `services/api/app/routers/v2_v3.py:48` (no prefix), `main.py:83`; `get_principal_optional` at `:288,435,469,504,927,976,996,1011,1020` | Glossaries / style rules / translation memories are reachable without a principal unless the handler adds its own tenant check (asserted only by the non-CI `test_tenant_security_extended.py:19-23`) |
| **B-5** | **The inference worker resolves the stale provider tree.** It puts `ai/` **before** `services/api` on `sys.path`, so that process imports the drifted `ai/gt_ai` copy — which has no `airllm` adapter, no cache-first Silero and no DeepL source validation. | `workers/inference-worker/main.py:20-21` (`ai` inserted last ⇒ first) vs `infrastructure/docker/Dockerfile.api:19` (`services/api` first) | The GPU worker is the one process that can build a provider the API cannot, and its Silero path can still clone from GitHub |
| **B-6** | **The phone-call intake bypasses the provider router** and loads its own Whisper instance. | `services/api/app/routers/translate.py:338` (`WhisperModel("tiny", …)`), with the facade fallback at `:385-388` | Two Whisper code paths; the router's cache gate, readiness filter and attempt deadline do not apply to the direct one |

### 10.2 Ownership and drift

| # | Risk | Evidence | What goes wrong |
|---|---|---|---|
| **O-1** | The `ai/` tree and `services/api/gt_ai/` are mirrors that have **drifted** (8 files differ; 3 exist only in the canonical copy; `ai/gt_ai/registry.py` omits the `airllm` adapter; `ai/gt_ai/vad.py` lacks the cache-first Silero fix; `ai/gt_ai/translation/neural_online.py` lacks the DeepL source-text validation). | `services/api/gt_ai/registry.py:62` vs `ai/gt_ai/registry.py`; `services/api/gt_ai/vad.py:123-160` vs `ai/gt_ai/vad.py`; `services/api/gt_ai/translation/neural_online.py:282-300` | Two answers to "where does the provider layer live" — and the older one is what one worker imports (B-5) |
| **O-2** | The root-level `gt_ai/` **SDK** shares a name with the canonical package. | `gt_ai/` at the repo root vs `services/api/gt_ai/`; `pyproject.toml:3` puts `services/api` first for pytest, but `run_api.py:15` and `workers/inference-worker/main.py:20-21` manipulate the order themselves | Whichever copy is first on `sys.path` wins — the canonical one for the API image, the legacy one for the inference worker |
| **O-3** | Two realtime fan-out engines with different semantics. | `app/realtime/translation_fanout.py:132` is imported only by the telephony bridge (`telephony/bidirectional_bridge.py:26`); the meeting pipeline runs its own (`pipeline.py:894,940`) | The invariant test (`test_translation_fanout.py`, 10 tests) covers the telephony one; the pipeline's is covered by a different suite |
| **O-4** | Staleness / barge-in logic exists twice in the same room. | `agents/supervisor.py:158,218,222` vs `pipeline.py:1241` (`_is_stale`), `:516` (`_handle_barge_in`), `:466` (`_split_running_utterance`) | Two sources of truth; `test_realtime_barge_in.py` covers the pipeline path, `test_realtime_agents_trace.py` the agent path |
| **O-5** | `/api/v1` prefix ownership is split across **seven** router modules. | `translate.py:30`, `write.py:15`, `customization.py:30`, `orgs.py:22`, `meetings.py:33`, `assistant.py:25-26`, `platform.py:32` | No single owner for the prefix; a new route can collide with seven modules' expectations |
| **O-6** | `app/workers_runner.py` is an **orphan** worker entry point that duplicates the in-process registration and omits the `default` queue. | `workers_runner.py:31-37` vs `main.py:180-192`; no importer, no Docker/Make target | Two competing "worker" entry points; the standalone one is not what the image runs |
| **O-7** | Unreachable modules inside the canonical backend: `app/mcp/indic_server.py`, `app/globaltalk_client.py` (whose docstring claims "all callers inject the same singleton" — false), `gt_ai/evaluation/runner.py`, `gt_ai/translation/translator.py` + `gt_ai/stt/recognizer.py` (451 lines, imported only by tests). | `globaltalk_client.py:26-27` vs zero importers; `gt_ai/translation/translator.py` imported only by `tests/unit/test_translation_adapter.py:2` | Dead code that reads as live; the "only place" claim in the docstring is wrong |
| **O-8** | Two modules named `webhook_service` with different owners. | `app/services/webhook_service.py:39` (org webhooks) vs `app/telephony/webhook_service.py:20` (carrier callbacks) | A naming trap for the matrix and for reviewers |
<<<<<<< Updated upstream
=======
| **O-9** | **Two entry points resolved the stale mirror instead of the canonical provider layer — fixed.** `run_api.py` (the documented dev server, `AGENTS.md`, `START_ALL.bat:11`) and the GPU inference worker both inserted `ai/` *last* at `sys.path[0]`, so `ai/gt_ai` won. | `run_api.py:14-15`; `workers/inference-worker/main.py:20-21` — both now insert the canonical path last, and `tests/test_entrypoint_provider_resolution.py` imports each entry point in a subprocess and asserts which `gt_ai` was resolved | The dev server and the GPU worker ran a provider layer 8 files behind the canonical one — no AirLLM adapter, no Silero turn debounce, no DeepL echo guard — while the worker also imported the canonical app |
| **O-10** | **`make dev` starts the legacy backend, not the canonical one.** | `Makefile:22` → `scripts/run_dev.sh:7` (`PYTHONPATH="apps/api:."`, `uvicorn globaltalk.main:app`) | A developer following the documented command debugs `apps/api/globaltalk`, whose providers come from the legacy `ai/providers` lane — every fix made in `services/api/gt_ai` is invisible locally |
| **O-11** | **The canonical service declares the mirror as its `gt-ai` dependency.** | `services/api/pyproject.toml:30` + `:41-42` (`[tool.uv.sources] gt-ai = { path = "../../ai" }`); `ai/pyproject.toml:25-26` (`include = ["gt_ai*"]`) | Any `pip install ./services/api` puts the **stale** `ai/gt_ai` into site-packages under the name `gt_ai`; where site-packages precedes the service directory, the wrong copy is imported |
| **O-12** | Two stale scripts in `scripts/` **mutate source in place** and are referenced by nothing. | `scripts/apply_phase4_hardening.py:52,83,160,194,204` write to `services/api/app/**` without the guard used at `:43` (its pattern no longer matches, so the later blocks rewrite unconditionally); `scripts/update_cross_tests.py:183-188` appends a test that already exists at `tests/test_cross_tenant_security.py:161` | Running either silently rewrites or duplicates canonical source and test files — and CI lints them, so they look maintained |
>>>>>>> Stashed changes

### 10.3 Configuration and environment

| # | Risk | Evidence | What goes wrong |
|---|---|---|---|
| **C-1** | **18+ settings are declared and never read** (plus 4 read only through `getattr`): `api_host`, `fallback_database_url`, `supabase_url`, `supabase_anon_key`, `supabase_service_role_key`, `supabase_jwt_secret`, `telephony_sample_rate`, `telephony_recording_default`, `ocr_provider`, `otel_enabled`, `otel_endpoint`, `sentry_dsn`, `csrf_enabled`, `rate_limit_ws_connect`, `rate_limit_telephony_call`, `rate_limit_telephony_webhook`, `rt_stale_after_ms`, `rt_min_chunk_ms`, `rt_max_chunk_ms`, `rt_session_ttl_s`, `worker_inproc`, `doc_job_poll_interval_s`. | `services/api/app/config.py:47,64,72-75,114,214,252-255,262-264,267,271-273,307,337-338`; a repo-wide search for each name outside `config.py` returns 0 hits | An operator sets `RT_SESSION_TTL_S` and the sweeper ignores it (it hard-codes a 300 s grace at `realtime/ws.py:550`); `CSRF_ENABLED=false` does **not** disable CSRF (the middleware always enforces it, `middleware.py:41-66`); `RATE_LIMIT_TELEPHONY_CALL` / `_WEBHOOK` are named limits that `deps.py` never wires |
| **C-2** | The carrier auto-selection can silently pick the **simulated** provider when only part of the credentials are set. | `app/telephony/service.py:85-91`; the prod validator only blocks `auto` when *complete* carrier credentials exist (`config.py:392-403`) | A half-configured deployment calls the simulated provider in production and reports success |
| **C-3** | Webhook signature verification **fails open** outside production when the carrier token is absent. | `app/telephony/security.py:41-44` (Twilio), `:74-77` (Telnyx), `:140-142` (`"unauthenticated_dev_pass"`) | "Signature verified" cannot be trusted outside prod; the callers must honour the returned reason, not just the boolean |
| **C-4** | `/metrics` is public by default outside production and `METRICS_ENABLED` defaults to `True`. | `app/routers/health.py:112-123`; `config.py:274` | Latency histograms and tenant-labelled series are world-readable on a dev box |
| **C-5** | The `ModelRegistry` seed is **insert-only** for every row except the `*_http` ones, while the registry is the routing source of truth. | `app/seed.py:145-163`; `app/ai.py:333-345` | An operator who edits a registry row in the database keeps a stale row next to the config-driven one |

### 10.4 Frontend (details in §2.4)

F-1 a whole duplicate router is dead · F-2 five dead files · F-3 two production-dead modules · F-4 duplicated chrome/primitive layers · F-5 the admin routes are unguarded in the router · F-6 368 lines of commented-out legacy translators · F-7 the CRM area has no page · F-8 19 pages and 3 hooks have no test.

### 10.5 Test and gate (details in §7.3–§7.5)

- **T-0** — 9 suites (102 test functions) ran in **no CI job**, and they were disproportionately the
  *security* ones: tenant isolation, BOLA/IDOR, WS authorization, the full auth flow, storage/webhook
  SSRF, the agent graph, the meeting-media contract, the deployment alignment. **They are now wired**
  into the hardened lane — the tenant isolation, the full auth flow, the cross-tenant checks, the real
  social verification, the storage/webhook SSRF guards, the agent graph, the meeting-media contract and
  the deployment alignment (all pass there). The one suite that stays out is
  `test_realtime_security_hardened.py` — excluded on purpose, for the SQLite lock contention documented
  in `ci.yml`.
- T-1 … T-12 — the order-dependence and environment-dependence landmines (the `app.config` reload that forks the `settings` singleton, the shared session SQLite, the `MODEL_CACHE_PATH` leak, the weights-dependent skips, the wall-clock assertions, the process-global Prometheus counters, the stale `__pycache__`).

---

## 11. Documentation corrections this map shows are needed

Each row is **filed, not applied** — a docs-only PR should follow the same review as this one.

| # | File:line | Says | Reality |
|---|---|---|---|
| D-1 | `docs/ARCHITECTURE.md:74` | "`apps/api` — FastAPI control+data plane" | the deployed plane is `services/api` (`infrastructure/docker/Dockerfile.api:19,36` → `app.main:app`); `apps/api` is the legacy tree |
| D-2 | `docs/ARCHITECTURE.md:73-84` | the repository layout | it omits `services/api` as canonical, the root `gt_ai/` SDK, `apps/amazon-connect-v2v`, `mcp/`, `sdk/`, `cli/`, `workers/*` |
| D-3 | `docs/AI.md:7-17` | the provider abstraction is `ai/interfaces.py` + `ai/providers/**` + `ai/model_router` | those paths exist but are the **legacy lane**; the canonical is `services/api/gt_ai/{base.py,registry.py,model_router/router.py}` — the doc never says which tree is authoritative |
| D-4 | `AGENTS.md:42` | "Tests use `services/api/conftest.py` fixtures" | that file does not exist; the canonical fixtures are in `tests/conftest.py` |
| D-5 | `docs/AI.md`, `docs/API.md`, `docs/REALTIME.md` | — | they do not mention the surfaces this cycle added: the `*_HTTP_PRIVATE` flags, `GET /api/v1/billing/plans`, the `private_only` / `tenant_private_only` request fields, the meeting/call privacy flags, the canonical dimension vocabulary |

---

## 12. Keeping this map true

The map is a snapshot of `017be8f` (+ #116 open). To refresh it, re-run the same four sweeps and re-check the specific claims that move fastest:

| Claim | How to re-check |
|---|---|
| the hardened lane's membership | list the flat suites and grep `ci.yml` for each name — 9 are referenced nowhere |
| the mirror drift | diff `services/api/gt_ai/` against `ai/gt_ai/` file by file; the canonical is the one `Dockerfile.api` puts first on `sys.path` |
| the unread settings | for each name in `app/config.py`, grep the app for a read; a `getattr(settings, "x", …)` counts as read |
| the dead frontend files | for each module, grep the whole `apps/web/src` for its import path — a test-only import is still dead code |
| the gate landmines | the `app.config` reload in `tests/conftest.py` is the one that silently changes test outcomes — keep T-1 in view |

**A rule for future maps:** a matrix is only worth its cost if it names *which* file is authoritative for each responsibility. Where two files claim it, this document says which one the deployed system loads — not which one looks newer.

---
