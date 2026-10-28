# TalkFlow / GlobalTalk AI — Evidence-Based Full Repository Audit and DeepL Gap Report

> **Provenance note (added 2026-10-29):** This document is the preserved historical snapshot of the
> initial repository audit, written against **commit `bb5425d`** (2026-10-28). Its **NO-GO** verdict
> reflects the state of that commit only. Subsequent remediation is tracked in
> [`04-gap-register.md`](04-gap-register.md), [`09-phased-remediation-plan.md`](09-phased-remediation-plan.md),
> [`10-release-go-no-go.md`](10-release-go-no-go.md) and
> [`11-initial-report-reconciliation.md`](11-initial-report-reconciliation.md). Do not cite this
> snapshot's findings as current facts.

**Audit date:** 2026-10-28
**Repository:** https://github.com/Aman678317/TalkFlow
**Current branch:** main
**Observed HEAD:** `bb5425d88f6588268047cfce2606d4201f5fbe62` — feat: cleanly separate Global Call and Live Voice into distinct pages and navigation routes
**Reference:** DeepL public translator, DeepL API, and DeepL Voice public product documentation
**Audit type:** Remote repository/code/document inspection plus public reference research

**Important limitation:** This is not a complete local runtime or production penetration test. The
repository tree and selected source files/docs/PRs/issues were inspected remotely. I did not run the
repository locally, access private production dashboards, read secret values, log into DeepL, or
verify real provider credentials. A deployed TalkFlow URL was not accessible through the web browser
in this audit. Findings below clearly separate repository evidence from runtime verification.

---

## 1. Executive summary

TalkFlow is a large full-stack codebase, not a blank MVP. GitHub reports the repository as public,
with Python as its primary language, 1,635 tracked paths in the current main tree, a
Vite/React/TypeScript frontend, FastAPI/Python services, database migrations, realtime
WebRTC/LiveKit/WebSocket code, translation/STT/TTS adapters, MCP servers, SDKs, telephony,
documents, and test suites.

The main issue is not a lack of code or a lack of documented features. It is proving that the active
deployed configuration delivers a complete, correct, low-latency experience from real microphone
audio through STT, translation, TTS, per-listener routing, and audible playback while the video call
remains healthy.

### Current release assessment

**Recommendation: NO-GO** for a production pilot until the open per-listener translation/video
blocker is reproduced and closed, a staging deployment rehearsal is evidenced, real-provider and
mobile-network checks pass, and privacy/support gates are signed off.

This is a release recommendation based on repository evidence, not a claim that the deployed site
was tested.

**Key reasons:**

1. GitHub issue #53 remains open and explicitly tracks group video reliability and per-listener
   live translated audio.
2. The measured local CPU realtime drill documented in `docs/LOAD_CAPACITY_ENVELOPE.md` reports
   end-to-end p50 latency increasing from about 12.2 seconds at concurrency 1 to 35.4 seconds at
   concurrency 2 and 51.2 seconds at concurrency 4. The document attributes the dominant bottleneck
   to STT finalization/queueing. These are local test results, not production measurements, but they
   are far above a comfortable conversational target.
3. The same load report records provider failures for configured language routes in cold-start runs
   and voice coverage gaps: Japanese is described as a valid source but not a target for the
   measured Piper setup because no Japanese voice was installed. A feature must be considered
   supported only when the exact source/target/modality/model/voice path is validated.
4. The repository intentionally contains two backend/schema lineages: `services/api` (canonical
   deployed API) and legacy `apps/api`, with different model/migration sets. Documentation says 43
   tables in the deployed API lineage and 39 in the legacy lineage, with 35 shared tables still
   having differences. This creates ongoing maintenance and migration risk unless the legacy
   boundary is tightly controlled.
5. The existing reference-parity benchmark is useful but limited: Issue #102 compares a local
   production frontend bundle against DeepL web pages for loading and payload, not DeepL Voice's
   end-to-end speech translation quality/latency. Its issue remains open and explicitly lists
   remaining parity gaps.
6. The repository has security and production-hardening documentation, but its checklist still
   contains uncompleted items such as secret rotation confirmation, malware scanning, TLS/HSTS,
   database/Redis/object-storage hardening, model-license review, and Sentry/OTel wiring.
   Configuration files cannot prove that deployed secrets and services are set correctly.
7. GitHub combined status on the observed HEAD returned two successful Vercel contexts. That is not
   equivalent to evidence that every CI suite, provider integration, live call, database migration,
   or production workflow passed on this exact SHA.

---

## 2. Evidence reviewed

The audit inspected the current repository metadata/tree, `README.md`, root `package.json`,
`.env.example`, `render.yaml`, `.github/workflows/ci.yml`, `docs/PRODUCTION_AUDIT.md`,
`docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/REALTIME.md`, `docs/DATABASE.md`,
`docs/LOAD_CAPACITY_ENVELOPE.md`, `docs/TRANSLATION_ACCEPTANCE.md`,
`services/api/requirements.txt`, `services/api/app/routers/auth.py`,
`services/api/app/services/social_auth_service.py`,
`services/api/app/realtime/agents/translation.py`,
`services/api/app/realtime/translation_fanout.py`, `apps/web/src/lib/api.ts`,
`apps/web/src/pages/MeetingRoom.tsx`, `apps/web/vite.config.ts`, and
`apps/web/e2e/livekit-outage.spec.ts`.

**Also reviewed:**

- Open Issue #53 — group video reliability and per-listener live translated audio
- Open Issue #52 — live translation quality, writing correction, and PDF coverage/performance
- Open Issue #102 — DeepL reference-parity benchmark report
- Merged PR #138 — load/latency/cost envelope
- Merged PR #101 — frontend reference-parity pass
- Merged PR #71 — Asterisk ExternalMedia transport
- Merged PR #61 — telephony webhook security/idempotency and CRM/consent gate

**Not inspected or verified:** secret values, production database, deployed environment variables,
provider account quota/billing, real customer data, private Vercel/Render runtime logs, a live
multi-device call, a real microphone-to-translated-audio session, mobile carrier/TURN path, and
current legal/privacy sign-off.

---

## 3. Repository architecture and scope

### Observed stack and main paths

| Layer | Evidence in repository | Audit interpretation |
| :--- | :--- | :--- |
| Frontend | `apps/web`, React/Vite/TypeScript, `MeetingRoom.tsx`, `Voice.tsx`, API client, E2E tests | Substantial UI and integration code exists. Runtime correctness is not proven by source presence. |
| Canonical API | `services/api`, FastAPI, async SQLAlchemy, Pydantic, Alembic | README and deployment docs identify this as the deployed API path. |
| Legacy API/worker | `apps/api/globaltalk`, separate synchronous SQLAlchemy models and Alembic lineage | Must be treated as legacy/worker-only unless a specific deployment target proves otherwise. Avoid accidentally testing/deploying it as the canonical API. |
| Database | PostgreSQL/pgvector in production docs; SQLite in dev; Alembic migrations | Schema/migration design exists, but the two lineages diverge and production DB state was not accessible. |
| Cache/queue | Redis in production docs; in-process/memory in development | In-memory fallback must not silently masquerade as production distributed coordination. |
| Media | LiveKit SFU path, WebRTC P2P code, WebSocket PCM path | Multiple transports increase complexity. One canonical production path should be the default and tested end to end. |
| AI | STT, translation, TTS adapters, model router, local/offline models, optional cloud providers | Provider readiness is a runtime property. An adapter or environment variable alone does not mean it is configured or performant. |
| MCP | `mcp/desi-mcp-server` and `services/mcp` contain overlapping MCP implementations | Review parity and deployment ownership to avoid one implementation drifting from the other. |
| Python SDK / tools | `gt_ai_sdk`, `sdk/`, `cli/`, `services/api/gt_ai` | Many public surfaces require contract tests against the canonical API. |
| Telephony | Twilio/provider adapters, Asterisk ARI/ExternalMedia, CRM/call job paths | Merged code/CI does not prove a real carrier sandbox round trip; provider credentials and sandbox drills must be separately evidenced. |
| Deployment | `render.yaml`, `vercel.json`, Docker Compose, Kubernetes and CI workflows | Multiple deployment targets require a documented canonical target and a staging rehearsal on the exact release SHA. |

### Architectural risk: dual backend and schema lineages

`docs/DATABASE.md` documents:

- `services/api`: canonical deployed API and its Alembic lineage.
- `apps/api`: legacy worker lineage, separate version table, models and migrations.
- 35 shared tables with different column names and/or ID types; each lineage also has tables the
  other does not.

This is not automatically a production defect if the ownership boundary is real and enforced. It is
a significant change-risk area. Every migration, test, task worker and deployment entrypoint must
explicitly state which lineage it uses. Do not merge the two schema sets as part of a quick fix;
first add ownership checks and CI guards against the wrong migration path.

### Deployment entrypoint drift

The README identifies `services/api` as the canonical deployed backend and local API port 8088.
`.env.example` shows `API_PORT=8000`; deployment docs mention container API port 8000; Render uses
`PORT=10000`. These values can all be valid for different environments, but they are easy to mix up.

**Required fix:** document and test the effective bind port, public API base URL, frontend proxy
target, WebSocket URL, health route, and deployment service for each environment. The app must not
rely on a developer remembering which port applies.

---

## 4. DeepL reference comparison

The reference was evaluated from public DeepL documentation/product pages, not by reverse-
engineering private internals. "Unknown" means there is no evidence in the public reference
material or inspected TalkFlow files to support a claim.

| Capability | DeepL public reference evidence | TalkFlow evidence/status | Gap and next step |
| :--- | :--- | :--- | :--- |
| Text translation | DeepL API supports server-side HTTP translation; public docs list 100+ languages and glossary/formality/context controls. | `/v2/translate`, translation provider adapters, glossaries and translation memory are documented in TalkFlow. | Run the same curated source/target corpus through both systems, measure quality with blind human review plus BLEU/COMET or other appropriate metrics, and document pair-specific limits. Do not claim parity from endpoint existence. |
| Live subtitles | DeepL Voice supports live translated subtitles for Teams, Zoom and Google Meet according to its public product docs. | TalkFlow has caption events, transcript/translation events, browser caption UI and meeting WebSocket code. Issue #53 remains open. | Prove correct speaker/utterance attribution and per-listener language delivery under overlapping speech, reconnects and group calls. |
| Voice-to-voice | DeepL Voice public docs describe voice-to-voice translation for online meetings through its desktop app and eligible plan. | TalkFlow has STT→translation→TTS, audio playback and fan-out architecture; the load report reveals high local latency and target-voice coverage gaps. | Make real translated audio—not only captions—the release gate. Measure first translated audio and end-to-end p50/p95 by language pair on target hardware. |
| Meeting integrations | DeepL Voice public pages name Microsoft Teams, Zoom and Google Meet, with desktop app integration. | TalkFlow has its own meeting experience and telephony/agent integrations; no evidence inspected proves it automatically detects/joins all three external meeting products. | Treat native TalkFlow meetings and third-party meeting integration as separate products. Add platform-specific adapters only with authorized supported integration paths and E2E tests. |
| Voice/language coverage | DeepL publishes a modality-specific Voice language matrix; some transcription/speech features are supplied by external providers, and not every language has every modality. | TalkFlow has a capability registry and language-pair acceptance docs, but the load report notes a missing Japanese TTS voice in its tested setup and unconfigured/failing paths. | Publish a truthful matrix by source language, target language, STT, MT, TTS voice, provider, deployment profile and validation status. Never advertise a language as full voice-to-voice if only text translation works. |
| Terminology | DeepL Voice documents glossaries, spoken terms and formality/customization. | TalkFlow has glossary/TM/style features in docs and API routes. | Compare UI workflows, term coverage, spoken-term handling, versioning and real speech recognition impact, not just the presence of a glossary table. |
| Privacy | DeepL states meeting content is not used to train models; public pages describe temporary processing/deletion and enterprise controls. | TalkFlow documents consent, tenant scoping, retention, voice consent and synthetic-audio flags. Deployment/legal evidence is not available in this audit. | Publish precise data-flow and retention disclosures; validate cleanup jobs, consent withdrawal, provider terms and deletion across originals and derivatives. Legal review remains a separate gate. |
| API key safety | DeepL explicitly says not to call its API directly from browser code and to route calls through a backend. | `.env.example` places `DEEPL_API_KEY` server-side and warns never to put it in `VITE_*`; actual secret values were not inspected. | Confirm frontend bundles contain no provider key; test a real backend request in staging and test invalid key, quota, timeout and provider outage. |
| Frontend performance | Issue #102 benchmark: local production bundle measured against DeepL web pages on 2026-10-21. | After PR #101, the report lists `/translate` DCL 158 ms vs 1,187 ms reference, load 159 ms vs 2,095 ms, transfer 15 KB vs 1,047 KB, and entry chunk 265 KB vs prior 841 KB. | This is a narrow local browser benchmark and not a global production SLA. Re-run on real devices/networks and keep the exact method/build SHA. It says nothing about live translation latency. |
| Page/URL translation | DeepL's web product includes translation workflows; issue #102 identifies page/URL translation as a remaining parity gap. | Issue #102 says page/URL translation is not present in the app. | Add only if it belongs in MVP. Scope a secure URL-fetching/proxy design with SSRF defenses, or defer explicitly. |
| Language selector UX | DeepL reference uses a mature searchable language experience. | Issue #102 identifies TalkFlow's native select + "More" list as less capable than a searchable keyboard-accessible combobox. | Build a searchable, accessible selector with native language names, keyboard navigation and capability-aware disabled states. |
| Writing keyboard UX | Issue #102 reports shortcuts were added in PR #101 but remains open for other parity work. | PR #101 includes shared shortcut fixes; the exact current browser behavior was not run here. | Keep unit/E2E coverage and verify the current main build. |
| Internal backend/database | Not disclosed by public DeepL pages. | TalkFlow has inspectable Python backend/database code. | Not comparable from public evidence. Do not invent DeepL's database, routing, API-key management internals or MCP architecture. |

### Benchmark interpretation

The PR #101 benchmark is meaningful evidence for frontend bundle performance, but it is not proof
that TalkFlow is faster than DeepL for translation or speech translation. It compares specific
page-load metrics in a local environment. The comparison must remain scoped to those metrics.

DeepL's API documentation says browser-side direct API calls are blocked and expose credentials;
TalkFlow should preserve the backend proxy pattern. Reference:
https://support.deepl.com/hc/en-us/articles/9773914250012-About-DeepL-API

- DeepL Voice product reference: https://www.deepl.com/en/voice-app
- DeepL Voice API reference overview: https://www.deepl.com/en/developers
- DeepL Voice language matrix: https://support.deepl.com/hc/en-us/articles/26625846174364-DeepL-Voice-languages

---

## 5. Prioritized gap register

Severity is based on expected user/production impact. "Verified in repository" does not mean
reproduced in production.

| ID | Severity | Area | Finding and evidence | Status | Required resolution / acceptance |
| :--- | :--- | :--- | :--- | :--- | :--- |
| G-001 | P0 | Group calls + translated audio | Issue #53 is open and explicitly tracks group video reliability and per-listener translated audio. `MeetingRoom.tsx`, `useLiveKitRoom.ts`, `webrtc.ts`, `ws.ts`, and realtime pipeline span multiple paths. | Verified repository blocker; live reproduction not performed | Run 3+ real browser participants across different devices/networks; each chooses speak/hear language; assert correct per-seat audio/caption, no cross-room leaks, no echo, no wrong-speaker captions; close #53 only with artifacts. |
| G-002 | P0 | Realtime latency | `docs/LOAD_CAPACITY_ENVELOPE.md` reports local end-to-end p50 around 12.2 s at C=1, 35.4 s at C=2, 51.2 s at C=4; STT finalization is identified as bottleneck. | Measured local result; production unknown | Profile STT queueing, VAD hangover, model cold start, thread/process isolation and CPU contention. Set an agreed conversational SLO; report p50/p95/p99 on target pilot hardware. Do not hide slow traces or use fake-provider results as production evidence. |
| G-003 | P1 | Language/voice readiness | Load envelope says Japanese can be a source but not a target in the measured Piper setup because no Japanese voice is installed; cold provider routes can fail. | Verified in local report | Readiness must be modality-aware; block/disable unsupported voice output, allow captions when possible, and test every advertised pair with actual STT+MT+TTS. |
| G-004 | P1 | Staging/release gate | Prior Day-7 launch checkpoint documented missing candidate-freeze/staging rehearsal, qualified privacy/legal review, and support ownership; current audit did not find proof that these were completed. | Not verified complete | Run `docker-compose.staging-rehearse.yml` or the current documented staging procedure against exact release SHA; record health, migration, provider, rollback, support owner and sign-offs. |
| G-005 | P1 | Database lineage | `docs/DATABASE.md` documents two divergent schema/migration lineages and 35 shared tables with differing columns/ID types. | Verified documentation | Add CI checks that canonical services use only `services/api` migrations; test upgrade, drift, rollback and fresh database on PostgreSQL. Prohibit accidental legacy migrations in API deployment. |
| G-006 | P1 | Provider configuration and API keys | `.env.example` has many provider variables; configuration presence is not proof of valid credentials, quotas, voice availability or deployment wiring. | Partially verified; live credentials unavailable | Add safe diagnostics for configured/available/supported/validated status; never print secret values. Staging tests must prove success and error paths for each selected provider. |
| G-007 | P1 | Security checklist | `docs/SECURITY.md` includes unchecked production tasks for secret rotation, malware scan, TLS/HSTS, database/Redis/S3 hardening, model-license review and observability. | Verified checklist; deployed state unknown | Complete and evidence each item or record approved exception. No pilot if critical security controls are unverified. |
| G-008 | P1 | Old audit documentation drift | `docs/PRODUCTION_AUDIT.md` is dated 2026-10-04 and reports localStorage tokens and insecure social login; current `apps/web/src/lib/api.ts` shows sessionStorage access-token persistence and an HttpOnly refresh-cookie pattern, and `social_auth_service.py` contains cryptographic provider verification code. | Verified documentation/code discrepancy; runtime tests not run | Re-audit these controls against current code and tests; update old findings to fixed/partial/open with commit/test evidence. Do not carry stale vulnerabilities forward as current facts, and do not assume the newer code is fully secure without tests. |
| G-009 | P1 | Auth/config/tenant safety | Security docs claim tenant-scoped checks, hashed API keys and WebSocket join tickets, but no live cross-tenant penetration test was run in this audit. | Documented controls; independent verification blocked | Run negative tests for every protected route/WebSocket: wrong org, wrong meeting, expired/replayed ticket, revoked API key, forged social token, refresh race and unauthorized transcript/audio access. |
| G-010 | P1 | CI and exact HEAD | Combined status on `bb5425d…` showed two successful Vercel status contexts; it did not expose a complete green CI matrix for that SHA in the retrieved status result. | Partial evidence | Verify GitHub Actions for exact HEAD, including secret scan, backend, frontend, migrations, Docker, realtime-golden and WebRTC smoke; save run IDs and logs. |
| G-011 | P1 | MCP duplication | Both `mcp/desi-mcp-server` and `services/mcp` contain MCP server implementations with overlapping source filenames. | Verified repository layout; divergence not tested | Declare canonical package; compare tool schemas/permissions; add shared contract tests and one release process. Keep tool allowlists, bounded timeouts/output, user/tenant scope and prompt-injection defenses. |
| G-012 | P1 | External meeting integration | DeepL publicly advertises meeting detection/translation across Teams, Zoom and Google Meet; inspected TalkFlow code demonstrates its own meeting room and telephony integrations, but no evidence proves automatic integration into all three external meeting platforms. | Gap in available evidence; scope needs confirmation | Define whether external Teams/Zoom/Meet is an MVP requirement. If yes, implement only via authorized integration path and test each platform separately. Do not describe native TalkFlow rooms as equivalent to external meeting integration. |
| G-013 | P2 | PDF/OCR | Open Issue #52 says PDF parsing lacks an OCR branch for scanned/image-only PDFs and coverage QA is incomplete. | Verified in open issue's code analysis; current branch fix not checked fully | Add OCR only for scanned pages; track per-page extracted text/block counts; validate output coverage and table/page reconstruction; include scanned, mixed and digital PDF fixtures. |
| G-014 | P2 | Writing correction | Issue #52 says grammar improvement relies heavily on regexes and does not provide broad contextual correction. | Verified in open issue; full current implementation not run | Keep regexes as quick fixes; add context-aware correction behind a provider interface, preserve code/URLs/numbers/names, show diff, allow accept/reject and cancel stale requests. |
| G-015 | P2 | Translation memory/glossary UX | Issue #102 identifies richer editor, bulk TM import/export and glossary management as parity gaps. | Verified in open issue | Decide MVP scope; build searchable term/TM editor and import/export validation only if required. Backend CRUD alone is not feature parity. |
| G-016 | P2 | Language selector | Issue #102 says current selector uses native selects plus a "More" list instead of a searchable, keyboard-accessible combobox. | Verified in open issue | Implement accessible search, native language names, keyboard controls and disabled/experimental states driven by capability registry. |
| G-017 | P2 | URL/page translation | Issue #102 lists page/URL translation as missing. | Verified in open issue | Add only if in MVP; design secure fetching with SSRF defenses, domain/redirect allowlist policy, size/time limits and content sanitization. |
| G-018 | P2 | Performance observability | `docs/REALTIME.md` documents latency events and p50/p95/p99 metrics; the measured load report shows a real need for actionable stage-level tracing. | Documented mechanism; full telemetry deployment unverified | Propagate correlation IDs from UI through WS/STT/MT/TTS to playback; export stage histograms, queue depth, drops, provider errors and target-specific outcomes. |
| G-019 | P2 | Deployment environment drift | API ports differ by documented environment (local 8088/8000, container 8000, Render PORT 10000); frontend API URL and WS URL are environment-dependent. | Verified config/doc differences; may be intentional | Create an environment matrix and smoke-test it; validate startup and health routes; ensure Vercel, Render and Docker are not accidentally mixing backend trees or base URLs. |
| G-020 | P2 | Load and recovery | A local load harness exists, but production capacity and cross-network media reliability are not proven. | Partial | Run approved staging load tests with target hardware, real provider path, 1:1 and group meetings, provider failures and recovery. Record memory, CPU/GPU, queue depth, p95/p99, drops, cost/minute and error rates. |
| G-021 | P3 | Product parity polish | DeepL provides mature shortcuts, selectors, overlay and desktop workflows; TalkFlow's own benchmark lists remaining UX gaps. | Verified scope gap | Prioritize by user value; avoid copying DeepL's branding/assets. Implement original UX and test accessibility. |
| G-022 | P1 | License compliance | `docs/SECURITY.md` calls out license review for model assets (including NLLB CC-BY-NC and Silero VAD CC-BY-NC). | Unresolved checklist item in docs | Inventory actual model files and providers used in each deployment; obtain qualified license review before commercial routing. Do not assume model code license and weight license are identical. |

---

## 6. Translation and live-call architecture to preserve

The current documented architecture has the right high-level invariant:

```
human audio → VAD → streaming/final STT → immutable canonical source segment
    → parallel translation per distinct target language
    → target-language TTS → per-listener audio router + captions
```

Preserve these rules:

1. Translate every target directly from the immutable original source segment. Never translate a
   prior translation.
2. Deduplicate provider calls by distinct target language, then route that result to the correct
   seats.
3. Do not fabricate translations when a provider fails or returns source text unchanged. Send an
   explicit failure/degraded state and preserve source captions when available.
4. Do not emit unstable partial STT to TTS if it causes flicker or repeated speech. Use partial text
   for live captions; use stable/final phrases for translation/TTS according to the latency design.
5. Tag every transcript, translation, audio chunk and playback result with room, speaker, listener,
   language, utterance/segment ID, sequence and timestamps.
6. Enforce per-listener authorization at the event/audio delivery boundary; never rely only on
   frontend filtering.
7. Keep source audio and translated TTS separate to prevent TTS-to-STT feedback.
8. On leave, disconnect or cancellation, stop capture tracks, close peer connections, flush queues,
   cancel provider work, close sockets, remove listeners and clear timers.
9. Readiness must separately report STT, translation, TTS voice, transport, and target-pair
   capability.
10. The live-call release test must prove audible translated output, not just a `translation.final`
    event or visible caption.

### Root-cause investigation for Issue #53

Do not jump straight to a rewrite. Capture one trace from a real failed session and follow:

- microphone permission and PCM format/sample rate;
- socket/session authentication and room membership;
- source sequence/utterance ID;
- VAD start/end and STT partial/final;
- source language and confidence;
- translation provider/model/target result;
- TTS voice selection and audio bytes;
- target listener routing and dedup key;
- browser autoplay/audio-unlock state;
- AudioPlayer queue order and actual playback outcome;
- LiveKit/WebRTC connection state and reconnect events.

Use a reproducible test with speaker A in Hindi and listeners B/C set to English/Marathi; then
reverse direction. Add a third participant, a target-language change mid-call, one provider outage,
one media outage, one reconnect and one listener joining late. The same utterance ID must correlate
all stages.

---

## 7. API keys, environment configuration and provider routing

### What was verified

- `.env.example` has server-side variables for `DEEPL_API_KEY`, STT/translation/TTS providers,
  LiveKit, Redis, database and model cache.
- It explicitly warns that the DeepL key is server-only and must not be placed in `VITE_*`.
- `docs/DEPLOYMENT.md` documents optional Azure Speech/Translator adapters and states that provider
  selection/credentials are server-side.
- `services/api/requirements.txt` explains that some optional native/cloud SDKs are not installed in
  the serverless dependency set because of package-size constraints.
- `render.yaml` sets production mode, generated `SECRET_KEY`/`JWT_SECRET`, database/Redis
  configuration and provider selectors, while several actual service credentials are marked
  `sync: false`.
- The GitHub tree contains `.env.example`, `.env.production.example`, `.mcp.json`, Docker, Render,
  Vercel and Kubernetes configuration.

### What remains unknown

This audit did not read deployed secret values or test any live provider key. Therefore it cannot
confirm that DeepL/Azure/LiveKit/Redis/Postgres keys exist, are valid, have quota, or point at the
correct region/account.

### Required tests

For every provider and environment, test:

- key absent;
- invalid key;
- quota/rate limit;
- timeout;
- provider 5xx;
- unsupported language or voice;
- malformed response;
- successful real request;
- cancellation and bounded retry;
- fallback/disable behavior;
- no key in frontend bundle, browser storage, logs, telemetry, or exception payload.

Do not log key values. Use secret-scanning in CI and rotate only if a real exposure is confirmed. A
successful frontend build is not a provider-health check.

---

## 8. Database audit

`docs/DATABASE.md` identifies PostgreSQL/pgvector as production storage and SQLite as a
development/test option. It documents separate Alembic lineages and the canonical `services/api`
schema.

Required validation:

1. Start from a clean PostgreSQL database matching production version/extensions.
2. Run only the canonical migration chain to head.
3. Run schema drift detection (`alembic check` or the repository's equivalent).
4. Run upgrade from the current staging schema and verify row counts and constraints.
5. Test downgrade/rollback on a disposable database, not production.
6. Verify indexes on tenant/time, meeting/sequence and dedup keys.
7. Test cross-tenant isolation for meetings, transcripts, translation segments, documents, API
   keys, glossaries and billing.
8. Verify deletion/retention across database rows, object storage, cached results and backups
   according to policy.
9. Verify pool sizing, connection timeouts, Redis outage behavior and worker recovery.
10. Record the migration revision and database engine in the release artifact.

Do not merge the legacy and canonical schemas during the initial bug-fix phases.

---

## 9. Python, MCP, and service tests

### Python/backend

The repository contains a substantial Python service tree and requirements. A dependency list does
not prove that all packages install on the production runtime, especially optional native model
dependencies. Validate clean install on the exact Python version and operating system used in
deployment. The repository has had Windows ONNX/Piper runtime issues recorded in prior work;
re-test on the actual target host.

Required tests:

- startup/import/health/readiness;
- no network model downloads in the request path unless explicitly enabled;
- inference off the async event loop where appropriate;
- bounded concurrency and queues;
- cancellation, timeout and graceful shutdown;
- provider contracts and model cache readiness;
- real STT→MT→TTS smoke on supported language pairs.

### MCP

MCP implementations exist under both `mcp/desi-mcp-server` and `services/mcp`. Confirm which is
deployed and which is canonical. For each tool:

- schema validation;
- allowlisted destinations and tools;
- least privilege and tenant scope;
- timeout, output-size and call-depth limits;
- prompt-injection handling for untrusted tool results;
- no arbitrary shell execution or unrestricted URL fetch;
- no credentials in tool output/logs;
- audit record for actions with sensitive side effects;
- graceful handling of server timeout/malformed response.

MCP is a tool integration mechanism, not a replacement for internal API authorization.

---

## 10. Production security assessment

### Positive evidence in code/docs

`docs/SECURITY.md` documents tenant-scoped queries, hashed API keys and refresh tokens, CSRF
cookies, rate limits, upload validation, webhook signatures, WebSocket tickets, structured logs with
redaction, retention cleanup and consent controls. Current frontend API code uses `sessionStorage`
for the access token and documents that refresh tokens remain in an HttpOnly cookie. Current
social-auth service contains provider token/JWKS verification paths.

### Outstanding proof needed

The older `docs/PRODUCTION_AUDIT.md` (dated 2026-10-04) contains some findings that appear stale
relative to current source (for example, it describes localStorage access/refresh token handling
and unverified social login, while current files show a newer cookie/sessionStorage pattern and
cryptographic social-auth service). Update this document rather than treating every old line as a
current vulnerability. However, do not mark the newer design "secure" without regression tests.

The production checklist in `docs/SECURITY.md` still lists uncompleted hardening tasks. Confirm each
on the actual target deployment:

- rotate default secrets;
- TLS/HSTS and secure headers;
- Redis auth/TLS;
- PostgreSQL TLS and least-privilege role;
- private S3 bucket policy and encryption;
- malware scan where required;
- rate-limit and admin allowlist;
- model/weight license review;
- telemetry/alerting;
- backups and restore drill;
- consent/retention/deletion;
- incident response and support ownership.

No secrets or production data were accessed in this audit.

---

## 11. Test and CI status

### Evidence available

- Root `package.json` exposes web, SDK, CLI and other workspace test/build scripts.
- `.github/workflows/ci.yml` defines secret scan, backend, migration, frontend, Docker and related
  test lanes; the exact current workflow output was not fully retrieved in this audit.
- `docs/TRANSLATION_ACCEPTANCE.md` documents provider-readiness and honesty tests, including an
  October 23 CI observation in which backend, migrations, frontend, realtime-golden and Docker were
  recorded as passing, with a WebRTC smoke run passing after an offline fixture fix.
- The observed current main SHA has two successful Vercel status contexts in the GitHub combined
  status response.
- PR #71 includes an Asterisk lab test report with 7 criteria passing in that lab; this is not proof
  of a carrier PSTN round trip.
- PR #101 includes local frontend benchmark results.

### Not proven for current HEAD

- all required GitHub Actions jobs passed on `bb5425d88f6588268047cfce2606d4201f5fbe62`;
- clean install and all tests pass on a clean machine;
- real provider keys and quota work;
- a real Android/mobile network uses TURN correctly;
- all advertised source/target voice pairs work;
- translated audio is actually audible for every listener in group calls;
- production staging migration, rollback and restore work.

Rule: tests on an earlier commit, local-only tests, mocked providers and CI fakes must not be
described as proof of the current deployed app.

---

## 12. Phased remediation plan

Each phase should be a small PR with a clear acceptance test. Do not rebuild the whole app.

**Phase 0 — Freeze baseline and evidence**

- Record current HEAD, deployment SHA, environment matrix and working tree.
- Re-run all current CI jobs and collect run IDs/logs.
- Identify canonical API, frontend base URL, WebSocket route, media transport and database lineage
  per environment.
- Update `docs/PRODUCTION_AUDIT.md` to distinguish fixed, open, partial and unverified findings.
- Deliverable: `docs/audit/00-baseline.md`, no feature changes.
- Exit: reproducible baseline and current blocker list exist.

**Phase 1 — Reproduce and close P0 #53**

- Build a browser test with 3+ participants and per-listener languages.
- Add structured trace IDs for audio capture → STT → MT → TTS → delivery → playback.
- Fix only the demonstrated root cause: event ordering, target routing, provider readiness,
  playback/autoplay, transport state or reconnect.
- Verify source-segment immutability, no translation chaining, no cross-room audio, and complete
  cleanup.
- Deliverable: failing test first, minimal fix second, green test and trace artifact.
- Exit: real end-to-end translated audio reaches every intended listener and fails honestly under
  outage.

**Phase 2 — Realtime latency and queueing**

- Profile STT finalization and model startup under concurrency.
- Measure cold and warm behavior separately; record CPU/GPU, memory, queue depth and provider stage
  times.
- Use streaming/partial STT for captions; translate stable/final segments and cancel stale work.
- Warm models, bound concurrency, avoid blocking the event loop, and set stage deadlines.
- Re-run load drill at C=1/2/4 and realistic utterance rates on target hardware.
- Exit: owner-approved p50/p95/p99 target met on a documented deployment profile. If not, mark
  degraded/NO-GO and document capacity limit.

**Phase 3 — Language/voice readiness matrix**

- Generate capability status from runtime diagnostics, not a static README.
- Test every marketed pair through STT, MT, TTS and actual listener playback.
- Install/configure missing voices only after checking model license, quality and runtime footprint.
- Disable unsupported voice pairs while preserving available captions/text.
- Deliverable: `docs/audit/language-capability-matrix.md`.
- Exit: every advertised language/modality has a repeatable test and a known provider/model/voice.

**Phase 4 — Database and backend lineage guard**

- Add CI assertions for the canonical migration directory and deployment entrypoint.
- Test clean PostgreSQL migration, schema drift, rollback on disposable DB and tenant isolation.
- Verify worker import paths and ensure legacy API cannot be accidentally deployed as the primary
  HTTP API.
- Do not consolidate models unless a separate approved migration project requires it.
- Exit: migration tests pass on current SHA and deployment points to the intended lineage.

**Phase 5 — API keys, provider failures and MCP**

- Add safe readiness checks: configured, package installed, credentials accepted, provider
  reachable, pair/voice supported.
- Test missing/invalid/quota/timeout/5xx/unsupported voice paths.
- Confirm server-only secrets and no secret leakage in bundles/logs.
- Select canonical MCP package and add shared contract/security tests.
- Exit: real staging provider calls pass; all failure modes degrade honestly.

**Phase 6 — Frontend and UX integration**

- Validate API base URL, WebSocket URL, auth refresh and error states in production build.
- Improve searchable language selection and clearly label unsupported/degraded modes.
- Keep current layout/auth/meeting flow; fix specific regressions only.
- Run Playwright on the exact production build, including camera/mic permissions and reconnect.
- Exit: key user flows work in a real browser against staging, not just mocked UI.

**Phase 7 — PDF, writing and parity features**

- Add scanned PDF OCR and page/block coverage checks if required by MVP.
- Add contextual writing correction with diff/accept/reject, preserving code and names.
- Implement glossary/TM UX depth, URL translation, selection translation or external meeting
  integrations only if prioritized by product requirements.
- Keep a clear list of deliberately deferred features.
- Exit: each feature has explicit acceptance criteria and no misleading "supported" label.

**Phase 8 — Security and privacy gate**

- Close production hardening checklist; verify actual deployed config.
- Run auth, cross-tenant, WebSocket ticket, upload, webhook, rate-limit and secret scanning tests.
- Complete model-license and privacy/data-flow review with qualified reviewers.
- Verify retention and deletion including audio, transcripts, translations, objects and cache.
- Exit: no unresolved critical security issue and documented approval/exception for each required
  gate.

**Phase 9 — Staging rehearsal, operations and GO/NO-GO**

- Deploy the exact release candidate to staging.
- Run migration, health/readiness, real-provider, 1:1/group calls, mobile/TURN, outage/reconnect,
  performance and rollback drills.
- Verify backups and restore; add alerts/runbooks and assign support/incident owner.
- Publish test counts, performance results, known limitations, release SHA and rollback command.
- Exit: all mandatory gates pass. If #53, live audio, staging rehearsal, privacy review or support
  ownership remains unresolved, verdict stays NO-GO.

---

## 13. Acceptance matrix for MVP release

| Gate | Must be demonstrated | Pass evidence |
| :--- | :--- | :--- |
| Build and install | Clean install, lockfiles, frontend/backend startup | CI run ID + command logs |
| Auth and tenancy | Login/refresh/logout, cross-user denial, room tickets | Automated tests + negative cases |
| Database | Fresh migration, upgrade, drift and rollback test | PostgreSQL logs and migration revision |
| Text translation | Real provider/local model results and honest fallback | Corpus report, provider/model metadata |
| Live speech | Actual microphone capture → STT → MT → TTS → audible target | E2E trace plus audio/playback assertions |
| Per-listener routing | Different target languages in one group call | Participant/segment delivery ledger |
| Video/media | Camera/mic, join/leave, TURN relay, reconnect | Cross-device browser run and WebRTC stats |
| Failure recovery | Provider outage, quota, disconnect, permission denial | Expected degraded state and recovery traces |
| MCP | Tool allowlist, permissions, schema, timeout and prompt-injection tests | Security suite output |
| Performance | p50/p95/p99 and error rate by pair/concurrency | Reproducible benchmark artifacts |
| Secrets/privacy | No exposed keys; consent/retention/deletion verified | Secret scan + configuration review |
| Operations | staging deploy, rollback, backup restore, support owner | Signed rehearsal report |
| Reference parity | Clearly scoped comparison with DeepL | Same test protocol, measured results, explicit gaps |

---

## 14. Deliverables to create in the repository

Create/update these files without overwriting useful existing documents:

- `docs/audit/00-baseline.md`
- `docs/audit/01-repository-map.md`
- `docs/audit/02-system-architecture.md`
- `docs/audit/03-reference-comparison.md`
- `docs/audit/04-gap-register.md`
- `docs/audit/05-security-and-secrets.md`
- `docs/audit/06-translation-pipeline.md`
- `docs/audit/07-realtime-calls.md`
- `docs/audit/08-test-plan-and-results.md`
- `docs/audit/09-phased-remediation-plan.md`
- `docs/audit/10-release-go-no-go.md`

This report may be committed as `docs/audit/INITIAL_REPOSITORY_AND_DEEPL_GAP_REPORT.md` after review.
Do not automatically push or deploy without explicit authorization.

---

## 15. Final decision

### What is already strong

- A large, modular codebase with substantial test and deployment infrastructure.
- A canonical-source and independent target-language fan-out design.
- Explicit provider/readiness/translation honesty concepts.
- Existing realtime, migration, security, browser E2E and load-test artifacts.
- A measurable frontend bundle optimization compared with selected DeepL web routes.

### What is still the critical path

1. Close and prove issue #53.
2. Reduce the measured realtime latency on the target deployment profile.
3. Validate real language/voice coverage end to end.
4. Prove staging deployment, migration, rollback and provider configuration.
5. Complete the security/privacy/license/support release gates.
6. Reconcile stale audit documentation with current code and exact test evidence.
7. Keep the DeepL comparison scoped: current web-load numbers are not voice-translation parity.

**Verdict: NO-GO** for production pilot on the evidence available in this audit. This does not mean
every feature is broken. It means the release-critical live translated-audio path and required
operational gates are not yet proven sufficiently for a production claim.

---

## Sources

### TalkFlow repository evidence

- Repository: https://github.com/Aman678317/TalkFlow
- Current observed HEAD: https://github.com/Aman678317/TalkFlow/commit/bb5425d88f6588268047cfce2606d4201f5fbe62
- README: https://github.com/Aman678317/TalkFlow/blob/main/README.md
- P0 group-call/live audio issue: https://github.com/Aman678317/TalkFlow/issues/53
- Translation/PDF/writing issue: https://github.com/Aman678317/TalkFlow/issues/52
- DeepL web performance benchmark: https://github.com/Aman678317/TalkFlow/issues/102
- Production audit: https://github.com/Aman678317/TalkFlow/blob/main/docs/PRODUCTION_AUDIT.md
- Load/latency envelope: https://github.com/Aman678317/TalkFlow/blob/main/docs/LOAD_CAPACITY_ENVELOPE.md
- Translation acceptance: https://github.com/Aman678317/TalkFlow/blob/main/docs/TRANSLATION_ACCEPTANCE.md
- Realtime protocol: https://github.com/Aman678317/TalkFlow/blob/main/docs/REALTIME.md
- Database: https://github.com/Aman678317/TalkFlow/blob/main/docs/DATABASE.md
- Security: https://github.com/Aman678317/TalkFlow/blob/main/docs/SECURITY.md
- Deployment: https://github.com/Aman678317/TalkFlow/blob/main/docs/DEPLOYMENT.md
- CI workflow: https://github.com/Aman678317/TalkFlow/blob/main/.github/workflows/ci.yml
- Meeting room: https://github.com/Aman678317/TalkFlow/blob/main/apps/web/src/pages/MeetingRoom.tsx
- Translation fan-out: https://github.com/Aman678317/TalkFlow/blob/main/services/api/app/realtime/translation_fanout.py
- Frontend API client: https://github.com/Aman678317/TalkFlow/blob/main/apps/web/src/lib/api.ts

### DeepL public reference

- DeepL Voice meeting app: https://www.deepl.com/en/voice-app
- DeepL API overview and key-safety guidance: https://support.deepl.com/hc/en-us/articles/9773914250012-About-DeepL-API
- DeepL for Developers: https://www.deepl.com/en/developers
- DeepL Voice language matrix: https://support.deepl.com/hc/en-us/articles/26625846174364-DeepL-Voice-languages
- DeepL Voice product: https://www.deepl.com/en/products/voice
