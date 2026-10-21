# Testing

```bash
make test            # everything
make test-unit       # tests/unit        — pure logic, no models needed
make test-integration# tests/integration — FastAPI + real DB/storage/queue
make test-realtime   # tests/realtime    — golden multilingual call (needs weights)
cd apps/web && npx vitest run && npx tsc -b
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
  numbers with real weights exist only for the second backend tree (`apps/api`, run by
  `tests/realtime/test_golden_call.py` and `bench_latency.py`); the deployed
  `services/api` tree has no real-provider latency harness yet, so production latency
  for this path is still unmeasured. A green tick here is not a listening check either —
  only two browsers with two microphones can prove a conversation feels natural.
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
- **Translation fan-out benchmark** (`make benchmark-translation`): an offline,
  deterministic scheduler benchmark for one utterance sent to eight target languages.
  It runs the former serial orchestration as a control and the production
  `TranslationAgent.fan_out` implementation against the same delayed fake provider,
  reporting per-run samples, medians, p95, speedup, and observed parallel calls. It
  does not download model weights or call a network service.
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
