# REA / DeepL Findings

*Research date: 2026-10-25. Scope: REA 6.7.0 setup verification plus a public-contract study of DeepL for a clean-room feature-parity build. No app code was written and no system/client configuration was changed.*

---

## 1. Setup verification

| Check | Result |
|---|---|
| `rea --version` | `6.7.0` |
| `rea doctor --json` | Exit code `1`; `healthy:false`, `environment_healthy:false`, `scope.mode:"audit-wide"`. Native engines absent: Hopper, Ghidra, IDA, JADX, Kuna. Four unrelated client registrations drift: `antigravity`, `claude_code`, `copilot_cli`, `gemini_cli`. **Qoder registration is aligned**: `C:\Users\acer\.qoder\settings.json` → `cmd.exe /d /c npx -y rea-agents@6.7.0 mcp`. |
| Identity | CLI package `6.7.0`; SDK server/client/core `2.3.1`; skill version `42` (installed 42, `aligned`); catalog `153` CLI commands, `207` MCP tools, `6` prompts. |
| `rea capabilities --json` | Only four providers listed: `native-macos` (unsupported on Windows), `rea-artifact-graph` (available), `rea-dotnet-static` (available), `sqlite` (available). No browser/CDP provider is advertised in this session. |
| `rea providers --json` | Same provider set as `capabilities`. |
| Install state | `installations.state:"multiple"` (two npm shims); `live_server.state:"unknown"`. Cosmetic, not remediated. |

No `rea setup`, no engine installs, no file/config edits. MCP tools were not exposed in the session, so all REA work used the CLI. No API keys or secrets were used or printed.

---

## 2. Evidence table

| # | Command / source | Result | Confidence |
|---|---|---|---|
| 1 | `rea --version` | `6.7.0` | Observed |
| 2 | `rea doctor --json` | Qoder aligned; optional engines missing; 4 unrelated clients drift; `healthy:false` | Observed |
| 3 | `rea capabilities --json` / `rea providers --json` | 4 providers; no browser provider; web commands still exist in CLI | Observed |
| 4 | `rea analyze-web-bundle --help` | Requires a loopback CDP endpoint plus target ID; optional source-map fetch | Observed |
| 5 | `gh api orgs/DeepL/repos` | Public org contains SDKs, OpenAPI, MCP server, CLI, proxy, docs, examples; **no engine/server repository** | Observed |
| 6 | `https://raw.githubusercontent.com/DeepL/openapi/main/openapi.json` | OpenAPI `3.0.3`, spec version `3.14.0`; full path/auth/param/error contract | Observed |
| 7 | `https://raw.githubusercontent.com/DeepL/openapi/main/voice.asyncapi.json` | AsyncAPI `3.0.0`, Voice WebSocket spec `1.0.0`; message schemas | Observed |
| 8 | `developers.deepl.com/docs/resources/usage-limits` | Header 16 KiB; body 128 KiB; per-format document size table | Observed |
| 9 | `developers.deepl.com/docs/best-practices/error-handling` | 456 = quota reached, do not retry; 429/5xx = backoff, honor `Retry-After` | Observed |
| 10 | `developers.deepl.com/docs/best-practices/cors-requests` | Browser calls fail `403` "blocked by CORS policy"; use a backend proxy | Observed |
| 11 | `developers.deepl.com/api-reference/detect-language/detect-language-beta` | `POST /v3/detect/language`, max 50 texts, four statuses | Observed |
| 12 | `developers.deepl.com/docs/mcp` | Remote MCP at `https://mcp.deepl.com/v1/mcp`, Streamable HTTP, OAuth 2.1 | Observed |
| 13 | `github.com/DeepL/deepl-mcp-server` README | Local stdio server, `DEEPL_API_KEY`, 12 tools, read-only style rules | Observed |
| 14 | `github.com/DeepL/deepl-api-nodejs-proxy` README | CORS proxy explicitly "local development only"; API enforces all limits | Observed |
| 15 | `github.com/DeepL/deepl-python` README | SDK retries transient failures; default 5 retries; configurable timeout/connection reuse | Observed |
| 16 | `developers.deepl.com/docs/translate/translating-large-volumes` | Max 50 texts and 128 KiB per request; batch/parallelize | Observed |
| 17 | `developers.deepl.com/docs/customize/managing-glossaries` | Up to 5 dictionaries/glossary, 10 MB each, 50 MB total; CSV/TSV | Observed |
| 18 | `deepl.com/translation-flow`, Translator blog, DeepL Agent press release | Agentic Translator/Translation Flow; DeepL Agent is beta and uses virtual UI interaction | Product observed; API mapping inferred |
| 19 | `analysis/DEEPL_ANALYSIS.md` (prior probe) | REA-owned browser launch failed; manual CDP worked; scenario partially completed; `analyze-web-bundle` OOM-crashed (exit 134) on multi-MB Next.js bundle; SPA shielded by `clearance.deepl.com/shield-widget` | Prior observed; not re-run |

---

## 3. 12-pillar contract matrix

| # | Pillar | Concrete contract (endpoint / param / protocol) | UX behavior worth replicating | Limits / quotas | Confidence |
|---|---|---|---|---|---|
| 1 | Translation Agent | No public endpoint named "Translation Agent". Public product surfaces: new DeepL Translator agentic workflow and Translation Flow (SharePoint, AEM, Google Drive, InDesign; human review by email invite/comment). API composition is `POST /v2/translate` with `context`, `glossary_ids`, `style_id`/`style_profile_id`, `translation_memory_id`, `custom_instructions`, `model_type`. | Agentic pipeline auto-applies glossary/style/TM, preserves layout, routes human review, and keeps a run/review state. Surface a step trace rather than a black box. | Inherits translate limits (50 texts, 128 KiB). No public agent-run API, job queue, trace schema, or pricing unit. | Product observed; API mapping inferred |
| 2 | API key configuration | `Authorization: DeepL-Auth-Key <key>`; Free host `api-free.deepl.com`, Pro `api.deepl.com`; Free keys end `:fx`; validate with `GET /v2/usage`; Admin API `/v2/admin/developer-keys` (POST/GET, `/deactivate`, `/label`, `/limits`). | Validate-on-save, show plan/host, quota progress, key name and scopes, masked display, permanent revoke. Never put the key in a URL or log. | Free 2 keys, Pro 25; deactivation permanent; no per-key spend limit and no last-used tracking documented. | Observed doc/spec |
| 3 | English correction (Write) | `POST /v2/write/correct` and `POST /v2/write/rephrase`; body `text[]` + `target_lang` enum (`de,en,en-GB,en-US,es,fr,it,ja,ko,pt,pt-BR,pt-PT,zh,zh-Hans`); response `improvements[{detected_source_language,target_language,text}]`; rephrase adds `writing_style` and `tone` with `prefer_*` fallbacks. | Correct = minimal-change grammar/spelling; Rephrase = style/tone rewrite; client computes inline diff; separate Write workspace. | Global 128 KiB / 50 texts apply (50 for Write is inferred); no glossary, context, or TM parameters; API returns full text, not a diff. | Observed spec |
| 4 | Real-time voice translation | `POST /v3/voice/realtime` → `streaming_url`, one-time `token`, `session_id`; WSS `/v3/voice/realtime/connect?token=...`; reconnect `GET /v3/voice/realtime?token=...`; JSON TEXT frames or MessagePack BINARY frames; client sends `source_media_chunk{data}`, receives source/target transcript updates and TTS chunks. | Two-tier captions (tentative grey → concluded colored), per-target panes, voice choice male/female/match, reconnect banner, headphone/echo warning, mic state machine. | ≤5 `target_languages`; ≤1 `target_media_languages`; chunk ≤100 KB or 1 s, 50–250 ms recommended, gap ≤30 s; token one-time; a protocol error terminates the session and cannot be resumed. | Observed spec + AsyncAPI |
| 5 | Secure API-key handling | Key held server-side; browser-direct calls are blocked by CORS; scoped keys cover `translate:text`, `translate:document`, `voice:realtime`, `write:improve`, `glossaries:read/write`, `style_rules:read/write`, `translation_memories:read/write`, `languages:read`, `usage:read`; missing scope → 403. `document_key` is a client-held per-document encryption key, not an API key. | Masked key, scope picker, revoke, proxy health indicator, explicit 403 taxonomy (bad key vs missing scope vs CORS). | 2/25 keys; official proxy is dev-only and has no rate/size limits of its own; production must use an owned backend proxy. | Observed doc; proxy topology inferred |
| 6 | Context-aware agent | `POST /v2/translate` `context` (surrounding text, not billed); `custom_instructions` ≤10 × 300 chars; `style_id` or `style_profile_id`; `translation_memory_id` + `translation_memory_threshold` (default 75, values below 50 treated as 50); `glossary_ids` ≤5. | Side "context" panel, "glossary applied: N terms" indicator, detected-language override, style-profile selector, ambiguity examples (e.g. short snippets). | `context` maximum length is not published; 10-instruction cap; TM threshold 0–100; style list language must match target. | Observed doc; context max unknown |
| 7 | Multi-agent architecture (incl. MCP) | Remote MCP `https://mcp.deepl.com/v1/mcp` (Streamable HTTP, OAuth 2.1). Local stdio `npx -y deepl-mcp-server` with `DEEPL_API_KEY`. Tools: `translate-text`, `translate-document`, `rephrase-text`, `get-source/target-languages`, `get-writing-styles/tones`, `list-glossaries`, `get-glossary-info`, `get-glossary-dictionary-entries`, `list-style-rules`, `get-style-rule`, `get-custom-instruction`. | Tool discovery, OAuth handoff, read-only corporate style assets, per-tool language/glossary errors surfaced to the agent. | No public orchestration/trace API; remote requires DeepL account sign-in; local server exits without a key; style/instruction tools are read-only. | MCP observed; internal multi-agent design unknown |
| 8 | PDF / document translation | Three POSTs: `POST /v2/document` multipart (`file`, `target_lang`, optional `source_lang`, `glossary_ids`, `style_id`, `output_format`, `enable_watermark`, `enable_quality_evaluation`) → `document_id` + `document_key`; `POST /v2/document/{id}` with `document_key` → status; `POST /v2/document/{id}/result` with `document_key` → binary. Formats include docx, pptx, xlsx/xlsm, pdf, html, txt, xlf/xliff 1.2/2.0/2.1, srt, vtt, idml, xml, json, yaml, properties, strings, md, dita, mif, zip/SCORM, odt, rtf, resx, jpeg/png. | Drag-drop, format-aware output, progress with `seconds_remaining`, watermark toggle, quality report, download; client must persist `document_key` or lose the job. | Statuses `queued`, `translating`, `done`, `error`; billed only on successful download; results expire in 24 h. Free 10 MB/500k chars and paid 100 MB/1M chars for Word/PDF/PPT; Excel paid 30 MB; TXT/JSON/YAML 1 MB; HTML/DITA 5 MB; SRT/VTT 150 KB; images 3 MB. | Observed spec/doc |
| 9 | Custom dictionary / glossaries | v3: `POST/GET /v3/glossaries`; `GET/PATCH/DELETE /v3/glossaries/{id}`; `PUT/DELETE /v3/glossaries/{id}/dictionaries`; `GET /v3/glossaries/{id}/entries?source_lang&target_lang`. v2 is single-pair and legacy. Entries are TSV or CSV. Translate with `glossary_id` or `glossary_ids` ≤5 (mutually exclusive) and explicit `source_lang`. | CRUD manager, one dictionary per language pair/direction, import/export, readiness flag, per-translation applied-hit count. v3 root codes (`en`, `pt`, `zh`) apply across variants. | ≤5 dictionaries per glossary; 10 MB entries per dictionary; 50 MB total; account-wide glossary count is plan-dependent (1,000 is cited publicly but unverified); entry count cap is unclear for the API. | Spec observed; account/entry caps uncertain |
| 10 | Live subtitles / transcripts | Voice WS: `source_transcript_update{concluded[],tentative[]}` with `language,text,start_time,end_time` (ms); `target_transcript_update{language,concluded[],tentative[]}`; `target_media_chunk{language,content_type,headers,data[],duration,text}` for A/V sync. Async jobs: `POST /v1/jobs/voice/translate` → `upload_url` + `signature`; `GET /v1/jobs/voice/translate/{job_id}`; outputs include `text/plain` and `application/x-subrip` (SRT). | Tentative → concluded styling, timestamps, per-language panes, TXT/SRT export, auto-scroll, speaker/language labels. | ≤5 translation targets; async result retention unspecified; VTT is an input document format, not an observed transcript output. | Observed spec; VTT export unknown |
| 11 | Language auto-detection | Omit `source_lang` on `/v2/translate`; response always includes `detected_source_language` (it echoes `source_lang` when supplied). Beta `POST /v3/detect/language` with `text[]` ≤50 → `results[{detected_language,detection_status}]`. Voice `source_language_mode` is `auto` or `fixed`. | "Detected: EN" badge with one-click override; short-text warning; explicit confidence state instead of a silent guess. | Detection statuses: `success`, `insufficient_confidence`, `unsupported_language`, `no_language_detected`. Very short text is unreliable; beta endpoint is absent from OpenAPI 3.14.0. | Observed doc; beta |
| 12 | Production testing / optimization | `GET /v2/usage` (`character_count`, `character_limit`, document/team counters, `products`, speech minutes, billing window). Document quality evaluation: `enable_quality_evaluation=true` → `quality_evaluation_job_id` → `GET /v1/quality-evaluations/{job_id}` (202 while running + `Retry-After`; 404 if expired/other account). Retry 429/5xx with backoff; never retry 400/403/404/413/456. | Quota and cost dashboard, p50/p95 latency, error taxonomy, health endpoint, per-key usage, quality report, cache hit metrics. | 456 is a hard stop until the limit is raised; numeric 429 rate is not published (DeepL staff guidance ~50 req/s in a 2023 issue is not an official contract); SDK default 5 retries; document results 24 h. | Docs observed; numeric rate inferred |

---

## 4. Load-bearing contract notes

### Auth model
- Header only: `Authorization: DeepL-Auth-Key <key>`.
- Free: `https://api-free.deepl.com`; Pro: `https://api.deepl.com`. Free keys end in `:fx`.
- Query-parameter auth is not in the current spec and the pre-production checklist forbids it.
- The same key can be scoped; a scoped key can call only endpoints fully covered by its scopes.

### CORS constraint
- Browser calls to `api.deepl.com` / `api-free.deepl.com` fail with **403 "blocked by CORS policy"**. This is deliberate credential protection, not a misconfiguration.
- Required architecture: browser → your backend proxy → DeepL. The official `deepl-api-nodejs-proxy` is explicitly local-development-only and should not be deployed to production.
- UX implication: a pure client-side "bring your own key" mode is not viable against DeepL; the clone must proxy or terminate the key server-side.

### Error semantics

| Code | Meaning | Retry? |
|---|---|---|
| 400 | Bad request / invalid parameter / unsupported language pair | No |
| 401 | Authorization failed | No |
| 403 | Invalid key, scoped key missing a required scope, **or** browser CORS block | No (fix auth/scope/proxy) |
| 404 | Unknown document/job/resource | No |
| 413 | Request body over 128 KiB or document over its format limit | No |
| 415 | Unsupported media type (Write/glossary paths) | No |
| 429 | Too many requests in a short period | Yes, exponential backoff; honor `Retry-After` |
| 456 | Quota exceeded; character limit reached | No; retrying cannot succeed until the limit is raised |
| 500/503/504/529 | Server error / unavailable / timeout / overload | Yes, backoff |

### Document 3-call flow (all POST)
1. **Upload** `POST /v2/document` as `multipart/form-data`: `file`, `target_lang`; optional `source_lang`, `glossary_ids` (≤5), `style_id`, `output_format`, `enable_watermark`, `enable_quality_evaluation`, `input_conversion_options`. Returns `document_id`, `document_key`, and optionally `quality_evaluation_job_id`.
2. **Poll** `POST /v2/document/{document_id}` with `document_key`. Returns `status` (`queued` / `translating` / `done` / `error`), `seconds_remaining` while translating, `billed_characters`, `error_message`.
3. **Download** `POST /v2/document/{document_id}/result` with `document_key`. Returns the binary document; billing is triggered only on a successful download.
- The server encrypts the upload with a uniquely generated key and does **not** persist that key. If the client loses `document_key`, the job/result is unrecoverable.
- Results expire; documentation states 24 hours. A watermark ("Translated by DeepL") is optional for docx/pdf output and must not be imitated in a clone.

### Glossary v3 dictionaries
- `POST /v3/glossaries` accepts `name` + `dictionaries[]`; each dictionary has `source_lang`, `target_lang`, `entries`, `entries_format` (`tsv` default, `csv`).
- `PUT /v3/glossaries/{id}/dictionaries` replaces or creates one dictionary; `DELETE` takes `source_lang` and `target_lang` query parameters.
- `GET /v3/glossaries/{id}/entries` requires the same pair as query parameters and returns entries wrapped in JSON.
- v3 is multilingual (many pairs/directions per glossary); v2 is a single pair. New integrations should use v3.
- `glossary_id` and `glossary_ids` cannot be combined. Both require explicit `source_lang`; every glossary must contain the requested pair.
- `style_profile_id` bundles glossaries, style rule lists, and translation memories behind one ID.

### Voice tentative/concluded protocol
1. `POST /v3/voice/realtime` fixes options at creation time (languages, message format, media types). Invalid options are rejected with 400 before a session exists.
2. Connect to `wss://api.deepl.com/v3/voice/realtime/connect?token=...`. Use TEXT frames for JSON or BINARY frames for MessagePack; mixing frame types is a protocol error.
3. Client sends `{"source_media_chunk":{"data":"<base64>"}}` at 50–250 ms cadence (max 100 KB or 1 s per chunk; silence gaps ≤30 s).
4. Server sends incremental `source_transcript_update` / `target_transcript_update`. `concluded` segments are final and appear once; `tentative` segments may change or disappear.
5. `target_media_chunk` carries synthesized audio. The first chunk of a segment has `content_type`, optional `headers` (initialization packet count), and `text`; `duration` is in ms and accumulates per subtitle segment for sync.
6. To finish: send `end_of_source_media`; receive `end_of_source_transcript`, `end_of_target_transcript`, `end_of_target_media`, and finally `end_of_stream`. Only then close.
7. An `error` message carries `request_type`, `error_code`, `reason_code`, `error_message` and terminates the session. A dropped connection can exchange the session token via `GET /v3/voice/realtime?token=...` for a fresh URL/token; a protocol error cannot be resumed.

### Detection confidence statuses
- `success`: a language was detected with adequate confidence.
- `insufficient_confidence`: text too short/ambiguous; ask for more text.
- `unsupported_language`: detected language is outside the supported set.
- `no_language_detected`: no language signal (e.g. numbers/symbols only).
- `/v3/detect/language` is beta and not present in the 3.14.0 OpenAPI file; treat it as opt-in and version-sensitive.

---

## 5. REA limits: how close REA can stretch

**Observed now (this session)**
- REA is installed and functional as a CLI. Qoder registration, SDK, skill, and tool catalog are aligned.
- `doctor` is red only because optional native engines are absent and four unrelated clients are unregistered. None of those affect web/docs research.
- The current capability surface advertises artifact, .NET, SQLite, and macOS-native providers only. **No browser/CDP provider is advertised**, even though the CLI exposes `capture-browser-scenario`, `capture-web-screenshot`, `inspect-web-page`, `analyze-web-bundle`, `export-web-scripts`, and `inspect-web-network-capture`.

**Observed in the prior probe**
- REA-owned browser launch failed with `execution_failure` in both headless and headful modes.
- Manual Chrome CDP + `list-browser-targets` + `capture-browser-scenario` worked: DeepL loaded, 730 runtime events were retained, and typing actions executed. The evidence-completion step still failed and returned only a partial observation blob.
- `analyze-web-bundle` on the DeepL Next.js bundle exceeded the default V8 heap and crashed the MCP server (exit 134). This was not retried.
- The translator SPA is fronted by `clearance.deepl.com/shield-widget`, so automated capture may be challenged.

**What REA can establish**
- Public contract facts from docs and OpenAPI/AsyncAPI.
- Page structure, network endpoints, request/response shapes, and client-side strings through bounded CDP inspection or HAR/SAZ/qlog inspection.
- Script inventory and static import tracing via `export-web-scripts` from an already-saved capture, then ordinary static analysis.

**What REA cannot establish**
- DeepL's hosted model quality, weights, inference stack, prompt/agent internals, or server-side orchestration.
- Actual production quotas or rate limits beyond published docs.
- A reliable full-bundle analysis of the multi-MB Next.js app under the current default heap.

**Bounded alternatives (not yet proven on DeepL)**
- Manual CDP + `inspect-web-page` (passive, 500 ms default) and `capture-web-screenshot`.
- `inspect-web-network-capture` on HAR/mitmproxy/SAZ/qlog for endpoint and payload shapes.
- `export-web-scripts` from a saved page/scenario capture, then static JavaScript analysis.
- Raising the Node heap before `analyze-web-bundle` is untested; it is not a documented REA guarantee and may still hit memory or time limits.

---

## 6. Clean-room / legal note

- This document contains only publicly documented API facts, protocol shapes, and observable product behavior. No DeepL source code, SDK code, proprietary assets, or branding was copied.
- The implementation must be independently written. Do not copy DeepL UI pixels, illustrations, iconography, or the "Translated by DeepL" watermark/trade dress.
- Do not use the DeepL name or logo as product branding, and do not claim affiliation, endorsement, or certified compatibility. Descriptive references to an external API should be reviewed by counsel.
- DeepL's API terms, website terms, and acceptable-use policy may restrict scraping, competitive benchmarking, or using outputs to train a competing translation model. Review them before launch. This is not legal advice.
- No API keys were used or printed. `document_key` is a per-document encryption secret and must be treated as sensitive user data in any clone.

---

## 7. Key findings (≤10 lines)

- REA 6.7.0 is operational for CLI/docs research: Qoder is aligned, but optional native engines are absent and four unrelated client registrations drift; nothing was reconfigured.
- DeepL's auth is a single `DeepL-Auth-Key` header against two hosts; browser-direct calls are deliberately blocked by CORS, so a backend proxy is mandatory.
- Global request limits are 128 KiB body / 16 KiB headers / 50 texts; 456 is a non-retryable quota stop, 429/5xx require backoff, and 403 conflates bad key, missing scope, and CORS.
- Documents use a three-POST flow with a client-held `document_key`, billing on download, and 24-hour result expiry.
- Glossaries v3 are multilingual dictionary sets: up to 5 pairs, 10 MB each, 50 MB total, and an explicit `source_lang` is required to apply them.
- Voice is REST session creation plus a one-time-token WSS stream: ≤5 text targets, ≤1 TTS target, 50–250 ms chunks, and explicit `tentative`/`concluded` transcript segments.
- Detection is beta and returns `success`, `insufficient_confidence`, `unsupported_language`, or `no_language_detected`; omitting `source_lang` remains the production auto-detect path.
- MCP is DeepL's only public agent surface (remote OAuth or local API-key stdio); there is no public multi-agent orchestration or run-trace API.
- REA reached DeepL only through manual CDP; owned-browser launch and multi-MB bundle analysis failed, and the hosted engine remains opaque.

---

## 8. Open items

- `context` maximum length is unpublished; determine empirically only within documented request limits.
- Voice token TTL, per-account concurrent session caps, and idle-session behavior are not stated publicly.
- Official numeric rate limits are absent; the ~50 req/s figure comes from a 2023 issue, not current documentation.
- Glossary account-wide count and API entry-count caps conflict across sources; confirm against a live account before hard-coding UI limits.
- Transcript export to VTT is not observed; only TXT and SRT outputs are documented for async voice jobs.
- Quality-evaluation report retention, score semantics, and pricing impact are not fully documented.
- Whether `analyze-web-bundle` can finish under a raised Node heap, or whether `export-web-scripts` handles the DeepL bundle without memory pressure, remains untested.
- Current DeepL plan names, character quotas, and pricing should be re-checked at build time; the 2026 rebrand is only partly reflected in older docs.
- Legal review is still required for competitive-use, benchmarking, and branding constraints in DeepL's terms.
