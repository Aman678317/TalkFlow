# TalkFlow — Production Verification Report (Phase 6 release gate)

**Tree:** `feat/phase5-6-release-gate`, code commit `b4a2e19` (13 commits ahead of
`origin/main` at the time of writing), working dir
`C:\Users\acer\Documents\Qoder\2026-10-11\6c2fa753\repo`. Commits after `b4a2e19`
on this branch touch documentation only, so every number below describes the code
as of `b4a2e19`.
**Backend tree under test:** **Tree A** = `services/api` (`app.*`, port 8088) — the
code Render deploys, plus the frontend `apps/web` (Vite). Tree B (`apps/api`,
port 8000) is the legacy golden-test tree and is called out where it differs.
**Date run:** 2026-10-14.

> **Read this first: the Phase 6 merge gate is NOT met.**
> The PDF's gate is *"regression tests pass **and** a genuine two-browser,
> real-provider call proves both directions."* Half one is now demonstrated; half
> two is not (§5). This report is scoped to the tree and commands named above.
> It is not a claim that anything else in the product works, and nothing here has
> been deployed.

---

## 1. Commands run, and what each returned

Every line below was executed on this tree and the exit status is the process
status, not a filter's. Local test environment for the Python lanes:
`APP_ENV=test CACHE_BACKEND=memory REDIS_URL="" JWT_SECRET=<32-char test value>
RATE_LIMIT_AUTH=100000/minute RATE_LIMIT_TRANSLATE=100000/minute`.

| # | Command | Result | Duration |
|---|---|---|---|
| 1 | `python -m pytest tests/unit tests/integration -q -rs` | **411 passed, 2 skipped** | 74.6 s |
| 2 | `python -m pytest tests -q -rs --ignore=tests/unit --ignore=tests/integration --ignore=tests/realtime` | **121 passed** (5 warnings) | 94.2 s |
| 3 | `python -m pytest tests/realtime -q -rs` | **3 passed, 2 skipped** | 0.1 s |
| 4 | `npx tsc -b` (in `apps/web`) | **exit 0**, no diagnostics | — |
| 5 | `npx vitest run` (in `apps/web`) | **88 passed** (8 files) | 10.7 s |
| 6 | `npx vite build` (in `apps/web`) | **exit 0** (chunk >700 kB warning) | 10.3 s |
| 7 | `npx playwright test --reporter=line` (in `tests/e2e`, `WEB_URL=http://localhost:5173`) | **3 passed**, 2 workers | 32.3 s |

Lane 2 is the one that **previously ran nowhere automatically**: `pytest tests/unit
tests/integration` never collects the top-level `tests/*.py` files,
`tests/deployment/` or `tests/browser_e2e/`, so 121 regression tests — every
cross-tenant, migration, observability, `render.yaml`/`vercel.json` alignment,
media-contract and browser-checklist-runner check — only ever ran on whoever's
machine happened to be set up for them. `.github/workflows/ci.yml` now runs them as
a step in the `backend` job.

**Lane 2 and lane 7 are local numbers that the first CI run did not reproduce** —
lane 2 failed there on an undeclared `playwright` import and lane 7's job never got
a server to talk to. See §1.2 for the run-back and the fixes.

**Warnings in lane 2** (not failures, but named rather than hidden):
`jwt.InsecureKeyLengthWarning: The HMAC key is 31 bytes long` — five tests in
`tests/test_meeting_media_contract.py` mint LiveKit tickets with a 31-byte test
secret. Harmless in a test; it is a real failure mode if a deployment reuses a
short secret, and it is the kind of thing to fix forward in the test fixture.

### 1.1 Every skip, with its exact prerequisite

A skipped test is **not** a pass. These are the skip reasons printed by `-rs`,
verbatim, and what would make each one run.

| Test | Skipped because | Prerequisite to make it run |
|---|---|---|
| `tests/integration/test_api.py:174` | `Argos en/hi packages not installed in this environment` | `pip install argostranslate` **and** the en⇄hi packages on disk |
| `tests/integration/test_api.py:197` | `Argos en/hi packages not installed` | same |
| `tests/realtime/test_golden_call.py:264` (Tree B) | `golden prerequisites missing under \tmp\globaltalk-models (run MODEL_PROFILE=CPU bash scripts/download_models.sh)` | download the CPU model set into the model cache |
| `tests/realtime/test_deployed_tree_golden_call.py:238` (Tree A) | `deployed-tree golden prerequisites missing: `argostranslate` not installed (needed for MT); argos package hi->en not in \tmp\globaltalk-models\argos; argos package en->hi not in \tmp\globaltalk-models\argos (run MODEL_PROFILE=CPU bash scripts/download_models.sh)` | `pip install argostranslate` + `MODEL_PROFILE=CPU bash scripts/download_models.sh` |

**Where those prerequisites *are* satisfied:** the CI `realtime-golden` job —
`MODEL_PROFILE=CPU bash scripts/download_models.sh` and then
`python -m pytest tests/realtime -q -rs` with `MODEL_CACHE_PATH` pointed at the
runner's downloaded models, followed by `python scripts/verify_ai_stack.py`. That
job is the **only** place the real STT / MT / TTS legs execute unattended. On this
machine they do not, so the offline golden path is unproven locally.

### 1.2 CI read-back — the first run on this branch was red

Run `38494934668` on PR #37 (commit `e9a4447`) finished `frontend` pass, `docker`
skipped, `Vercel – globaltalk-ai` pass, and **three jobs failed**:

| Job | Result | Evidence |
| --- | --- | --- |
| `backend` | 1 failed, 120 passed | `ModuleNotFoundError: No module named 'playwright'` at `tests/browser_e2e/runner.py:20`, collected by the hardening step added in `b4a2e19` |
| `browser-e2e` | setup failed | the "Start backend and the Vite dev server" step exited 7 (curl "failed to connect") after the full 60×2 s readiness loop; the `if: failure()` log step *also* failed (`tail: option used in invalid context -- 8`), so **no server log was captured and the root cause is still unknown** |
| `realtime-golden` | 1 failed, 4 passed | Tree B's `test_golden_call.py` passed; the Tree A call died at `await a.speak(hi_speech)` with `ConnectionClosedError: received 4409 duplicate_connection_superseded`, emitted from `services/api/app/realtime/ws.py:229` |

Each cause was then established, not guessed:

- **`backend`** — the Python `playwright` package is imported at module scope by
  the runner but is declared in **no** requirements file, so no CI job had it. It
  passed locally only because this machine has it installed. Fixed by installing
  the package (no browser download) in that lane.
- **`realtime-golden`** — the test signed all three participants up with **one**
  access token. `meeting_service.join_meeting` is idempotent by
  `(meeting_id, user_id)` (`services/api/app/services/meeting_service.py:87`), so
  all three joins returned the same `participant_id`, and each WebSocket connect
  superseded the previous one. Reproduced against a live Tree A server with dev
  providers: *without* `guest_key` → 1 distinct participant, 1 of 3 sockets open;
  *with* a `guest_key` per seat → 3 distinct participants, 3 of 3 open. Fixed by
  giving every seat its own `guest_key` (the same escape `bench_latency.py:105`
  already uses) and asserting the three ids differ.
- **`browser-e2e`** — the likely trap is the one already hit on this machine: Vite
  binds whatever `localhost` resolves to (`::1`), while the readiness probe asked
  `127.0.0.1`. **Not confirmed** — nothing was logged. The step now starts Vite
  with `--host 127.0.0.1`, points `WEB_URL` at the same literal address, reports
  which of the two servers never answered, and dumps both logs with valid
  `tail -n 80` usage. The next run either passes or tells us why.

The consequence for the gate is unchanged by these fixes: **the real-provider
golden legs have still never completed on GitHub**, so the level-2 evidence the
merge gate asks for does not exist yet. The numbers above are local evidence, and
CI is currently red on this branch.

---

## 2. Evidence level 1 — unit

411 Python tests (`tests/unit` + `tests/integration`, SQLite + in-memory cache) and
88 frontend tests (vitest, jsdom). Covers: stage ordering and the supervisor's
interrupt/flush rules, barge-in, phrase segmentation, per-connection bounded send
queues, provider timeout/retry/circuit-breaker behaviour, capability registry,
RBAC and cross-tenant denial, transcript retention, the frontend caption/timeline
model, and the audio decode path.

`tests/unit/test_translation_pipeline.py::TestNeuralOnlineFallback` makes **live
network calls** to a public web translator. It passed, so it is counted here as
unit + a small amount of real-provider connectivity — and also as a test that can
fail from the internet, not from the code.

## 3. Evidence level 2 — integration, with actual provider connectivity

What is genuinely proven on this tree:

- HTTP/API contracts against a real FastAPI app + SQLite (lane 1), and against
  PostgreSQL + Redis in CI's second backend step.
- The **deployed tree's** full stage trace against injected fake providers — every
  stage event landing in order, and the failure legs (STT failure stays recoverable,
  one language's TTS failure does not condemn another, stale audio dropped before it
  talks over current speech, original-audio relay reaching only original/mixed
  listeners). That lives in `tests/unit/test_realtime_agents_trace.py`,
  `tests/integration/test_realtime_phase3_gate.py` and friends, i.e. **inside
  lane 1's 411**, not in `tests/realtime`.
- Lane 3 (`tests/realtime`) contributes **3** tests on this machine, and they are
  benchmark-report matching logic (`test_bench_report_matching.py`: a turn counted
  once even when the sink still holds it, each turn reported exactly once, another
  language's report not treated as this listener's wait). It contributes **no**
  golden-call evidence here — both golden calls skip (§1.1).
- `GET /version` now reports, per AI task, both the configured provider **and**
  whether this image can run it (`importable` / `missing` / `remote` /
  `remote_unconfigured` / `dev_stand_in`) — commit `425b18f`. Before this, an
  operator setting of `auto` let a build advertise `faster_whisper` while every
  call fell through to a dev stand-in.

What is **not** proven at this level: a run with real faster-whisper / Argos /
Kokoro weights on this machine (see §1.1 — it skips), and any paid/managed provider
credential path.

## 4. Evidence level 3 — browser end-to-end

`npx playwright test` drives **two distinct browser sessions** against a live Vite
dev server (`:5173`) proxying to a live Tree A backend (`:8088`), with
`TRANSLATION_PROVIDER=dev_echo`, `STT_PROVIDER=dev_text`, `TTS_PROVIDER=dev_tone`:

1. **Golden demo, both directions of one turn.** Speaker A signs up, creates a
   meeting, joins as a Hindi speaker; Listener C opens the **share link
   anonymously** (guest `join_token`), joins as an English listener. A injects
   `नमस्ते दुनिया!` over the live WebSocket. Asserted: the source caption is visible
   to **both**, `Hello world!` is visible to **C**, and `Hello world!` has
   **count 0 on A's screen** — i.e. the translation was delivered only to the seat
   that asked for it.
2. **Document pipeline.** Upload → row appears → status reaches `ready` or `failed`.
3. **Translate journey.** Signup → login → debounced `en→hi` translation → history
   → sign-out → re-login.

- **These three passed locally, not on GitHub.** The `browser-e2e` job that now runs
  them never reached the specs: its servers did not answer the readiness probe and
  the failure log step was itself broken (§1.2). So level 3 is currently
  single-machine evidence.

**Honest limits of level 3, stated in full:**
- **Speech is injected, not captured.** The test uses the dev `transcript.inject`
  channel and `--use-fake-device-for-media-stream`. No real microphone capture, no
  real VAD on real audio, is proven by this.
- **Remote playback is not verified.** The assertions are on captions. The browser
  decode/queue path is unit-tested (§2) but nothing here proves that audible audio
  reached a real output device.
- **The MT answer came from the offline dev table**, so this proves plumbing, not
  translation quality. (`b4a2e19` deliberately made the canned transcripts exact
  `dev_echo` keys; before that, a canned phrase not in the table silently went to a
  **public web translator**, so the assertion was checking the internet rather than
  the fixture.)
- One direction per run (hi→en). en→hi, zh→hi and the reverse legs are covered by
  unit tests only.

## 5. Evidence level 4 — human listening check: **not performed**

This is the gap that keeps the gate shut. Required, and not done:

**Procedure (user-owned, needs two physical devices):**
1. Two laptops, two browsers, both on `https://<deployment>`, one on Wi-Fi and one on
   a different network if you want a realistic path.
2. Set the providers to real engines on the server, then confirm it:
   `GET /version` → every task must read `importable`/`remote`, **none** `dev_stand_in`.
3. Speaker joins with `I speak: Hindi`, `I want to hear: original voice`.
   Listener joins the share link with `Translate incoming speech into: English`.
4. Speaker says a full sentence aloud into the mic. **Listen on the listener's
   device**: is there translated audio, does it start before the next sentence
   would have arrived, is it intelligible, and did the speaker's own voice get cut
   when they interrupted (barge-in)?
5. Swap roles and repeat, so **both directions** are proven by a person.
6. Open `GET /api/v1/meetings/{id}/realtime/health` from a session on the same
   replica and read the four stage statuses; check `gt_e2e_latency_ms` p50/p95 and
   that `gt_translation_failures_total`, `gt_stale_audio_dropped_total` and
   `gt_ws_send_dropped_total` did not move.
7. Record who listened, on what hardware/network, which providers, and what they
   heard — as evidence, not as a verdict.

## 6. Latency: measured, and explicitly not a promise

`docs/REALTIME.md` (2026-10-13) records the only baseline this repo has:
`hi→en`, 20 injected turns, **p50 1429 ms / p95 2217 ms**, translation p50 1385 ms,
TTS first frame p50 11 ms, on dev STT/TTS stand-ins over a **live** `neural_online`
MT path, loopback. Server-side rollup for the same run: `n=20 p50 1407 p95 2137`.

The 1.5 s median / 2.5 s p95 first-audio target is **a goal to measure, not a
promise**. That number is inside the target and simultaneously worthless as a
guarantee: it contains no real speech recognition, no real synthesis, no network
beyond loopback, 20 samples, one direction, one machine. It must never be quoted
without the provider set, direction, sample count and environment that produced it.

## 7. What is NOT proven by this report

- ❌ A **real-provider**, two-browser call in both directions (§5) — the gate item.
- ❌ Human listening / audio quality / barge-in felt from a seat (§5).
- ❌ **LiveKit mode**. `LIVEKIT_ENABLED=false` in the browser-e2e job; the media
  contract tests use fakes.
- ❌ Anything about **this branch deployed**. PR #37 is open and unmerged; nothing
  was deployed to staging or production as part of this work.
- ❌ **CI green.** Three of five jobs failed on the first run of this branch (§1.2).
- ❌ Multi-replica behaviour. The per-meeting stage health endpoint answers from
  the worker that holds the room's WebSocket; another replica returns
  `{"live": false, "stages": {}, "healthy": true, "reason": "no session in this
  process"}`. Fan-out across replicas is untested — see runbook §6.1.3.
- ❌ Real Argos/whisper/Kokoro inference on this machine (§1.1 skips).
- ❌ Load, soak, or cost. No concurrency numbers; no per-minute provider pricing.
- ❌ Accessibility and responsive layout beyond the checks already in
  `docs/TESTING.md`.

Two genuine product findings came out of making the browser suite honest, both
recorded rather than papered over:

1. **`no_targets` race at meeting start.** If a turn is published while the room
   still holds one participant, it fans out to nobody and the speaker is shown
   "Translation Unavailable · no_targets". "Add to call" returns when the click
   lands, not when the handshake completes. The test now waits for the listener's
   "Connected · Realtime Translation Active" pill and for the speaker's roster to
   show the listener before anyone speaks. **The underlying UX behaviour is
   unchanged** — a real user who talks immediately after joining can still hit it.
2. **Fixture drift into a live internet translator** (§4). Fixed by using exact
   `dev_echo` keys.

## 8. Rollback

Full procedure in `docs/PRODUCTION_RUNBOOK.md` §4. The part that is easy to get
wrong and therefore belongs next to this report:

- The deployment is **Render** (`globaltalk-api`, `rootDir: services/api`) +
  **Vercel**, not the Docker/Kubernetes route the runbook used to describe.
- `services/api/start.sh` runs `alembic upgrade head` on boot, and production
  boot **fails closed** unless `alembic_version == "2202ca7dc080"`.
- Consequence: **an app rollback must not outrun the schema.** Reverting the app
  while the database stays at the newer head produces a crash loop, not a
  rollback. Additive migrations usually tolerate the app revert; destructive ones
  require downgrade-or-restore **together with** the app. Backup first, order is
  restore → deploy → `/ready` → one real two-browser call.
- Never delete or disable the failing feature area to make a dashboard green, and
  keep the feature branch isolated until it has passed staging.

## 9. Phase 5 cross-reference

Lip-sync was **assessed and declined for this release** in
`docs/PHASE5_FACE_AND_VIDEO_DECISION.md`: MediaPipe Face Landmarker detects
landmarks/blendshapes, it does not generate lip movements matching a translated
voice; the audio-driven models were compared on licence, access, GPU/CPU, fps,
inference delay, input limits and privacy, and translated audio plus synchronised
captions is the shipping product. Translated playback is disclosed in-room as
*"a machine-generated voice, not the speaker."* Nothing in Phase 5 may delay or
drop core translated audio, and that ordering is unchanged by this report.

## 10. Gate checklist

| PDF requirement | State |
|---|---|
| Regression tests pass | ✗ The first CI run on this branch (§1.2) was **red**: `backend`, `browser-e2e` and `realtime-golden` all failed; only `frontend` passed. Causes are diagnosed and fixes committed, but green CI has not been observed. Locally lanes 1–7 pass; no skip is counted as a pass. |
| Genuine two-browser, real-provider call proves both directions | ✗ Not done (§5). Browser two-session coverage exists but on dev providers with injected speech (§4). |
| Deploy to staging first | ✗ Not done. A Render staging service is a paid resource and needs an explicit owner decision. |
| Verify production configuration | ◐ Method written (runbook §3.2/§3.3); not executed against any live service from this session. |
| Monitor stage-level failure metrics | ◐ Real `gt_*` metric names and the per-meeting stage health endpoint now documented (runbook §5); the earlier version of that section listed metrics the code never emitted. |
| Attach a test report | ✅ this document |
| Attach rollback instructions | ✅ runbook §4 + §8 above |
| 1.5 s median / 2.5 s p95 | ◐ Measured at p50 1429 / p95 2217 ms under dev stand-ins and a live MT path; **a goal to measure, not a promise** (§6). |
