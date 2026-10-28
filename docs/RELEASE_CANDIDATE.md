# TalkFlow / GlobalTalk AI — Release-candidate freeze record (Day-1)

**Recorded:** 2026-10-23 · **Tag:** `launch-candidate-1` → `45c15b9` (main, "fix(day7): go/no-go checkpoint … (#139)").
**Governance:** this record realizes the mechanical half of GO_NO_GO_CHECKPOINT §8 **R1** (Day-1 exit per `docs/POST-COMPLETION-30-DAY-LAUNCH-ROADMAP.md` §Day 1). The day-7 checkpoint's NO-GO stands; this tag makes the freeze rule binding while remediation runs.

## 1. Candidate identity and reproducibility

| Item | Value |
|---|---|
| Tag / commit | `launch-candidate-1` @ `45c15b9` (annotated tag; pushed 2026-10-23) |
| Squash lineage | #138 (`b92ed66`) → #139 (`45c15b9`) — launch-phase docs era on the day-6 envelope tree |
| PR-run CI on this exact content | run **39908976764** on `52008cf` (= the same tree content, docs-only delta) — **all green**: backend 4m0s · frontend 1m18s · migrations 2m18s · realtime-golden 4m32s · docker 3m26s · Vercel deployment pass · Vercel Preview Comments pass (Supabase Preview: skipping, as configured) |
| Main CI run on the tagged SHA | run **39909886180** on `45c15b9` (in progress at record time; final verdict recorded in the roadmap row once complete) · pages run 39909885414 success |
| E2E lane | path-filtered per `.github/workflows/e2e.yml` (docs-only delta; realtime-golden exercised the translated-audio wire directly) |

## 2. Precise launch scope recorded at freeze (features and languages)

**Features in candidate scope (evidence-anchored):**
- Text translation, write/grammar, TM engine, documents (upload/extract/retry/QA), history — day-3 clean journey PASS (`docs/TRANSLATION_ACCEPTANCE.md` §"Clean browser journey sign-off record"; `7203e7d` #132).
- Realtime translated audio over the canonical `/ws/realtime` lane — realtime-golden CI suite green (run 39908976764) + day-6 multi-target drill (`scripts/load_drill_realtime.py`, `docs/LOAD_CAPACITY_ENVELOPE.md`).
- Meetings: signup/login, create/join/leave, captions/transcripts visible to participants (day-3 PASS); per-listener fan-out served by the realtime lane (day-6).
- Telephony: **beta/disabled-by-default** (simulated provider default; carrier lanes honest-degraded, consent-gated — `e2181a6` #126; day-4 §record). No telephony launch claims.
- Capacity posture: proposed pilot cap **max 1 concurrent AI-translated meeting per server process** + alert thresholds (`docs/LOAD_CAPACITY_ENVELOPE.md` §8) — **pending owner approval (R7)**.

**Languages (validated truth, not aspirational):**
- Realtime-validated targets: en→hi, en→zh (installed pairs + TTS voices); hi→en, hi→zh; zh→en, zh→hi (pivot-served); **ja is a SOURCE only** (no ja TTS voice — latency events honestly not published for ja as target); **en→mr is intentionally unconfigured** → honest recoverable `translation.failed` with captions kept (degradation lanes per `docs/LOAD_CAPACITY_ENVELOPE.md` §2.2/§7).
- Text-translation matrix: per `docs/TRANSLATION_ACCEPTANCE.md` day-3 pair-matrix truths (`#132`).
- Document-derived and text-history translation: per day-3 record.

**Excluded by scope decisions (recorded, not waived):** two-way realtime caption fan-out and mic/camera in the automated clean-browser journey (no grantable capture permission in the harness); SPA realtime-signalling connect-loop observation (canonical lane verified healthy raw).

**Pilot Scope Narrowing (Remediation R10 / Issue #53 Decision):**
Per roadmap line 29 ("narrow the release scope if items are unchecked"), the pilot release scope is formally narrowed:
- **Included in Pilot Cohort:** 2-way video meetings with live translation, text translation, Write/grammar correction, document translation (DOCX/PDF), and live meeting captions.
- **Excluded / Disclosed Beta Limitation (Issue #53):** 3+ party concurrent browser per-listener translated audio fan-out remains in beta. In meetings with 3+ distinct language listeners, participants receive live multilingual captions and original-call audio; synthetic voice fan-out is limited to 2 participants until browser multi-listener acceptance is unblocked. This limitation is published in the capability matrix and pilot onboarding guide.

## 3. Dependency lockfiles recorded

- `services/api/requirements.txt` (+ `requirements-dev.txt`, `requirements-gpu.txt`)
- `apps/api/requirements.txt` (legacy compatibility API, separate lineage — not the launch runtime)
- `package-lock.json` (root JS workspace) · `apps/web/package-lock.json`

## 4. Runtime, config and migration versions

| Layer | Version anchor |
|---|---|
| API/worker container base | `python:3.12-slim` (`infrastructure/docker/Dockerfile.api:2`; also Dockerfile.worker) |
| Infra images (docker-compose.yml) | `postgres:16` · `redis:7-alpine` · `minio/minio:RELEASE.2024-06-13T22-53-53Z` · `livekit/livekit-server:v1.13.10` (pinned per PR #74 policy) |
| GPU-lane pins | `torch==2.9.0`, `transformers==4.49.0` (`services/api/requirements-gpu.txt`) |
| AI-lane minimum pins | `faster-whisper>=1.0.0`, `argostranslate>=1.9.0` (`services/api/requirements-dev.txt`) |
| Config system | `services/api/app/config.py` — pydantic-settings, env-driven (`​.env.example` contract). Production-forbidden rules at config lines: SQLite forbidden (`:376`), Redis required (`:372`), no `*` CORS origin (`:380`), secure cookies forced (`:386`), ≥32-char secrets (`:364,368`), `wss://` LiveKit required (`:458`), full carrier credential set (`:416-426`), `TELEPHONY_PROVIDER=auto` blocked when carrier creds exist (`:392-403`), Asterisk lane must be explicitly admitted (`:436`) — per `docs/ARCHITECTURE_OWNERSHIP.md` |
| Schema/migration head | `f4e2a9c1d8b7` (`python -m alembic heads` on the candidate tree; also verified post-restore in the day-5 drill) |
| Model/weights inventory | faster-whisper small (HF cache 463.7 MB) · 6 Argos pairs (en↔hi, en↔zh, en↔ja — 650.4 MB) · 3 Piper voices (en_US-lessac, hi_IN-pratham, zh_CN-huayan — 181.1 MB) · `model_cache` total 1357.3 MB (`docs/LOAD_CAPACITY_ENVELOPE.md` §2.1); `HF_HOME` pinned to `MODEL_CACHE_PATH/hf` at settings load (`docs/TRANSLATION_ACCEPTANCE.md` line 143) |

## 5. Known limitations recorded at freeze

- **GO_NO_GO_CHECKPOINT.md R1–R10 open gates** (privacy sign-off, CI secret-scan step, GDPR deletion decision, standalone translation-history retention, CORS wildcard pin, hosted TLS/WSS staging + first staging backup + runbook approval, caps approval, support owner, P0 #53 pilot-scope decision) — the NO-GO verdict and its re-checkpoint rule govern advancement. R2's isolated production-mode rehearsal is saved (`docs/STAGING_REHEARSAL.md`), with the hosted/TLS staging and deferred browser-round residuals recorded there.
- **MinIO image pullability (found during R2, 2026-10-23):** `docker-compose.yml` pins `minio/minio:RELEASE.2024-06-13T22-53-53Z`, but the upstream Docker Hub repository is no longer served — a cold start of the compose stack cannot pull MinIO. The rehearsal used the Bitnami legacy mirror of MinIO 2024.6.13 (pinned digest) in the drill overlay only; a production image-source decision is required (owner).
- Scope exclusions + observed faults: day-3 exclusions (capture permissions; SPA lane connect-loop), ja source-only, en→mr unconfigured lane, session-environment boot-contract findings (`docs/TRANSLATION_ACCEPTANCE.md` lines 201–208: CWD-relative DB path trap; CPython 3.14 faster-whisper warmup crash with proven `sitecustomize` mitigation; vite `detectBackendPort` race; duplicate-email signup under the fresh-DB condition).
- The fake-provider fairness benchmark (`scripts/benchmark_translation_fanout.py`, 7.11× dispatch-overhead metric) measures scheduler overhead only — **never** a production-latency claim (`docs/LOAD_CAPACITY_ENVELOPE.md` §1.1).
- Day-6 envelope is a local-machine characterization; absolute capacity claims require production re-measurement with the same harness.
- **Post-freeze remediation note (2026-10-23):** R5 (CI secret-scan) is realized after the freeze — `.github/workflows/ci.yml` runs a digest-pinned gitleaks v8.30.1 full-history scan, with the 34 audited historical placeholders pinned in `.gitleaksignore` (PR #142, CI run `39936233786` on `6e62caf` green). The open-gate sentence above records the freeze-date state.

## 6. Freeze rule (binding from this tag)

Unrelated feature work is frozen on the launch-candidate branch lineage: **focused, reviewed fixes only** (roadmap §Day-1 line 35). Remediation work proceeds per the checkpoint's R-list; pilot activation waits for the re-checkpoint.

## 7. Owner list (the open half of R1)

Issue **#80** is the phase tracking issue (scope, hard rule, exit). The baseline owner registry is established below:

| Role / Gate | Designated Owner | Responsibilities & Coverage |
|---|---|---|
| **Phase & Release Lead (R1, R8, R10)** | Aman Shandilya (@Aman678317) | Issue #80 stewardship, candidate freeze, pilot scope decisions, backup policy approval |
| **Engineering & Infra Lead (R2, R5, R6)** | Shandilyaprahald | Staging rehearsal execution, CI secret-scan integrity, production CORS origin rules |
| **Legal, Privacy & Compliance (R3, R4)** | Qualified Reviewer / Aman Shandilya | Privacy policy, subprocessor DPA, GDPR deletion policy |
| **Capacity & Performance Lead (R7)** | Lead AI Engineer / Aman Shandilya | `docs/LOAD_CAPACITY_ENVELOPE.md` §8 sign-off, concurrency caps, alert thresholds |
| **Support & Incident Lead (R9)** | Aman Shandilya | `docs/TROUBLESHOOTING.md` support owner, incident triage, rollback execution |
