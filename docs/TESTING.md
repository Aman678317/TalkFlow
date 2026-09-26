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
