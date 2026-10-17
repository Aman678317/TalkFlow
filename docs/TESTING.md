# Testing

```bash
make test            # everything the Makefile knows about (unit + integration + realtime)
make test-unit       # tests/unit        — pure logic, no models needed
make test-integration# tests/integration — FastAPI + real DB/storage/queue
make test-realtime   # tests/realtime    — golden multilingual call (needs weights)
cd apps/web && npx vitest run && npx tsc -b

# The Makefile does NOT cover these two — CI runs them, so run them too:
APP_ENV=test CACHE_BACKEND=memory REDIS_URL="" JWT_SECRET=<32-char test value> \
  python -m pytest tests -q -rs --ignore=tests/unit --ignore=tests/integration \
  --ignore=tests/realtime                    # 121 hardening + deployment + runner tests
cd tests/e2e && npx playwright install --with-deps chromium
#   then, with a Tree A API on :8088 and Vite on :5173 (see tests/e2e/playwright.config.ts):
WEB_URL=http://localhost:5173 npx playwright test
```

## Layers

- **Unit** (tests/unit): security primitives (hashing, JWT types, refresh rotation
  material, webhook HMAC), RBAC matrix, rate-limit parsing, protocol frames (binary
  layout round-trips), MIME sniffing, translatable detection, glossary enforcement,
  TM hash normalization, embedding determinism, billing config, script-heuristic LID,
  extractive summarizer determinism.
- **Integration** (tests/integration): full app via TestClient — auth lifecycle
  (signup/login/refresh-rotation/replay-rejection/logout), password reset, tenant
  isolation (cross-org 404s), viewer RBAC, TM exact-hit path, history, API-key auth +
  metering + rotation/revocation, document pipelines (TXT + DOCX structural rebuild:
  headings/tables preserved), upload validation (mislabeled binary rejected), meeting
  lifecycle, webhook CRUD, search scoping, health/ready/components honesty, real-MT gate
  (`@pytest.mark.model`, auto-skips without weights, asserts Devanagari output and
  no `untranslated_fallback`).
- **Realtime golden call** (tests/realtime/test_golden_call.py): live uvicorn server,
  5 WebSocket participants, REAL Piper-synthesized Hindi/English speech fed as PCM16:
  canonical transcript fan-out, per-listener translation + real TTS audio (WAV decoded
  and length-checked), same-target dedup (exactly one en translation row), Marathi
  honest degradation (`translation.failed` recoverable + user_message), original-audio
  binary relay, multilingual chat + per-listener chat translation, reconnect with
  `session.resumed` + monotonic replay, live preference updates, AI summary from the
  stable transcript.
- **Browser journeys** (`tests/e2e`, Playwright + Chromium, run by CI's `browser-e2e`
  job against a live Tree A API on :8088 and Vite on :5173 with `dev_text`/`dev_echo`/
  `dev_tone`): the golden demo opens **two distinct browser sessions** in one meeting —
  a Hindi speaker plus an anonymous guest joining over the share link — injects a turn
  over the real WebSocket, and asserts the source caption reaches both while the English
  translation appears on the listener's screen and is **absent** from the speaker's.
  Also covers the document upload pipeline and signup→translate→history→re-login.
  What it does **not** prove: real microphone capture (speech is injected through the
  dev `transcript.inject` channel with a fake media device), audible playback on a
  remote seat (assertions are on captions), or any real provider's translation quality.
  See `docs/PRODUCTION_VERIFICATION_REPORT.md` §4.
- **Realtime conversation gate** (tests/integration/test_realtime_phase3_gate.py): the
  composed Tree A path — real `MeetingPipeline`, real `SessionManager` routing, real wire
  protocol, four real agents — with only the providers faked. Four tests, one per exit
  clause: back-and-forth speech (two speakers, two listeners, each direction delivered in
  full), interruption (barge-in flushes exactly the interrupted correlation, the cancelled
  run stops where it stopped and leaves no gap/duplicate/queue behind, the next turn plays
  complete), caption alignment (source and translated captions of one turn carry the same
  segment/seq/`start_wall_ms`/`duration_ms`, and the timeline comes from the measured turn,
  not arrival order), and per-stage latency, printed with `-s`:
  `APP_ENV=test python -m pytest tests/integration/test_realtime_phase3_gate.py -q -s`.
  Those millisecond figures are pipeline overhead plus fake providers. Provider-side
  numbers with real weights used to exist only for the second backend tree
  (`apps/api`, run by `tests/realtime/test_golden_call.py` and `bench_latency.py`);
  the deployed `services/api` tree now has its own golden call
  (`tests/realtime/test_deployed_tree_golden_call.py`, marked `realtime`) which runs
  on real engines wherever the weights are present — that is CI's `realtime-golden`
  job, and it **skips with its prerequisites named** on any machine without them.
  Until such a run is recorded here, production latency for this path is unmeasured.
  A green tick here is not a listening check either — only two browsers with two
  microphones can prove a conversation feels natural.
- **Voice benchmark** (`python scripts/bench_tts_voices.py --lang en,hi,ur`): the Phase 3
  requirement to *benchmark target-language TTS voices*. Measures, per
  (language, provider, voice), time-to-first-audio, real-time factor, produced audio
  length and peak amplitude, against sentences taken from the golden translation dataset.
  Needs model weights; without them it is still the right tool, because it reports every
  voice it could not measure and *why* — three different answers that must never be
  confused: the file is absent, the provider is installed but cannot start (on Windows
  this is `onnxruntime` failing to find the Visual C++ runtime), and the language has no
  voice to offer at all. Tamil, Gujarati and Kannada are in that last category for both
  shipped providers, so speech output for them is not a tuning problem. `passed_gates`
  is false for all three; none of them is a skip and none is a score.
  Covered in CI by `tests/unit/test_tts_voice_bench.py`, which runs the harness against a
  fake provider so the arithmetic and the honesty rules hold on a machine with no weights.
- **Frontend** (apps/web): vitest on the binary protocol decoder, API error contract
  normalization, base64 audio round-trip; `tsc -b` strict gate in CI.
- **Failure tests** (section 56): provider-down paths are covered by the passthrough/
  fallback unit tests + golden-call Marathi degradation; Redis-down ⇒ cache fallback
  warning path exercised in every test run; DB/Storage failure ⇒ `/ready` 503 semantics.

## Conventions

- Tests never mock the DB — real SQLite file, fresh per session, seeded.
- Model-dependent tests carry `@pytest.mark.model` / the realtime mark and SKIP cleanly
  when weights are absent (CI downloads them in a dedicated job).
- Assertions check *honesty invariants*: no silent passthrough as "translation",
  synthetic audio always flagged, derivatives always carry source references.
