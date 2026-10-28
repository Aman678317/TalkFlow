# Translation acceptance — the pair-matrix record

Created day-3 (2026-10-23), as the output the 30-day roadmap names for the
language-pair work (`docs/30-DAY-ROADMAP.md`). Every claim here points at a
pin that fails if the claim becomes false. Nothing here is marketing.

## The source of truth

`services/api/gt_ai/capabilities.py::DEFAULT_LANGUAGES` — 20 languages with
**independent** per-capability statuses
(`EXPERIMENTAL < BETA < SUPPORTED < PRODUCTION`) and the provider names that
serve them. The database (`language_capabilities` table, seeded at startup)
is the runtime truth; the module is the seed and the code-level mirror. A
language is never "fully supported" just because a model claims it.

## How each surface serves a pair

| Surface | Pair gate | Reference |
|---|---|---|
| Canonical text (`/api/v1/translate`) | `validate_pair` — target must exist in the registry and not be `EXPERIMENTAL`; glossary mismatch surfaces as `glossary_note` | `app/services/translation_service.py:110-132` |
| Realtime meeting pipeline | same service gate per segment; echo/empty results re-fail and flag `untranslated_fallback` instead of shipping | `app/realtime/agents/translation.py:60-163` |
| Documents | per-segment failure keeps the segment **missing** so the quality gate fails the job honestly (never "ready with source text") | `app/services/document_service.py:612-648` |
| Phone bridge | registry check at **call creation** (both sides), then the bridge's own per-segment degradation; detected-language override is carried in-bridge | `app/telephony/call_service.py`, `app/telephony/bidirectional_bridge.py:241-289` |
| v2/v3 compatibility surface | registry-derived language lists; formality claimed only where `FORMALITY_RULES` exist (de / es / fr) | `app/routers/v2_v3.py` |
| Frontend pickers | filter on `*/supported` booleans from `/api/v1/languages` (the registry) | `apps/web/src/hooks/useLanguages.ts` |

## What is NOT servable today (recorded honestly)

- **Speech output (TTS)** is claimed only where the registry's BETA+ voice
  coverage matches an actual voice adapter: kokoro's voice set covers
  en / hi / ja / zh / es / fr / de / pt; `mr`, `bn`, `ta`, `te`, `gu`, `kn`,
  `ml`, `pa`, `ur`, `ar`, `ru`, `ko` stay `EXPERIMENTAL` (dev/http adapter
  until a validated voice exists). Captions remain available for all.
- **Formality** is a real transformation today only for **de / es / fr**
  (the language set of `FORMALITY_RULES` in `gt_ai/translation/neural_online.py`).
- The v2 compat surface no longer advertises Latin / Esperanto / Amharic or
  any of the other ~80 unservable codes; `la` (beta) and `sa` (external)
  surface **only** behind an explicit `?include=beta,external` query flag —
  never in the default list.
- Diagnostics (`/ready?diagnostics=true`, `/api/v1/system/diagnostics`)
  report the pair matrix **derived from the registry** (hub-and-spoke
  `en<->X` for every translation-supported language) and never load model
  weights to do it.

## Degradation contract (what a client sees when a pair cannot be served)

- `422` with `unsupported_language` when a requested language is not in the
  registry: at **call creation** on the phone lane (before any provider or
  meeting work) and at request time on the canonical surfaces. The v2
  compatibility surface keeps its DeepL-shaped contract and answers the
  degraded item honestly instead: `text: ""` + `untranslated_fallback`.
- A provider that fails, or answers with the source text again, is treated as
  a failed attempt: the response carries `untranslated_fallback` (realtime)
  or `text: ""` + `untranslated_fallback` (v2 compat) — never a fabricated
  translation, never the source labelled translated.
- Private-only promises are never silently downgraded (`gt_ai/types.py:121-128`,
  pinned by `tests/test_private_only_guarantee_hardened.py`).

## Verification pins (evidence, not claims)

- `tests/unit/test_readiness_diagnostics.py::test_the_diagnostics_pair_matrix_is_the_capability_registry`
  — the diagnostics matrix is the registry, not a frozen sample.
- `tests/test_v2_v3_surface_auth_hardened.py` (day-3 honesty block) — the v2
  language list serves only registry languages, formality is claimed only
  where rules exist, a real provider result is never replaced by the
  dictionary, and a failed provider answers with a flag, not a fabrication
  (both `/v2/translate` and `/v2/desi/translate`).
- `tests/unit/test_translation_pipeline.py` (day-3 echo-guard tests) — the
  guard compares text even when the source is unknown; an all-echo chain
  fails closed on Latin-script targets exactly where the old guard leaked.
- `tests/test_outbound_idempotency.py::test_a_call_in_an_unregistered_language_is_rejected`
  — the phone lane validates both languages at creation.
- `tests/unit/test_document_parallel_batching.py::test_a_failed_segment_never_ships_as_its_own_translation`
  — a failed segment stays missing and the document does not claim ready.
- `tests/integration/test_desi_compatibility.py::test_v3_languages_and_resources_conformance`
  — the compat surface's shape contract holds (registry-derived lists,
  `la`/`sa` only behind explicit include).

## Day-3 plan checklist (30-DAY-ROADMAP §Day 3 vs shipped PR #132, 2026-10-23)

| Plan item (Day 3) | Status | Evidence |
|---|---|---|
| Deterministic language-pair matrix (en↔hi, hi↔en, en↔mr, code-switch→en, one unsupported pair) | **PASS for the matrix itself** (registry-derived, 20 languages, 38 hub pairs, diagnostics mirror); **partial** for the raw-input matrix cases — en↔hi pinned end-to-end, en↔mr pinned at registry/diagnostics level, code-switch (Hinglish) cases are open and belong to the day-6 string sweep | `TRANSLATION_ACCEPTANCE.md` + `tests/unit/test_readiness_diagnostics.py`, `tests/integration/test_desi_compatibility.py` |
| One unsupported pair behaves honestly | **PASS** | phone `xx`/`zz` → 422 (`test_a_call_in_an_unregistered_language_is_rejected`); v2 `XX` → `text:""` + `untranslated_fallback` |
| Test provider-down and timeouts | **PASS** (existing pins + new) | chain deadline failover (`tests/test_provider_chain_hardened.py`), all-echo chain fails closed (`tests/unit/test_translation_pipeline.py`), failed provider → honest flag (`tests/test_v2_v3_surface_auth_hardened.py`) |
| Results record source/target, provider/model, latency, flags, fallback status | **PASS** | `TranslationResult` carries `source_lang/target_lang/model/provider/latency_ms/quality_flags` (`gt_ai/types.py:44-57`); v2 items surface `quality_flags`/`untranslated_fallback`; realtime events carry per-segment provenance |
| Never a false "success translation" | **PASS** | the 10 red proofs → echo guard, v2 fabrication removal, dictionary provenance, document segment honesty (`docs/ARCHITECTURE_OWNERSHIP.md` B-7…B-10, O-13, O-14) |
| Launch-plan Day-3: record unsupported pairs + disabled features | **PASS** | this document's "What is NOT servable today" section |
| Launch-plan Day-3: full clean-browser sign-off journey | **OPEN** (documented scope exclusion) | API-path truth proven live on localhost (:8000) this PR; the browser journey is the launch sign-off exit checklist, scheduled with the staging deployment round |

## Localhost verification (2026-10-23, live, canonical backend on :8000)

Boot contract per `scripts/run_dev.sh` (`#130`): canonical backend
(`app.main:app`, PYTHONPATH `services/api:apps/api:ai:.`), API :8000. Probes
against the running server through the product's real HTTP stack (traces and
output below are verbatim):

- `GET /health` → `200` `{"status":"ok","version":"0.1.0",…}`.
- `GET /readyz` → `{"ready":true,"checks":{"database":true,"cache":true,
  "queue":true,"storage":true}}` — the readiness probe reports
  **infrastructure**, it does not claim AI readiness.
- `GET /ready?diagnostics=true` → `diagnostics.status="degraded"` (no
  production provider configured — honest), `tasks.mt.healthy=false`,
  `language_pairs.supported_count=38`, `languages=` all twenty registry
  codes (**bn, ta, te, gu, kn, ml, pa, ur, pt, ar, ko included** — they were
  invisible in the frozen pre-repair matrix).
- `GET /api/v1/system/diagnostics` → same registry-derived matrix
  (`en->hi`, `hi->en`, … `en->ko`, `ko->en`, 38 pairs), `overall="degraded"`.
- `GET /api/v1/languages` → 20 registry entries.
- `GET /v2/languages?type=target` → exactly the 20 registry codes
  (EN,HI,MR,BN,TA,TE,GU,KN,ML,PA,UR,JA,ZH,ES,FR,DE,PT,RU,AR,KO);
  `supports_formality` only for ES,FR,DE; no Latin/Esperanto/Amharic.
- `GET /v2/glossary-language-pairs` → 38 registry-hub pairs (EN <-> every
  other registry language), not the frozen ten-language list.
- `POST /v2/translate` (`"hello world"`, EN→DE) →
  `{"text":"Hallo Welt","quality_flags":["dev_provider","neural_mt"]}` —
  a real translation with explicit provenance flags; no `"[DE] text"` tag,
  no unflagged dictionary swap.
- `POST /v2/translate` (EN→`XX`, unregistered target) →
  `{"text":"","untranslated_fallback":true}` `200` — the honest empty
  degradation in the DeepL-shaped contract, nothing fabricated.
- `POST /v2/desi/translate` (en→hi) →
  `"नमस्ते दुनिया"` with `"translated_by":"dictionary"` — the phrase
  dictionary announces itself.

Authed mutation probes (call creation against the registry, 422 mapping) are
pinned deterministically in `tests/test_outbound_idempotency.py`; visible
degradation here is recorded above.


## Day-4 plan checklist (30-DAY-ROADMAP §Day 4 — model router, provider health, configuration, 2026-10-23)

Audit of the canonical router/chain/health surface
(`gt_ai/model_router/router.py`, `app/ai.py`, `app/routers/health.py`,
`scripts/verify_ai_stack.py`) found and fixed four truths the stack was
getting wrong. Everything here is pinned in
`tests/test_day4_provider_config_hardened.py` (14 tests — 13 from the audit
plus the DEV-inject payload pin added with `bd993cb`).

| Finding (day-4 audit) | Status | Evidence |
|---|---|---|
| `dev_echo` — the private-classified final hop — forwarded non-canned text to the public MyMemory/LibreTranslate endpoints via `neural_online` and relabelled the cloud result `provider=dev_echo`, `neural_mt` | **FIXED** | the smuggle is removed; a cache miss is flagged passthrough (`untranslated_fallback`+`dev_provider`), a canned hit is flagged `phrase_table` — never `neural_mt`; the online provider is asserted-never-called (`test_dev_echo_never_calls_the_online_provider`) |
| Canonical HF-weight root split: `scripts/download_models.sh` provisions `MODEL_CACHE_PATH/hf` (HF_HOME), while the canonical adapters loaded with `download_root=MODEL_CACHE_PATH` — a provisioned host reported NOT_CONFIGURED and would re-download | **FIXED** | `app.config` pins `HF_HOME=MODEL_CACHE_PATH/hf` at settings load; faster-whisper/madlad400 no longer override the HF root (`test_provider_kwargs_do_not_override_the_hf_root`); local proof: whisper probe flipped NOT_CONFIGURED → PASS on the existing provisioned cache |
| `make verify-ai-stack` probed the LEGACY lane (`ai/providers/*` + apps/api `globaltalk` config), not the deployed `services/api/gt_ai` tree | **FIXED** | script rewritten against `app.ai`/`gt_ai` — 16 probes, every non-PASS row names the setting/command that flips it, quick mode runs import+filesystem only; no secrets or URLs in output |
| `/api/v1/system/diagnostics` collapsed configured / available / supported / production-validated into one `healthy` boolean | **FIXED** | per-task diagnostics now carry `supported_languages` and `validated_pairs` from the loaded registry specs (`test_diagnostics_report_supported_languages_and_validated_pairs`); secrets asserted absent from the payload |
| Router coverage filters (`validated_pairs`, `languages`) are decisive only while another candidate survives them; the last-resort ladder reintroduces a filtered-out candidate when nothing else remains | **PINNED (documented behavior)** | the provider adapter rejects an unvalidated pair at execution time and the chain fails over honestly; pinned by `test_last_resort_ladder_reintroduces_a_filtered_candidate` so any change is deliberate (revisit for day-7 quality gates) |
| faster-whisper's default `vad_filter=True` needs `onnxruntime`, which no requirements file pins (the meeting pipeline segments with `gt_ai.vad`, not the STT-internal VAD) | **RECORDED** | probe reports honest NOT_CONFIGURED with the install hint; adapter-default decision deferred to day 9 (speech detection/segmentation) |
| Post-fix CI exposure: `webrtc-smoke` guest-flow failed deterministically because the DEV inject payloads were phrase-table **misses** in the now-offline `dev_echo` (`नमस्ते दुनिया।` with trailing danda, `Hello, world.`, `The meeting starts at 3pm.`, `你好世界。`) — an honest flagged passthrough that the realtime translation agent refuses to ship, so chip `mt` never reached ok | **FIXED** | all four payloads (+ comma-greeting inverse, zh→hi/zh→en coverage) added as real offline `phrase_table` entries (`bd993cb`); pinned red→green by `test_dev_echo_serves_every_dev_inject_payload_offline` with a keep-in-sync note against the MeetingRoom inject panel; webrtc-smoke **PASS** run 39885304046 (5m45s), full CI success run 39885303973 |

Verification (this workstation, 2026-10-23): `verify_ai_stack.py` full run
exit 0 — 16 probes, 4 ok (router, GPU profile, STT weights, dev-fallback
honesty), 12 not configured with actionable hints, 0 failed. Local suites:
`test_day4_provider_config_hardened.py` (13), `test_provider_chain_hardened`
+ `test_private_only_guarantee_hardened` + `tests/unit/test_ai_layer.py`
(69), `test_model_fetch_gates_hardened` + `test_argos_cache_dir` (26),
`test_realtime_translation_invariant_hardened` (13) — all green. The
day-3 localhost record above predates the dev_echo flag change: a canned
`/v2/translate` hit now reports `phrase_table` where it reported
`neural_mt` (same text, honest provenance).

## Post-Push CI observation (2026-10-23)

`gh pr checks --watch` on PR #134 showed:

| Check | Pre-avg_logprob fix | Notes |
|---|---|---|
| backend | pass | |
| migrations | pass | |
| frontend | pass | |
| docker | pass | |
| realtime-golden | **pass** (re-check on `bd993cb`) | avg_logprob fix confirmed — CI run 39885303973 green (migrations, frontend, realtime-golden, backend, docker) |
| webrtc-smoke | **pass** after root-cause fix on `bd993cb` (run 39885304046, 5m45s) | the "environment gap" reading above was **wrong and is corrected here** (not waved away): chip `mt` never reached ok because post-day-4 offline `dev_echo` returns an honest flagged passthrough on a phrase-table miss — which `agents/translation.py` refuses to ship as a translation — and the DEV inject payloads were misses; fixture drift previously masked by the removed cloud delegate, not a WS-bridge/compose gap. Fixed by offline phrase-table entries + a pinned inject contract (see the day-4 table above) |
| Vercel Preview Comments | pass | |

This matches the roadmap rule: "A failing required gate blocks release." Update (2026-10-23, `bd993cb`): both gates now pass on CI — realtime-golden inside run 39885303973 (all five jobs) and webrtc-smoke run 39885304046 (browser smoke ✓, guest-flow/livekit lanes green). The BLOCKED note above is superseded, not waived: the failure was root-caused offline with a red→green hardened pin — fixing the real inject-fixture defect instead of re-running against a wrong environment guess.

## Clean browser journey sign-off record (2026-10-23)

Live browser journey against `localhost:5173` (`apps/web` dev) → API `127.0.0.1:8000`
(`services/api` canonical, SQLite `data/globaltalk.db`), on the day-4 working tree
(1162276). Recorded per-step: PASS with evidence / FAIL / documented exclusion.

| Step | Status | Evidence |
|---|---|---|
| Signup → dashboard | PASS | `POST /api/v1/auth/signup` 201; dashboard renders "Welcome back, Asha 👋 · Day3JourneyWorks · FREE · 20 realtime-ready languages"; user `b15c9e93…`, org `3af00ab9…`; translations(30d)=11 counter later serves journey DB rows |
| Login (UI, email+password) | PASS | pre-restart + re-verified post-restart on the restored DB (API login 200, user id matches signup); password policy enforced |
| Text translate (text path) | PASS (honest-unavailable locally) | UI refuses to render any `dev_*|untranslated_fallback|echo`-flagged output (`isUsableTranslation`, `apps/web/src/lib/translation.ts:71`) and shows "Translation provider is unavailable or not configured. Please retry." in a no-keys environment; API envelope carries honest provenance/flags |
| private_only egress promise | RED PROOF (pre-#134) → FIXED by PR #134 | replay with `intent:"private_only"` on dictionary-impossible text produced fluent German in 1688 ms with flags `[neural_mt, high_quality, dev_provider]` — text egressed to a public online MT service through the `dev_echo`→`neural_online` delegate, contradicting the facade promise ("the content was not sent to any external service"). PR #134 removes the path (offline-always `dev_echo`: miss=`passthrough`, canned hit=`phrase_table`) |
| Write / grammar (AMPL Refine) | PASS | `POST /api/v1/write` 200 local rule engine, 27–39 ms, improved text + 8 changes; alternatives panel renders |
| Translation memory | engine PASS / list UI FAIL | create memory + entry both 201; TM-hit engine proof `provider=translation_memory, model=tm/exact, flags [tm_exact_match]`; TM page still renders "Memory is empty" while the response carries data (list-render bug, open) |
| Documents | PASS (metadata mismatch noted) | upload `.docx` → 202 → status `ready` (2 segments, 1 page, target hi) → real Hindi segment text → download 200 valid DOCX; `model_version` says `madlad400` while the chain log shows madlad400 excluded — metadata-vs-reality mismatch finding |
| History | PASS | 11 records, honest per-row engine labels; micro-texts ("hlo my") detected CS by fasttext auto-detect |
| Meeting create/join (host) | PASS | meeting 2026-10-22 session: `Connected · Realtime Translation Active`; city chips Link/Mic/STT/MT/Voice render; member-specific honesty: "Browser Microphone Permission Blocked" (no capture in harness) = documented exclusion |
| Guest join ("Add to call", anonymous) | PASS | second tab joins by name without login; participant prefs persisted (AUTO/en, translated captions, ducking 0.3) |
| Two-way realtime caption fan-out | **NOT ACHIEVABLE (documented exclusion, this session)** | (i) the canonical lane is healthy: a raw WS client on `/ws/realtime?ticket=<join rt_url>` connects and holds, first frame = session payload (meeting id, participant id, display name); (ii) the in-room SPA uses `/ws/meetings/{id}?ticket=` — server accepts then closes <1 s, 272 cycles logged, guest shows "Connection lost — reconnecting" (pre-restart day-3 tree joined/stayed fine → day-4 regression candidate on the SPA signalling lane); (iii) host-alone inject shows honest `Translation Unavailable · no_targets`; (iv) when the bounded recovery gives up, the room exits via `homeFromMeeting()` → `nav('/meetings?end=<id>')` → meetings page silently `POST /api/v1/meetings/{id}/end` 200 — **a leave/exit path also ends the meeting for everyone** (leave-vs-end conflation finding; no `meeting.ended` audit row) |
| Captions / language preferences (UI) | PASS (room selectors) | pre-join selects honored (`AUTO / hi` accepted then ws give-up; re-join `AUTO / en`); in-room strip "I speak: AUTO ➔ Hear: English"; DB `participant_preferences` + users `speak_lang/hear_lang` columns are the persisted truth; style registry rows carry a misleading "(custom)" label for global seed profiles (org_id=None) |
| Reconnect | NOT DEMONSTRABLE (documented exclusion) | API restarts during the session cause honest "Connection lost — reconnecting" but every SPA-lane reconnect cycles (see two-way row) — reconnect recovery can be observed, not confirmed |
| Leave meeting | PASS-with-finding | explicit end POST observed (`POST …/end` 200); seats marked left, room view exits; **but the same exit path is reachable by "leave/back" intent (conflation above)** — a plain participant leave should not end the meeting |
| Sign out | PASS | dashboard "Sign out" → `/login` ("Welcome back / Sign in to GlobalTalk AI") |

### Session-environment findings (boot contract, 2026-10-23)

| Finding | Status | Evidence |
|---|---|---|
| API DB path is CWD-relative (`sqlite+aiosqlite:///./data/globaltalk.db`); a uvicorn booted from the workspace root (not repo root) silently creates a FRESH seeded DB | **RECORDED (boot-contract trap)** | wrong-CWD boot produced: login of the pre-existing user → 401 "Invalid email or password" (user never existed in the fresh DB), then a duplicate-email signup → 201 (no row to reject); both artifacts vanish once the boot CWD is repo-root (bcrypt hash of the original row verified `checkpw=True`) |
| faster-whisper warmup crashes the process on CPython 3.14 (Windows): native heap corruption `0xC0000374` inside the concurrent lazy import chain (`sklearn.utils.fixes` → `pandas` → `dateutil`) triggered during provider warmup (faulthandler thread dump captured); every un-shimmed boot died ≤70 s with no app traceback | **RECORDED + env mitigation proven** | `sitecustomize.py` preload (imports sklearn/pandas/scipy/dateutil single-threaded before the app's warmup threads) → boot survived 8.5 min unattended under the same poller that killed every prior boot; all five imports also pass standalone |
| vite `detectBackendPort()` boot race (fallback 8088, never re-evaluated) | **RECORDED with live occurrence** | with no :8000 API alive at vite boot, the 5173 dev-server silently proxied ALL UI traffic to a stray `run_api.py` on :8088 (a different DB); symptom set: dashboard renders, list 404s, `POST /translate` lands on the wrong backend. Rebinding vite with `VITE_BACKEND_PORT=8000` fixed the session; the map-row already flags this |
| Duplicate-email signup silently 201s under the not-existing-row condition | covered by the boot trap above | honest behavior per-DB (row exists → 422), but a fresh/wrong DB yields a second usable account for the same email (id `b6ca01b1…` vs `b15c9e93…`); login then resolves an arbitrary duplicate row |

## Day-4 security, privacy and data-retention sign-off record (2026-10-23)

Execution of 30-DAY-ROADMAP §Day 4 on the launch-candidate tree (`b98cd47`,
`fix/day4-provider-health-config`, PR #134). Method: re-run every named
security surface that exists as a suite, audit the code paths the suites
cannot see (retention sweeps, deletion wiring, CSP/CORS config, log/telemetry
content, tracked-file secrets), fix what is deterministically fixable inside
the freeze rules, and RECORDED the owner-decision items — none disguised.

**Security re-run (local, SQLite lane, 82.4 s):** 157 passed across
`test_auth_hardened` · `test_auth_full_flow` (CSRF cookie/protection) ·
`test_tenant_security_extended` · `test_cross_tenant_security` ·
`test_v2_v3_surface_auth_hardened` · `test_social_auth_hardened` ·
`test_copilotkit_auth_hardened` · `test_realtime_security_hardened` +
`test_realtime_security` (WS authorization) · `test_production_security_hardened` ·
`test_production_readiness_hardened` · `test_telephony_webhook_security` ·
`test_storage_webhooks` · `test_retention_escalations` · `test_call_gate`
(consent/DNC/disclosure) · `test_telephony_privacy_abuse_gates` ·
`test_developer_platform_hardened` (api-key rate limiter, 429 + retry-after) ·
`integration/test_resilience_failures` (rate-limit fail-open on cache outage).

| Day-4 audit item | Status | Evidence |
|---|---|---|
| **Retention advertised schedules are never enforced** — `config` promises `retention_transcript_days` (365, "0 = forever") and the module docstring promises "audio goes first", but `sweep()` never touched transcripts: meeting transcript TEXT and each segment's per-segment `audio_object_key` lived forever, and the audio bucket with a `0` window swept EVERY audio object instead of none | **FIXED (`b98cd47`, red→green)** | new transcript buckets: text sweep deletes rows past the transcript window (stale non-final fragments included), translation fan-outs die with their source, transcript-audio keys age on the same audio schedule, keys orphaned by a row deletion are purged, meeting rows survive; `0` guarded to "forever" per the config's own contract. Pinned in `tests/test_retention_transcripts_hardened.py` (4 tests, id-scoped seeds + exact-row `finally` purge for the shared-DB lane) + the escalations counts-shape pin updated; retention + escalations suites 7 passed (22.5 s) |
| Deletion behavior | **PASS + RECORDED finding** | per-object deletion exists and is permission-gated (`DELETE contacts/{id}`, glossaries/TM/style-profiles, `DELETE /me/identities/{provider}`); transcript export is `principal.require("view_transcript")` + audited (`transcript.exported`). **RECORDED:** `delete_user_data`/`delete_org_data` exist in `retention_service.py` with ZERO callers — no GDPR-style anonymization endpoint is wired; owner decision needed (self-service account deletion vs delete-on-request flow) before public pilot |
| Standalone translation rows outlive their windows | **RECORDED (product decision)** | `TranslationSegment` rows with `segment_id NULL` (product text/document/chat — one-off history) are outside the transcript window by design decision, not retention fallout; document-derived rows also outlive their document's `expires_at` sweep. Owner call: should document/text history follow the document/usage schedules? |
| CORS / CSRF / security headers | **PASS + hardening note** | explicit origin allowlist (`settings.cors_origins` + narrow regex) + bounded methods + `allow_credentials=True`; CSRF middleware runs ahead of CORS; headers nosniff / HSTS (2y, includeSubDomains) / CSP (`default-src 'self'; frame-ancestors 'none'`; docs paths only excepted). **RECORDED (low):** the CORS regex allows any `*.vercel.app` origin with credentials — browser third-party/CSRF defenses mitigate, but pin exact preview domains |
| Upload validation | **PASS (pinned)** | `validate_upload` (app/storage.py) rejects executables/MIME mismatches and sanitizes `../../etc/passwd.pdf`; `malware_scan` hook wired; pinned in `test_storage_webhooks.py` |
| **Secret scan** | **CLEAN + RECORDED CI gap + hygiene executed** | CI has NO secret-scan step (only dummy `JWT_SECRET` values in `ci.yml`) — owner decision to adopt gitleaks/trufflehog. Local scan: 12 high-signal patterns (AWS AKIA, GitHub tokens, Stripe live keys, OpenAI/Anthropic-style keys, Slack tokens/hooks, Google AIza, private-key blocks, Twilio account SIDs, DeepL) over all 1 624 tracked files → **zero real credentials in source**; only hits were tracked tool/IDE artifacts (`.vs` index binaries, `.mimosa` hook state, `.specify` integration manifests — sha256 inventories; the Twilio-pattern hits are hash substrings). Verified clean individually: `apps/web/.env.production` (two public `VITE_*` URLs) and `plugins/desi-claude-plugin/.mcp.json` (env-var indirection, no embedded key). Hygiene committed `eb0234d`: 442 machine-local files untracked + ignore rules (`.vs/`, spec-kit local registry; `.mimosa/` was already ignored) |
| Logs / telemetry content | **PASS (+ 2 minor notes)** | no transcript text, tokens or credentials are logged anywhere (grep over all logging sites in `services/api/app`); realtime transcript delivery is the WS channel by design, not logs. Notes: 3 error paths log provider response bodies (`indic_server` `resp.text`, `twilio_token` `res.text` ×2) and `translate.py` logs transcription failure exceptions — error-path content only |
| Consent & user-visible indicators | **PASS** | telephony: recording **disabled by default**, two-party consent mandatory and un-disableable at graph build (`prompt_composer` L1 platform rule) — pinned by call-gate + telephony privacy/abuse suites; disclosure text surfaced in agent prompts. Meetings: **no recording surface exists** (grep clean) — captions/transcripts are the core feature, visible on screen to every participant by design; transcript retention now genuinely enforced (row 1 above) |
| Hourly sweep wiring | **PASS** | `_retention_loop` task in lifespan (`main.py:283`), sleeps 3600 s between sweeps, exceptions logged and never fatal |

**Owner actions & sign-off status (Updated 2026-10-27):**
- **R3 (Legal & Privacy Sign-Off):** CLOSED. Privacy notice, consent indicators, and subprocessor DPA terms reviewed and approved by Aman Shandilya (@Aman678317).
- **R4 (GDPR Deletion & Standalone Retention):** CLOSED. Implemented `DELETE /api/v1/auth/me` and `DELETE /api/v1/organizations/current` in `services/api`; configured `retention_translation_history_days` sweep; verified with `tests/test_gdpr_deletion_hardened.py`.
- **R5 (CI Secret Scan):** CLOSED. Pinned gitleaks v8.30.1 job in `.github/workflows/ci.yml`.
- **R6 (CORS Wildcard):** CLOSED. Production enforces exact origins (`allow_origin_regex=None`).

The Day-4 exit criterion ("no open critical/high security finding; legal/privacy review completed by responsible qualified reviewer") is fully satisfied and closed.







