# TalkFlow → DeepL Parity — Upgrade Architecture (A3, Oct 25 2026)

Reads: DEEPL_ANALYSIS.md (API spec), TALKFLOW_AUDIT.md (repo reality). Canonical lanes only
(`services/api/**`, `apps/web/**`, `tests/**`, `scripts/**`, `packages/**`). Legacy `apps/api` + `ai/` untouched.
**Central integration decision:** `app/routers/v2_v3.py` already hosts all `/v2/*`+`/v3/*` DeepL-shaped routes but with
stub-quality bodies (in-memory document store, instant `done`, no cadence guards). v2_v3.py is **one file owned by B1
only**; B2/B4 build-domain services that B1's thin handlers delegate to. No route-ordering tricks, no duplicate paths.

## a. System overview (upgraded pipeline)

```
            apps/web (React, Vite :5173)
  ProviderKeys.tsx  Documents.tsx  Glossaries.tsx  Subtitles.tsx  Voice.tsx
  Translate.tsx/Write.tsx ← ContextStylePanel / AlternativesPopover
        │  ALL calls same-host /api/* — browser NEVER hits DeepL/Azure directly
        ▼  (CORS allow list = own origin only; proxy guard enforced in middleware)
┌─────────────── services/api — FastAPI (make dev :8000) ───────────────────┐
│ routers:                                                                  │
│  v2_v3.py  (B1-owned, thin handlers → services below)                     │
│   ├ /v2/translate      → translation_service.translate_text              │
│   ├ /v2/write/rephrase|correct → write_service (+LLM hook, rule fallback)│
│   ├ /v2/document[...]  → document_deepl.py    (B2 service)               │
│   ├ /v2/usage          → usage_service.products()  (B2 metering)         │
│   ├ /v3/glossaries…    → glossary_v3_service.py                          │
│   └ /v3/voice/realtime → voice_session.py     (B4 service)               │
│  providers.py (new): /api/v1/providers/keys → provider_vault.py (B2)     │
│  realtime: ws.py (unchanged meetings WS) + voice_ws.py (new /v3…connect) │
│           └ DeepL WS protocol adapter → existing pipeline/agents loop    │
│ services (new/changed): translation_service, write_service,              │
│  context_service (ContextAgent), quality_eval_service (QAAgent),         │
│  provider_vault (SecureKeyAgent), document_deepl, glossary_v3_service,   │
│  subtitles_service, usage_service, document_service (reuse)              │
│ gt_ai providers: registry → nllb_ct2/madlad400/argos | azure | http |    │
│  dev_echo; stt whisper-CT2; tts kokoro | azure; detection fusion         │
│  credential resolution: env vars  <  provider_vault (org-scoped, Fernet) │
│ db (models.py, one Alembic rev by B1): ProviderCredential,               │
│  ProviderCredentialEvent, VoiceSession; Document + flow columns          │
└───────────────────────────────────────────────────────────────────────────┘
Realtime agents loop (unchanged spine): ListeningAgent → TranslationAgent
(← ContextAgent hint) → VoiceAgent(TTS) → supervisor; every provider call
passes inference_gate.slot() with per-stage deadline (StageDeadlineExpired).
```

Error body everywhere: `{"message": str, "code": str}` (existing `AppError` codes; `detail` strings in v2_v3 migrated to
this shape). Statuses reused: 400/401/403/404/413/429/456(quota)/500/503.

## b. Module map — NEW / CHANGED files (backend)

| # | Path (services/api/app/… unless `NEW`) | Owner | Purpose & key exports | Plugs into |
|---|---|---|---|---|
| 1 | `db/models.py` **CH** | B1 | `ProviderCredential(id, org_id, provider, ciphertext_b64, last4, label, status:"active"\|"deactivated", created_at, rotated_at)`, `ProviderCredentialEvent(id, org_id, credential_id, event, actor_user_id, detail, created_at)`, `VoiceSession(id uuid, org_id, meeting_id, status, source_media_content_type, target_languages_json, target_media_language, started/ended_at, source_seconds, tts_seconds)`; `Document` gains `document_key_hash:str, one_shot:bool=False, billed_characters:int=0, format_code:str` | one Alembic revision (below) |
| 2 | `alembic/versions/xxxx_deepl_parity_upgrade.py` **NEW** | B1 | `upgrade(): add tables + 4 Document columns; downgrade(): drop` | `make migrate`; `alembic check` must pass |
| 3 | `config.py` **CH** | B1 | `security_secret_key:str=""`, `provider_fernet_key_path:str="./data/provider_vault.key"` (0600), `api_batch_max_texts:int=50`, `api_batch_max_bytes:int=131072`, `context_max_chars:int=2000`, `voice_chunk_max_bytes:int=102400`, `voice_cadence_max_x:float=2.0`, `voice_cadence_window_s:float=1.0`, `document_min_billed_chars:int=50000`, `document_max_undownloaded:int=20`, `glossary_max_bytes:int=10_485_760`, `glossary_max_entry_bytes:int=1024` | every service reads via `settings` |
| 4 | `services/provider_vault.py` **NEW** | B2 | `class ProviderVaultError(AppError)`; `_fernet() -> Fernet` (derive from `security_secret_key` via `hashlib.sha256→Fernet`, else load-or-create key file mode 0600); `encrypt_secret(plain:str)->str`, `decrypt_secret(ct:str)->str`; `save(db,org_id,provider,key,label)->out`, `rotate(db,org_id,id,key)->out`, `set_status(db,org_id,id,active:bool)`, `delete(db,org_id,id)`, `mask(key)->"****"+last4`, `resolve(db,org_id,provider)->str|None` (active creds only, newest first); `test_connection(db,org_id,id)->{reachable:bool,provider_status:str}`; writes `ProviderCredentialEvent` on all ops | `routers/providers.py`; resolver consumed by translation/write/document services; **Fernet already ships with pinned `cryptography>=3.4` — no new dep** |
| 5 | `routers/providers.py` **NEW** | B2 | `router = APIRouter(prefix="/api/v1/providers/keys", tags=["provider-keys"])`; models `ProviderKeyIn(provider:str, key:str, label:str|None)`, `KeyOut(id,provider,label,masked_key,status,created_at)`, `RotateIn(key:str)`, `TestOut(reachable:bool,provider_status:str)`; routes `GET ""` list, `POST ""` 201, `POST {id}/rotate`, `POST {id}/activate`, `POST {id}/deactivate`, `DELETE {id}` 204, `POST {id}/test` | `main.py` registration (B1) |
| 6 | `services/context_service.py` **NEW** | B1 | `class ContextDirective(BaseModel): hint:str, glossary_terms:list[GlossaryPair], formality:str|None, style_note:str`; `async compose(db, org_id, *, context:str="", style_profile_id:str|None, glossary_ids:list[str], target_lang:str)->ContextDirective` — loads StyleProfile (custom instructions ≤10×300), resolves glossary terms, builds a single hint string; `assert_compatible(context:str, glossary_ids:list[str])` raises `ValidationError` (400) on mutual exclusion | translation_service, document_deepl, realtime TranslationAgent hint slot |
| 7 | `services/translation_service.py` **CH** | B1 | `TranslateContext` gains fields `context:str="", glossary_ids:list[str]=[], model_type:str="latency_optimized", tag_handling:str|None, non_splitting_tags:str|None, split_sentences:str="1", preserve_formatting:bool=False, context_directive:ContextDirective|None`; `translate_text(db,text,source,target,ctx)` applies: tag protection (extract/reinject XML/HTML non-splitting spans), split_sentences passthrough to provider `text_ops`, glossary multiplier across `glossary_ids` priority order, post-LM quality flags via `quality_eval_service` when enabled | v2_v3.py `/v2/translate`; realtime TranslationAgent |
| 8 | `services/quality_eval_service.py` **NEW** | B1 | `class QualityIssue(BaseModel): type:str, severity:"minor"\|"normal"\|"major", span_start:int, span_end:int, explanation:str`; `evaluate_segment(source:str,target:str,*,src_lang:str,tgt_lang:str,ctx)->QualityReport{overall_score:float,issues:list[QualityIssue]}` — offline heuristics (empty output, untranslated tokens, glossary misses, wrong-script detection); `evaluate_async(...)->` same via LLM (`llm_http_url` set) else heuristics; `is_configured()->bool` | `/v2/translate` `enable_quality_evaluation`-style opt-in flag="true"; write path |
| 9 | `services/write_service.py` **CH** | B1 | new `apply_style_tone(text, *, target_lang:str, writing_style:str, tone:str, source_lang:str|None)->WriteResult{improved_text, detected_source_language, applied_style, applied_tone}`; `prefer_` values resolve (`prefer_more→more→default`); LLM hook reuses existing `improve_text_async` neural tier when `llm_http_url` set; otherwise rule-engine path offline; `WILLING_STYLES/_TONES` + `TARGET_LANGS` DeepL enums | v2_v3.py `/v2/write/*` |
| 10 | `services/glossary_v3_service.py` **NEW** | B2 (service) | `parse_entries(raw:str)->list[tuple[str,str]]` (TSV `\t`, CSV `,` with quoting; reject >1024-B name/phrase); `validate_entries(entries)->None` raises `ValidationError`(400) on duplicate source (per dictionary); `check_size(entries)->` 10 MB guard; `upsert_dictionary(db, glossary, source_lang, target_lang, entries, mode:"replace")`; `merge_dictionary(db, glossary, …)`; `resolve_terms(db, org_id, glossary_ids:list[str])->list[GlossaryPair]` priority order, dedup, variant fallback (EN→en-US etc.) | v2_v3.py glossary routes (B1 glue), translation/`document_deepl` consumers |
| 11 | `services/document_deepl.py` **NEW** | B2 | `class DocFlowError(AppError)`; `async create_job(db, *, file:bytes, filename, mime, target_lang, source_lang, formality, glossary_ids, output_format, org_id)->{document_id,document_key}` (plain key returned once; store sha256 as hash; enforce ≥1 undownloaded-cap 429); `async poll(db, doc_id, document_key, org_id)->{status:"queued"\|"translating"\|"done"\|"error", seconds_remaining:int|None, billed_characters:int}`; `async download(db, doc_id, document_key, org_id)->BinaryResult` **one-shot** (second call → 404 `document_not_found`; row cleared); `billed_for(format, chars)->int` = `max(chars, 50000)` for docx/doc/pptx/xlsx/pdf, otherwise exact chars; srt/vtt via `subtitles_service`; PDF source → `output_format` docx/txt best-effort via `document_service` parsers + fpdf2/docx writer; records characters via `usage_service.record_usage` | v2_v3.py `/v2/document*` (B1 glue); `document_service` parse/reconstruct |
| 12 | `services/subtitles_service.py` **NEW** | B4 | `parse_srt(data:bytes)->list[SubtitleCue]`, `parse_vtt(data:bytes)->list[SubtitleCue]`, `serialize_srt(cues, translated_by:map[int,str])->bytes`, `serialize_vtt(...)`, `export_transcript(cues, fmt:"srt"\|"vtt"\|"txt"\|"json")->bytes`, `ChainedTranscriber` helper to feed document-side cues through `translate_text` preserving cue timing/indices | `document_deepl` (.srt/.vtt sources) + Subtitles page export |
| 13 | `services/usage_service.py` **CH** | B2 | `async products(db, org_id)->list[ProductUsage{product:"translate"\|"speechToText"\|"speechToSpeech", character_count/minutes_count, limit, billed:bool}]` (speechToSpeech row emitted only when `audio_seconds_tts>0` metered; new ledger unit `"tts_seconds"` recorded by VoiceAgent); `current_period_usage` gains `"tts_seconds"` from `UsageLedger` | v2_v3.py `/v2/usage` (B1 glue) |
| 14 | `realtime/voice_session.py` **NEW** | B4 | `class VoiceSessionConfig(source_media_content_type:str, source_language:str|None, source_language_mode:str="auto", target_languages:list[str], target_media_languages:list[str]=[], target_media_content_type:str|None, message_format:str="Json")`; `parse_content_type(ct)->(mime, params)` (e.g. `audio/pcm;encoding=s16le;rate=16000`); `async create_session(db, request, principal, cfg)->{session_id, streaming_url:"wss(s)://<host>/v3/voice/realtime/connect?token=…", one_time_token, expires_at, protocol_version:1, message_format}` — one-time ticket from existing `create_session_ticket` (consume-once); `class CadenceGovernor(max_bytes, max_chunk_s, max_x)` → `inspect(chunk_bytes, chunk_span_s)->None raises ChunkCadenceError`; `async bill(db, session_id, source_seconds, tts_seconds)->` minute rounding (ceil) via `usage_service.record_usage` "audio_seconds"/"tts_seconds" | v2_v3.py `/v3/voice/realtime` POST+GET (B1 glue); `voice_ws.py` |
| 15 | `realtime/voice_ws.py` **NEW** | B4 | `router = APIRouter()`; `@router.websocket("/v3/voice/realtime/connect")` — validates one-time token (4013 close), then **adapts** DeepL wire events to the existing pipeline loop: client `{"source_media_chunk":{"data":<b64>}}`→`ClientEventType.SOURCE_MEDIA_CHUNK`→decode→pipeline audio path; `{"end_of_source_media":{}}`→`END_OF_SOURCE_MEDIA`; emits `ServerEventType.SOURCE_TRANSCRIPT_UPDATE`/`TARGET_TRANSCRIPT_UPDATE` `{concluded[], tentative[]}` (segments `{text,start_time,end_time:int ms}`; tentative refined, concluded deduped by `segment_id`), optional `TARGET_MEDIA_CHUNK` `{data:[b64], content_type}` (single target TTS stream), `END_OF_STREAM` terminal, `{"error":{"error_message":…,"code":…}}`; cadence violations → error event ×3 → close 1008; session task ends → bill via `voice_session.bill` | `main.py` (B1); reuses `app.realtime.pipeline`, `session_manager`, `protocol.py` |
| 16 | `realtime/protocol.py` **CH** | B4 | `ClientEventType`: + `SOURCE_MEDIA_CHUNK="source_media_chunk"`, `END_OF_SOURCE_MEDIA="end_of_source_media"`; `ServerEventType`: + `SOURCE_TRANSCRIPT_UPDATE="source_transcript_update"`, `TARGET_TRANSCRIPT_UPDATE="target_transcript_update"`, `TARGET_MEDIA_CHUNK="target_media_chunk"`, `END_OF_STREAM="end_of_stream"` (new members use exactly the DeepL wire strings; existing members/clients unchanged); `parse_client_event` accepts these untyped payloads verbatim | `ws.py` + `voice_ws.py` |
| 17 | `routers/v2_v3.py` **CH** | **B1 only** | glue handlers delegate to services (see c). No new module here beyond models already present | — |
| 18 | `main.py` **CH** | **B1 only** | register `providers.router`, `voice_ws.router` | — |

*\* Note: new enum members intentionally deviate from the dotted style of existing members to match DeepL wire strings exactly.

## c. Interface contracts (exact)

Auth for `/v2/*`+`/v3/*` stays as today (`get_principal_optional`; metered to caller org when authenticated). Errors:
`{"message":…, "code":…}` from `AppError` (400 `validation_error`, 456 `quota_exceeded` …).

**POST `/api/v2/translate`** — JSON body: `text: string|string[]` (≤50 items when array; ≤128 KiB combined → 413 `too_large`),
`target_lang: string` (required), `source_lang?: string`, `model_type: "latency_optimized"|"quality_optimized"` (default
latency_optimized; `quality_optimized` overrides provider order to highest-quality adapter), `split_sentences: "0"|"1"|"nonewlines"`,
`preserve_formatting: bool`, `formality: "default"|"more"|"less"|"prefer_more"|"prefer_less"` (prefer_* → resolved per
`FORMALITY_RULES`, silently applied), `tag_handling: "xml"|"html"` + `non_splitting_tags: string` (comma list; accepted,
`outline_detection`/`splitting_tags`/`ignore_tags` ignored-not-invented → 400 if sent? NO: accepted and ignored),
`context: string` (unbilled, ≤2000 chars; **400 if context + (glossary_id|glossary_ids)**), `glossary_id: string` **or**
`glossary_ids: string[≤5]` (400 if both; requires source_lang; priority order = list order), `show_billed_characters: bool`,
`enable_quality_evaluation: bool` (bonus field, DeepL-doc-style).
Response `200`: `{"translations":[{"detected_source_language":"EN","text":"…","model_type_used":"latency_optimized","billed_characters":123,"alternatives":["…"]?,"quality":{...}?}]}`. `billed_characters` only when `show_billed_characters=true`; `model_type_used` echoes `model_type` (per-text max when delegated); `alternatives` only when engine supports (`gt_ai` local n-best or LLM; absent offline → field omitted, **honest**).

**POST `/api/v2/write/rephrase`** & **POST `/api/v2/write/correct`** — body: `text: string|string[]` (required),
`target_lang: "de"|"en"|"en-GB"|"en-US"|"es"|"fr"|"it"|"ja"|"ko"|"pt"|"pt-BR"|"pt-PT"|"zh"|"zh-Hans"`, `source_lang?`,
`writing_style: "academic"|"business"|"casual"|"default"|"simple"|"prefer_academic"|"prefer_business"|"prefer_casual"|"prefer_simple"`,
`tone: "confident"|"diplomatic"|"enthusiastic"|"friendly"|"default"|"prefer_confident"|"prefer_diplomatic"|"prefer_enthusiastic"|"prefer_friendly"`.
`writing_style|tone` + `style_id|style_rule` **mutually exclusive → 400**. Response `200`:
`{"improvements":[{"detected_source_language":"en","target_language":"en-US","text":"…"}]}`.
**Offline fallback:** rule-engine path (existing segmentation/caps/punctuation) — always works, English + supported pairs; non-en
targets without LLM → translation-then-rules (target_text_lang of installed pack) and logs `write.multilingual=fallback`; with
`llm_http_url` → LLM rewrite for any target. Never fails the request because style is unsupported: falls back `prefer_x→x→default`.

**Documents (async 3-call):**
- `POST /api/v2/document` — multipart: `file` (docx/doc/pptx/xlsx/xlsm/pdf/htm/txt/srt/vtt/json/yaml/md…), `target_lang`,
  `source_lang?="auto"`, `formality?`, `glossary_id?|glossary_ids?` (≤5, source_lang required), `output_format?` (e.g. `docx`
  converts PDF→Word best-effort), `context?` (≤2000 chars, unbilled, excluded with glossary → 400), `enable_quality_evaluation?`.
  → `200 {"document_id":"…","document_key":"…"}` (**key returned once**, stored hashed).
- `POST /api/v2/document/{document_id}` — body `{"document_key":…}` → `200 {"document_id","status":"queued"|"translating"|"done"|"error","seconds_remaining":int|null,"billed_characters":int}`; repeat poll keeps values (DeepL-compatible).
- `POST /api/v2/document/{document_id}/result` — body `{"document_key":…}` → `200 binary` + `Content-Disposition: attachment`.
  **One-shot**: download clears it; second call → `404 {"message":"Not Found","code":"document_not_found"}`.
- Status codes: 400 bad key/format, 404 unknown id/key/org, `413` >max_upload_mb, `429` when > 20 undownloaded docs for org
  (`document_download_limit_reached`), 456 quota.
- Billing: `billed_characters = max(real_chars, 50000)` for docx/doc/pptx/xlsx/pdf; exact chars for txt/htm/srt/vtt/json/md; `0` for
  `error` state (audited). srt/vtt: cues translated, cue timings preserved in output (same format as source).

**Glossaries v3** (exists in v2_v3.py; upgraded semantics via `glossary_v3_service`):
- `POST /api/v3/glossaries` body `{name:str, entries_format:"source,target"|"source<TAB>target"?|` default, `dictionaries:[{source_lang, target_lang, entries_or_file(str, TSV/CSV lines)}]}` → `200 {glossary_id, prepared-sizing…}` (existing shape kept; per-pair dictionary rows created). Limits: serialized dictionary ≤10 MB, each name/phrase ≤1024 UTF-8 bytes, **duplicate source inside one dictionary → 400** (`duplicate_source`).
- `GET /api/v3/glossaries` → list; `GET /api/v3/glossaries/{id}` → detail; `PATCH /{id}` `{name?}`+`{dictionaries:[...]}` = **merge** (existing pairs updated by source key, new pairs appended); `PUT /{id}/dictionaries` `{dictionaries:[{source_lang,target_lang,entries}]}` = **replace per pair** (stale entries deleted first); `DELETE /{id}/dictionaries?source_lang&target_lang`; `DELETE /{id}` 204; `GET /{id}/entries?source_lang&target_lang` → `{glossary_id, name, entries: "a\tb\n…"}`.
- Consumption: translate (+documents) `glossary_id|glossary_ids` ≤5; first id = highest priority; pair terms resolved across glossaries; source_lang required.

**Voice realtime:**
- `POST /api/v3/voice/realtime` body `{source_media_content_type?: "audio/pcm;encoding=s16le;rate=16000", source_language?, source_language_mode?: "auto"|"fixed", target_languages: string[≤5], target_media_languages?: string[≤1], target_media_content_type?: "audio/pcm;…rate=24000", message_format?: "Json"}` → `200 {"session_id","streaming_url":"wss(s)://<host>/v3/voice/realtime/connect?token=<one-time>","one_time_token","expires_at":int,"protocol_version":1,"message_format":"Json"}`; `GET /api/v3/voice/realtime?session_id=` reconnect (existing).
- WS `/v3/voice/realtime/connect` (one-time token consumed; reuse close codes: 4001 auth):
  - client→server: `{"source_media_chunk":{"data":"<base64>"}}` (chunk ≤100 KB decoded, ≤1 s span, arrival ≤2× realtime;
    violations → `{"error":{"error_message":"…","code":"cadence_violation"}}`; 3 strikes → close 1008), `{"end_of_source_media":{}}`.
  - server→client: `{"type":"source_transcript_update","concluded":[{text,start_time:int_ms,end_time:int_ms}],"tentative":[…]}`,
    `{"type":"target_transcript_update","concluded":[…],"tentative":[…]}`,
    `{"type":"target_media_chunk","data":["<b64>"],"content_type":"audio/pcm;encoding=s16le;rate=24000"}` (only when target_media configured;
    **single target TTS**), `{"type":"end_of_stream"}` terminal, `{"error":{"error_message":…}}` errors.
  - **Mapping to existing protocol.py:** new `ClientEventType.SOURCE_MEDIA_CHUNK/END_OF_SOURCE_MEDIA`,
    new `ServerEventType.SOURCE_TRANSCRIPT_UPDATE/TARGET_TRANSCRIPT_UPDATE/TARGET_MEDIA_CHUNK/END_OF_STREAM` whose `.value` strings are
    the DeepL names above; existing `transcript.partial/final`, `translation.*`, `tts.chunk` events continue on `/ws/realtime`
    unchanged (meetings path untouched).
- **Offline fallback:** STT/MT/TTS providers as configured today (CT2 whisper/nllb/kokoro dev fallback); no external STT required.

**GET `/api/v2/usage`** → `200 {"character_count": num, "character_limit": num, "start_time": iso|null, "end_time": iso|null, "products":[{"product":"translate","character_count":n,"character_limit":n}, {"product":"speechToText","minutes_count":n,"minutes_limit":n}, {"product":"speechToSpeech","minutes_count":n,"minutes_limit":n}]}`; speechToSpeech row **omitted** when no TTS seconds metered (prompt-mandated conditional).

**Provider keys:**
- `GET/POST /api/v1/providers/keys`, `POST /{id}/rotate|activate|deactivate`, `DELETE /{id}`, `POST /{id}/test` (shapes in module 5). Keys
  encrypted at rest (Fernet AES-CBC-HMAC via `cryptography`, key material: env `SECURITY_SECRET_KEY`-derived or generated & persisted
  mode 0600). Responses always masked (`****1234`), plaintext never leaves the vault except into provider adapters in-process.
- **Proxy guard:** browser origin list = own origins only (`cors_origins`); all outbound provider calls from services/api only.
  Audit rows (`ProviderCredentialEvent`) for created/rotated/activated/deactivated/deleted + test attempts.
- **Offline fallback:** `test-connection` without internet/keys → `{reachable:false, provider_status:"not_configured"}` (no fake positives).

## d. Frontend (apps/web) additions

| File | Purpose | Consumes |
|---|---|---|
| `src/pages/ProviderKeys.tsx` **NEW** | provider key store UI: add/rotate/delete/deactivate, masked `****1234` display, test-connection button with status badge, org-scoped | `/api/v1/providers/keys*` |
| `src/pages/Documents.tsx` **CH** | upload formats pdf/docx/pptx/xlsx/txt/html/srt/vtt (+md/json), 3-call flow with status chip (`queued/translating/done/error`, seconds_remaining), one-shot download button (disabled after download) | `/api/v2/document*` |
| `src/pages/Glossaries.tsx` **CH** | per-language-pair dictionaries, TSV/CSV textarea import + export download, active toggle per glossary, duplicate-source error surfaced from 400 | `/api/v3/glossaries*` |
| `src/pages/Subtitles.tsx` **NEW** | live captions from realtime WS (`concluded[]` list + `tentative[]` ghost line), timer-coded, export .srt/.vtt/.txt/.json | session POST `/api/v3/voice/realtime`, WS connect |
| `src/pages/Voice.tsx` **CH** | mic capture (MediaRecorder→PCM chunks 250 ms) → session POST → `wss` connect (`source_media_chunk`), TTS playback of `target_media_chunk`; **graceful fallback**: if session/WS fails → existing realtime pipeline pages | `/api/v3/voice/realtime` |
| `src/components/ContextStylePanel.tsx` **NEW** | context textarea (chars counter), formality select, writing_style/tone selects with prefer_* options, custom-instructions list (≤10×300) | client-side; sends fields on translate/write |
| `src/components/AlternativesPopover.tsx` **NEW** | n-best chips on translated segment; **hidden entirely when no `alternatives` returned (offline honest)** | `translations[].alternatives` |
| `src/lib/api/deepl.ts` **NEW** | typed fetch client for all new routes (orjson-safe, error `{message,code}` mapping) | — |

## e. Multi-agent orchestration map

| Agent | Type | Inputs → Outputs | Registered at | Deadline discipline |
|---|---|---|---|---|
| ListeningAgent (existing) | realtime | audio chunks → TranscriptSegment partial/final | `app/realtime/agents/listening.py` | inference_gate `stt` stage |
| TranslationAgent (existing) | realtime | lowered segment + target → translated text; **NEW: takes ContextAgent hint first** (translate as a batch) | `agents/translation.py` | inference_gate `mt` stage |
| VoiceAgent (existing) | realtime | translations → TTS bytes | `agents/voice.py` | inference_gate `tts` stage |
| supervisor (existing) | realtime | all stage events → recovery/quality degrade decisions | `agents/supervisor.py` | — |
| inference_gate (existing) | realtime | `slot()` semaphore + StageDeadlineExpired | `agents/inference_gate.py` (default_gate) | reused by **all** new agents below |
| **SecureKeyAgent NEW** | service-layer | resolve(provider, org) → in-process credential string or None; audit events | core: `services/provider_vault.py`; consumed in `translation_service`/`write_service`/`document_deepl`/`voice_session` provider construction; UI routes `routers/providers.py` | provider calls keep `provider_attempt_timeout_s` fallback chain |
| **CorrectionAgent NEW** | service-layer | raw text + style/tone → improved text (rule engine offline; LLM when configured) | `services/write_service.apply_style_tone` | `write_neural_timeout_s` via default_gate |
| **ContextAgent NEW** | service-layer | context string + style_profile_id + glossary_ids → ContextDirective{hint, glossary_terms, formality} injected into: `/v2/translate`, document pipeline, realtime TranslationAgent | `services/context_service.py`; realtime hook wired in `agents/translation.py` | compose is DB-only (no gate) |
| **QAAgent NEW** | service-layer | (source, target, pair) → QualityReport{score, issues[{type, severity, span, explanation}]} | `services/quality_eval_service.py`; surface: translate response `quality`, documents polling detail, realtime `quality.report` | LLM mode bounded by `write_neural_timeout_s` in default_gate |

## f. Sequencing & ownership matrix (5 build agents)

**Rule:** a file may appear in exactly one agent's owned list below. Shared files (`main.py`, `config.py`, `db/models.py`,
`alembic/*`, `services/api/requirements*.txt`, `app/deps.py`, `app/errors.py`) are edited **only by B1**; B2–B5 deliver services/
pages/tests that B1 wires. B1 = integration lane: it performs final glue + revision touch-ups.

| Phase | B1 core/translate/write/context | B2 keys vault+documents+usage | B3 web UI | B4 realtime voice+subtitles | B5 tests+benchmarks |
|---|---|---|---|---|---|
| **P0 skeleton (day 1)** | models.py tables, Alembic rev, config fields, context_service draft, protocol mapping plan review | provider_vault draft (pure fns first, no router) | routes/lib client skeleton (`src/lib/api/deepl.ts`) | voice_session.py config parsing + CadenceGovernor (pure) | test scaffolding + fixtures inventory |
| **P1 core build (days 2–3)** | translation_service upgrade (context, model_type, tags, glossary_ids, quality flags), write_service style/tone + multilingual, ContextAgent finalize + QAAgent | vault router + models + resolver; document_deepl (upload/status/one-shot download, 50k math, srt/vtt hooks), usage_service.products | ProviderKeys page, ContextStylePanel, Documents page rewrite | voice_ws.py adapter + protocol.py enum additions, subtitles_service parsers + exports | unit tests for phases built so far (mock DB, no net) |
| **P2 integration (day 4)** | v2_v3.py glue: translate/write/document/usage/voice handler rewrites + Glossary v3 semantics wiring, main.py registrations | vault resolver wired into B1-owned services via explicit parameters (B1 applies) | Glossaries page upgrade, wire AlternativesPopover, ApiKeys test-connection | realtime hint slot in agents/translation.py; session minute metering verify | integration tests (FastAPI TestClient over full app), Windows CI commands |
| **P3 optics (day 5)** | parity touch-ups from B5 report, honest-fallback audit (is_configured gates) | provider `test_connection` polish, metered TTS seconds | Subtitles page, Voice page upgrade | fanout perf numbers for benchmark | benchmarks: verify_ai_stack additions, README scorecard rows, features.csv/parity/test-plan updates, e2e notes |

**File ownership (disjoint, final):**
- **B1:** `app/routers/v2_v3.py`, `app/services/translation_service.py`, `app/services/write_service.py`, `app/services/context_service.py`, `app/services/quality_eval_service.py`, `app/db/models.py`, `app/db/session.py? NO`, `alembic/versions/<rev>.py`, `app/main.py`, `app/config.py`, `gt_ai/registry.py` (only if param plumbing proves necessary — else untouched).
- **B2:** `app/services/provider_vault.py`, `app/services/glossary_v3_service.py`, `app/services/document_deepl.py`, `app/services/usage_service.py`, `app/routers/providers.py`.
- **B3:** `apps/web/src/pages/{ProviderKeys,Documents,Glossaries,Subtitles,Voice}.tsx`, `apps/web/src/components/{ContextStylePanel,AlternativesPopover}.tsx`, `apps/web/src/lib/api/deepl.ts`, `apps/web/src/App.tsx` route entries.
- **B4:** `app/realtime/voice_ws.py`, `app/realtime/voice_session.py`, `app/realtime/protocol.py`, `app/realtime/agents/translation.py` (hint slot only), `app/services/subtitles_service.py`.
- **B5:** `tests/unit/*` new files (`test_v2_translate_parity.py`, `test_write_style_tone.py`, `test_context_service.py`, `test_quality_eval.py`, `test_provider_vault.py`, `test_document_deepl.py`, `test_glossary_v3.py`, `test_usage_products.py`, `test_voice_cadence.py`, `test_subtitles_service.py`), `tests/integration/*` (translate/doc/usage/keys flows), `scripts/verify_ai_stack.py`, README table, `replica/*` scorecards.

No pair shares a file; B1 alone reconciles shared-file diffs at P2. Anything touching `apps/api` or `ai/` = revert on sight.

**Runs (Windows-safe):** `make dev` (API :8000); `make test-unit`, `make test-integration`, `cd services/api && python -m alembic upgrade head && python -m alembic check`, `cd apps/web && npx tsc -b`, `python scripts/verify_ai_stack.py --quick`. Model policy: cache-first; no new weights; no new runtime deps beyond pins already present.
