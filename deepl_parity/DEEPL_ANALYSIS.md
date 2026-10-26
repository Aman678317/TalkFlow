# DeepL Feature & API Study — parity inputs for TalkFlow
Aggregated from public DeepL docs (agents A1, Oct 25 2026) + live observation of
deepl.com through the CDP browser harness (agent M, Oct 25 2026). Evidence class is
marked per claim: [DOC] = public docs, [LIVE] = observed on https://www.deepl.com.

## 0. Live-observation results (agent M) [LIVE]
- Target: https://www.deepl.com/en/translator, /en/translate (desktop harness, real tab).
- The public web translator page embeds BOTH editors in DOM as contenteditable
  divs: `aria-labelledby="translation-source-heading"` and
  `aria-labelledby="translation-target-heading"`, placeholder
  "Type to translate…". Keystrokes injected through CDP never land (focus is
  refused); synthetic `click()` calls on the page fail with shield errors.
- GATE: `https://clearance.deepl.com/shield-widget?appearance=interaction-only&issue_shield_token_on_error=true`
  + UI state "Checking if the connection is secure...". Conclusion: DeepL web app
  token-gates its translation endpoint against automation; live E2Eing of the
  web app is not possible without real browser interaction. TalkFlow must NOT
  replicate this downside; it must expose a friendly web UI + honest API.
- Observed network endpoints (no bodies obtainable, URLs only):
  - `https://w.deepl.com/web?request_type=jsonrpc&il=en&method=getClientState`
    (legacy JSON-RPC "web" gateway still serving the SPA).
  - `https://www.deepl.com/locales/en/voice-conferences.json` (Voice assets load
    on the translator SPA).
  - `/locales/en/pro-api.json`, CMP (usercentrics) consent stack.
- Translation modes visible on landing: Translate text / Translate files /
  Translate speech / Use API / Use in AI apps. Banner: "Real-time voice
  translation that still sounds like you" → /en/products/voice.
- REA note: the REA MCP server OOM-crashed (Node heap, exit 134) on this target
  and could not re-register mid-session; the CDP harness observation above is
  the substitute evidence. Static-only conclusion below stays [DOC].

## 1. Translation engine [DOC]
- `POST /v2/translate`, Auth header: `Authorization: DeepL-Auth-Key <key>`.
  Hosts: `https://api.deepl.com` (Pro), `https://api-free.deepl.com` (Free).
- Body: `{"text":["paragraph …"], "target_lang":"DE", "source_lang"?…}` →
  `{"translations":[{"detected_source_language":"EN","text":"Hallo …"}]}`.
- Engine splits paragraphs into sentences internally and rejoins; client sends
  whole paragraphs.
- `model_type`: `latency_optimized` (default) | `quality_optimized`;
  response echoes `model_type_used`. No model names exposed.
- Alternatives (UI-layer): word alternatives + sentence rephrases, auto-adjust
  surrounding text, save-to-glossary. No public REST endpoint.
- Batch: ≤50 texts/request, ≤128 KiB body; independent translations.
- `split_sentences`: `0|1|nonewlines`; `preserve_formatting`: bool;
  `tag_handling`: `xml|html` (+`outline_detection`, `non_splitting_tags`,
  `splitting_tags`, `ignore_tags`) to protect placeholders.
- `formality`: `default|more|less|prefer_more|prefer_less` (per-target support).
- `context` param: free-form context text, NOT translated, not billed, applies
  to every text in the request; explicit docs warning that it is not a system
  prompt. Use for disambiguation/gender/transliteration.
- `glossary_id` or `glossary_ids` (≤5, first = priority); requires source_lang.
- `style_profile_id`/`style_id` bundle glossary+style+TM (mutually exclusive
  with granular params else 400).

## 2. API key configuration [DOC]
- Keys created client-side at /your-account/keys; header-only auth
  (`DeepL-Auth-Key` scheme); query/body `auth_key` removed Nov 2025; GET /translate
  deprecated → POST only.
- Standard error statuses: 400,403,404,413,429,456(quota),500,504,529.
  Body `{"message": "...", "code": "..."}`; edge errors nest
  `{"error":{"message":"Bad Gateway."}}` → parse both.
- Scoped keys + per-key usage caps (`api_key_character_limit`) via Admin API.
- 19 standardized codes overall; parse `message`, log `X-Trace-ID`.

## 3. Writing assistant (English correction agent) [DOC]
- `POST /v2/write/rephrase` — fluency rewrite; params `text[]` (required),
  `target_lang` enum (de,en,en-GB,en-US,es,fr,it,ja,ko,pt,pt-BR,pt-PT,zh,zh-Hans),
  `writing_style`: academic|business|casual|default|simple (+`prefer_` fallback),
  `tone`: confident|diplomatic|enthusiastic|friendly|default (+`prefer_`).
- `POST /v2/write/correct` — minimal-change spelling/grammar fix.
- Response: `{"improvements":[{"detected_source_language":"en","target_language":"en-US","text":"…"}]}`.
- Write characters count in same quota; Write Pro add-on product.

## 4. Real-time voice translation (Voice API) [DOC]
- Two-step: `POST /v3/voice/realtime` → `{session_id, streaming_url:
 wss://api.deepl.com/v3/voice/realtime/connect, token}`; connect WS with token.
- Session: `source_media_content_type` e.g. `audio/pcm;encoding=s16le;rate=16000`,
  `target_languages` ≤5, optional `source_language` + `source_language_mode:
  "fixed"` (skips detection), `target_media_languages` ≤1 +
  `target_media_content_type` (`rate=24000`) for speech-to-speech TTS output.
- Client→server `{"source_media_chunk":{"data":"<base64>"}}` every 50–250 ms
  (≤100 KB or 1 s per chunk; ≤2× realtime); finish `{"end_of_source_media":{}}`.
- Server→client: `source_transcript_update` / `target_transcript_update` with
  `concluded[]` (final, once) + `tentative[]` (live, refined); segments
  `{text,start_time,end_time}`; TTS as `target_media_chunk.data[]`; terminal
  `end_of_stream`; errors `error.error_message`; MessagePack supported.
- Billing: STT/STS per minute (rounded up) in `/v2/usage`
  (`speech_to_text_minutes_count` etc.).

## 5. Secure key posture [DOC]
- CORS 403 for browser-direct API calls; prescribed pattern = own backend proxy
  (official example: DeepL/deepl-api-nodejs-proxy); env-var storage in prod code;
  key deactivation/regeneration in account UI; enterprise: BYOK, audit logs,
  network restrictions, per-key caps.

## 6. Context features [DOC]
- `context` (see §1), formality, language variants (EN-US/EN-GB/PT-BR/PT-PT/
  ZH-HANS/ZH-HANT…), glossary enforcement, `style_id` lists + up to 10 custom
  instructions (≤300 chars each) per target language.

## 7. System decomposition (public-surface level) [DOC]
Engine (single /v2/translate, `model_type` goal) + glossary preprocessor (v3
"intelligently flexes entries": case/gender/tense; reports
`applied_glossary_term_pairs`) + per-format document pipelines + writing
assistant (/v2/write/*) + voice pipeline (STT→translate→TTS on one WS) + QA
agent (beta quality evaluation: per-segment severity/type + explanation +
char spans) + admin control plane (keys/scopes/caps). No internal LMT papers.

## 8. Documents [DOC]
- Async 3-call flow: `POST /v2/document` (multipart file, target_lang,
  source_lang?, formality?, glossary_id(s)?, output_format?,
  enable_quality_evaluation?) → `{document_id, document_key}`;
  `POST /v2/document/{id}` (document_key) → status
  queued|translating|done|error + seconds_remaining + billed_characters;
  `POST /v2/document/{id}/result` → binary (one-shot; deleted after).
- Formats: docx/doc/pptx/xlsx/xlsm/pdf/htm/txt/xliff/srt/vtt/idml/xml/json/yaml/
  properties/strings/md/dita/mif/odt/rtf/resx (+ images beta). `.doc`→`.docx`;
  `output_format=docx` converts PDF→Word.
- Limits: per-format upload caps (docx 10 MB free / 100 MB pro; 500K free chars
  / 1M pro chars per doc); billing minimum 50,000 chars per docx/doc/pptx/xlsx/pdf
  upload; beta formats unbilled. Too many undownloaded docs → 429.
- Per-format rules: XLIFF overwrites `<target>`; JSON keeps `{stars}`; SCORM
  manifest at zip root <4 MB; VTT cue sync preserved; ICU plural skeletons.

## 9. Glossaries (custom dictionary) [DOC]
- v3 model: glossary contains dictionaries (one per language pair); entries TSV
  `source<TAB>target` or CSV `source,target` per line; 10 MB/dictionary;
  name/phrase ≤1024 UTF-8 bytes; no duplicate sources.
- CRUD: `POST /v3/glossaries` (dictionaries[]), `GET /v3/glossaries`,
  `GET /v3/glossaries/{id}`, `PATCH /v3/glossaries/{id}` (rename+merge),
  `PUT /v3/glossaries/{id}/dictionaries` (replace pair dictionary),
  `DELETE /v3/glossaries/{id}`,
  `DELETE /v3/glossaries/{id}/dictionaries?source_lang&target_lang`,
  `GET /v3/glossaries/{id}/entries?source_lang&target_lang`.
- Translate/documents accept `glossary_id`(s) ≤5 priority; EN/PT/ZH target
  dictionaries cover language variants; web + API glossaries unified.

## 10. Live subtitles & transcripts [DOC]
- DeepL Voice desktop app: auto-detects Teams/Zoom/Meet calls, one-click start,
  always-on-top live subtitles overlay, voice-to-voice translation with tone
  preservation, in-meeting join link, spoken terms bias for STT.
- Transcripts assembled from time-coded `concluded` segments; export at client.

## 11. Auto-detection [DOC]
- `source_lang` optional everywhere (translate/write/document/voice);
  `detected_source_language` returned per segment; `target_lang` required.
- Long text is more reliable than single words; docs recommend explicit source
  when possible; glossary requires known source_lang (mutual exclusion).
- `GET /v3/languages` documents per-language resources/features.

## 12. Production practices [DOC]
- Backoff-with-jitter retries on 429/5xx/529; never retry 456 or 400; cap
  in-flight requests; honor `Retry-After`; Keep-Alive; poll document status
  with backoff (seconds_remaining unreliable).
- Cache `(source,target,text)` results (pre-production checklist item);
  `show_billed_characters` telemetry.
- Quota monitoring: `GET /v2/usage` → character_count/character_limit +
  per-product splits (translate; speech_to_text_minutes; speech_to_speech_minutes).
- Benchmarks: DeepL methodology = blind head-to-head human panels; state that
  BLEU/COMET "fall short". TalkFlow keeps BLEU/COMET as regression guard +
  adds human-panel-style comparative eval.

## 13. Parity checklist (viable replica targets for TalkFlow)
- /translate endpoint shape identical to §1 (batched text[], detected lang,
  model_type echo, alternatives in UI, tag handling, split_sentences,
  preserve_formatting, formality, context).
- /write/rephrase + /write/correct with style/tone enums + prefer_ fallbacks.
- Voice: session→WS streaming chunks, concluded/tentative transcript updates,
  optional 1-language TTS stream, minute billing in usage.
- Documents async 3-call flow with document_id/key, status polling, one-shot
  download, 50K-char billing minimum, docx/pptx/xlsx/pdf/xliff/srt/json/html.
- Glossaries v3 shape (dictionaries per pair, TSV/CSV, CRUD+replace+merge,
  ≤5 ids priority) unified with UI.
- Auto-detect default; confidence surfaced; explicit-source prompt on short text.
- Secure keys: server-side proxy only; env vars; rotation; per-key caps.
- Production: backoff+jitter, never-retry 456/400, usage endpoint, caching,
  batch ≤50 & ≤128 KiB; quality eval per segment.
