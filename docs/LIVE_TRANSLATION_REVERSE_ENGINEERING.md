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
