# TalkFlow 2.0 — DeepL-inspired Translation Suite

A zero-dependency, feature-complete translation web app inspired by DeepL's Language AI platform, built as the next generation of [TalkFlow / GlobalTalk AI](https://github.com/Aman678317/TalkFlow).

**Status: verified 2026-10-25** — 103/103 automated tests pass with 0 skipped, all 8 views boot on localhost, and the core journeys were exercised in a real browser (Translate, Write, Glossary, Documents, Usage, Settings, Tests). See [`TEST_REPORT.md`](TEST_REPORT.md).

## Feature pillars (all 12 implemented)

| # | Pillar | Where |
|---|--------|-------|
| 1 | **Translation Agent** | `engine/translator.mjs` + `engine/orchestrator.mjs` + Translator view — demo multilingual engine (9 languages) with optional **real DeepL API** pass-through |
| 2 | **API Key Configuration** | Settings view + `engine/deepl.mjs` (`api-free.deepl.com` vs `api.deepl.com`, `POST /v2/usage` validation, tier detection) |
| 3 | **English Correction Agent** | `engine/corrector.mjs` — DeepL Write-style corrections with word-diff + rephrase modes/styles |
| 4 | **Real-Time Voice Translation** | Voice view — Web Speech STT → live translation loop → speechSynthesis TTS |
| 5 | **Secure API key agent** | `engine/security.mjs` + `engine/key-vault.mjs` (AES-GCM via WebCrypto, passphrase-derived; masked everywhere; server never logs keys) |
| 6 | **Context-aware AI agent** | `engine/context.mjs` — context panel, homograph disambiguation, glossary-aware translation |
| 7 | **Multi-agent architecture** | `engine/orchestrator.mjs` Coordinator (8 agents with live decision trace) + agent trace UI |
| 8 | **PDF & document translation** | `engine/documents.mjs` (TXT/MD/HTML/SRT/VTT/JSON + heuristic PDF text extraction via zlib) + `/api/document` + Documents view |
| 9 | **Custom dictionary** | `engine/glossary.mjs` + `/api/glossary` CRUD (persisted) + Glossary view |
| 10 | **Live subtitles & transcripts** | Voice captions overlay (tentative vs concluded) + SRT/VTT/TXT/JSON exports (`engine/subtitles.mjs`) |
| 11 | **Language auto-detection** | `engine/detect.mjs` (script + function-word scoring) + detected badge + `/api/detect` |
| 12 | **Production testing & optimization** | 103 `node:test` cases + built-in Tests view + usage metering + latency display |

## Quick start

```bash
cd talkflow2
npm start        # http://127.0.0.1:8096
```

Open http://127.0.0.1:8096. Optionally configure a real DeepL API key in **Settings**
(free keys validated against `api-free.deepl.com`, pro against `api.deepl.com`). Without a key,
the built-in demo engine still translates with honest coverage reporting.

## Tests

```bash
npm test         # node --test tests/  (engine + server suites)
```

Verified result: **103 passed, 0 failed, 0 skipped, 0 todo** (24 core + 33 tools + 24 docs + 22 server).

## Architecture

```
talkflow2/
├── engine/          # pure ESM: detect, lexicon, translator, corrector, glossary, context,
│                    # security/key-vault, deepl client, documents, subtitles, orchestrator
├── server/          # node:http server (static app/ + /engine/ + REST /api/*)
├── app/             # vanilla JS SPA (8 views) + DeepL-style dark/teal theme
├── tests/           # node:test suites + fixtures (txt/html/srt/pdf)
├── scripts/         # fixture generation
└── SPEC.md          # exact shared build contract
```

## Design notes

- **Honest by default**: the demo engine reports coverage % and says so when partial — it never fakes quality. Glossary-restored terms count toward coverage.
- **CORS reality respected**: DeepL API keys are used through the local server proxy (browser-direct calls to DeepL are rejected), mirroring production practice.
- **Security model**: keys are AES-GCM-encrypted at rest in the browser vault, masked in transit logs, and scrubbed server-side via `redactKeys`. The server accepts a key from `X-Deepl-Key` or `DEEPL_API_KEY`.
- **No dependencies**: `package.json` declares none; the app runs on Node >= 18.

## Known limitations (honest)

- No live DeepL key was available, so live translation/Write/quota calls and DeepL error mapping were verified only with stubbed `fetch` and the local demo engine.
- Voice live microphone capture was not exercised in the headless QA browser; the graceful idle/unsupported states were verified instead.
- The demo lexicon covers 9 languages and a bounded vocabulary; coverage is reported rather than hidden. A real DeepL key provides full-quality translation.
- The main FastAPI TalkFlow app has separate, documented P0 gaps (see `../deepl_parity/STATUS_CORRECTION.md`); this standalone app does not silently claim to fix them.

## Benchmarks & analysis inputs

- `../analysis/DEEPL_ANALYSIS.md` — DeepL product/API dossier
- `../analysis/REA_DEEPL_FINDINGS.md` — REA 6.7.0 evidence and 12-pillar contract matrix
- `../analysis/TALKFLOW_GAP_REPORT.md` — verified main-repo gap audit
- `../analysis/TALKBENCHMARK.md` — TalkFlow (GlobalTalk AI) repo audit
