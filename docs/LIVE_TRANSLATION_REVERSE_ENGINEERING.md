# DeepL live translation — runtime evidence and TalkFlow design

Observed on 2026-10-23 against `https://www.deepl.com/en/translator`
(unauthenticated free tier) from the in-app browser. Evidence comes from a
main-world instrumentation script injected at document start that wrapped
`WebSocket` (`send` + `message`) and `fetch`/`XMLHttpRequest`; timestamps are
page-relative `performance.now()` milliseconds. This is **runtime observation
of the delivered page**, not access to DeepL source, servers, or documentation.

## 1. What was observed

### 1.1 Transport

A single persistent WebSocket carries interactive translation:

```
wss://ita-free.www.deepl.com/v2/sessions?s=<session-uuid>&p=2&i=<opaque-token>&client=<client-uuid>
```

- `ita-free` host (free tier); query string carries a session token.
- First frame sent by the client is text:
  `{"protocol":"messagepack","version":1}`
- Every following frame in both directions is **binary MessagePack**. Printable
  strings extracted from the frames expose the RPC method names
  `Participate`, `AppendRequest`, and `AppendResponse`.

### 1.2 Request cadence — per edit, no button, no long debounce

Each input change produced an `AppendRequest` within roughly 0.1–1 s of the
edit (the instrumentation environment was slow, so absolute gaps include page
overhead). The client sent one frame per newly typed word/segment:

| Typed text reaches | Client `AppendRequest` | Frame | Payload string |
|---|---|---|---|
| `Live translation` | t=10600 | 62 B | `...AppendRequest..."...translation` |
| `... should` | t=10900 | 57 B | `...AppendRequest...should` |
| `... update` | t=11814 | 57 B | `...AppendRequest...update` |
| `... as` | t=12850 | 53 B | `...AppendRequest...as` |
| `... I` | t=13801 | 52 B | `...AppendRequest...I` |
| `... type` | t=15786 | 55 B | `...AppendRequest...type` |
| `... without` | t=16764 | 58 B | `...AppendRequest...without` |
| `... pressing` | t=17770 | 60 B | `...AppendRequest...pressing` |
| `... a` | t=18819 | 53 B | `...AppendRequest...a` |
| `... button` | t=19765 | 58 B | `...AppendRequest...button` |

- Frames are 49–62 bytes and contain only the appended delta plus a sequence
  id (`0`, `1`, `2`, … encoded as MessagePack strings). **Inference:** the
  server keeps per-session state; the client does not resend the document.
- No debounce window was observed on the wire: typing pauses did not delay the
  next append, and translation began before the sentence was finished.

### 1.3 Response — revised translations, not append-only tokens

Server frames include small acknowledgements and larger `AppendResponse`
payloads containing the translated text. For the German target the same
sentence was revised twice as more source text arrived:

| Server time | Rendered target text |
|---|---|
| t=16249 | `Die Live-Übersetzung sollte sich während der Eingabe aktualisieren` |
| t=19924 | `... aktualisieren, ohne dass ich die A-Taste drücken muss.` |
| t=20394 | `... aktualisieren, ohne dass ich eine Taste drücken muss.` |

The final revision differs from the previous one (“eine Taste” instead of
“die A-Taste”), so the server **re-translates and replaces** the displayed
result rather than only appending tokens. The UI must therefore render the
latest revision for a sequence number, not concatenate blindly.

A 1456-byte `AppendResponse` at t=15957 contained a language-pair capability
list, i.e. the same socket also bootstraps supported languages.

### 1.4 Session resilience

The first socket reported `open` then `close:1000`; the client immediately
opened a second socket with the **same session id** and continued with
`AppendRequest` sequence 1, 2, 3. **Inference:** the session is resumable and
the sequence counter is server-reconciled.

### 1.5 What is *not* the live path

An XHR to `https://www2.deepl.com/jsonrpc?method=LMT_handleAdditionalData`
fires after translation with a `translationState` payload:

```json
{"version":"v1","type":"translationState",
 "lang":{"source":"en","target":{"lang":"de","variant":"de-DE"},...},
 "sourceText":"Live translation should update ...",
 "targetText":"Die Live-Übersetzung sollte ...",
 "rawCharacterCountSourceText":139,"rawCharacterCountTargetText":180,
 "trigger":"newSourceText"}
```

The response is `{"jsonrpc":"2.0","id":...,"result":null}` — this is state
reporting/telemetry, not the translation transport. A separate
`https://w.deepl.com/web?...method=getClientState` call bootstraps account /
feature state.

## 2. Mechanism summary

| Observation | Conclusion |
|---|---|
| WS opens before typing, one socket per page session | Persistent duplex channel |
| MessagePack handshake, `Append*` methods | Stateful append protocol |
| One small frame per edit, delta only | Client streams edits; server stores session state |
| Server sends progressively revised target text | Retranslation with last-write-wins revisions |
| Socket reconnects with same session token | Resumable session |
| JSON-RPC call contains both texts after the fact | Telemetry only |

**Unknowns (not claimed):** the full MessagePack schema, how `i` is derived,
server-side debounce/scheduling thresholds, whether the server speculatively
decodes ahead of the visible text, and rate-limit policy. Those would require
server-side access or a much deeper protocol decode.

## 3. What TalkFlow implements (and why it differs)

DeepL’s exact protocol is proprietary and session-authenticated. TalkFlow
implements the same *user-visible contract* — translate while typing, show
progressively refined text, never require a submit button — over a standard,
inspectable HTTP interface:

- `POST /api/v1/translate/stream` → `text/event-stream` (SSE over `fetch`,
  so the request body and auth headers are normal HTTP).
- Events: `meta` (detected language / request id), `draft` (fast translation
  of the stable prefix, marked as provisional), `ping` (keep-alive while the
  final translation runs), `done` (final `TranslationOut`), `error` (typed
  error contract). The client aborts the in-flight stream on the next edit;
  `done` is the only event that is persisted/metered and only `done` replaces
  the final result.
- The UI keeps the previous translation visible while a new stream runs
  (stale-while-revalidate), so keystrokes never blank the result panel.
- Drafts come from the longest complete-sentence prefix; the final pass
  retranslates the whole text through the existing pipeline (TM, glossary,
  style, QA, persistence) — mirroring DeepL’s revision behavior without
  copying its transport.

Rationale for SSE instead of a bespoke WebSocket: it reuses the existing
authenticated HTTP path, works through the Vite proxy and serverless
platforms, is trivially observable (benchmarks can read raw frames), and the
per-edit request model gives the same UX without maintaining server state.

## 4. Measured behavior vs DeepL

Reproduce with the backend running and Argos packs installed
(`scripts/download_models.sh`):

```
ARGOS_WARM_PAIRS=en:de,en:fr,en:es python run_api.py   # optional startup priming
python scripts/benchmark_live_translation.py --pairs en:de en:fr en:es --repeat 3
```

Each measured pass sends a cache-busting nonce, so the numbers are model work,
not cache hits. Provider on this machine is `argos` (CTranslate2, CPU, fully
offline); text is the same ~250-character, four-sentence paragraph.

| Condition | Time to first draft | Final result |
|---|---|---|
| Unprimed, first request ever for a pair | 4.4 – 9 s | 4.4 – 9 s |
| First request after `ARGOS_WARM_PAIRS` priming | 439 – 2780 ms | 968 – 3383 ms |
| Warm, median of 3 (en→de / en→fr / en→es) | 695 / 788 / 473 ms | 1615 / 1411 / 816 ms |
| Cached identical text | no draft (final wins) | 20 – 186 ms |
| Short sentence, warm (REST) | — | 157 ms model / 202 ms wall |
| Browser UI, live typing (`/translate`, EN→DE) | 763 ms | 1959 ms |


Under 7 overlapping streams (5 of them the same pair) every stream still
delivered a draft and a final, and none fell back to a dev provider; the
slowest same-pair final degraded from 1.77 s to 8.82 s because the CPU is
shared. That is the honest ceiling of a local-CPU deployment.

Against the DeepL observations in §1.2–1.3:

| Dimension | DeepL | TalkFlow |
|---|---|---|
| Trigger | every edit, delta-only frame, no debounce | 350 ms idle, then one stream per text state |
| Superseded work | client keeps session state server-side | in-flight stream aborted by the client |
| Progressive output | continuous partial revisions (~0.5–3.7 s apart here) | one stable-prefix draft, then one final |
| Latency to first visible target | sub-second on hosted GPUs | 0.47–0.79 s on local CPU once primed |
| Revision semantics | last-write-wins replacement | last-write-wins replacement (`done` replaces draft) |

The remaining gap is *number of revisions*, not transport: DeepL re-translates
each appended fragment, so a long paragraph updates many times. TalkFlow
currently emits exactly one draft per text state. Closing the gap is a
scheduling change, not a protocol change — emit a draft per newly stable
sentence while the final pass runs.

`ARGOS_WARM_PAIRS` exists because the first use of a pair loads the
CTranslate2 weights and the stanza sentencizer; `AIFacade.warmup()` now primes
the private, runtime-ready providers in the auto chain so local traffic does not
land on a cold model.

## 5. Defects found while measuring (all fixed)

- **Draft/final overlap crashed the offline chain.** The live path runs the
  draft and final passes concurrently; `argostranslate.translate.translate()`
  rebuilt its `Translation` per call, so stanza re-downloaded and
  `os.replace()`d `resources.json` twice at once and raised
  `PermissionError [WinError 5]`. The chain then failed over to `dev_echo` and
  the UI correctly reported "Translation unavailable". Fixed by caching one
  `Translation` per pair and serialising only the cold init
  (`gt_ai/translation/argos.py`).
- **Superseded streams leaked provider work.** `_translate_stream_events`
  re-raised `CancelledError` without cancelling its child tasks, so aborted
  keystrokes kept translating. Fixed with a `finally` that cancels and awaits
  both tasks (`app/routers/translate.py`).
- **Duplicate identical stream requests per edit.** A React effect re-ran on
  re-render and aborted the stream it had just started; now keyed on the full
  text+settings tuple (`apps/web/src/pages/Translate.tsx`).
- **Startup warmed the wrong provider.** `AIFacade.warmup()` only pre-loaded the
  *configured* provider, which is normally a hosted API, so the offline packs
  that local traffic actually uses stayed cold and their first request paid
  4–9 s. It now also primes private, runtime-ready providers
  (`ARGOS_WARM_PAIRS` selects argos pairs; RAM grows per primed pack, so it is
  opt-in).
- **A ~2.4 s phantom latency floor in tooling.** Python clients hitting
  `http://localhost:8088` stall on IPv6 before falling back to IPv4; the
  backend listens on IPv4 and the Vite proxy already targets `127.0.0.1`, so
  only scripts were affected. The benchmark pins `127.0.0.1`.
- **`.lower()` on language codes erased the only script-distinct pair.**
  `translate_text()` and `_translate_stream_events()` normalised with
  `.lower()`, so `zh-Hant` became `zh-hant`, missed the capability registry
  (keyed by code) and answered 422 `unsupported_language` — for the one
  language where case carries meaning. Both call sites now use
  `normalize_lang()`, which folds locales, tokens and casing onto the registry
  code and preserves it (`app/services/translation_service.py`,
  `app/routers/translate.py`).
- **`normalize_lang()` returned model tokens as codes.** A detector result
  like `mar_Deva` hit the `raw in _BY_TOKEN` branch and came back unchanged,
  which the registry reads as an unknown language. Tokens now resolve to the
  registry code, and the case-insensitive lookup runs *before* the region
  subtag is stripped, so `ZH-HANT` no longer folds into Simplified
  (`gt_ai/translation/nllb_languages.py`).
- **CTranslate2's `translate_batch()` has no `source_lang` argument.** The
  adapter passed one (and `target_prefix=[str]` instead of a list per
  example); the branch had never executed because no checkpoint was on disk
  until now. NLLB's encoder language token is part of the *input*, and this
  checkpoint has `add_source_eos: false`, so the caller appends `</s>`.
- **`import ctranslate2` before `transformers` segfaults on Windows.**
  Exit 139 inside `AutoTokenizer.from_pretrained` (ctranslate2 4.8.1 +
  tokenizers, bisected 2026-10-24): translator-first is fine, tokenizer-first
  is fine, both in that order is not. The adapter now tokenizes with
  `sentencepiece` directly and never imports `transformers`, which also drops
  the requirement for the 2.4 GB fp32 HF repo. **Do not import `transformers`
  into a process that has already imported `ctranslate2`.**
- **A 20 s attempt deadline is shorter than one CPU beam search.** A
  low-resource NLLB target measures 3–14 s on this 7.8 GB box; under memory
  pressure it crossed the generic per-attempt timeout, failed over to argos (no
  pack installed) and landed on `dev_echo` — "the language does not work" for a
  language the model serves fine. Self-hosted MT now has its own attempt budget
  (`MT_LOCAL_ATTEMPT_TIMEOUT_S`, default 45 s) and beam search defaults to 2
  (`NLLB_BEAM_SIZE`) rather than 4 (`app/ai.py`, `gt_ai/translation/nllb_ct2.py`).
- **The DB connection was held across the model call.** `translate_text()` used
  one session for detection, TM, glossary, the provider call and the write, so
  a 3–10 s decode parked a QueuePool checkout for its whole duration. Eight
  concurrent live streams (two sessions each) exhausted SQLite's 5 + 10 pool and
  the API answered `internal_error: Translation failed`; the pool timeout, not
  the model, was the failure. The session is now committed and released before
  the provider call and re-acquired for the write
  (`app/services/translation_service.py`).
- **A provider excluded for errors could never come back.** `record_outcome()`
  only re-enables a provider on a routed success, and routing skips unavailable
  providers, so the exclusion was self-locking. A concurrent benchmark tripped
  it, and the very next single-shot REST request answered `dev_echo` in 50 ms.
  Worse, `AIFacade` re-affirms the exclusion while it assembles each failover
  chain, which reset any cooldown clock on every request. Exclusions now carry a
  timestamp, reaffirmation does not restart it, and after
  `PROVIDER_REPROBE_AFTER_S` (default 30 s) the provider is re-admitted with
  clean counters (`gt_ai/model_router/router.py`).
- **The panes laid RTL scripts out left-to-right.** The registry already knows
  which languages are right-to-left (`LanguageCapability.rtl`, true for `ar`,
  `fa`, `he`, `ps`, `sd`, `ug`, `ur`, `yi`, `ckb`, `prs`), but neither pane read
  it, so an Arabic translation sat flush-left with its full stop on the wrong
  side — visible in the browser at 2026-10-24 while verifying `ta→ar`. Both
  panes now set `dir` from the selected language (the source follows the
  detected language while `AUTO` is active), and
  `apps/web/src/pages/TranslateDirection.test.tsx` pins the behavior.

## 6. Measured capacity of the local model

One 600M int8 model on 4 CPU cores, 262-character source, beam 2
(`scripts/benchmark_live_translation.py`, 2026-10-24, backend on :8088):

| pair | TTFD (median) | total (median) |
| --- | --- | --- |
| ja→en | 2.6 s | 6.1 s |
| de→en | 2.6 s | 6.4 s |
| zh-Hant←en | 3.1 s | 5.6 s |
| en→sw | 4.0 s | 8.5 s |
| en→de | 4.5 s | 8.9 s |
| en→hi | 4.6 s | 9.0 s |
| en→ta | 4.8 s | 10.3 s |
| en→ar | 5.3 s | 9.9 s |
| en→sr | 4.9 s | 8.6 s |
| en→glg | 5.7 s | 9.6 s |
| en→tk | 5.2 s | 10.3 s |

(2026-10-24 final sweep: warm medians on 12 stream pairs sampled across the
added inventory — `en:sr en:glg en:tk` verified alongside the historical rows.)

That is DeepL-shaped in behaviour (draft before final, revised output, one
request per edit) but not in speed: DeepL answers in tens of milliseconds
because it serves a fleet of GPUs, and this box serves one CPU model. The
concurrent pass measures the ceiling — 12 simultaneous streams, each opening a
draft and a final, push individual decodes past the attempt budget.

Measured overload and recovery, same hardware, 2026-10-24: a single short
request answers in 1.8 s; a 12-stream storm takes 47.5 s wall clock; the
request fired immediately after the storm lands on `dev_echo` because the model
is still inside its 30 s exclusion window; 35 s later the same request is served
by `nllb_ct2` again and stays served. Degradation under overload is honest and
**self-healing** — which it was not before the cooldown existed, when the same
storm silently disabled local MT until the process was restarted.

## 7. Language coverage: what "all languages" means here

DeepL's public list is ~35 languages. The request was ~120 including
Acehnese, Konkani, Kapampangan, Latin and Aragonese, in both directions.
`nllb_ct2` (NLLB-200 distilled 600M, CTranslate2 int8, 622 MB) serves 119 of
them (115 after the first pass, +4 from §7.1) from one model with no English
pivot, which is why it was chosen over
per-pair Argos packs and over MADLAD (4.4 GB, ~1.1 GB RAM headroom left).

- The table is `gt_ai/translation/nllb_languages.py`; every token in it was
  checked against the checkpoint's own `special_tokens_map.json` (202 tokens),
  and `checkpoint_codes()` derives coverage from disk rather than from the
  table, so a subset checkpoint cannot advertise more than it serves.
- Regional variants (`en-GB`, `es-419`, `fr-CA`) are *accepted* but not
  listed as separate languages: NLLB has one `eng_Latn`, and offering
  "English (American)" alongside "English" would promise an accent the model
  does not have.
- `/api/v1/languages` intersects the registry with `AIFacade.served_languages()`,
  so the picker only ever shows a language a runtime-ready provider covers —
  the "show only what works" rule, enforced by construction instead of by
  review. Without the checkpoint the extra ~95 languages disappear.
- Speech statuses are untouched: a text model's vocabulary is not evidence of
  a working TTS/STT voice, and those rows are still earned by the evaluation
  harness.
- Licence: NLLB is **CC-BY-NC 4.0**. Fine for this local build; a commercial
  deployment must swap `nllb_ct2` for a licensed MT provider before shipping.

Verification is `scripts/verify_language_coverage.py --all`, which translates
pivot→language→pivot per advertised code through the same routing the UI uses
and rejects empty output, output that is the input, output in the wrong Unicode
script, and any `dev_echo`/fallback provider. `--live` also exercises the SSE
path the UI types into.

Run on 2026-10-24 against this install: **115/115 passed** both directions,
provider `nllb_ct2` for every one of them, and the `--live` sample over
`ar he ckb fa zh zh-Hant ja ko hi ta sw de` passed on the stream path too.

The same day, the feature was driven by hand in the browser on
`http://127.0.0.1:5173/translate` through the SSE path, typing into the upper
pane and reading the lower one: `en⇄ta`, `ta⇄ar`, `ar→ta`, `en⇄zh-Hant`,
`zh-Hant→en`, `en⇄ace` — every one answered from `nllb_ct2` in 1.7–6.5 s for a
single sentence, and `Swap languages` reversed direction on each. Two of those
were the point: `zh-Hant` produced 圖書館 (Traditional) rather than the
Simplified row the `.lower()` defect used to serve, and `ace` — a language the
benchmark had previously dropped to `dev_echo` — answered in the UI as well as
it does in the sweep.

### 7.1 Completing the requested inventory (2026-10-24)

The user request listed the full DeepL public table (~35 languages), the wider
multilingual extensions and every DeepL regional variant, for both panels.
Cross-checking that list against this checkpoint's own vocabulary (202 language
tokens) surfaced four listed languages the registry had not yet surfaced, each
verified present in `special_tokens_map.json` before being added:

| Added | code | token |
|---|---|---|
| Galician | `glg` | `glg_Latn` |
| Irish | `gle` | `gle_Latn` |
| Serbian (Cyrillic script, as DeepL default) | `sr` | `srp_Cyrl` |
| Turkmen | `tk` | `tuk_Latn` |

Registry and advertised coverage: **119 codes**, plus the six DeepL regional
variant rows (`en-US`, `en-GB`, `de-CH`, `es-419`, `fr-CA`, `pt-BR`) exposed as
`PICKER_VARIANTS` on `/api/v1/languages`. Every variant aliases a served base
language the request path folds through `LOCALE_VARIANTS` (`pt-BR`→`pt`,
`de-CH`→`de`, …), so a variant can only appear on offer while the model that
translates the base is actually running — picking "English (British)" cannot
work worse or differently than "English", it just names the convention like
DeepL does.

Four requested languages remain honestly absent because this checkpoint
cannot serve them: **Latin** and **Aragonese** (no token in the NLLB-200
released table) and **Breton** and **Konkani** (in NLLB-200 but not in this
distilled conversion). No row is shipped for them — the alternative was a
picker entry that answers `dev_echo`, the exact lie §7's rule exists to
prevent. They can be served later by adding a licensed provider that covers
them (the provider chain is already failover-ready); the registry would add
rows the same day the provider proves the language.
