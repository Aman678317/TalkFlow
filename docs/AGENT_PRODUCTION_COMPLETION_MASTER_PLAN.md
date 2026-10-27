# TalkFlow / GlobalTalk AI — Agent Production Completion Master Plan

**Repository:** https://github.com/Aman678317/TalkFlow  
**Assessment baseline:** 27 October 2026  
**Purpose:** Hand this document to an autonomous coding/engineering agent with repository access. The agent must inspect the existing project, implement fixes, run tests, validate the actual browser/provider behavior, and prepare an evidence-backed production release. This is an execution contract, not merely a list of suggestions.

> **Starting release status: NO-GO.** The repository's Day-7 Go/No-Go checkpoint records an open P0 browser per-listener realtime translation defect (#53), unmet privacy/legal sign-off, missing named support owner, and incomplete hosted TLS/WSS staging and browser verification. Do not change this verdict to GO until each mandatory gate is evidenced and the required human approvals are recorded.

## 0. Rules for the agent

You own execution across application code, AI providers, real-time media, automated tests, security, infrastructure, documentation, and release evidence.

1. **Inspect before editing.** Read AGENTS.md, CLAUDE.md, other agent instructions, README, architecture/testing/deployment docs, .github workflows, Makefile, package manifests, dependency lockfiles, .env.example, the current issue tracker, and recent CI results. Record current branch, commit SHA, uncommitted changes and remotes. Never overwrite unrelated user changes.
2. **Do the work, not just the planning.** Implement in priority order, write regression tests with each fix, run targeted tests immediately, then the complete relevant suites. Continue until each possible acceptance gate is PASS or explicitly BLOCKED with evidence and exact required access/input.
3. **Preserve the existing product.** Do not casually rebuild the UI, authentication, meeting flow, or database schema. Prefer focused fixes and backward-compatible changes. Add versioned migrations if schema changes are truly necessary.
4. **Use the canonical runtime.** README identifies services/api as the canonical deployed backend; apps/api is a legacy/compatibility backend with a separate model/migration lineage. Trace each behavior to the runtime that actually serves it. Do not accidentally start, test or deploy both as though they were identical.
5. **Trust evidence over documentation claims.** Code existing is not proof a feature works. Unit tests are not proof of a two-browser call. Green CI with fake providers is not proof of model quality. A socket handshake is not proof translated audio is audible. Never mark a feature DONE merely because the implementation exists.
6. **Never weaken tests to create a green build.** Do not remove tests, hide failures, loosen assertions without a valid spec change, switch off required workflows, or label fake-provider output as real translation. Mock only where deterministic unit tests call for it.
7. **Protect credentials, data, and infrastructure.** Never commit, print or report secret values. Use environment/secret stores and redact diagnostic output. Do not overwrite production data, rotate shared secrets, change DNS, trigger real customer/PSTN calls, incur substantial paid-resource spend, or deploy to live production without explicit owner authorization. Local and isolated staging work is expected.
8. **Keep working when one item is blocked.** Complete all independent work. Mark only the dependent gate BLOCKED; name the missing credential, domain, reviewer, device, permission, or owner action and provide exact steps to unblock. Never fabricate credentials or mark a blocked gate PASS.
9. **Make changes reviewable.** Use a feature branch if main is protected/shared, commit logically grouped tested fixes, push a branch and open/update a PR where available. Do not force-push, reset, or delete user work.
10. **Maintain evidence as you go.** Keep docs/AGENT_EXECUTION_LOG.md, or the project's existing equivalent, with task ID, finding/root cause, files, command/environment, PASS/FAIL/BLOCKED/NOT RUN, test output or artifact link, commit SHA and next action. Update this master plan's checkboxes only after evidence exists.
11. **Do not falsely claim a final launch.** Code can be ready while the owner still needs to approve legal/privacy, costs, scope or final production deployment. Record those owner gates honestly.

## 1. Project-specific starting findings to revalidate

Read and compare the current code with these sources before fixing anything; documentation may be stale.

- README.md
- docs/ARCHITECTURE.md, docs/REALTIME.md, docs/AI.md
- docs/TESTING.md, docs/TRANSLATION_ACCEPTANCE.md
- docs/DEPLOYMENT.md, docs/PRODUCTION_RUNBOOK.md
- docs/PRODUCTION_AUDIT.md, docs/PRODUCTION_ROADMAP.md
- docs/GO_NO_GO_CHECKPOINT.md, docs/STAGING_REHEARSAL.md
- docs/LOAD_CAPACITY_ENVELOPE.md, docs/RECOVERY_RUNBOOK.md
- docs/TRANSLATION_QUALITY_REMEDIATION_PLAN.md
- GitHub issue #53: https://github.com/Aman678317/TalkFlow/issues/53
- GitHub issue #109: https://github.com/Aman678317/TalkFlow/issues/109
- GitHub issue #80: https://github.com/Aman678317/TalkFlow/issues/80
- Current GitHub Actions workflows and CI runs for the exact commit under test.

The previous repository review recorded:

- The 23 October 2026 checkpoint says NO-GO. Treat it as the opening state, then verify current code and owner actions.
- Issue #53 is the P0 meeting reliability and per-listener translated audio defect. The realtime backend tests do not, by themselves, prove that real browsers receive correct audible translation.
- Playwright E2E has used test providers such as dev_text, dev_echo and dev_tone. That proves event plumbing, not real model quality, actual provider configuration, or natural speech output.
- The test guide warns that the canonical services/api lane needs real-provider latency/acceptance evidence rather than inferred results from the legacy backend's realtime golden-call harness.
- Issue #109 describes possible model downloads in request/health-check paths, incomplete private_only propagation, inaccurate provider privacy flags, and usage/billing accounting inconsistencies. Revalidate each finding against current code.
- The checkpoint records an isolated production-mode rehearsal but says hosted TLS/WSS staging and a complete real-browser meeting round were still open.
- Recorded CPU sandbox performance was far slower than an unqualified sub-second claim and proposed strict pilot concurrency pending approval. Remeasure the intended deployment; don't copy old numbers into marketing.
- A stale/unavailable MinIO image source was recorded as a cold-start deployment blocker. Verify cold Docker pulls/builds and select a supported pinned image or an approved S3-compatible service.
- Some language pairs and TTS voices may not be available. Translation text support, speech recognition support and voice output support must be inventoried independently.
- Older audit documents may include defects later partly fixed. Trace the live source and add tests; do not blindly reapply stale findings.

## 2. Phase 0 — Inventory and reproducible baseline

- [ ] Record current HEAD SHA, branch, git status and remotes; preserve all uncommitted changes.
- [ ] Map frontend routes and user journeys to APIs, database models, workers, provider adapters, queues, storage and deployment configuration.
- [ ] Identify the actual backend entry point used in local, CI, staging and production. Document the separation between services/api and apps/api and which tests target each.
- [ ] Map provider paths and defaults for STT, MT, TTS, language detection, writing, summaries, embeddings, meetings/realtime and telephony. Track fallback order, model/weight availability, language/voice coverage and private-only semantics.
- [ ] Inspect the Makefile, package scripts, Python dependency configuration and CI before choosing commands. Resolve discrepancies in docs rather than assuming all commands still exist.
- [ ] Check .env.example completeness and settings validation; ensure it contains placeholders only.
- [ ] Run baseline backend tests, migration tests, frontend type-check/tests/build and targeted realtime tests before edits. Record the failures and exact environment.
- [ ] Run docker compose config and audit images, volumes, ports, health checks, startup dependencies and secret injection. Avoid destructive database operations against any existing developer service.
- [ ] Create a P0/P1/P2 tracker with deduplicated existing GitHub issues and root causes, not only user-visible symptoms.

**Phase 0 exit gate:** reproducible setup, baseline SHA, architecture map, test commands and evidence log exist.

## 3. Phase 1 — P0: real browser calls and per-listener live translation

Primary issue: #53.

### 3.1 Reproduce and observe

- [ ] Start the canonical frontend, API and required backing services. Confirm /health, /ready, database, cache/Redis, storage, workers and realtime provider state.
- [ ] Reproduce the failure using two independent browser contexts with camera/microphone permissions. Capture browser console/network, WebSocket/data-channel messages, LiveKit state, ICE state, provider errors and redacted server logs.
- [ ] Create a correlation ID spanning participant join, media session, audio input, canonical utterance, provider execution, audio publication and listener playback.
- [ ] Represent each state independently: joining, media connected, mic capture, STT ready, MT ready, TTS ready, translated audio delivered/playing, degraded or unavailable. Never infer full translation readiness from a socket handshake.
- [ ] Add a regression test for the observed root cause as part of the fix.

### 3.2 One authoritative production media path

Use docs/REALTIME.md as the protocol reference after verifying the implementation:

- Production media should use the configured LiveKit/WebRTC transport for human media and the designed production path for AI translated audio; captions/control use the documented realtime channel.
- The WebSocket PCM path may remain for development/edge usage if the architecture specifies it, but it must not compete with production audio, create duplicate playback/echo, or produce a false green state.
- Tokens must be server-issued, short-lived and room-scoped. Never expose LiveKit API secrets to the client.
- Verify audio-track publication and subscription, speaker/recipient ownership, language routing, cleanup and recovery. If current code uses a different sound architecture, document it and enforce one authoritative path per mode.

### 3.3 Canonical speech pipeline

Required semantic flow:

**Microphone → validated PCM frames → VAD/segmentation → STT → immutable canonical source segment → independent MT fan-out per unique target language → language-appropriate TTS → ordered per-listener routing → observed playback outcome.**

- [ ] Validate mono PCM16, 16 kHz, little-endian framing, packet sequence and bounded payload sizes at every boundary. Reject malformed, out-of-order, oversized and stale frames safely.
- [ ] Use partial STT only for provisional captions. Final segments need immutable source text, speaker/utterance identity, sequence, timings, language and correlation ID.
- [ ] Persist or reliably emit the canonical segment before any derivative. Every translation/audio derivative must reference that source segment.
- [ ] Translate each target directly from the source. Never chain translation through another target language.
- [ ] Deduplicate by source segment and target language; listeners sharing a target should reuse work when the design permits.
- [ ] Validate each target voice supports the target language/script. Do not equate text MT coverage with audio TTS coverage.
- [ ] Ensure chunks are ordered, speaker-attributed and delivered only to intended recipients. Handle language changes, barge-in, cancellation, reconnect, replay and duplicate events.
- [ ] Preserve the human conversation/original audio when AI is unavailable. Emit documented translation.failed or quality.degraded events with actionable UI messages; never fabricate translation or successful audio.
- [ ] Prevent translated output from looping back into microphone/STT as a new user utterance.
- [ ] Handle browser autoplay and user-gesture requirements. A received event, audio URL or generated file is not sufficient proof that a listener heard output.
- [ ] Use bounded inference, retry, queue, timeout and backpressure behavior. Do not block an async event loop with slow model inference or download models during live speech.
- [ ] Measure time to first partial, final STT, MT, first audio, delivery/playback, end-to-end latency, dropped frames, retries, queue depth, reconnect recovery and provider failures.

### 3.4 Mandatory browser/media acceptance matrix

Save Playwright trace, screenshots/video, redacted logs, exact commit, browser version, provider/model versions, language configuration and test result.

- [ ] Two browsers: Hindi speaker → English listener; translated speech must be actually audible and captions attributed correctly.
- [ ] Two browsers: English speaker → Hindi listener, with correct Hindi voice/output.
- [ ] Two or more listeners share one target language; verify expected translation/TTS dedup and delivery to all intended listeners.
- [ ] At least three supported target languages in one room; no cross-recipient audio and each derivative references the canonical source.
- [ ] Four-to-six participants, distinct preferences, participant join/leave and roster consistency.
- [ ] Change listening language mid-call; test stale queue cancellation/completion policy and correct subsequent routing.
- [ ] Mic/camera toggles, device unplug/reselect, local/remote tracks, host end, leave/rejoin and clean resource disposal.
- [ ] Wi-Fi/network switch, WebSocket half-open, LiveKit reconnect, browser background/resume and restored preferences.
- [ ] TURN-required/restricted network test; STUN success alone is not enough.
- [ ] Failure injection: LiveKit unavailable, STT unavailable, unsupported MT, TTS unavailable, cache/queue/DB outage. Human conversation should remain usable where possible and UI must tell the truth.
- [ ] Android Chrome test and available iOS/Safari test: speaker/headphones, autoplay unlock, orientation, background/resume, mobile data. If no device is available, mark that device gate BLOCKED.
- [ ] Prove playback beyond a green badge: combine observable delivery/playback state with human listening review on a real browser/device.
- [ ] Keep a fake-provider pipeline check but clearly label it as event-plumbing coverage, separate from real model tests.

**Phase 1 exit gate:** issue #53 is closed only after the actual root cause is fixed and the two-browser real-provider acceptance plus appropriate regression/CI checks pass. If missing credentials/devices block a test, mark the gate BLOCKED, not passed.

## 4. Phase 2 — P0/P1: AI provider readiness, language coverage and quality

- [ ] Readiness diagnostics report configured provider, credential/config validity, model/cache availability, supported languages/pairs and voice inventory without leaking secrets.
- [ ] Model loading/download behavior is cache-first, bounded and explicitly opted in for a controlled install/warmup process. A normal request or health/admin poll must not trigger a multi-hundred-MB/GB download.
- [ ] Separate provider states: installed, configured, credentials valid, weights present, model loaded, pair supported, inference-tested.
- [ ] Apply bounded deadlines, retry/backoff, cancellation and honest error/fallback flags; avoid retry storms and duplicate expensive work.
- [ ] Enforce private_only across STT, MT, TTS, detection, summaries, embeddings, writing, streaming, realtime and telephony. Correctly pass intent through all call paths and assign truthful private/public metadata to each provider.
- [ ] If private_only is enabled, cloud fallback is prohibited unless the setting/policy explicitly authorizes it. If no permitted provider is available, fail closed with a recoverable error.
- [ ] Audit model and voice licensing, redistribution restrictions, commercial-use rights, attribution, data processing requirements and server-side credentials before shipping a model.
- [ ] Build a measured capability matrix separating STT, MT and TTS for every launch language. Include auto-detection confidence, supported pairs, script/voice coverage, provider and limitations.
- [ ] Add an opt-in real-provider smoke suite against the active services/api backend with actual configured weights/credentials in a controlled environment. Do not substitute legacy apps/api results for the canonical service.
- [ ] Benchmark every claimed launch pair: human-reviewed quality samples plus fit-for-purpose automatic metrics, partial/final STT time, MT time, first TTS audio, end-to-end latency, real-time factor, audio length, errors, memory/CPU/GPU, cold/warm startup and concurrency.
- [ ] Record host/hardware, network, provider/model version, language pair, concurrency and test conditions. Fake-provider timing must never be presented as production latency.
- [ ] Improve performance with stable segmentation, bounded parallel fan-out, batching/cache where correctness allows, reusable loaded models and backpressure. Prove quality does not regress.
- [ ] Set capacity/rate limits based on target-environment measurements and owner approval. Do not oversell concurrent sessions or latency.
- [ ] Update README/product claims to match actual tested latency, supported languages and voices. Remove unsupported universal sub-second or production-ready claims.

**Phase 2 exit gate:** active provider paths are truthful and secure; all advertised language/voice claims have evidence; real-provider smoke and benchmark artifacts exist.

## 5. Phase 3 — P0/P1: security, privacy, tenancy and abuse controls

Use OWASP ASVS 5.0.0 and the OWASP API Security Top 10 as verification references. Map applicable controls to concrete tests; passing a checklist is not a certification.

### Authentication and authorization

- [ ] Review signup/login, refresh/logout, password reset, social login, API keys, admin routes, meeting tokens, documents, transcripts, contacts, campaigns, billing and all organization-scoped resources in the active backend.
- [ ] Validate social/OIDC identity server-side: signature, issuer, audience, nonce/state and expiration using the provider's supported flow. Client-supplied email/name is not proof of identity.
- [ ] Ensure development-only account/password shortcuts cannot run in production; fail closed and add regression tests.
- [ ] Enforce object/function-level authorization on every database object and action. Never trust client-supplied user/org ownership.
- [ ] Scope WebSocket and LiveKit credentials, enforce expiry, room membership, replay/revocation rules where intended, and authorize reconnect/preference mutations.
- [ ] Review browser token storage, XSS/session risk, refresh races and multi-tab state. Use secure HttpOnly/SameSite cookie patterns where compatible and CSRF protection for cookie-authenticated state mutations; document trade-offs.
- [ ] Rate-limit auth and high-cost endpoints; prevent enumeration, resource exhaustion and unsafe error detail leakage.

### Privacy and data handling

- [ ] Document audio/transcript collection, purpose, storage, retention, access, processors and any cross-border processing.
- [ ] Verify consent and disclosure for transcription, recording, AI voice transformation and PSTN/AI calling. Respect opt-out and do-not-call controls where applicable.
- [ ] Decide and implement user/org deletion. Test propagation to rows, audio objects, caches, embeddings, history, downstream processors and backup retention according to policy.
- [ ] Enforce explicit audio, transcript and history retention periods.
- [ ] Redact speech text, audio, tokens, auth headers, phone numbers and sensitive user values from logs/traces/crash dumps by default. Correlation IDs must not contain transcript content.
- [ ] Verify export/download authorization, signed URL expiry and object access rules.

### Other controls

- [ ] Review webhook SSRF/DNS rebinding, internal metadata access and URL allowlisting.
- [ ] Validate upload size/content/MIME, archive nesting/decompression limits and safe names; enable production malware scanning where supported.
- [ ] Secure HTTPS/WSS, HSTS, CSP, frame restrictions, Permissions-Policy, trusted hosts, CORS allowlists and cookie attributes.
- [ ] Verify webhook signatures, timestamp/replay controls and provider-event idempotency.
- [ ] Add secret/dependency/container scans and static/security analysis to CI. Fix critical/high findings or obtain documented, authorized risk acceptance with owner and expiry.
- [ ] Test SQL/command injection, path traversal, mass assignment, auth bypass, rate/size abuse and tenant boundaries.
- [ ] Verify API key hashing/scopes/rotation/revocation, usage metering and billing quota units against the actual usage ledger.
- [ ] Ensure diagnostics and metrics never expose credentials or tenant-private data.
- [ ] Record qualified privacy/legal approval. Automated tests do not replace the responsible human review.

**Phase 3 exit gate:** no unresolved critical/high security item without approved risk acceptance; all applicable auth/privacy tests pass; human privacy/legal review is actually recorded.

## 6. Phase 4 — full product workflow verification

Test every route/API family listed in README and the current OpenAPI spec; do not regress existing UI/auth/meeting workflows.

- [ ] Authentication lifecycle and social login if enabled.
- [ ] Text translation: source/target, autodetection, styles/formality, glossaries, translation memory, tags/HTML, batch requests and error paths.
- [ ] Writing: grammar correction, rephrase/tone, protected URLs/code/numbers, meaning preservation, offline/provider fallback and diff/accept/reject.
- [ ] Documents: validation, upload, async progress, cancellation/retry/resume, download, cleanup and quota enforcement.
- [ ] PDF: searchable/scanned files, OCR availability, page/block coverage, layout/geometry/tables/headings, fonts/overflow and clear OCR warnings.
- [ ] Meetings: create/join/invite/guest ticket, device permissions, roster, preferences, captions/chat, actual translated audio, history/export, leave/end and cleanup.
- [ ] Glossary/TM CRUD/import/export, authorization, deduplication, language-pair validation and quotas.
- [ ] API keys, API versions, rate limits, metering, webhook signatures and revocation.
- [ ] Usage/billing/plans/admin values match server truth; remove contradictory hard-coded prices or quotas.
- [ ] Multi-agent studio, MCP/SDKs and optional integrations: verify only the features advertised as supported; label experimental ones clearly.
- [ ] Telephony/PSTN: no claim of production-ready calling until real provider sandbox, verified webhook, consent/disclosure and two-way real audio/translation tests pass with authorized credentials. Exclude blocked PSTN features from the launch scope.
- [ ] Test responsive usability, accessible controls, actionable errors, invalid input, unauthorized access and provider/database outage for each critical journey.

## 7. Phase 5 — test pyramid and CI

Inspect repository targets before using commands. Expected layers:

- Unit: security/auth primitives, role matrix, provider routing and private-only rules, canonical source immutability, language detection, PCM framing, sequence/order, fan-out dedup, barge-in, queue flush, usage/billing, document validation and failures.
- Integration: active API runtime with fresh test database, migrations, object storage, queues/workers, tenancy, auth, documents, meetings, diagnostics and provider fallback.
- Realtime golden call: canonical persistence, audio contracts, multilingual fan-out, TTS, routing, reconnect/replay, preference changes and honest unsupported-language degradation.
- Frontend: Vitest, strict TypeScript, API contract/error states, audio decoder, component behavior and resource cleanup.
- Browser E2E: separate browser contexts/participants, actual getUserMedia permission handling, video/audio/signaling, language fan-out, leave/rejoin, outage and recovery.
- Real-provider acceptance: separate opt-in suite against canonical services/api. Must be real-provider evidence, not fake-provider CI.
- Migration: fresh install, upgrade from prior release, head/drift check, safe downgrade/restore strategy.
- Security/negative: tenant authorization, WebSocket auth, token replay, quotas, private-only, secret redaction, uploads, SSRF and webhooks.
- Load/failure: concurrency, slow providers, saturation, retries, Redis outage, worker restart, DB pressure, storage outage, memory leak and reconnect storm.

Adapt these documented commands after checking the current Makefile/scripts:

~~~bash
make test
make test-unit
make test-integration
make test-realtime
make lint
make build

cd apps/web
npm ci
npx vitest run
npx tsc -b
npm run build
~~~

- [ ] Keep separate, readable CI jobs for backend, migration, frontend, realtime, E2E, security and container build.
- [ ] Required checks run on pull requests and release candidate branches.
- [ ] Heavy model tests use a controlled optional lane; secrets and weights must not leak.
- [ ] Fake-provider tests are labelled as event plumbing, not translation quality.
- [ ] Attach Playwright traces/screenshots/video and safe logs on failure.
- [ ] Re-run required checks on the exact final candidate SHA. Any failure must be fixed or transparently marked BLOCKED with an approved reason; never make it green by deleting the check.

## 8. Phase 6 — database, queue, storage and resilience

- [ ] Document the active model/migration lineage and prevent accidental dual-backend schema drift.
- [ ] Keep production migrations versioned and explicit. Do not silently patch production schema at startup.
- [ ] Test clean install, previous-release upgrade, migration head/drift and recovery using disposable databases; never test destructive migration operations against live data.
- [ ] Bound PostgreSQL pool size/timeouts and make readiness reflect required dependency failure.
- [ ] Verify Redis/queue/worker config for production; bound retries, implement idempotency and dead-letter/replay behavior where required, and instrument queue age/depth.
- [ ] Ensure jobs survive API restarts and retries do not duplicate/corrupt translated segments or documents.
- [ ] Fix the MinIO image/source cold-start issue and validate clean pulls/builds. Pin supported versions/digests, or use an owner-approved S3-compatible service with documented credentials, TLS, lifecycle and backup.
- [ ] Test object upload/download/hash integrity, authorization, URL expiry and deletion/retention.
- [ ] Execute isolated PostgreSQL backup/restore, migration-head verification, object-store restore/hash check and queue/DLQ recovery. Record RTO/RPO and get owner approval.
- [ ] Test graceful shutdown, deployment restart, SIGTERM, connection draining and in-flight work.
- [ ] Make health checks honest. Liveness must not trigger costly inference; readiness must not download models or disclose secrets.

## 9. Phase 7 — production deployment and rollback

Use the existing hosting platform and deployment model where practical. Do not add costly orchestration without a concrete requirement.

- [ ] Separate dev/test/staging/prod settings and secrets.
- [ ] HTTPS/WSS with trusted public certificates, correct proxy headers and stable URLs.
- [ ] Production bundle contains no localhost, temporary tunnel, preview-only host or unauthorized wildcard CORS.
- [ ] PostgreSQL, Redis, storage and workers are authenticated and correctly configured.
- [ ] LiveKit has a stable domain and trusted TLS. Configure advertised IP, network/firewall ports and port ranges, room-scoped tokens and suitable TURN transport for restrictive networks; test relay connectivity from an external network.
- [ ] Keep database/cache/internal metrics endpoints private.
- [ ] Inject secrets through the host secret store; do not bake into browser bundles, images or logs.
- [ ] Persist required model caches without uncontrolled downloads during app startup.
- [ ] Run migration as a controlled pre-deploy job, not concurrently in each API replica.
- [ ] Configure readiness/liveness, restart policies, worker health, request/upload limits, WebSocket timeouts and safe reverse-proxy headers.
- [ ] Pin and scan container images, use supported bases and non-root users where practical.
- [ ] Cold-start the complete stack from a clean cache/environment. Prove there is no hidden dependency on local developer files or warmed sessions.
- [ ] Document instance requirements, scale limitations, provider/model costs and expected spend.
- [ ] Deploy a release candidate to staging; verify health/readiness, login, text, documents, real-browser meeting, real translation, migrations and metrics.
- [ ] Restart API/worker and verify recovery; test rollback to an immutable prior image/commit and compatible schema plan.
- [ ] Store staging/restart/rollback evidence. Local Compose success is not hosted staging verification.

## 10. Phase 8 — observability, capacity and cost

- [ ] Propagate trace/request IDs across HTTP, WebSocket, meeting, provider, queue and worker paths.
- [ ] Instrument STT/MT/TTS, first translated audio, target-language failures, queue age/depth, dropped frames, active sessions, reconnect, DB pool, storage failures and provider fallback.
- [ ] Redact logs; do not emit transcript text or raw audio by default.
- [ ] Avoid high-cardinality or sensitive user identifiers in metric labels.
- [ ] Add actionable alerts for readiness/error rate, provider failures, queue backlog, audio delivery failure, latency, memory/disk, DB pool exhaustion and usage/cost spikes.
- [ ] Create dashboards and a runbook for each critical alert.
- [ ] Benchmark real text/audio, cold/warm start, language pair, concurrency, p50/p95/p99, errors, degradation, CPU/GPU/RAM, bandwidth and cost.
- [ ] Run a soak test for session/memory leaks, stale connections, queue growth and reconnect storms.
- [ ] Base concurrency/latency limits on measured target deployment. If one translated meeting per worker is the only safe measured capacity, document/enforce it instead of hiding it.
- [ ] Obtain owner approval for pilot capacity and alert thresholds, and rerun benchmarks after model, provider or hardware changes.

## 11. Phase 9 — documentation and developer experience

- [ ] Update README claims to match tests, real supported languages/voices and actual deployment status.
- [ ] Publish a distinct STT/MT/TTS capability matrix; document unavailable pairs, voice gaps, device constraints and experimental features.
- [ ] Validate documented Python/Node versions and Windows/Linux/macOS setup against lockfiles and CI.
- [ ] Ensure .env.example is complete, safe and aligned with settings validation.
- [ ] Document provider selection, offline/private-only behavior, model caching/warm-up, licensing, language support and fallback behavior.
- [ ] Document API/event contracts, WebSocket/PCM formats, auth, rate limits, errors, idempotency and versioning.
- [ ] Update deployment, TLS/WSS/TURN, migrations, backup/restore, metrics, incident and rollback documentation.
- [ ] Remove stale setup commands, nonexistent file references, unpullable image tags, contradictory billing values and unsupported performance claims.
- [ ] Add release notes and honest known limitations.

## 12. Phase 10 — human operations and legal/privacy gates

A coding agent can prepare evidence and implement technical controls, but cannot impersonate a qualified reviewer or invent approval.

- [ ] Name the product/production owner and support/on-call owner.
- [ ] Assign owner and due date for every unresolved P0/P1 and launch gate.
- [ ] Complete qualified review of privacy notice, terms, data processing/retention, consent and disclosure as applicable.
- [ ] Approve launch languages, providers, regions, concurrency, costs and exclusions.
- [ ] Approve backup retention, recovery RTO/RPO, incidents, support escalation and rollback plan.
- [ ] Verify third-party/model licenses and provider data-processing terms.
- [ ] If PSTN/AI calling is blocked, explicitly exclude it from the pilot scope and remove misleading live-production claims.

## 13. Phase 11 — final release gate

No overall progress percentage can substitute for acceptance evidence. Required gates:

- [ ] Clean checkout builds deterministically.
- [ ] Required unit, integration, frontend, migration, realtime, browser, security and container checks pass.
- [ ] Final candidate CI is green.
- [ ] All P0 defects are closed with regression tests.
- [ ] Critical/high security issues are closed or formally risk-accepted by an authorized owner with scope and expiry.
- [ ] Real-provider browser translation works both directions with correct voices and recipient routing.
- [ ] Failure injection proves truthful degradation and recovery.
- [ ] Language/voice coverage and measured provider benchmark report exist.
- [ ] Hosted HTTPS/WSS, LiveKit/TURN, deployment/restart, backup/restore and rollback are tested.
- [ ] Capacity, latency and cost envelope is documented and approved.
- [ ] Human privacy/legal sign-off, support ownership, runbooks and release-scope approval are recorded.
- [ ] Deployment authorization explicitly received before live production changes.
- [ ] Final launch report records exact commit/build/deployment SHA, CI links, test evidence, supported features/languages/devices, performance/capacity/cost, limitations and decision-maker.

**GO** requires all mandatory gates and the authorized owner's recorded approval. Otherwise record **NO-GO** or **BLOCKED**, or request a formally approved narrower pilot scope. Never silently waive the missing requirements.

## 14. Required deliverables before the agent reports completion

1. Implemented code fixes and regression tests.
2. Required CI/security checks updated and passing.
3. Current execution log with exact commands and PASS/FAIL/BLOCKED results.
4. Real-browser live translation evidence, separate from fake-provider E2E.
5. Real-provider language/voice support matrix and performance/quality benchmark.
6. Tested deployment, environment setup, rollback, backup and recovery instructions.
7. Security/privacy findings and evidence-backed disposition. Human sign-offs remain PENDING until approved.
8. Updated README, testing guide, production runbook, recovery instructions and known limitations.
9. An evidence-backed docs/LAUNCH-REPORT.md with commit/build/deployment SHA, CI runs, scope, metrics, costs, incidents, limitations and GO/NO-GO.
10. GitHub issues/PRs updated and only closed after their acceptance criteria actually pass.

Final agent response must include exact commit SHA/PR links, changed files, test commands and results, browser/provider environment, real acceptance evidence, migration/deploy/rollback status, security findings, unresolved blockers with owner/input needed, and an explicit GO/NO-GO/BLOCKED decision.

## 15. Official technical research references

Check these official references at implementation time and reconcile them with the pinned dependencies and hosting platform:

- LiveKit secure self-hosted deployment, TLS, networking and TURN: https://docs.livekit.io/transport/self-hosting/deployment/
- LiveKit self-hosting overview: https://docs.livekit.io/transport/self-hosting/
- FastAPI production deployment concepts: https://fastapi.tiangolo.com/deployment/concepts/
- Playwright isolated browser contexts and permissions: https://playwright.dev/docs/api/class-browsercontext
- OWASP Application Security Verification Standard 5.0.0: https://asvs.owasp.org/
- OWASP API Security Top 10: https://owasp.org/www-project-api-security/
- PostgreSQL backup and restore: https://www.postgresql.org/docs/current/backup-dump.html
- OpenTelemetry Python instrumentation: https://opentelemetry.io/docs/languages/python/instrumentation/

Do not blindly paste a blog sample into production. Confirm current official settings for the exact versions and deployment target.

---

## Agent execution status — update this while working

- Initial inspected commit SHA: **PENDING**
- Working-tree baseline: **PENDING**
- Baseline test results: **PENDING**
- P0 issue #53: **OPEN / NEEDS REPRODUCTION AND REAL-BROWSER EVIDENCE**
- P1 issue #109: **OPEN / REVALIDATE AGAINST CURRENT SOURCE**
- Hosted staging and real-provider browser acceptance: **PENDING EXECUTION**
- Qualified privacy/legal review: **PENDING HUMAN APPROVAL**
- Named support/on-call owner: **PENDING OWNER**
- Final release decision: **NO-GO UNTIL ALL REQUIRED GATES PASS**
