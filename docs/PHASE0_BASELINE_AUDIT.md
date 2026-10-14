# Phase 0 — Repository Audit & Baseline (TalkFlow / GlobalTalk AI)

Generated: 2026-10-13. Read-only audit performed per
`GlobalTalk_AI_Four_Agent_Implementation_Guide` §6 Phase 0. **No source file was
modified.** Every claim below carries file:line evidence or exact command output.
Runtime root causes are marked `static-confirmed` vs `needs runtime repro` — the
guide's rule "do not claim an observed runtime root cause without reproducing it"
is honored throughout.

---

## 1. Git / working-tree baseline

| Item | Value |
|---|---|
| Remote | `https://github.com/Aman678317/TalkFlow.git` |
| Default branch | `origin/main` → `647cc12` ("Merge pull request #26 from fix/share-link-p2p-default-camera") |
| Current branch | `fix/share-link-p2p-default-camera` |
| Current HEAD | `90aa968f32df8e58cb5ff9456834fb7ee3223efc` |
| vs `origin/main` | **ahead 5, behind 1** |
| Untracked | `services/api/model_cache/`, `tests/e2e/package-lock.json` |
| Modified | `.github/PULL_REQUEST_TEMPLATE.md` |
| Untracked new test | `tests/unit/test_globaltalk_pipeline_failures.py` |

The 5 local-only commits (verified with `git merge-base --is-ancestor 90aa968 origin/main` → **NO**):

```
7270cb7 fix(meeting): seed P2P manager with local tracks and await replaceTrack
7eb472f fix(realtime): translate TTS audio as WAV, dev-aware inject, end-to-end tests
303b536 docs(realtime): production AI provider deploy requirements + troubleshooting entry
9f2b17a docs(realtime): final report — share-link translated-audio debug
90aa968 fix(realtime): port dev-mode gating, transcript.inject, and diagnostics to Tree B
```

PR #26 merged only as far as `a218a77`. **Audio-path commit `7eb472f` and Tree-B port
`90aa968` are not on `main`.** Any "deployed behaviour" observed on Render corresponds
to `647cc12`, not to this working tree.

## 2. Toolchain baseline

`python 3.14.2`, `node v26.7.0`, `npm 11.19.0`, no venv at repo root, `apps/web/node_modules` present.
CI pins **Python 3.11** (`.github/workflows/ci.yml:29`) — local runs one major version ahead
of every CI lane; results are not equivalent.

---

## 3. Baseline results (recorded exactly as they exist, before any edit)

| Command (from repo root) | Result |
|---|---|
| `python -m pytest tests/unit -q` | **95 passed** in 5.54s |
| `python -m pytest tests/integration -q` | **42 passed, 2 skipped** in ~98s |
| `python -m pytest tests/deployment -q` | **9 passed** in 1.68s |
| `python -m pytest tests/realtime/test_golden_call.py -q -rs` | **1 skipped** — `test_golden_call.py:237: AI model weights not downloaded` |
| `cd apps/web && npx vitest run` | **45 passed** (6 files) in 9.72s |
| `cd apps/web && npx tsc -b` | **pass** (verified via `npm run build`, whose script is `tsc -b && vite build && node scripts/generate-spa-routes.js`) |
| `cd apps/web && npm run build` | **pass**, 2422 modules, largest chunk `index-*.js` 803.72 kB / 212 kB gz (chunk-size warning only) |
| `ruff check apps/api ai services scripts --select E9,F --ignore F401,F841,F541` (CI-blocking, `ci.yml:37`) | **All checks passed** |
| `ruff check apps/api ai services scripts --select E,F,W --ignore E501,E402,W505` (CI non-blocking, `ci.yml:42`) | **197 errors** (backlog; 156 auto-fixable) |

Skip reasons (a skip is not a pass):

- `tests/integration/test_api.py:174` and `:197` — "Argos en/hi packages not installed in this environment".
- `tests/realtime/test_golden_call.py:237` — model weights absent. `_models_available()`
  (`test_golden_call.py:46-50`) requires BOTH `$MODEL_CACHE_PATH/piper/hi_IN-pratham-medium.onnx`
  and `$MODEL_CACHE_PATH/argos/en_hi`, defaulting to `/tmp/globaltalk-models`.
  `argostranslate` is not in `pip list` at all, and `/dev/stdout` + `/tmp` paths in
  `test_golden_call.py:62` and `:86` are POSIX — **the golden call cannot run on this
  native Windows Python without WSL and a model download.**

Local package availability: `piper-tts 1.8.0`, `faster-whisper 1.2.1`, `ctranslate2 4.8.1`,
`onnxruntime 1.27.0`, `livekit 1.1.5`, `livekit-agents 1.5.6`, `torch 2.9.1` are installed;
`argostranslate`, `kokoro`, `fasttext` are not.

---

## 4. Dependency / deployment map

```
                      DEPLOYED ARTIFACTS
  render.yaml:9  rootDir: services/api  ->  start.sh:9  uvicorn app.main:app      [TREE A]
  vercel.json    api.root: services/api, entrypoint app.main:app                  [TREE A]
  infrastructure/docker/Dockerfile.api:22,29  APP_MODULE=app.main:app, WORKDIR /app/services/api [TREE A]
  docker-compose.yml:96  uvicorn app.main:app                                     [TREE A]
  docker-compose.yml:121 worker runs globaltalk.workers                            [TREE B ← mixed]

                      DEV ARTIFACTS
  Makefile:23 / scripts/run_dev.sh:7   uvicorn globaltalk.main:app --port 8000     [TREE B]
  run_api.py:19,24                     app.main:app, PORT default 8088            [TREE A]
  apps/web/vite.config.ts:27,37-45     proxy target 8088                           [TREE A only]

                      TEST ARTIFACTS
  tests/realtime/test_golden_call.py:87,94  PYTHONPATH=apps/api; globaltalk.main:app  [TREE B]
  tests/unit/test_globaltalk_*              imports globaltalk.*                        [TREE B]
  tests/unit/test_translation_pipeline.py   imports app.realtime.session_manager        [TREE A]
  tests/integration, root tests/*_hardened  services/api conftest (tests/conftest.py:14-15) [TREE A]

                      AI PROVIDER LAYER — three coexisting `gt_ai` trees
  gt_ai/                (121K)  standalone SDK: types, exceptions, http_client, voice
  ai/gt_ai/             (316K)  engine used by run_api.py (AI_DIR inserted last → wins)
  services/api/gt_ai/   (611K)  engine used by tests + Docker/Render; has extra
                                stt/recognizer.py and translation/translator.py (diff -rq)
```

Verified resolution inside the real pytest environment (temporary probe file, since deleted):

```
gt_ai                        -> repo/services/api/gt_ai/__init__.py
gt_ai.registry               -> repo/services/api/gt_ai/registry.py
app.main                     -> repo/services/api/app/main.py
globaltalk.realtime.audio_pipeline -> repo/apps/api/globaltalk/realtime/audio_pipeline.py
ai.bootstrap                 -> repo/ai/bootstrap.py
```

**Conclusion:** under pytest, everything resolves inside this repo (the two conftests insert
the right paths). Under `python run_api.py`, `gt_ai` resolves to `ai/gt_ai` while tests and
production use `services/api/gt_ai` — two divergent copies of the same package name.

---

## 5. Ranked bug list (evidence first)

### P1-1 — Same translated TTS chunk is delivered over TWO channels, and the two channels can never deduplicate each other — `static-confirmed`

`services/api/app/realtime/pipeline.py:680-690` broadcasts each streamed chunk as JSON
`tts.chunk` with `audio_base64`; `:697-703` immediately sends the *same* `audio.data` as a
binary frame — to the identical `audio_listeners` set. Frontend handles both:
`MeetingRoom.tsx:624` (`enqueueWav(b64ToBytes(audio), \`tts-${uid}\`)`) and
`MeetingRoom.tsx:349` (`enqueueWav(new Uint8Array(frame.pcm), \`tts-${frame.shortId}\`)`).

The tags are provably different strings, so no cross-path dedup is possible:

| path | producer | consumer | resulting tag |
|---|---|---|---|
| binary | `pipeline.py:659` `…[:16].ljust(16, "\x00")` (NUL pad) | `ws.ts:41` `.replace(/0+$/,"")` strips ASCII `"0"`, not NUL | keeps NULs (`abc…\x00\x00`) |
| JSON | `pipeline.py:685` `u_id` sliced in `MeetingRoom.tsx:622-623` | — | keeps hyphens (`abc-def-…`) |

Tree B does **not** duplicate: translated audio is JSON base64 only
(`apps/api/globaltalk/realtime/audio_pipeline.py:632-637`); `BinaryFrame.encode_tts`
(`protocol.py:86`) is never called from application code (only
`tests/unit/test_core.py:101`, `tests/unit/test_globaltalk_realtime_dev_mode.py:112`).

### P1-2 — `AudioPlayer.enqueueWav` deletes queued chunks that share a tag; both call sites pass no sequence or chunk index — `static-confirmed`

`apps/web/src/lib/audio.ts:249`:
```ts
this.queue = this.queue.filter((q) => q.tag !== tag);
```
Both TTS call sites call `enqueueWav(bytes, tag)` with **no `opts`**
(`MeetingRoom.tsx:349`, `MeetingRoom.tsx:624`), so `audio.ts:237-238` defaults
`sequence = 0`, `chunkIndex = 0`; the sort at `audio.ts:261-265` then degenerates to
arrival order. Consequence for a multi-chunk streamed utterance: every chunk that arrives
while earlier chunks are still queued **erases those earlier chunks**. Combined with P1-1
(same audio arriving on two channels) the listener hears scrambled, truncated, or no
translated speech while captions still render correctly — which matches the reported
"translated speech is not being heard" exactly.
`synthesize_stream` yields one chunk per sentence (`gt_ai` kokoro/dev_tone providers), so
multi-chunk utterances are the normal case, not an edge case.
*Needs runtime repro:* measure how many chunks a real utterance produces on the deployed
provider, and confirm the queue length before/after the filter.

### P1-3 — The flagship end-to-end test validates a different codebase than the one that ships — `static-confirmed`

`tests/realtime/test_golden_call.py:87,94` boots `globaltalk.main:app` (Tree B, `apps/api`),
while `render.yaml:9` + `start.sh:9` deploy `app.main:app` (Tree A, `services/api`).
Tree A's duplicate-delivery behaviour (P1-1) therefore has **no automated coverage**, and a
green golden job proves nothing about production. It additionally skips locally (§3).

### P1-4 — This machine's Python interpreter has editable installs pointing at an *older copy of the project outside the repo* — `static-confirmed`

```
__editable__.globaltalk_api-0.1.0.pth   -> C:\Users\acer\3D Objects\globaltalk-ai\services\api
__editable__.gt_ai-0.1.0.pth            -> C:\Users\acer\3D Objects\globaltalk-ai\ai
__editable__.desi_python-2.1.0.pth      -> C:\Users\acer\3D Objects\globaltalk-ai\sdk\python\desi-python
```
(plus `pip list` rows `globaltalk-api 0.1.0`, `gt-ai 0.1.0` at those paths).
Outside pytest — where `conftest.py:9-10` / `tests/conftest.py:14-15` do the path insertion —
plain `python` resolves `gt_ai.base` **into that stale tree**. Any ad-hoc script, migration,
or manual server start run from this machine can silently execute the wrong code.
pytest and `run_api.py` were verified NOT to hit it (§4). Fix before Phase 1 triage, or
triage results are untrustworthy.

### P1-5 — Dev workflow boots the dead tree on a port the frontend never talks to — `static-confirmed`

`Makefile:23` / `scripts/run_dev.sh:7` → Tree B on **8000**; `apps/web/vite.config.ts:27,37-45`
proxies to **8088**; `JoinCall.tsx:40,45` and `PhoneCallingTab.tsx:391` hardcode
`ws://127.0.0.1:8088`. `run_api.py:24` reads `PORT` (default 8088) while `.env.example` defines
`API_PORT` (8000), which nothing reads. `make dev` therefore starts a backend the UI cannot reach.
`run_api.py:19` also force-sets `APP_ENV=development`, so the production secret validator
(`services/api/app/config.py:214-245`) never runs on the dev entrypoint.

### P2-6 — Environment contract drift between code and both `.env` examples — `static-confirmed`

Read by code but absent from `.env.example` / `.env.production.example`:
`STT_PROVIDER` (only in `render.yaml:45`), `STT_HTTP_URL`, `TRANSLATION_MODEL`, `DEEPL_API_KEY`,
`DEEPL_API_URL`, `MT_HTTP_URL`, `MT_HTTP_STYLE`, `TTS_MODEL`, `TTS_HTTP_URL`,
`LANG_DETECT_PROVIDER`, `FASTTEXT_LID_MODEL`, `FALLBACK_DATABASE_URL`, `BCRYPT_ROUNDS`,
and (prod only) `LIVEKIT_ENABLED`, `LIVEKIT_PUBLIC_URL`.
Name mismatch: examples define `ACCESS_TOKEN_TTL_MINUTES` / `REFRESH_TOKEN_TTL_DAYS` while
`services/api/app/core/security.py:74-80` reads `JWT_ACCESS_TTL_MINUTES` / `JWT_REFRESH_TTL_DAYS`.
Present in examples but never read by the deployed tree: `KOKORO_MODEL_PATH`, `KOKORO_VOICES_PATH`,
`DB_AUTOCREATE`, `API_BASE_URL`, `STORAGE_BACKEND`.
`docker-compose.yml:15-16,22-24` sets `SECRET_KEY`, `JWT_SECRET`, `LIVEKIT_API_SECRET` and S3
credentials **as literal inline values** (values not printed here). No secret values were read or
logged during this audit.

### P2-7 — Provider failover silently substitutes dev stubs, including in production — `static-confirmed`

`services/api/app/ai.py:173-232` fails over MT→`dev_echo`, STT→`dev_text`, TTS→`dev_tone`
(`:200-215`) rather than raising; `is_dev_mode` (`ai.py:374-390`) documents that in production
a missing model file yields a stub that still enables `transcript.inject`. A meeting can look
healthy while no real translation or voice exists (guide lead E).

### P2-8 — Binary-frame format contradicts its own documentation — `static-confirmed` (code is right, docs are wrong)

`docs/REALTIME.md:15-23` and `apps/api/globaltalk/realtime/protocol.py` describe the `'T'`
payload as *raw PCM16 mono 16 kHz*; Tree A actually embeds **WAV** bytes
(`pipeline.py:694-696` comment, `:697` `bin_frame = bin_header + audio.data`), and the
frontend correctly decodes it as WAV (`MeetingRoom.tsx:343-348`). Guide lead C is not a live
bug on the JSON path — `decodeAudioData` (`audio.ts:248`) resamples, so sample-rate mismatch is
effectively ruled out. The wire *contract text* is wrong in two places and must be corrected so
Phase 2's typed contracts are built on accurate docs.

### P2-9 — Tree A failure events and fan-out broadcast violate the documented degradation contract — `static-confirmed`

- TTS failure emits a generic `error` `code="tts_unavailable"` (`pipeline.py:727-733`) where
  `docs/REALTIME_PRODUCTION.md:98` promises captions continue + explicit TTS failure; Tree B does
  it correctly (`audio_pipeline.py:586-600` → `quality.degraded`, captions-only).
- `translation.final` is broadcast with **no `to`** (`pipeline.py:607-614`) — every listener
  receives every target language — and re-broadcast under `TRANSLATION_SEGMENT_FINAL`, which no
  client handler exists for.
- Native listeners in `audio_mode: "translated"` get no original relay
  (`session_manager.py:248` mode filter) unless LiveKit is connected, contradicting
  "original relay always available" (`docs/REALTIME.md:88-89`).
- `latency.report` is broadcast untargeted (`pipeline.py:756-759`); `stt_first_partial_ms` is
  declared (`protocol.py:153-166`) but never assigned, so every report carries a 0.

### P3-10 — Smaller, real, catalogued

- Tree B `capture_ms` (`audio_pipeline.py:332`) is a raw `perf_counter` second-delta, never ×1000 → reported latency is ~1000× too small on that field.
- Frontend **playback** has zero test coverage: `apps/web/src/lib/__tests__/protocol.test.ts` only decodes frames; nothing asserts `AudioPlayer` ordering or once-only chunk playback.
- CI (`ci.yml`) never runs Playwright E2E (`tests/e2e`), the 19 root `tests/*_hardened.py`, or `tests/deployment` — 9 deployment tests and all security-hardened tests are local-only.
- `docker-compose.yml` mixes Tree A (`:96`) with Tree B modules (`:121`).
- `node v26`, `python 3.14` locally vs CI's `python 3.11`.

---

## 6. Guide leads A–E — verdict

| lead | verdict | evidence |
|---|---|---|
| A. Dual JSON + binary TTS paths duplicate audio | **CONFIRMED statically on Tree A** (deployed); Tree B's binary TTS path is inert | §5 P1-1 |
| B. Same-tag queue replacement drops earlier chunks | **CONFIRMED statically**; aggravating factor is that no `opts` is passed on either call site | §5 P1-2 |
| C. Format mismatch PCM16 vs WAV by transport | **PARTLY** — payload is WAV everywhere and handled correctly; the *documentation and Tree B's frame docstring* are wrong. Rate/container mismatch ruled out by `decodeAudioData` | §5 P2-8 |
| D. AudioContext suspended / autoplay blocked | **PLAUSIBLE, needs runtime** — `AudioPlayer` is constructed inside a `React.useEffect` (`MeetingRoom.tsx:315`) → context may start suspended; `audio.ts:317` `await this.resumeContext()` inside a `void this.playNext()` chain (`audio.ts:267`) turns a rejected `resume()` into an unhandled rejection that also poisons later enqueues. `resumeContext` is only gesture-triggered in `toggleMic` (`MeetingRoom.tsx:747`) | §5 P1-2 note |
| E. Connected meeting ≠ translation health | **CONFIRMED statically** — dev-stub failover | §5 P2-7 |

Root-cause ranking for "translated speech is not being heard", highest first:
**B (chunk replacement) → A (dual delivery, same audio twice, un-dedupable tags) → D (blocked/suspended context) → server-side stale-drop/skip → rate mismatch (ruled out).**
B and A are the same defect surface: the queue keys don't encode (utterance, sequence, chunk), so the two channels fight each other.

---

## 7. Risky files identified for Phase 1 (do not touch before the branch decision)

1. `apps/web/src/lib/audio.ts:231-330` — queue semantics, cancel API, playback lifecycle.
2. `apps/web/src/pages/MeetingRoom.tsx:315-355, 605-632` — the two TTS call sites.
3. `apps/web/src/lib/ws.ts:38-48` — binary frame decode.
4. `services/api/app/realtime/pipeline.py:653-710` — dual TTS delivery; choose one canonical path.
5. `services/api/app/realtime/session_manager.py:167-182, 238-252` — routing + original relay gating.
6. `tests/realtime/test_golden_call.py` — currently validates the wrong tree; POSIX-only on this host.
7. Two divergent `gt_ai` engines (`ai/gt_ai` vs `services/api/gt_ai`) + a stale out-of-repo editable install.

Provider notes: MT = argos (missing locally) / DeepL or online (needs keys); TTS = piper (installed,
voices need download) / kokoro (not installed) / dev_tone stub; STT = faster-whisper (installed,
weights need download). Credentials were not read.

## 8. Phase 0 exit-gate status

- [x] audit report — this file
- [x] baseline results saved — §3, verbatim counts
- [x] risky files and providers identified — §7
- [x] dependency diagram — §4
- [x] ranked bug list with evidence — §5
- [ ] **branch created** — deliberately NOT done; see §9
- [ ] correlation-ID triage run (guide lead E / "required triage output") — Phase 1, needs two live browser sessions

## 9. Blocker for Phase 1 entry (needs your decision)

The guide says to branch `feat/four-agent-realtime-translation`; your standing instruction is to
keep using `fix/share-link-p2p-default-camera`, and that branch currently holds 5 unmerged commits
plus uncommitted work. Also decide whether the Phase 1 fix targets **Tree A** (what Render actually
serves) or **Tree B** (what `make dev` and the golden test use) — the two need different code.
The P1-4 stale editable installs should be cleared before any runtime triage.
