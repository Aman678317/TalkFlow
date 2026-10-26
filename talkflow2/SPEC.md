# TalkFlow 2.0 — Build Spec (SHARED CONTRACT)
 houses a DeepL-inspired feature-complete translation suite; benchmark: TalkFlow repo + analysis/DEEPL_ANALYSIS.md.
Root: `C:\Users\acer\omnirush.ai\talkflow2\`. Zero npm dependencies. ESM only (`"type":"module"`). Node ≥ 18 (host has 26).

## Ownership (strict)
| Builder | Files (write ONLY these) |
|---|---|
| integrator (me) | `package.json`, `README.md`, `tests/fixtures/*` |
| build-engine | `engine/*.mjs`, `tests/engine.test.mjs` |
| build-server | `server/server.mjs`, `tests/server.test.mjs` |
| build-ui | `app/index.html`, `app/styles.css`, `app/js/*.mjs` |

Rules for all: no npm deps; code concise, real logic (no TODO stubs); every module pure ESM `export` named fn/classes; resolve imports relative; no console noise except server request log (masked); handle malformed input with 400s; never log or echo raw API keys — always `maskKey()`.

## Feature → pillar mapping (the 12 requirements)
1 Translation Agent → translator.mjs + orchestrator + Translator view
2 API Key Configuration → deepl.mjs hosts + Settings view + /api/deepl/validate + /v2/usage proxy
3 English Correction Agent → corrector.mjs + Write view (DeepL Write-like diff)
4 Real-Time Voice Translation → Voice view (Web Speech API + /api/translate loop)
5 Secure API key agent → security.mjs + key-vault.mjs (AES-GCM passphrase) + masked server handling
6 Context-aware AI agent → translator context/homograph disambiguation + context panel
7 Multi-agent architecture → orchestrator.mjs Coordinator + agent trace UI
8 PDF & document translation → documents.mjs (PDF Flate/Tj extraction) + /api/document + Documents view
9 Custom dictionary → glossary.mjs + /api/glossary CRUD + Glossary view
10 Live subtitles & transcripts → subtitles.mjs (SRT/VTT/TXT/JSON) + Voice overlay + exports
11 Language auto-detection → detect.mjs + badge + /api/detect
12 Production testing & optimization → node --test suites + Tests view (self-check runner) + usage meter

## ENGINE modules (build-engine)
`engine/index.mjs` — re-export all below + `export const VERSION="2.0.0"` + `export const AGENT_MANIFEST=[{id,name,description,version}, …8 agents…].

`engine/detect.mjs`
- `detectLanguage(text)` → `{lang:"en"|"de"|"fr"|"es"|"it"|"pt"|"hi"|"ja"|"zh", confidence:0..1, status:"success"|"insufficient_confidence"|"no_language_detected", scores:{lang:score}}`.
- Script detection first (Hiragana/Katakana→ja, CJK→zh, Devanagari→hi), then latin function-word scoring + diacritic boosts. ≤12 chars → likely `insufficient_confidence` (still best guess).

`engine/lexicon.mjs` — demo data only:
- `PHRASES`: sentences map: `{ hello: {en:"Hello",de:"Hallo",fr:"Bonjour",es:"Hola",it:"Ciao",pt:"Olá",hi:"नमस्ते",ja:"こんにちは",zh:"你好"} , … ≥20 common phrases (greetings, how are you, weather, thanks, names, business phrases) }` keyed by stable English phrase keys.
- `WORDS`: map `enWord → {de,fr,es,it,pt,hi,ja,zh}` for ≥120 words (core nouns/verbs/adjs: world, day, night, good, bad, beautiful, water, food, friend, family, book, city, home, work, time, money, love, happy, thank, please, yes, no, dog, cat, computer, internet, phone, meeting, project, team, email, question, answer, help, price, market, customer, contract, quality, security, translation, language, voice, document, glossary ...).
- `FUNCTION_WORDS`: `{en:[…20], de:[…], fr:[…], es:[…], it:[…], pt:[…], hi:[…], ja:[…], zh:[…]}` used by detect.
- `HOMOGRAPHS`: `{ bank: {finance:{de:"Bank"}, river:{de:"Ufer"}}, bass:{music:{de:"Grundton"}, fish:{de:"Barsch"}}, … 3+ entries }` with disambiguation trigger keywords each ({keywords:["river","shore","water"]}).
- Formality variants: `FORMALITY_HINTS`: e.g. `you:{de:{informal:"du",formal:"Sie"},…}` (only where meaningful).

`engine/translator.mjs`
- `translatePipeline(text,{sourceLang="auto",targetLang="de",formality="default",context="",glossaryEntry?=null})` →
 `{text, detectedSourceLanguage, coverage:0..1, usedFallback:boolean, notes:string[], charsBilled, agentTrace:[{agent,decision,ms}]}`.
- Pipeline: (1) detect when auto (reuse detect.mjs); (2) protect glossary entry (placeholder tokens via glossary.mjs API); (3) phrase-table lookup (whole sentence, case-insensitive, also on trimmed punctuation); (4) word-map translate preserving word count + capitalization + numbers/punct; homograph resolution with context.pack keywords when context present; (5) formality-aware pronoun replacement via FORMALITY_HINTS when affected tokens observed; (6) gluing: `coverage = translatedChars/sourceChars`; if coverage < 1 push note "Demo engine: partial coverage (N%); add a DeepL API key for full quality", set usedFallback when coverage<0.6. Deterministic — same input → same output (tests rely on it).

`engine/corrector.mjs`
- `correctEnglish(text,{mode:"correct"|"rephrase",style:"default"|"business"|"academic"|"casual"|"simple"})` →
 `{original,corrected,changes:[{type:"spelling"|"grammar"|"style"|"punctuation",before,after,description}], diff:[{kind:"eq"|"del"|"ins",value}]}`.
- ≥50-entry misspellings map (alot→a lot, recieve→receive, definately→definitely, seperate→separate, teh→the, untill→until, wierd→weird, beleive→believe, buisness→business, calendar, government…), `i`→`I`, double-space collapse, space before punctuation, missing space after sentence punct, duplicate consecutive word, capitalize sentence starts, terminal punctuation. Rephrase mode: style rewrites (business: expand contractions `won't→will not`; academic: `gonna/hafta→going to/have to`; casual: expand 2 contractions back? no—casual: collapse `will not→won't`, `do not→don't`; simple: split >28-word sentences at `;`/`, and`). Word-level LCS diff.

`engine/glossary.mjs`
- `export class GlossaryStore` — in-memory with `create(name)→id`, `remove(id)`, `add(id,{sourceTerm,targetTerm,sourceLang,targetLang})`, `list()→[{id,name,entries}]`, `get(id)`.
- `applyPre(text,{glossaryId,get}) → {text, map: Map placeholder→entry}` — replace source terms (case-insensitive, whole-word) with tokens `⟦g123⟧`.
- `applyPost(text,{map}) → {text,hits}` — restore target terms for surviving placeholders, count occurrences of target terms as hits.
- Persistence is server-side (data/glossaries.json), not here.

`engine/context.mjs`
- `buildContextPack({text, context="", glossaryEntry?=null})` → `{text,pack:{lastLine, keywords:string[], homographHints:{word,sense}|[]}}` — keywords = capitalized/domain words from context; homograph sense = HOMOGRAPHS sense whose keywords appear in context.

`engine/security.mjs`
- `validateKeyFormat(key)` → `{valid:boolean, tier:"free"|"pro"|null, host:"api-free.deepl.com"|"api.deepl.com"|null, reason?}` — DeepL keys: ≥32 chars `[\w-]+`, `endsWith(":fx")`→free. Empty/short → invalid.
- `maskKey(key)` → `"ab…" + last2` style masked.
- `redactKeys(text)`/`isKeyLike(str)`.
- `engine/key-vault.mjs` (browser-only; uses `crypto.subtle`; no Node imports):
 `encryptWithPassphrase(plaintext,passphrase)→{salt,iv,ct}` (base64, PBKDF2 150k, AES-GCM), `decryptWithPassphrase(blob,passphrase)→plaintext`, `saveVault(localStorageKey,blob,passphrase)`, `loadVault(localStorageKey,passphrase)`, `export const VAULT_KEY="talkflow.vault"`.

`engine/deepl.mjs` (Node or browser fetch; UI uses it ONLY via server proxy — enforced by code layout: UI imports server endpoints, not this file)
- `hostFor(key | tier)`, `translate({keyHost(or {key}), text, targetLang:"DE", sourceLang?, formality?, context?, glossaryId?})` → POST JSON `{text:[…]}` header `Authorization: DeepL-Auth-Key k` wait wait — exact header value is `DeepL-Auth-Key <key>`; parse `{translations:[{detected_source_language,text}]}`.
- `usage({key})` → GET `/v2/usage`.
- `writeCorrect({key or host, text, targetLang="EN-US"})`, `writeRephrase({...writingStyle?, tone?})` → POST `/v2/write/correct` / `/v2/write/rephrase`.
- Error mapping → `{status:"quota_exhausted"|"throttled"|"auth_invalid"|..., httpStatus}`.

`engine/documents.mjs` (SERVER-ONLY: dynamic `import("node:zlib")` inside function; throws if no zlib — fine for tests)
- `extractText({filename, bytes})` → `{text, meta:{kind:"pdf"|"txt"|"html"|"md"|"srt"|"vtt"|"json", pages?, warnings:[]}}`.
  - txt/md plain; html strip script/style/tags + entity decode; srt/vtt strip timecodes; json pull string values; **pdf**: scan `stream…endstream`, inflate FlateDecode via zlib.inflateSync (try/catch per stream), collect `(...)` literals from `Tj`/`TJ`/`T*`/`TD`/`Td` ops, join with spaces, heuristic paragraph breaks `TD`, unescape `\(`\)\\`, estimate pages by count of `/Type /Page`; set warning "Heuristic PDF text extraction (demo)" when suspicion of low quality. Errors → throw descriptive Error.
- `chunkSentences(text)→string[]` (split on [.!?。！？]\s boundaries, merge very short).
- `translateDocument({text, meta}, opts, translateChunk:(s,sentIdx)=>string)` → `{segments:[{source,target}], output:string, kind}` — txt/md/segments; html keeps tags around text nodes? NO — html: split document by tags, translate text-content-only chunks, re-join (preserve structure); pdf/txt: paragraph-level chunks.

`engine/subtitles.mjs`
- `toSrt(segments)` → blocks `i\n{HH:MM:SS,mmm} --> {HH:MM:SS,mmm}\ntext\n\n`
- `toVtt(segments)` → `WEBVTT\n\n00:00:00.000 --> …`
- `toTxt(segments)`, `toJson(segments)`, `parseTimeStr→ms` helper, `parseSrt(str)→segments`.
- segments: `{startMs,endMs,text,sourceTargetPairs?}` shape consumed by UI/server.

`engine/orchestrator.mjs`
- `export const AGENTS = [{id:"detector",…},{id:"context-aggregator",…},{id:"glossary-enforcer",…},{id:"translator",…},{id:"corrector",…},{id:"quality-guard",…},{id:"security",…},{id:"usage-meter",…}]` (id/name/description).
- `export class Coordinator { constructor({translator,corrector,store})` default wiring local engine ` }`
- `async runTranslate(task{text,sourceLang,targetLang,formality,context,glossaryId})`
  → `{result:{text,detected_source_language,coverage,notes,latency_ms,provider:"local"}, trace:[{agent:id,decision:str,ms,fields?}]}` — runs guard agents: security redaction check, detect step, context pack, glossary protect/apply, translate, quality guard (coverage gate + glossary hits), usage meter (charsBilled).
- `async runCorrect(task{text,style,mode})` → same shape.
- `makeLocalCoordinator()` factory.

`engine/engine.mjs` — aggregates re-exports of the whole engine (one import for server/UI/Tests).

## SERVER (build-server) `server/server.mjs`
- `node:http`, ESM; PORT = env PORT or 8096. Body JSON ≤10MB → else 413. Always `Content-Type: application/json; charset=utf-8` on /api.
- CORS: `Access-Control-Allow-Origin: *` + OPTIONS 204 handling on /api/*.
- Static: GET `/` and `/index.html` from app/, `/js/*` from app/js/, `/engine/*` from engine/ (browser imports), `/styles.css`; correct MIME map; reject `..`.
- Logging: `[time] METHOD /path → status (n ms) key=<masked if present>` — never raw key.
- Endpoints:
  - `GET /api/health` → `{status:"ok",version, uptime_ms, agents: count}`.
  - `GET /api/languages` → `{languages:[{code:"EN",name:"English"}, …for all 9 detect langs + target opts]}`.
  - `POST /api/translate` `{text,source_lang="auto",target_lang,formality="default",context="",glossary_id?=null,provider="local"|"deepl"}`
    - provider "local": Coordinator.runTranslate → `{text, detected_source_language, coverage, notes, agent_trace, latency_ms, provider}`.
    - provider "deepl": key = req header `X-Deepl-Key` or env `DEEPL_API_KEY`; none → 400 `{error:"no_key"}`; call engine deepl.translate; `{text, detected_source_language, provider:"deepl", latency_ms, chars_billed}`; map deepl errors → 456/429 passthrough `{error}`.
  - `POST /api/write` `{text, style, mode, provider}` — coordinator.runCorrect or deepl writeCorrect/writeRephrase → `{original,corrected,changes,diff,latency_ms,provider}` / deepl `{original, corrected(improvement text), latency_ms,provider}`.
  - `POST /api/detect` `{text}` → detectLanguage (no auto-translate).
  - `POST /api/deepl/validate` `{key?}` — if missing use env; validateKeyFormat → invalid 400 `{valid:false,reason}`; valid → live `usage({key})` catch → `{valid:true,tier,character_count,character_limit}` (network fail → `{valid:true,tier, live_check:"failed"}` 200).
  - `POST /api/deepl/usage` `{key?}` same live usage.
  - `GET /api/usage` → `{local:{chars_today, translations, corrections}, live?}` — in-memory counters since boot.
  - `GET /api/agents` → AGENT_MANIFEST (multi-agent listing for UI).
  - `GET/POST/DELETE /api/glossary` (+ `/api/glossary/{id}` and `POST /api/glossary/{id}/entries`): persisted `../data/glossaries.json` relative to server dir (mkdir as needed; read at boot). POST store `{name}`→`{id}`; POST entries `{source_term,target_term,source_lang,target_lang}`; DELETE deletes.
  - `POST /api/document` `{filename, content_base64, target_lang, source_lang?}` → decode; extract; translate chunks via coordinator translatePipeline (source auto; strip glossary); `{filename:"<name>-translated.<ext>", kind, text, segments, meta, latency_ms}`; errors 400 `{error}`; >5MB 413.
  - `POST /api/voice/export` `{segments, format:"srt"|"vtt"|"txt"|"json"}` → `{content}` (server-side builder; UI may build locally too).
- `tests/server.test.mjs` (node:test): spin server on port 0 (export `startServer()` + `if (process.argv[1]…)` guard for CLI run); assert STRUCTURE only (no specific translations!): 200 health has status ok+agents; /api/translate local 200 → text is string, agent_trace array, coverage number, detected_source_language length 2; /api/detect → lang field; /api/write → diff array + corrected string; glossary CRUD roundtrip (create/add/list/delete → 200/204); /api/document with fixture `tests/fixtures/hello.txt` → text nonempty + kind txt; 404 unknown api; static index.html 200 contains `<div id="app"`. No network calls to deepl.com in tests.

## UI (build-ui) `app/`
- `index.html`: shell `<div id="app">`, sidebar (logo TalkFlow 2.0 + 8 nav items + theme toggle), `<script type="module" src="/js/main.mjs">`. No framework; ES modules; hash routes.
- `styles.css`: DeepL-like dark navy sidebar `#0d1b2a`, teal accent `#0eb5a6`, cards, two-pane translator grid, caption overlay styles, diff styles (ins green/del red), trace chips, progress bars, responsive minimal. CSS variables theming (dark default, light toggle via `data-theme`).
- `js/api.mjs`: tiny fetch wrapper (+json, error handling, timeout).
- `js/vault.mjs`: secure API key agent UI — pass passphrase prompt; encrypt via `/engine/key-vault.mjs` import; store `{salt,iv,ct}` in localStorage; `getKey()` decrypt-on-use (never display full key; masked). Settings view uses `/api/deepl/validate`.
- `js/main.mjs` + views modules `js/views/*.mjs`: translator, write, voice, documents, glossary, usage, settings, tests.
  - **Translator**: selects (source Auto + 9 langs; targets all but same), textarea, live auto-detect badge (debounced /api/detect), char count, formality select, context collapsible panel, glossary dropdown, provider toggle (Demo/DeepL), Translate (Ctrl+Enter) → result pane + coverage bar + notes chips + agent trace accordion (from agent_trace) + latency.
  - **Write**: textarea + mode (Correct/Rephrase) + style select → diff view (del/ins spans) + changes table + copy button.
  - **Voice**: big mic toggle; Web Speech API (`webkitSpeechRecognition` w/ graceful unsupported warning); interim captions overlay (gray) → final segments (teal); each final → POST /api/translate (provider from settings; target = picked listen language); transcript table (time start-end, source, target); TTS speak button per row (speechSynthesis, target lang); exports SRT/VTT/TXT/JSON (build locally via `/engine/subtitles.mjs` import); headphone warning note.
  - **Documents**: file input (txt/md/html/srt/pdf ≤5MB), target lang, translate → result pane + download `<name>-translated.txt` (blob URL) + meta warnings shown.
  - **Glossary**: list stores; create; per-store table of entries; add entry form; delete store; all through /api/glossary.
  - **Usage**: bars from /api/usage; live DeepL quota when key validated (from /api/deepl/usage).
  - **Settings**: API key config (vault: passphrase, encrypted save, validate live button, tier+quota display, masked visual), server URL, theme, About (agents list from /api/agents).
  - **Tests** (Production testing tab): buttons run self-checks (health, detect, translate roundtrip EN→DE non-empty, write diff, glossary CRUD, document fixture-free roundtrip using inline text, deepl validate — only if key) → pass/fail + ms table (all green goal).
- Keep JS lean; ~≤120 lines per view file target (soft); real implementations only, no fake data.

## Acceptance (integrator)
`npm test` (tests dir) passes ≥ 30 tests; `npm start` boots; UI loads via browser smoke; every /api endpoint exercised; zero deps in node_modules (package.json has none).
