# DeepL Parity — Scorecard Fill Plan (A3, Oct 25 2026)

Executed by **B5** (owner) in P3, after B1–B4 land. All assertions must be backed by a real run (honesty rule of
`scripts/verify_ai_stack.py`: PASS only when probed successfully; `NOT_CONFIGURED` for un-set env lanes; never a silent claim).

## 1. README — "✅ Verified Capability Status (CPU Sandbox)" table

Append 8 rows after the existing rows (status column contains the exact verify string B5 puts there once the named check
passes; placeholder `⏳` until then).

| Capability row (exact text) | Status string to verify | Backing check |
|---|---|---|
| DeepL-shaped `/v2/translate`: batch ≤50 & ≤128 KiB, `model_type_used` echo, `context`, tag_handling, formality prefer_*, glossary_ids ≤5 priority | `✅ (tests/unit/test_v2_translate_parity.py)` | make test-unit |
| Write rephrase/correct with DeepL writing_style/tone enums + prefer_ fallbacks; multilingual via LLM when configured, rule-engine offline | `✅ (tests/unit/test_write_style_tone.py)` | make test-unit |
| Documents async 3-call flow: document_id/document_key, status polling, one-shot download, 50,000-char min billing, .srt/.vtt sources, PDF→docx best-effort | `✅ (tests/integration/test_translate_docs_flow.py)` | make test-integration |
| Glossaries v3: per-language-pair dictionaries, TSV/CSV entries, PATCH=merge / PUT=replace, ≤5 glossary_ids priority | `✅ (tests/unit/test_glossary_v3.py)` | make test-unit |
| Voice realtime session (`/v3/voice/realtime` → session_id + wss streaming_url + one-time token) + DeepL WS protocol (concluded/tentative, cadence guards, optional single-target TTS) | `✅ (tests/realtime + test_voice_cadence.py)` | make test-realtime |
| `/v2/usage` products metering: translate characters + speechToText/speechToSpeech minutes (conditional) | `✅ (tests/unit/test_usage_products.py)` | make test-unit |
| Provider credential vault: Fernet-encrypted at rest, org-scoped keys routes, masked responses, audit log, browser→proxy guard | `✅ (tests/integration/test_provider_keys_flow.py)` | make test-integration |
| Context-aware translation: `context` param (unbilled) + style_profile_id + ≤10×300 custom instructions fused into one directive | `✅ (tests/unit/test_context_service.py)` | make test-unit |

Rule: a row stays `⏳ (pending: <agent>)` if its backing test fails at time of writing; never remove the test, fix or mark honestly.

## 2. replica/features.csv — extension rows

Existing table keeps its 19 rows. Append after row 20 (columns: `feature,area,priority,original,clone,notes`):

```csv
"DeepL-shaped batch translate (model_type echo, context, tag_handling, formality)",translation,must,yes,yes,"v2_v3.py /v2/translate upgraded; tests/unit/test_v2_translate_parity.py"
"Writing assistant style/tone enums (rephrase + correct)",writing,must,yes,yes,"write_service.apply_style_tone; DeepL enums + prefer_ fallback"
"Async document translation flow (3-call, one-shot download, 50k min billing)",documents,must,yes,yes,"services/document_deepl.py on Document model + document_service parsers"
"Glossaries v3 dictionaries (per pair, TSV/CSV, merge/replace, ≤5 ids)",glossaries,should,yes,yes,"services/glossary_v3_service.py + v2_v3 glue"
"Voice realtime session + DeepL WS protocol + one-target TTS",voice,must,yes,yes,"realtime/voice_session.py + voice_ws.py protocol adapter"
"Usage endpoint with products metering (characters + STT/STS minutes)",api,should,yes,yes,"usage_service.products()"
"Provider key vault (encrypted, rotated, masked, audited, proxy-only)",developer,should,yes,yes,"services/provider_vault.py + routers/providers.py + ProviderKeys page"
"Context-aware agent (context param, style profile, custom instructions)",translation,should,yes,yes,"services/context_service.py feeding translate/write/documents/realtime"
```

Total rows become 27. `clone` column set only after the backing test listed in `notes` passes.

## 3. replica/parity.md — area scores recompute

Scores = (done counted features / counted features) × 100 per area with the 8 new rows folded in. Recompute and rewrite
the "By area, weakest first" list; new/affected area buckets: `translation`, `writing`, `documents`, `glossaries`, `voice`,
`api`, `developer`. Header line becomes `## Parity: <recomputed total> / 100` where total = mean over counted areas'
weights same as current generator logic (keep script of record: parity numbers derive from features.csv clone flags —
only update prose after CSV flags flip). "Missing, in build order" section then lists remaining honest gaps:
- Alternatives in UI hidden when offline (engine-gated) — item stays until LLM key configured.
- PDF→docx conversion best-effort (fpdf2/docx writers only) — stays flagged.
- Voice TTS limited to installed cached voices (kokoro/en + mapped voices) — stays flagged.
- Speech-to-speech minutes only metered when `target_media_languages` configured — note stays.

## 4. replica/test-plan.md — new case rows

Append to the case table (`case|flow|type|steps|expected|auto|result`; keep `17/17 PASS` line recomputed as `25/25 PASS`):

| case | flow | type | steps | expected | auto | result |
|---|---|---|---|---|---|---|
| v2-batch-caps | translate | unit | POST /api/v2/translate text[] with 51 items | 400 validation_error | yes | (fill by B5) |
| v2-model-echo | translate | unit | model_type=quality_optimized | translations[].model_type_used=quality_optimized | yes | |
| v2-context-exclusion | translate | unit | context + glossary_ids together | 400; context alone → translations unaffected + not billed | yes | |
| v2-tags | translate | unit | tag_handling=html + non_splitting_tags=span | tags preserved in output | yes | |
| write-enums | write | unit | writing_style=prefer_business, tone=prefer_friendly | improvements[] returned; fallback applied silently | yes | |
| doc-three-call | documents | integration | upload srt → poll → result | statuses queued/translating/done; one-shot; second download 404 | yes | |
| doc-bill-min | documents | unit | 200-char docx upload, done | billed_characters=50000 | yes | |
| doc-unused-quota | documents | integration | >20 undownloaded uploads | 429 document_download_limit_reached | yes | |
| gloss-dicts | glossaries | unit | PATCH merge then PUT replace | merge appends; replace drops stale entries; entries export TSV | yes | |
| gloss-dup | glossaries | unit | duplicate source lines in one dictionary | 400 duplicate_source | yes | |
| voice-session | voice | integration | POST /v3/voice/realtime then reconnect with token twice | second token use rejected | yes | |
| voice-cadence | voice | realtime | send 3 oversized chunks | error events then close 1008 | yes | |
| voice-tts | voice | realtime | target_media_languages=[es] with TTS provider | target_media_chunk frames arrive; usage tts metered | yes | |
| usage-products | api | unit | GET /v2/usage after STT minutes recorded | products[] includes speechToText row; speechToSpeech only when tts_seconds>0 | yes | |
| keys-crud | developer | integration | create/rotate/deactivate/delete key | masked response only; audit rows; deactivated not resolved | yes | |
| keys-guard | developer | integration | frontend-origin sim of direct provider call | no route exists (proxy guard); CORS denies non-owned origins | yes | |
| context-agent | translation | unit | /v2/translate with context + style_profile_id whose custom_instructions=localhosts | directive built; 400 on >10 instructions | yes | |
| qa-report | translation | unit | enable_quality_evaluation=true | quality.issues[] with severity+span; offline heuristic truthful | yes | |
| subs-export | documents | unit | parse .vtt, translate cues, serialize | cue timings preserved | yes | |

`result` column filled by B5 (PASS/FAIL + script name); `auto=yes` only for runnable-here commands (unit/integration);
Playwright-dependent cases stay `auto=yes` only if docker stack available, else `auto=no` with the exact manual command.

## 5. scripts/verify_ai_stack.py — additions

Extend the probe list (after existing records; same `record(component, status, note, hint)` helper; **no network in
--quick**, secrets never printed):

| Component probe (order) | Logic | Statuses possible | Hint text |
|---|---|---|---|
| `provider-vault` | instantiate `_fernet()` against configured/derived key material; roundtrip `encrypt_secret("x")` in-memory; count `ProviderCredential` rows for boot org (import-safe when tables missing → FAIL w/ alembic hint) | PASS (roundtrip ok), NOT_CONFIGURED (no SECURITY_SECRET_KEY and no key file yet → derived-local note), FAIL | "set SECURITY_SECRET_KEY or run make migrate" |
| `v2/document` | import `document_deepl` + parser coverage set; assert billed math `billed_for("docx", 100) == 50000`; dict of supported input formats | PASS (pure checks) or OPTIONAL (full pipeline needs `make test-integration`) | "full flow: make test-integration::test_translate_docs_flow" |
| `v3/voice-session` | `voice_session.parse_content_type("audio/pcm;encoding=s16le;rate=16000")` roundtrip + `CadenceGovernor.inspect` rejection test in-process | PASS, FAIL | "realtime lane needs MODEL_CACHE_PATH + weights (make test-realtime)" |
| `usage-metering` | `usage_service.products()` against ephemeral SQLite fixture: characters + audio_seconds/tts_seconds ceil minutes; conditional speechToSpeech row | PASS, FAIL | "ledger rows come from real traffic; zero rows is honest" |
| `provider-resolver` (folded into provider-vault note) | `resolve(org,"deepl")` returns None with no creds → translation falls back to local models; env `DEEPL_API_KEY` still honored when vault empty | NOT_CONFIGURED (expected default), PASS (key resolved), | "add keys via /api/v1/providers/keys or env" |

Run wiring: probes auto-run in current `--quick` mode; final table keeps per-row print format
`status component note -> hint`. Keep the exact
`OPTIONAL` constant name so ruff on the `scripts` lane stays clean. Also: parity additions must not break `python scripts/verify_ai_stack.py --quick` exit code
(FAIL rows still allowed as long as each prints its hint; exit code semantics unchanged from today).

## 6. Execution order for B5

1. Land unit battery → fix nothing itself; bounce defects to owning agent (B1 translate/write/context, B2 vault/docs/usage, B4 voice/cadence).
2. Run integration battery with `make migrate` precondition; fill test-plan.md `result` cells.
3. Update features.csv flags → re-run parity generator → rewrite parity.md prose section.
4. Append README rows with the verify-string statuses from §1.
5. Extend verify_ai_stack.py; run `python scripts/verify_ai_stack.py --quick` and paste the 4 new component lines into build-log.md.
6. Final re-read of honesty: every "yes" in features.csv `clone` column cites a test path in `notes`.
