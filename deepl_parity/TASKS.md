# TalkFlow → DeepL Parity — Per-agent task lists (A3, Oct 25 2026)

Companion to ARCHITECTURE.md. **Rule:** every file below is owned by exactly one agent; shared files
(`app/main.py`, `app/config.py`, `app/db/models.py`, `alembic/*`) are edited **only by B1**. All paths relative to
repo root unless prefixed. DoD per task = code + tests pass + honesty gates respected (no fake provider claims).
Statuses of commands: `make test-unit`, `make test-integration`, `cd services/api && python -m alembic upgrade head && python -m alembic check`,
`cd apps/web && npx tsc -b`, `python scripts/verify_ai_stack.py --quick` (Windows-safe).

## B1 — Core: translate + write + context + integration lane

**Owns:** `services/api/app/routers/v2_v3.py`, `app/services/translation_service.py`, `app/services/write_service.py`,
`app/services/context_service.py`(new), `app/services/quality_eval_service.py`(new), `app/db/models.py`, `app/config.py`,
`services/api/alembic/versions/<rev>_deepl_parity_upgrade.py`(new), `app/main.py`.

| Task | Files | Functions to write (signatures) | Consumes | DoD |
|---|---|---|---|---|
| B1.1 base tables + config | models.py, config.py, alembic rev | `ProviderCredential`, `ProviderCredentialEvent`, `VoiceSession` models; `Document` columns `document_key_hash,one_shot,billed_characters,format_code`; config fields per ARCHITECTURE §b (3) | existing Mixins | `alembic upgrade head` + `alembic check` pass (SQLite) |
| B1.2 ContextAgent | context_service.py | `compose(db, org_id, *, context="", style_profile_id=None, glossary_ids=[], target_lang)->ContextDirective`; `assert_compatible(context, glossary_ids)` → 400 | StyleProfile, glossaries (B2 resolver later) | unit: mutual-exclusion 400; compose merges style profile instructions ≤10×300 |
| B1.3 translate engine upgrade | translation_service.py | extend `TranslateContext` fields (context/glossary_ids/model_type/tag_handling/non_splitting_tags/split_sentences/preserve_formatting); in `translate_text(db,text,source,target,ctx)`: tag protect/reinject, glossary multi-id priority apply, formality prefer_* resolution, follow-up `quality_eval_service.evaluate_segment` when `enable_quality_evaluation` | gt_ai registry/`text_ops` | unit: batch ≤50 (51 → 400), ≤128 KiB (over → 413), `model_type_used` echo, glossary pairs applied, MCP-guard: no network when offline |
| B1.4 CorrectionAgent | write_service.py | `apply_style_tone(text, *, target_lang, writing_style, tone, source_lang=None)->WriteResult`; enums + prefer_ resolution; LLM path via existing neural hook (`llm_http_url`), offline rule path unchanged | write_service internals | unit: `prefer_more` on unsupported target → applied default; rephrase vs correct behavior difference; en detection |
| B1.5 QAAgent | quality_eval_service.py | `evaluate_segment(source,target,*,src_lang,tgt_lang,ctx)->QualityReport`; `is_configured()->bool` | heuristics + optional LLM | unit: untranslated-token + empty-output detected with spans; offline path deterministic |
| B1.6 v2_v3 glue (P2) | v2_v3.py | `/v2/translate` full param surface (see ARCHITECTURE §c), `/v2/write/rephrase|correct`, `/v2/document*` delegates to B2 `document_deepl`, `/v2/usage` → B2 `usage_service.products`, `/v3/voice/realtime` delegates to B4 `voice_session`, `/v3/glossaries*` delegates to B2 `glossary_v3_service`; migrate `HTTPException(detail=…)` → `AppError` shaped `{message, code}` | B2/B4 services (typed imports) | integration tests green; route list unchanged (no dup paths) |
| B1.7 registration + honesty scan | main.py, final pass | register `providers.router`, `ws.voice_ws.router`; route-conflict check: no route registered twice; `is_configured()` gates honored everywhere | — | app boots (`python run_api.py`), `/api/docs` lists new routes |

Interfaces B1 consumes: `provider_vault.resolve` (B2) via explicit parameter on `TranslateContext.provider_key` after P1;
`voice_session.create_session`, `document_deepl.create_job/poll/download`, `glossary_v3_service.*`.

## B2 — Secure vault + documents API + usage metering

**Owns:** `app/services/provider_vault.py`(new), `app/services/glossary_v3_service.py`(new), `app/services/document_deepl.py`(new),
`app/services/usage_service.py`, `app/routers/providers.py`(new).

| Task | Files | Functions to write | Consumes | DoD |
|---|---|---|---|---|
| B2.1 vault crypto | provider_vault.py | `_fernet()`, `encrypt_secret/decrypt_secret`, `mask(key)->"****"+last4`, key-file bootstrap with 0600 perms | `cryptography` Fernet (already pinned) | unit: roundtrip; wrong SECURITY_SECRET_KEY → decrypt raises; masked format |
| B2.2 vault ops+audit | provider_vault.py | `save/rotate/set_status/delete/resolve/test_connection`, writes `ProviderCredentialEvent` per op; plaintext never in logs | B1 models | unit: rotate replaces ciphertext; deactivate hides from `resolve`; audit rows written |
| B2.3 keys router | routers/providers.py | routes + Pydantic models `ProviderKeyIn/KeyOut/RotateIn/TestOut` per ARCHITECTURE §b (5); RBAC org-scoped (reuse `require_permission` pattern) | B2.2 | integration: create→list masked→rotate→deactivate→delete; 404 unknown id; key never serialized |
| B2.4 document flow | document_deepl.py | `create_job(db,*,file,filename,mime,target_lang,source_lang,formality,glossary_ids,output_format,org_id)->{document_id,document_key}`; `poll(...)` status `queued/translating/done/error` + `seconds_remaining`; `download(...)` one-shot; `billed_for(format,chars)`: `max(chars,50000)` for docx/doc/pptx/xlsx/pdf, otherwise exact chars; 429 when >20 undownloaded; uses `document_service.parse_*/reconstruct_*` + queue/task dispatch; srt/vtt via B4 `subtitles_service`; PDF→`output_format=docx` best-effort via docx writer (fpdf2 fallback txt) | document_service, usage_service, subtitles_service | unit: 50k min math; one-shot second call → 404 `document_not_found`; hash-only key stored; status transitions |
| B2.5 usage products | usage_service.py | `products(db, org_id)->list[ProductUsage]`; read current ledger (characters, audio_seconds→speechToText minutes ceil, tts_seconds→speechToSpeech only when >0) | UsageLedger | unit: minutes ceil; conditional speechToSpeech row; translate character count |
| B2.6 glossary v3 service | glossary_v3_service.py | `parse_entries` (TSV+CSV w/ quoting), `validate_entries` (duplicate source → 400), `check_size` (10 MB/entry ≤1024 B), `upsert_dictionary/merge_dictionary` (PATCH=merge, PUT=replace), `resolve_terms(db,org,glossary_ids)->priority list` | B1 models | unit: TSV/CSV parse; duplicate 400; merge vs replace semantics; resolve priority order + variant fallback |

Interfaces B2 consumes (B1-provided in P2): models `ProviderCredential/VoiceSession`/Document columns; `get_current_*` deps;
document parsers. B2 does **not** edit v2_v3.py/main.py/config.py/models.py.

## B3 — Web UI (apps/web)

**Owns:** `apps/web/src/pages/ProviderKeys.tsx`(new), `pages/Documents.tsx`(CH), `pages/Glossaries.tsx`(CH),
`pages/Subtitles.tsx`(new), `pages/Voice.tsx`(CH), `components/ContextStylePanel.tsx`(new),
`components/AlternativesPopover.tsx`(new), `src/lib/api/deepl.ts`(new), `src/App.tsx`(routing only — no conflicts; sole editor of App.tsx).

| Task | Files | Behavior | Consumes | DoD |
|---|---|---|---|---|
| B3.1 API client | lib/api/deepl.ts | typed wrappers for §c routes; `ApiError{message,code,status}` mapping; multipart helper for documents | backend | tsc clean |
| B3.2 ProviderKeys page | ProviderKeys.tsx | table (provider,label,`****1234`,status,created), add/rotate/delete/deactivate dialogs, test-connection badge (`reachable`/`not_configured` honest) | `/api/v1/providers/keys*` vitest mock | component test: masked render, no plaintext anywhere |
| B3.3 Context & Style panel | ContextStylePanel.tsx | context textarea (counter, 2000 cap), formality select (default/more/less/prefer_*), writing_style/tone selects, custom instructions editor (≤10×300); emits fields consumed by Translate + Write pages | state lift | unit: prefer_* options render; validation blocks >10 instructions |
| B3.4 Documents page | Documents.tsx | accept pdf/docx/pptx/xlsx/txt/html/srt/vtt/md/json; upload → `{document_id,document_key}` (key kept client-side), status chip polling (`queued/translating/done/error` + seconds_remaining), billed_characters display, one-shot download (button flips to "downloaded" after 1 call) | B3.1 | component test: polling states + one-shot disable |
| B3.5 Glossary manager | Glossaries.tsx | per-pair dictionaries list, TSV/CSV textarea import with client-side duplicate-source pre-check (server 400 surfaced otherwise), export download, active toggle | `/api/v3/glossaries*` | component test: import preview + toggle |
| B3.6 Subtitles mode | Subtitles.tsx | connects via Voice session, renders `concluded[]` timeline + `tentative[]` ghost, export `.srt/.vtt/.txt/.json` (client-side serializer mirrors B4) | WS events | test: renders updates in order, export formats byte-sane |
| B3.7 Voice mode | Voice.tsx | POST session → `wss` → 250 ms mic chunk loop (`source_media_chunk`), PlayTTS on `target_media_chunk`; **fallback**: on WS failure/session error → existing realtime pipeline path (current Voice flow), banner explains | `/api/v3/voice/realtime` | test: fallback path on session 503 |
| B3.8 Alternatives popover | AlternativesPopover.tsx | shows `translations[].alternatives` chips; **component returns null (hidden) when field absent** (offline honest) | translate response | test: hidden without alternatives, visible with |

Interfaces B3 consumes: exact §c contracts; no direct external provider domains ever.

## B4 — Realtime voice protocol + subtitles ingestion

**Owns:** `app/realtime/voice_ws.py`(new), `app/realtime/voice_session.py`(new), `app/realtime/protocol.py`(CH),
`app/realtime/agents/translation.py`(hint-slot only), `app/services/subtitles_service.py`(new).

| Task | Files | Functions to write | Consumes | DoD |
|---|---|---|---|---|
| B4.1 session service | voice_session.py | `VoiceSessionConfig`, `parse_content_type(ct)` (s16le/rate params), `create_session(db,request,principal,cfg)->{session_id,streaming_url,one_time_token,…}` (one-time ticket, ≤5 targets, ≤1 target_media, rate guard 24000), `CadenceGovernor.inspect(chunk_bytes, chunk_span_s)->None` raises `ChunkCadenceError`, `bill(db,session_id,source_seconds,tts_seconds)` ceil minutes | B1 VoiceSession model, usage_service | unit: caps → error; token single-use; minutes ceil; tts metered only when target_media |
| B4.2 protocol members | protocol.py | add 2 ClientEventType + 4 ServerEventType members (exact DeepL strings), typed `TranscriptSegmentUpdate{text,start_time:int_ms,end_time:int_ms}` helper, event builders used by voice_ws | — | unit: roundtrip JSON; legacy clients unaffected (old events identical) |
| B4.3 voice WS adapter | voice_ws.py | `@router.websocket("/v3/voice/realtime/connect")`: token consume → decode chunks (b64, ≤100 KB, ≤1 s, ≤2× realtime Governor) → pipeline audio path → emit `source/target_transcript_update` {concluded[], tentative[]} deduped by segment id → optional single-language `target_media_chunk` flow → `end_of_stream`; errors `{error:{error_message,code}}`; 3 cadence strikes → close 1008; on end-of-stream bill session | pipeline, session_manager, protocol, voice_session | realtime test (needs models, `-m realtime`): synthetic PCM in → concluded+tentative out, TTS buffer out when configured, cadence violation → error ×3 close |
| B4.4 transcript hint slot | agents/translation.py | accept optional `context_directive` in the translate step (prepended provider hint; no protocol change) | context_service | unit: hint present ⇒ provider receives combined instruction; absent ⇒ unchanged |
| B4.5 subtitles ingestion/export | subtitles_service.py | `parse_srt/parse_vtt(data)->list[SubtitleCue]`, `serialize_srt/serialize_vtt(cues, translations)->bytes` (cue sync preserved), `export_transcript(cues,fmt)` | document_deepl (B2), Subtitles page (B3) contract | unit: parse→serialize roundtrip keeps cue count + timings; vtt cue sync |

Interfaces B4 consumes: B1 `VoiceSession` model + `one_time` ticket verification (`app.security.verify_session_ticket` style);
B2 B3 consumers listed above. B4 does not touch v2_v3.py; the `POST /v3/voice/realtime` glue remains B1 calling B4's
`create_session`.

## B5 — Tests + benchmarks + docs scorecards

**Owns:** all `tests/unit/test_*deeply-named.py` files listed, `tests/integration/test_*` files listed,
`scripts/verify_ai_stack.py` (CH), `README.md` (capability table only), `replica/features.csv`, `replica/parity.md`,
`replica/test-plan.md` — per BENCHMARK_FILL_PLAN.md (exact edits specified there; B5 executes).

| Task | Files | To add | DoD |
|---|---|---|---|
| B5.1 unit battery | tests/unit/`test_v2_translate_parity.py` (batch caps, model_type echo, context exclusion, glossary_ids ≤5, show_billed_characters, tag_handling preserve), `test_write_style_tone.py`, `test_context_service.py`, `test_quality_eval.py`, `test_provider_vault.py` (roundtrip/mask/rotate/audit), `test_document_deepl.py` (50k, one-shot, statuses), `test_glossary_v3.py` (TSV/CSV/dup/merge-vs-replace), `test_usage_products.py`, `test_voice_cadence.py`, `test_subtitles_service.py` | FastAPI TestClient or pure-function units; no net; SQLite fixtures per conftest | `make test-unit` green incl. new; no flaky sleeps (timeouts via fakes) |
| B5.2 integration battery | tests/integration/`test_translate_docs_flow.py` (upload srt→poll→one-shot download→usage rows show billed ≥50000), `test_provider_keys_flow.py` (full CRUD + masked list + test-connection offline honest), `test_voice_session_flow.py` (POST session → token single-use via WS adapter fake), `test_usage_endpoint_parity.py` (products[] shape) | real app via create_app | `make test-integration` green; `alembic upgrade head`+`check` pass before suite (ordered fixture) |
| B5.3 benchmarks + verify | scripts/verify_ai_stack.py additions per BENCHMARK_FILL_PLAN.md; README rows; replica scorecards recompute | honest statuses only (`PASS`/`NOT_CONFIGURED`/`OPTIONAL`) | `python scripts/verify_ai_stack.py --quick` parity rows appear; scorecards updated with verification strings |
| B5.4 e2e notes | none (Playwright needs docker stack; B5 documents exact commands + expected states in replica/test-plan.md rows marked auto=no if gated) | — | notes reviewed by A3 |

Interfaces B5 consumes: everything above read-only; B5 never edits product files — bugs found → report back to owning agent.
