# TalkFlow / GlobalTalk AI — Day-7 Go/No-Go Checkpoint (first checkpoint)

**Date:** 2026-10-23 · **Tree under review:** main `b92ed66` (PR #138 merged; launch-phase days 1–6).
**Phase tracking:** Issue #80 ("Post-completion 30-day launch readiness, pilot and launch report").
**Scope:** review of test evidence, security/privacy approvals, deployment health, open defects, capacity limits and support readiness per `docs/POST-COMPLETION-30-DAY-LAUNCH-ROADMAP.md` §Day 7.

## 1. Verdict

**NO-GO for pilot launch today — issued as a time-boxed remediation list, not a silent waiver.**

The roadmap's Day-7 rule: "Only proceed if all entry/Day 1–6 release blockers pass." Two release-candidate
day exits were **never executed** (Day 1 — candidate freeze record; Day 2 — staging deployment rehearsal),
the Day-4 exit criterion — legal/privacy review completed by the responsible qualified reviewer — is unmet,
no support owner is defined anywhere in the repo (entry criterion), and a P0 defect on the browser
per-listener realtime lane (#53) is open. Everything else is code-side verified and CI-anchored.

Per the launch principles (roadmap lines 5 and 16): the schedule **shifts** rather than proceeding on a
guaranteed date, and this checkpoint records owner decisions — it does not disguise any of the above as
passing. Advancement to Day 8 (pilot onboarding) requires the §8 gates to clear and a re-checkpoint of §2/§3.

## 2. Day-exit status (Days 1–6)

| Day | Roadmap exit | Verdict | Evidence anchors |
|---|---|---|---|
| 1 — Freeze candidate and review scope | "Candidate is reproducible and the precise features/languages included in launch are listed." | **NOT VERIFIED — never executed** | No candidate tag exists on the launch tree (`git tag` = only `v0.1.0` at `da0f435`, 2026-10-03 — pre-dates the phase; `git tag --points-at HEAD` empty at `b92ed66`). No SHA/lockfile/config-version/migration-head/provider-version/limitations record doc. Release issue #80 exists **but carries no owner list** (its body defines scope + hard rule + exit only). |
| 2 — Production deployment rehearsal | "Staging deployment and restart/recovery evidence is saved." | **NOT VERIFIED — never executed** | No staging deployment/restart-recovery artifacts anywhere in `docs/`; `docs/PRODUCTION_VERIFICATION_REPORT.md` is a **0-byte stub**. The acceptance record itself defers the launch sign-off browser round to "the staging deployment round" (`docs/TRANSLATION_ACCEPTANCE.md` line 89, OPEN). Deployment surfaces exist as docs (`docs/DEPLOYMENT.md`, `docs/deployment/supabase_and_render.md`, `docs/REALTIME_PRODUCTION.md`) — not as executed evidence. |
| 3 — End-to-end functional sign-off | Checklist PASS or a documented, launch-approved scope exclusion. | **PASS (code-side) with recorded scope exclusions + 1 open P0** | Journey executed live: signup/login, text translation, write, TM engine, documents, history, meeting create/join/leave, sign-out PASS; two-way realtime caption fan-out + mic/camera are documented exclusions (harness cannot grant capture permission); SPA realtime signalling lane connect-loop observed — canonical `/ws/realtime` lane healthy raw. Anchors: `7203e7d` (#132), `c81b20b`, `docs/TRANSLATION_ACCEPTANCE.md` §"Clean browser journey sign-off record", roadmap line 51. Open P0: issue #53. |
| 4 — Security, privacy and data-retention sign-off | "No open critical/high security finding; any legal/privacy review requirement is completed by the responsible qualified reviewer." | **PASS on the code side — legal/privacy sign-off UNMET** | Security re-run 157/157 (18 suites); critical-class retention gap found and fixed red→green (`b98cd47` inside squash #134; 4 pin tests `tests/test_retention_transcripts_hardened.py`); secret scan 12 patterns / 1 624 tracked files = zero real credentials; hygiene `eb0234d` (442 machine-local files untracked). Merged anchors: `ad4523b` (#134), `a98d53a` (#135), owner's `5a84865` (#136). Recorded owner actions (5): privacy-notice/DPA review by the qualified reviewer; CI secret-scan step; GDPR deletion-endpoint decision (`delete_user_data`/`delete_org_data` have zero callers); standalone translation-history retention policy; pin the `*.vercel.app` CORS wildcard. Anchors: `docs/TRANSLATION_ACCEPTANCE.md` §"Day-4 … sign-off record" (lines 210–250), roadmap line 60. |
| 5 — Backup, restore and disaster-recovery drill | Restore succeeds; RTO/RPO observations documented; owner approves the runbook. | **PASS on the code side — owner approval UNMET** | Full drill: `pg_dump`→`pg_restore` into a fresh isolated `postgres:16` (PostgreSQL round-trip + `alembic_version` head `f4e2a9c1d8b7` + `alembic check` clean on the restored DB); SQLite audit asset `scripts/drill_backup_restore_sqlite.py`; object-storage byte-hash round trip; Redis proven stateless; queue/DLQ replay + escalations persistence. Anchors: `327e26f` (#137), `docs/RECOVERY_RUNBOOK.md`, roadmap line 70, CI run 39897189021. Recorded owner items (4): production-true RTO/RPO recording; **first staging backup execution**; S3/MinIO bucket backup policy; **runbook approval** (the day-5 exit sign-off itself). Drill timings are drill-scale — not production claims. |
| 6 — Load, latency and cost envelope | Capacity limits, alert thresholds and pilot concurrency written **and approved**. | **PASS on the code side — owner approval UNMET (the day-6 exit itself)** | Envelope measured + documented in `docs/LOAD_CAPACITY_ENVELOPE.md`: real-audio ramp C=1/2/4 — STT stage is the bottleneck (p50 11.1 → 26.2 → 41.4 s; translation ≤0.83 s; TTS ≤1.6 s); e2e p50 12.2 → 35.4 → 51.2 s (p99 102 s at C=4); server RSS max 2.41 GB; graceful degradation everywhere (42/44 configured attempts as latency events + 2 audited failure deliveries; 12/12 pivot legs; 16/16 honest recoverable `translation.failed` on en→mr). C=1 anomaly root-caused to a cold-window argos/stanza init race (recoverable failure delivered on the wire — not a lost event). Proposal: **max 1 concurrent AI-translated meeting per server process** (this hardware class); alerts e2e p50 >20 s WARN / >35 s CRIT, RSS >2.5 GB; production re-measure via the same harness before any absolute claim. Anchors: `b92ed66` (#138), roadmap line 79, CI runs 39906609442 (PR, `ac2fa06`) + 39907324861 (main). Recorded owner items: approve caps/thresholds (§8); serialize cold argos/stanza init; queue-depth/reconnect gauges in `/metrics`; cloud-lane cost worksheet; ja target TTS voice; VC++ redist in deployment images. |

## 3. Entry-criteria audit (roadmap lines 18–29)

| Criterion | Status | Note / anchor |
|---|---|---|
| L20 Initial-roadmap P0/P1 gates pass on the candidate | **PARTIAL** | First roadmap's tested surfaces carry PASS verdicts (`docs/TRANSLATION_ACCEPTANCE.md`), but its sweep tracker #109 stays OPEN (same-class findings: unguarded model downloads, private-only guarantee, usage/billing accounting — parts landed via #114/#111), plus sweeps #100/#102 open. Carried into the §5 defect register; not claimed either way without their own re-run. |
| L21 Actual configured providers/models, not only fake providers | **SATISFIED** (production latency claims still owner-gated) | Day-3 text lane + Day-6 real-audio pipeline (faster-whisper → Argos → Piper) measured on the candidate. Fake-provider benchmark numbers are never quoted as production latency (roadmap rule; sandbox mirror stays separate in the envelope doc). |
| L22 Two-way browser meeting passed; three-way per-listener if offered | **PARTIAL** | Wire level: realtime-golden CI green + day-6 multi-target drill. Browser level: webrtc-smoke green; full clean-browser journey has recorded exclusions (capture permissions) and open P0 #53 (per-listener translated audio in the browser). Three-way fan-out is offered → gated by #53/§8-R10. |
| L23 Capability matrix + measured latency/quality report | **SATISFIED** | Pair-matrix truth (day-3, #132) + `docs/LOAD_CAPACITY_ENVELOPE.md` (day-6). |
| L24 CI/build/E2E/migrations green on the exact candidate | **SATISFIED** | main `b92ed66`: CI run 39907324861 green (backend, migrations full cycle, frontend, realtime-golden, docker); pages run 39907323904 green; last PR run 39906609442 per-job durations recorded in roadmap line 79. |
| L25 Security review coverage (auth, tenancy, WS authz, secrets, uploads, consent, retention, logs) | **SATISFIED on code — sign-off pending** | Day-4 §record row-by-row; legal/privacy completion is the missing half (R3). |
| L26 Production env, backup/restore, monitoring, **support owner**, rollback defined | **PARTIAL** | Backup/restore drilled (day-5, owner items open); monitoring = `/metrics` + proposed thresholds pending owner adoption (day-6); rollback path documented in runbooks; **no support owner named in any doc** → R9. |
| L27 Telephony scope with real sandbox evidence + approved consent/disclosure plan | **SATISFIED for the recorded scope** | Carrier-honesty lane in place (simulated provider remains default; carrier access honest-degraded); consent gated and disclosure surfaces verified (day-4). Telephony stays outside the pilot scope unless the owner expands it. |
| L29 Narrow the release scope if items are unchecked | **BINDING** | This is the mechanism §8-R10 invokes: the pilot scope must be explicitly narrowed (no silent waiver). |

## 4. Deployment health of the current candidate

- main `b92ed66` — workflow `CI` run **39907324861: green** (backend · migrations downgrade/upgrade cycle · frontend · realtime-golden · docker); `pages-build-deployment` run 39907323904 green.
- docs-only changes path-skip the heavyweight CI jobs (verified on prior PR runs; E2E stays gated by its paths filter).
- Docker image builds are green through the CI docker job; **no staging deployment exists yet** (Day-2 unrealized — §2/R2).
- No runtime deployment of this repository was disturbed during this checkpoint; the parallel session's runtime surfaces (its `run_api.py` on :8088, pid 3620, and its DB `services/api/data/globaltalk.db`) were left untouched.

## 5. Open defects / P0–P1 register (consolidated)

| Item | Class | Anchor |
|---|---|---|
| #53 — group video meetings reliability + per-listener live translated audio (browser/SPA lane) | **P0, OPEN** | GitHub issue #53; day-3 recorded exclusion |
| #109 — same-class findings sweep (unguarded model downloads, private-only guarantee, usage/billing accounting) | OPEN tracker | GitHub issue #109 (parts landed: #114, #111) |
| #100 / #102 — full-localhost audit sweep (6 defects) / production-bundle benchmark comparison | OPEN | GitHub issues #100, #102 |
| Session-environment boot-contract findings (2026-10-23): CWD-relative API DB path trap; CPython 3.14 faster-whisper warmup crash (native-site `0xC0000374`, `sitecustomize.py` preload mitigation proven); vite `detectBackendPort()` backend-port race; duplicate-email signup 201 under the fresh-DB condition | RECORDED (each non-fatal with mitigation or honest per-DB semantics) | `docs/TRANSLATION_ACCEPTANCE.md` lines 201–208 |
| ja: no target TTS voice → ja stays SOURCE-only; latency events honestly not published for the ja target | RECORDED owner item | day-6 recorded items |
| en→mr (unconfigured pair): honest recoverable `translation.failed` + captions kept — correct behavior, disclosed in the capability matrix | working-as-documented | day-6 drill |
| Day-3 scope exclusions: two-way realtime caption fan-out + mic/camera in the automated clean-browser journey; SPA realtime signalling lane connect-loop (canonical `/ws/realtime` healthy raw) | RECORDED exclusions | roadmap line 51 |
| Day-4 owner actions (5) — see §2 Day 4 | RECORDED gates | `docs/TRANSLATION_ACCEPTANCE.md` line 243 |
| Day-5 owner items (4) — see §2 Day 5 | RECORDED gates | `docs/RECOVERY_RUNBOOK.md` |
| Day-6 owner items (caps approval + 5) — see §2 Day 6 | RECORDED gates | `docs/LOAD_CAPACITY_ENVELOPE.md` §8–§10 |

## 6. Capacity limits (for the record — owner adoption pending)

- Proposed pilot cap (this hardware class): **max 1 concurrent AI-translated meeting per server process**; C=2 delivers all targets but lags ≥29 s p50; C=4 is archival/caption quality.
- Alert thresholds anchored to measured warm C=1: e2e p50 >20 s WARN / >35 s CRIT; RSS >2.5 GB; failure-rate watch.
- Production re-measurement via the same harness is required before any absolute latency/capacity claim; the fake-provider dispatch benchmark (7.11× overhead-metric) stays strictly out of production-latency language.

## 7. Support readiness

- **Support owner: not defined.** No doc names a support owner/contact (entry criterion line 26 unmet; Day-8/§Day-15 both require a support contact). → R9.
- Onboarding guide, supported-language list, data-handling details, known-limitations page — Day-8 deliverables (not retro-claimed here).
- `docs/TROUBLESHOOTING.md` exists as the user-facing base; monitoring/alert **delivery** remains untested (§Day-26 gate, later phase).

## 8. Time-boxed remediation list (NO-GO → GO conditions)

Dates are **proposed timeboxes** for the owner to adopt (they shift the 30-day schedule rather than guaranteeing the original dates). Evidence-first: each gate closes only with its named evidence, recorded in the referenced doc/issue.

| # | Gate to clear | Evidence required | Owner | Proposed by |
|---|---|---|---|---|
| R1 | Execute **Day-1** for real | Tag the candidate on (a successor of) `b92ed66`; record commit SHA, dependency lockfiles, config version, migration head (`f4e2a9c1d8b7`), provider/model versions, known limitations; add the owner list to issue #80 → **partially realized 2026-10-23**: tagged `launch-candidate-1` @ `45c15b9`, record in `docs/RELEASE_CANDIDATE.md`; the owner-names-into-#80 half is still open | owner | 2026-10-26 |
| R2 | Execute **Day-2** staging rehearsal | Deploy the candidate to a staging-like environment; save `/health`, `/ready`, migrations, worker connectivity, secrets-injection evidence **and** API/worker restart-recovery evidence (also unblocks the deferred launch sign-off browser round) | owner + dev | 2026-10-28 |
| R3 | Day-4 legal/privacy sign-off | Privacy notice + data-processing/subprocessor description reviewed and signed by the responsible qualified reviewer | owner (qualified reviewer) | 2026-10-28 |
| R4 | GDPR deletion story + standalone translation-history retention policy | Written decision wired or scheduled in the retention plan | owner | 2026-10-28 |
| R5 | CI secret-scan step | CI workflow runs gitleaks/trufflehog (or documented equivalent) | dev/owner | 2026-10-28 — **dev half realized 2026-10-23**: the `secret-scan` CI job runs gitleaks **v8.30.1 (digest-pinned)** over full history (`fetch-depth: 0`); all 34 historical finding instances (22 still present in the current tree) were individually audited as CI/test/doc placeholders or machine-local tool artifacts and pinned by exact fingerprint in `.gitleaksignore`, so any new or relocated secret fails the job. Local full-history run with the CI command: 441 commits scanned, no unignored leaks found; the R2 drill's synthetic credentials are not flagged. CI verdict on this PR is recorded in the roadmap Day-4 status after the run |
| R6 | CORS wildcard pinned | `*.vercel.app` allowlist replaced with exact domains | owner | 2026-10-28 |
| R7 | Day-6 caps/thresholds approval | Owner sign-off recorded on `docs/LOAD_CAPACITY_ENVELOPE.md` §8 (this **is** the day-6 exit) | owner | 2026-10-28 |
| R8 | Day-5 runbook approval + backup policy execution | Runbook approval; first staging backup executed and recorded; production RTO/RPO numbers recorded; S3/MinIO bucket backup policy decided | owner | 2026-10-28 |
| R9 | Support readiness baseline | Support owner named + support contact channel published (prerequisite for the Day-8 exit) | owner | 2026-10-28 |
| R10 | Open-P0 #53 decision for the pilot scope | Either fix #53 before pilot exposure, **or** explicitly narrow the pilot scope (with disclosed limitation recorded in the capability matrix) — the roadmap's narrowing mechanism; never silently waived | owner | 2026-10-28 |

**Re-checkpoint rule:** once R1–R10 carry their evidence, re-run the §2 day-exit table and §3 entry-criteria audit;
a GO is then written referencing the same anchors. Any gate failing its timebox keeps this NO-GO and updates the
list (new dates or scope narrowing) — day by day, without silent advancement.

## 9. Recording conventions inherited by this checkpoint

- Owner items are RECORDED, not coded; code work on the launch candidate stays limited to focused, reviewed fixes (the day-1 freeze rule becomes binding the moment R1 lands).
- Benchmark numbers from fake providers (the sandbox mirror in `docs/LOAD_CAPACITY_ENVELOPE.md` and `scripts/benchmark_translation_fanout.py`) are never quoted as production latency anywhere downstream.
- "No known blockers" is different from "bug-free": this document claims only what its anchors support.
