# TalkFlow Codebase Audit — upgrade targets for DeepL parity
From agent A2 (Oct 25 2026). IMPORTANT: this project was already built by earlier
agent runs ("globaltalk-ai"); the canonical backend is `services/api`, NOT the
legacy `apps/api`/`ai/` mirror. Never run both lanes at once.

## Environment facts
- Canonical backend: Python 3.11+ FastAPI (services/api/app/main:app; Pydantic v2,
  SQLAlchemy async, Alembic, pyjwt, bcrypt, orjson, websockets 13).
- Backend deps: plain pip, `services/api/requirements.txt` (+/-dev/-gpu).
- Frontend: apps/web — React 18.3 + Vite 5 + TS 5.5 strict + Tailwind 3.4 +
  TanStack Query 5 + Zustand 4 + livekit-client 2.22 + CopilotKit 1.73.
 Providers live in `services/api/gt_ai/*` (registry + model_router +
 stt/tts/translation/detection/embeddings/summarize/vad). Cached weights already
 under `services/api/model_cache/` (whisper-small CT2, nllb-200-600m CT2 int8).
- npm workspaces; root Makefile; pyproject (pytest/ruff/pyright); docker compose.
- Start: `python run_api.py` (→ http://127.0.0.1:8088, docs /api/docs) or
  `make dev` (API :8000 + Vite :5173, Vite proxies /api + /ws). On Windows:
  `START_ALL.bat`. `DEV_LEGEACY` not needed; ignore apps/api entirely.
- `make migrate` — Alembic in services/api; `alembic check` must pass.

## Existing features that ALREADY satisfy DeepL-equivalent roles
| Area | Files | Status |
|---|---|---|
| Translation Agent | app/routers/translate.py + v2_*.py (Desi-parity /v2/translate etc), services/translation_service.py (validate → TM fuzzy → glossary → style → translate → persist), gt_ai/translation/{nllb_ct2, madlad400, argos, azureTranslator, http, dev_echo…} | working |
| API key config | env-only config.py (DEEPL_API_KEY etc); platform.py keys_router (per-user API keys, hashed) | partial |
| Write/correction | app/routers/write.py, services/write_service.py (~1900 lines: sentence segmentation, capitalization, punctuation, protected spans, alternatives, LLM rewrite hook), v2 /write/rephrase + /write/correct endpoints | working |
| Realtime voice | app/realtime/: ws.py, protocol.py (ServerEvent/ClientEvent), session_manager (RtSession/RtParticipant), agents/{listening,translation,voice,supervisor,inference_gate,bus}.py, translation_fanout, livekit_bridge, pipeline.py | working (offline lane, e2e-proven) |
| Secure keys | security.py hash-only user keys | partial (no provider-cred vault) |
| Context agent | assistant router + agents/prompt_composer.py + TM/glossstyle into translation | partial |
| Multi-agent | app/agents/* realtime agents + agent_studio bridge + multi-agent-portfolio + telephony agent graph | working/partial |
| Documents | routers/documents.py, services/document_service.py, workers/document-worker, parsers pypdf/docx/pptx/openpyxl/fpdf2 (+optional docling) | working |
| Glossary | routers/customization.py + v3 glossaries in v2_v3.py, models Glossary/GlossaryTerm/StyleProfile/TranslationMemory | working |
| Subtitles/transcripts | WS events transcript.partial/final + caption.updated; SRT/VTT/TXT/JSON export | working |
| Auto-detect | gt_ai/detection (fasttext+langid+langdetect fusion), audio LID | working |
| Testing | tests/unit+integration+realtime+e2e (Playwright)+~80 hardened test_*.py, scripts: verify_ai_stack, probe_e2e, benchmark_live_translation, load_drill_realtime, run_evaluation (BLEU/WER/CER golden_india_pairs), verify_language_coverage | strong |

## Prioritized gaps to close for DeepL parity (12 areas)
1. API Key Configuration + Secure vault — no per-org provider credential store,
   no runtime UI to add/rotate provider keys; no rotation/encryption-at-rest.
2. Write multilingual coverage — route existing LLM hook for non-English
   rephrase/correct; surface writing_style/tone enums like DeepL.
3. Documents — parity endpoints /v2/document(play) with document_id/key, status
   polling, one-shot download; DOCX style preservation; output_format=docx PDF
   conversion; 50K-char billing minimum accounting.
4. Realtime voice — DeepL-style session API (/v3/voice/realtime → wss URL +
   one-time token), chunk cadence 50–250 ms caps, concluded/tentative updates,
   optional 1-target TTS stream, minute billing in usage endpoint.
5. Context-aware — `context` param semantics (unbilled contextual text for
   disambiguation), mutual exclusion with glossary-detection, style_profile_id.
6. Glossary v3 hardening — dictionationaries per pair, TSV/CSV entries, PATCH
   merge vs PUT replace semantics, ≤5 glossary_ids priority, case/variant rules.
7. Auto-detect UX — confidence surfaced UI hint; mutual exclusion with glossary.
8. Subtitles ingestion — translate .srt/.vtt as document sources (DeepL does).
9. Usage endpoint — /v2/usage shape (character_count/limit + per-product
   minute counts + start_time/end_time) driven by real metering.
10. Production practices — backoff+jitter; never retry 456/400; caching layer;
    batch ≤50/128K; response deltas; consistent error JSON {message, code}.
11. Multi-agent — telephony turn-loop follow-up (AGENTS.md); avoid legacy lane.
12. Quality eval — add per-segment quality evaluation report (severity/type/
    spans) next to BLEU/COMET; regenerate README capability table automatically.

## Benchmarks to fill (the repo's own scorecards)
- README "✅ Verified Capability Status (CPU Sandbox)" table.
- replica/features.csv — columns: feature,area,priority,original,clone,notes
  (19 rows; must/should/could).
- replica/parity.md — "Parity: 100.0/100" per-area scores + missing-in-build-order.
- replica/test-plan.md — case|flow|type|steps|expected|auto|result (17/17 PASS).
- scripts/verify_ai_stack.py runtime honesty table (component/status/note/hint).

## Exact test commands
```bash
make test-unit            # pytest tests/unit -q                      (~40s)
make test-integration     # pytest tests/integration -q
make test-realtime        # pytest tests/realtime -q -m realtime      (needs models)
cd services/api && python -m alembic upgrade head && python -m alembic check
cd apps/web && npx tsc -b
cd apps/web && npm run e2e     # Playwright — needs docker compose stack
python scripts/verify_ai_stack.py --quick
python scripts/probe_e2e_features.py   # demo@globaltalk.local / demo1234
```
Windows note: bash scripts exist; use `START_ALL.bat` / `bootstrap_full_ai.ps1`,
or plain commands above. Model weights are cache-first: more pairs require
`scripts/download_models.ps1`; default `MODEL_CACHE_PATH` must NOT be
/tmp on Windows — point it to `services/api/model_cache` (already has weights).

## Hard rules for the upgrade work
- Never touch `apps/api` or `ai/` (legacy, drifted). Only `services/api/**`,
  `apps/web/**`, `scripts/**`, `tests/**`, `packages/**`.
- Never install huge new model weights at build time.
- Keep dev-echo/offline fallbacks honest (verify_ai_stack, private-only rules).
- account for port soup: canonical config default 8088 vs .env 8000 (use 8000
  for make dev flows; ARI also 8088 → don't fight it, document).
- Demo creds only seeded when ALLOW_TEST_AUTH/ALLOW_SEED explicitly on.
