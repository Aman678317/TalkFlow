# TalkFlow / GlobalTalk AI — 30-Day Roadmap
**Purpose:** Audit the repository, repair the core translation path first, then complete live translated meetings, writing quality, document translation, customer calling/AI-agent flows, infrastructure, MCP integration, and release verification.

**Planning window:** 30 consecutive days from the day execution starts.  
**Rule:** This is an execution plan, not a claim that every item is already working. Mark a task done only when its acceptance test and evidence link pass. Do not replace the existing UI, authentication, meeting flow, or database schema without proving a requirement and obtaining review.

## Executive priorities

1. **P0 — make translation truthful and reproducible:** confirm the canonical deployed backend, provider/model readiness, source text, target language, translation result, fallback state, and client rendering end to end. A “connected” badge is not proof of translation.
2. **P0 — fix the complete real-time audio loop:** PCM frames → VAD/segmentation → STT final → immutable canonical segment → independent translation fan-out → language-correct TTS → ordered playback. Audio/video calls must remain connected if AI stages fail.
3. **P1 — live customer/agent call:** first prove browser human-to-human translated calls, then bridge to SIP/PSTN in a sandbox. Add customer records, consent and DNC gates, agent queue, approved AI-agent state graph, human escalation, and audit trail.
4. **P1 — writing + documents:** grammar/spelling must be context-aware and protect names, URLs, numbers, code and meaning; PDFs need measurable coverage and visible OCR/layout limitations.
5. **P0 release discipline:** every PR gets focused tests, full affected-suite tests, migration/build checks, CI, deployed smoke checks, and a rollback note. One failing required gate blocks release.

## Evidence-based baseline and known risks

This roadmap was drafted after inspecting the repository README and available architecture, AI, realtime, testing, deployment, troubleshooting, document, and MCP documentation; CI/Makefile/package configuration; open Issue #53/#54; and recent PR/issue summaries including #56/#57/#59/#60/#61/#62/#63/#77/#78.

- Repo says **`services/api` is the canonical deployed API**; `apps/api` is a legacy compatibility tree with a distinct migration/model lineage. Never casually start, change, or test only one tree and assume the other is covered.
- Intended rule is **human source is canonical**. Every language projection is translated independently from the human segment; never translate from another translation and never re-transcribe synthetic TTS as a new source.
- The README describes a multilingual golden-call scenario, but documentation also says deployed `services/api` still lacks a real-provider latency harness and fake-provider tests alone are not an acoustic/natural-call listening test.
- Troubleshooting already lists plausible reasons for “Connected, but no translated audio”: provider/model missing or unavailable, model weights lost on ephemeral disk, low-memory/OOM, STT returning empty/dev text, incorrect WAV/PCM playback treatment, missing target-language TTS voice or translation pair.
- Model/provider status must be reported honestly. Passthrough/original text is **not a translation**; a captions-only state is not translated speech; an unconfigured provider must not be called healthy.
- Documents describe optional OCR as requiring Tesseract binaries and language packs. GPU/AirLLM is an optional isolated profile, not a default requirement for text translation or live speech translation.
- The repository includes MCP server tooling for translation/document/writing functions. It must be tested as an external client contract; an MCP tool is not proof the app’s internal routes or realtime loop are healthy.
- Recent pull request summaries are evidence of claimed changes, not independent proof that current production is deployed and healthy. Re-check merged state, CI and deployment before relying on them.
- Phone-number PSTN/SIP testing needs real sandbox credentials/numbers. GitHub-only checks cannot validate carrier connectivity.

## Day-zero rules / definition of done

- Open a dedicated execution branch from current `main`; never force-push or bundle unrelated changes.
- Record baseline commit SHA, current PR/CI states, deployment URL/commit, active env profile, provider capabilities, GPU/RAM/disk limits, and known failures.
- Use one logical PR per day or coherent fix, with a small scope, reproducer, root cause, tests, evidence, and rollback notes.
- Preserve public APIs and current UI/auth/meeting/data behavior unless a change is required and documented. Any DB migration must run upgrade, drift-check, rollback/forward checks on PostgreSQL.
- No secrets, customer recordings, real transcripts, model weights, or gated model tokens in Git or CI artifacts.
- Every acceptance test has one of: PASS with evidence; FAIL with issue; BLOCKED by missing credentials/hardware/data. Never disguise BLOCKED as PASS.

## 30-day implementation schedule

### Day 1 — Baseline and reproducibility (P0)
**Work:** Snapshot `main`, inspect open PRs/issues and merge status, capture current deploy SHA, inventory environment variables without printing secret values, map run commands, document active DB/cache/storage/media/provider configuration.
**Files/areas:** README, `.env.example`, Makefile, CI workflows, `services/api`, `apps/api`, `apps/web`, `ai/`, `services/realtime`, `tests/`.
**Acceptance:** A clean setup guide reproduces app startup; deployment commit is known; no secrets in the report; initial failures are logged with exact commands.

### Day 2 — Full repository architecture and ownership map (P0)
**Work:** Map frontend routes → API client → routers → services → provider interfaces → model router → DB/queue/workers → event protocol → playback UI. Identify duplicate implementations and the authoritative version of each feature.
**Acceptance:** A module ownership matrix lists entry point, canonical implementation, dependencies, test owner, runtime env and known risk. Flag stale/duplicate/unreachable paths rather than deleting them blindly.

### Day 3 — Translation API baseline and failing examples (P0)
**Work:** Build a deterministic language-pair matrix: en↔hi, hi↔en, en↔mr, Hinglish/code-switch→en, and one unsupported pair. Test empty input, long input, Unicode/Devanagari, punctuation, numbers, names, URLs, glossary terms, timeouts and provider-down.
**Acceptance:** Each result records source/target, provider/model, latency, quality flags, fallback status, HTTP/event result and expected output. Unsupported/unconfigured pairs return an honest degraded response, never a false “success translation”.

### Day 4 — Model router, provider health and configuration (P0)
**Work:** Inspect capability registry, route selection, fallback order, adapter timeouts, provider health probes and environment parsing. Make `make verify-ai-stack` produce actionable output; ensure lightweight health checks do not load full model weights.
**Acceptance:** Tests prove each fallback path and all-providers-down behavior; provider secrets remain server-only; health/readiness distinguish configured, available, supported and production-validated.

### Day 5 — Repair text translation end-to-end (P0)
**Work:** Fix the first confirmed root cause from Days 3–4. Verify API validation, language normalization, model invocation, target-script output, glossary/context, persistence/metering and frontend result rendering. Fix undefined symbols and swallowed exceptions as encountered.
**Acceptance:** Supported pair works through the actual UI and API against a real configured provider/model; provider outage is visible; regression tests reproduce the original bug; no silent passthrough is labelled translated.

### Day 6 — Translation correctness, strings and contract tests (P0)
**Work:** Check all translation entry points for request/response schema consistency, source/target codes, case normalization, blank/whitespace-only strings, Unicode graphemes, line breaks, markup, placeholder preservation, maximum size, retries/idempotency and fallback flags.
**Acceptance:** Shared contract tests cover UI/API/SDK/MCP call shape. Protected tokens (URLs, email, phone, numbers, code/placeholders) remain intact; malformed or empty inputs get clear validation errors.

### Day 7 — Translation quality gate and Day-7 checkpoint (P0)
**Work:** Run golden text dataset and language-pair evaluations; capture BLEU/COMET where available, chrF/character checks, named-entity/number/URL preservation, latency p50/p95 and regression diffs. Human-review a small representative sample.
**Acceptance:** Each language pair receives EXPERIMENTAL / SUPPORTED / PRODUCTION status based on evidence. Do not claim universal 100+ language support from a catalogue alone. Day-7 checkpoint: core text translation must be release-worthy before expanding.

### Day 8 — Realtime frame and audio contract (P0)
**Work:** Verify PCM16 mono 16 kHz format, frame size, sequence handling, channel/sample conversion, malformed-frame rejection, stale/duplicate frames, backpressure, WebSocket and LiveKit ingestion parity.
**Acceptance:** Tests cover valid and invalid frames, disconnect mid-frame, queue pressure and sequence gaps. No corrupted audio, unbounded queue or unhandled exception.

### Day 9 — Speech detection, segmentation and STT finalization (P0)
**Work:** Verify VAD thresholds, partial/final transcript lifecycle, phrase commit, overlapping speakers, short speech, long uninterrupted speech and language ID. Ensure final segments are immutable and uniquely identified.
**Acceptance:** Recorded/local test fixtures produce stable final transcript events; partial rotations cannot duplicate or overwrite finals; STT failure leaves original audio alive and visibly degrades.

### Day 10 — Real-time translation fan-out (P0)
**Work:** Fix pipeline orchestration after STT: canonical source persistence, unique correlation IDs, independent fan-out to each selected target language, same-target deduplication, bounded parallelism and per-language errors.
**Acceptance:** One source segment produces at most one translation per target; each translation references the same source segment; a failed language does not block other listeners; no translated-to-translated cascade.

### Day 11 — TTS voice selection, format and ordered playback (P0)
**Work:** Test voice map/provider voices by target language, WAV/container metadata, base64/binary frames, chunk ordering, time-to-first-audio, autoplay blocking, playback completion and dropped/cancelled turns.
**Acceptance:** Audio is decoded using the correct WAV/PCM path and target language voice. Unsupported TTS shows captions-only status. Browser test verifies that synthesized audio is actually audible/decoded, not only that an event arrived.

### Day 12 — Cancellation, interruption, reconnection and degradation (P0)
**Work:** Verify barge-in flushes only the interrupted utterance, cancels downstream MT/TTS work, preserves next turns, handles duplicate/late events and resumes sequence replay. Apply bounded provider deadlines and cancellation propagation.
**Acceptance:** Repeated interruption/reconnect tests show no deadlocks, ghost audio, reordered captions, duplicate translation or permanent “working” state. Original audio continues through AI outage.

### Day 13 — Real-browser translated meeting (P0)
**Work:** Run two browser participants with real browser media and then three participants/languages. Test camera, mic, leave/rejoin, language changes, tabs/background, Chrome/Firefox where supported and mobile Safari/Chrome smoke.
**Acceptance:** Participant A speaks Hindi and B hears English; B speaks English and A hears Hindi. Captions align to the correct source turn, audio language follows per-listener settings, video is live, and leaving cleans all tracks/seats.

### Day 14 — Real-provider latency and quality profiling (P0)
**Work:** Add/complete a real-provider harness for the canonical `services/api` path; measure stage times STT, MT, TTS first-byte, delivery and total end-to-end by language pair and hardware profile. Separate cold start vs warm pool.
**Acceptance:** A repeatable report includes p50/p95/p99, test conditions, model versions and failures. State target latency (e.g., 1.5–2.5 s warm production profile) as a target until measured. No fabricated numbers.

### Day 15 — Grammar, spelling and writing assistant (P1)
**Work:** Audit offline and neural correction tiers, context handling, timeouts, output-length/sanity checks, protected spans and abort behavior. Keep regex/offline fallback deterministic and safe. Verify grammar endpoint from the Write UI through API.
**Acceptance:** Tests cover Hinglish, Hindi/English mixed text, business tone, academic tone, spelling, punctuation, names, IDs, URLs, code, quoted text and unchanged-text cases. Preserve user intent; no grammar rewrite may silently change facts.

### Day 16 — Document translation: extraction and coverage (P1)
**Work:** Test PDF/TXT/DOCX/PPTX/XLSX/HTML parsing, page/block order, OCR-on/off, scanned pages, mixed text/image pages, malformed files, page limits and upload validation.
**Acceptance:** Per-file diagnostics report eligible blocks/pages/chars, translated coverage, empty segments and non-translatable blocks. Missing searchable text without OCR fails clearly; no “ready” status with untranslated eligible blocks.

### Day 17 — Document reconstruction, retry and QA (P1)
**Work:** Validate structure preservation, fonts/scripts, tables, hyperlinks, lists, page geometry, output escaping, length anomalies, partial progress, retries and idempotent reprocessing. Keep source and output separately.
**Acceptance:** Representative PDFs and office documents pass coverage/number checks; OCR prerequisites are verified on target host; any reconstruction that cannot fit safely yields review/failed instead of silently truncating text.

### Day 18 — Agent graph and customer-support conversation (P1)
**Work:** Verify deterministic agent graph/turn loop integrates with canonical transcript and translation runtime. Create a clear state graph for greeting → intent → identity check if needed → scoped knowledge retrieval → answer → confirm → resolve or escalate → end.
**Acceptance:** Unit/integration tests prove allowed transitions, bounded retries/turns, structured tool outputs, low-confidence escalation, no external action without authorization and no agent-generated text treated as original human speech.

### Day 19 — Customer CRM, documents and tenancy (P1)
**Work:** Audit customer contact fields/import/normalization, documents/notes, per-org access, roles and search. Test CSV malformed rows, duplicates and E.164 validation; make source citations available for authorized support documents.
**Acceptance:** Tenant isolation, RBAC, consent history and audit checks pass. One tenant cannot access another tenant’s contact, document, transcript or call. Retrieved documents are data, not policy instructions.

### Day 20 — Human customer-agent call workflow (P1)
**Work:** Test inbound queue, routing, browser answer/reject/hold/mute/transfer/end, outbound human call, reconnect, call outcome, duration and translated captions/audio. Separate browser calls from telephony calls in UI status.
**Acceptance:** Simulated mode is explicitly labelled. If call provider is unavailable, user sees failure, not a fake real call. Audio translation failure does not end the underlying call.

### Day 21 — Telephony provider sandbox and event safety (P1)
**Work:** Validate provider configuration and webhook signatures, replay protection, event idempotency, terminal-state ordering, retries, cancellation, status callbacks and sandbox inbound/outbound call. Do not enable arbitrary autonomous outbound calls.
**Acceptance:** Invalid signatures fail closed; duplicate callbacks create no duplicate side effects; real sandbox call is completed only when credentials and numbers are available. Otherwise mark blocked with exact setup requirement.

### Day 22 — AI customer agent policy gates (P1)
**Work:** Verify explicit campaign/workflow allowlist, AI disclosure, opt-out/DNC, contact consent, local call windows, retry/backoff, per-contact and campaign limits, immediate stop, human transfer, audit trail and approved action scopes.
**Acceptance:** Negative tests prove blocked contacts never dial, opt-out stops the flow, low confidence escalates, AI identifies itself, and payment/irreversible actions require authenticated approval. No cold-calling bypass.

### Day 23 — MCP server, router and tool contract (P1)
**Work:** Audit MCP stdio lifecycle, tool schemas, validation, errors, timeouts, output sizes, API auth, local file boundaries, cancellation and translation/document/write handlers. Compare MCP behavior against REST/UI contract tests.
**Acceptance:** MCP smoke test calls list-languages, translate, correct/rephrase, and document translation against a local test server; errors are structured and never leak secrets or stack traces. Verify MCP is not mistakenly used as an internal realtime router.

### Day 24 — Queue, database and migrations (P0)
**Work:** Exercise Redis outage/fallback, worker restart, stuck jobs, retries, dedupe, data retention, DB pool and migration behavior. Test both documented API trees independently where applicable.
**Acceptance:** Fresh PostgreSQL upgrade, Alembic check, downgrade/upgrade cycle and migration drift gate pass. Worker retries are bounded; DB failures produce meaningful readiness failures; no concurrent processing corrupts source segment/document state.

### Day 25 — GPU, CPU and deployment profiles (P1)
**Work:** Choose and document supported minimum profiles (CPU dev, CPU low-memory, production CPU, optional NVIDIA GPU). Validate dependency versions, CUDA/container toolkit, model cache persistence, disk requirements, download/auth behavior and worker isolation. Do not install AirLLM merely to make speech translation work.
**Acceptance:** `verify-ai-stack` explains every missing package/model/provider; a cold start and warm run are measured; RAM/VRAM/disk and concurrency limits are documented. Production secrets live in the server secret manager only.

### Day 26 — Security, privacy and abuse testing (P0)
**Work:** Run auth/RBAC/tenant tests, upload validation, CSRF/CORS/rate limits, WebSocket room authorization, join-ticket expiry, webhook signatures, API-key scopes, log redaction, transcript retention and voice/recording consent checks.
**Acceptance:** No credentials or raw private transcript in logs/artifacts; unauthorized cross-room/cross-org actions denied; consent and recording indicators work; dependency vulnerabilities assessed and triaged.

### Day 27 — Observability, recovery and capacity (P1)
**Work:** Ensure metrics/traces/logs exist for each AI stage, provider fallback, latency, queue depth, OOM, reconnect, per-target error, cost/usage and audio playback. Test concurrent calls and load with capped inference workers.
**Acceptance:** Alerts detect failing MT/TTS, provider timeout, queue growth, high p95, OOM and readiness failure. Load result states concurrency, machine type, language pairs and error rates. Define runbooks and rollback triggers.

### Day 28 — End-to-end release candidate (P0)
**Work:** Run complete CI from a clean environment: backend unit/integration/hardened/realtime, PostgreSQL+Redis, migrations, frontend Vitest/TypeScript/build, Playwright browser media, Docker smoke, MCP smoke and secret scan.
**Acceptance:** All blocking checks green on the exact release candidate commit. Flaky tests are fixed or explicitly isolated with an issue; required coverage isn't hidden in non-blocking jobs.

### Day 29 — Full day manual testing and bug bash (P0)
**Work:** Reserve the whole day for structured testing, not feature work. Two testers if possible; otherwise repeat every scenario from a fresh browser/profile. Test desktop + Android Chrome and iOS Safari if devices are available.
**Checklist:** sign-up/login/refresh/logout; create/join/leave meeting; mic/camera; two-way and three-way language fan-out; poor network/reconnect; barge-in; provider outage; captions-only fallback; UI language change; grammar correction; PDF scanned and searchable; document retry/download; contact import/permissions; simulated and real sandbox calls; AI disclosure/opt-out/escalation; MCP calls; worker/Redis/API restart; deploy health/rollback.
**Acceptance:** Each defect has severity, steps, expected/actual result, logs/request IDs, owner and fix PR. Re-run all impacted suites after fixes; no P0/P1 release blocker remains.

### Day 30 — Fix, verify, deploy and handoff (P0)
**Work:** Fix release-blocking issues; rerun all affected tests + complete smoke suite; deploy exact candidate; verify deployment SHA, `/health`, `/ready`, key API flows, browser call, provider readiness, metrics and rollback path. Publish a capability matrix and remaining risks.
**Acceptance:** Release checklist signed with links to CI, deployment, benchmarks and test results. Only claim “working” for paths validated in the target environment. Remaining blocked tests have named owner, blocker and next date.

## Core end-to-end acceptance scenarios

### A. Text translation
- Supported pair produces meaningful target-language text in API and UI.
- Unicode, punctuation, names, quantities, dates, URLs, code and glossary terms are retained as required.
- Invalid input gives validation error; provider outage yields clear degradation, not false translated success.
- Source, target, provider/model, status and latency are observable.

### B. Live meeting translation
1. Participant A joins with speaking language Hindi and listening language English.
2. Participant B joins with speaking language English and listening language Hindi.
3. A speaks; canonical Hindi transcript finalizes; English translation fans out; B hears English TTS and sees aligned captions.
4. B speaks; canonical English transcript finalizes; Hindi translation fans out; A hears Hindi TTS and sees aligned captions.
5. Change one participant’s language; only that listener’s route changes.
6. Add a third participant with a different language; each gets an independent projection.
7. Force MT or TTS unavailable; original meeting continues, affected listener sees a truthful degraded status, and no fake text/audio is emitted.
8. Interrupt, reconnect, leave/rejoin and send overlapping turns; ordering and correlation remain correct.

### C. Customer/human-agent / AI-agent call
- Customer records and linked docs are tenant-scoped; consent/DNC decision is recorded.
- Human agent can take a call and see language choice, authorized notes and live captions.
- AI agent can act only in an approved workflow, discloses AI identity, verifies as required, escalates when uncertain and stops immediately on opt-out.
- Sandbox PSTN/SIP call passes signed webhook and idempotency tests; without credentials, carrier verification remains BLOCKED, not PASS.

### D. Writing and documents
- Grammar fixes are optional, context-sensitive, and protect numbers, names, URLs and code.
- PDF QA reports coverage and scanned-page/OCR state; failures don't silently export incomplete documents as ready.
- Output documents are safely downloadable only by authorized users.

## Required PR checklist (use on every code push)

- [ ] One logical change; linked issue; exact reproduction steps.
- [ ] Root cause described; no speculative large refactor.
- [ ] Regression test fails before fix and passes after fix where feasible.
- [ ] Unit + integration tests for touched backend behavior.
- [ ] Frontend Vitest + `npx tsc -b` + production build for touched UI.
- [ ] Realtime golden/conversation tests for touched audio/event behavior.
- [ ] PostgreSQL + migration checks when schema or DB behavior is affected.
- [ ] Playwright browser test for user-visible meeting/call flows.
- [ ] Provider-down, timeout, cancellation, duplicate/retry and invalid-input tests.
- [ ] No credentials/secrets, unbounded loops/queues, swallowed exceptions or logging of private content.
- [ ] `/health` and `/ready` semantics preserved; degradation stays honest.
- [ ] CI green on the exact head commit; CI status checked after push.
- [ ] Deployment smoke test completed where deployment is affected.
- [ ] Documentation, env example, rollback note and evidence updated.
- [ ] Do not merge a red/unknown required gate; do not mark a feature complete from a mocked test only.

## Commands to standardize (adapt where a tool/profile is unavailable)

```bash
# Baseline / static checks
make verify-ai-stack
make lint
make build

# Backend tests
make test-unit
make test-integration
make test-realtime
python -m pytest tests/test_realtime_translation_invariant_hardened.py -q

# Frontend tests
cd apps/web
npx vitest run
npx tsc -b
npm run build
npm run e2e

# Return to repository root for deployment smoke
docker compose -f infrastructure/docker/docker-compose.yml config
docker compose -f infrastructure/docker/docker-compose.yml up --build -d
# Then check API /health, /ready, API docs, app UI, worker and logs.
```

Use `python` vs `python3` and install optional model/browser dependencies according to the operator's platform. Do not run destructive database cleanup against production.

## Workstream issue map

| Priority | Workstream | Depends on | Exit gate |
|---|---|---|---|
| P0 | Text translation + model router | Baseline, provider config | Real supported-pair API/UI smoke + regressions |
| P0 | Realtime STT/MT/TTS | Text MT baseline | Two-way and three-way browser media acceptance |
| P0 | CI + migrations + release process | All code changes | Exact commit green + deployment smoke |
| P1 | Writing/grammar | Text provider + safe fallbacks | Protected-span and contextual tests |
| P1 | Documents/PDF/OCR | Router + worker/storage | Coverage QA and output inspection |
| P1 | Customer calling + agent graph | Realtime + contacts/consent | Sandbox calls + policy tests |
| P1 | MCP/tools | API contract stable | External MCP smoke, auth and error tests |
| P1 | GPU/performance | Correct functionality first | Reproducible hardware/latency benchmarks |

## Final deliverables by Day 30

1. `docs/30-DAY-ROADMAP.md` — this roadmap, updated daily with evidence.
2. `docs/REPOSITORY_AUDIT.md` — modules, canonical ownership, risks and unresolved duplicate paths.
3. `docs/TRANSLATION_ACCEPTANCE.md` — language-pair matrix, tests, quality/latency reports.
4. `docs/RELEASE_EVIDENCE.md` — exact commit, CI, deployment, browser/manual test results and known blockers.
5. Maintained regression tests and focused PRs for each confirmed root cause.
6. Customer/agent calling status matrix distinguishing browser demo, simulated provider, sandbox PSTN and production carrier.

**Completion definition:** The roadmap is complete only when evidence shows which paths work in the target deployment, which fail, and which are blocked. Do not promise zero bugs or universal language support; build a repeatable process that catches and fixes regressions before each code push.
