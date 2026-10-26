# TalkFlow vs DeepL: 12-Pillar Gap Report

- Audit date: 2026-10-25
- Repo: `C:\Users\acer\omnirush.ai\TalkFlow` (github.com/Aman678317/TalkFlow)
- Branch / HEAD: `feat/deepl-parity-hardening-2026-10-25` / `54de0f6`
- Scope: canonical backend `services/api/app`, frontend `apps/web`, tests, CI. Legacy `apps/api` and root `ai/` were not treated as canonical.
- Method: read-only static audit with Grep/Read. No tests, migrations, Docker, builds, or network calls were run. Line numbers are from this checkout.

## 1. Executive summary

- 12 pillars: **4 CLOSED, 7 PARTIAL, 1 OPEN**.
- Granular gap register: **24 items = 5 CLOSED, 7 PARTIAL, 12 OPEN** (3 P0, 10 P1, 6 P2, plus 5 closed confirmations).
- The three material failures are:
  1. The provider-credential ("secure API-key agent") stack is dead code: no ORM model, no route, no UI, and the service raises `NameError` if called.
  2. The DeepL-shaped `/v2/document` three-call flow does not translate anything and does not verify `document_key`; it returns the uploaded bytes with `status="done"`.
  3. The parity migration adds a second Alembic base and new columns/tables that do not exist in the ORM, so the production migration lane is structurally broken and parity stores remain in-memory.
- Test volume is real and large (1,039 Python test functions, 272 web cases), but there is no coverage measurement, the named parity tests in `deepl_parity/FINAL_REPORT.md` do not exist, and the one real parity suite asserts the fake document behavior.

## 2. Verified feature matrix (12 pillars)

| # | Pillar | Real implementation (repo-relative) | Endpoint / UI | Tests | Status |
|---|---|---|---|---|---|
| 1 | Translation Agent | `services/api/app/services/translation_service.py:269` (detect -> TM -> glossary/style -> router -> QA -> persist); provider chain `services/api/app/ai.py:47`; `services/api/app/routers/translate.py:117`; SDK surface `services/api/app/routers/v2_v3.py:423` | `POST /api/v1/translate`, `POST /v2/translate`, SSE `/api/v1/translate/stream` (`translate.py:313`); UI `apps/web/src/pages/Translate.tsx:603`, alternatives at `:1434` | `tests/integration/test_desi_compatibility.py:34`, `tests/unit/test_translation_pipeline.py` | CLOSED core; v3 style/custom-instruction enforcement is partial (G08) |
| 2 | API key configuration | TalkFlow keys: `services/api/app/routers/platform.py:66,90,107,131`; provider keys: only env config (`services/api/app/ai.py:162`) and dead vault `services/api/app/services/provider_vault.py` | `/api/v1/api-keys`; UI `apps/web/src/pages/ApiKeys.tsx:43`; no provider-key UI | `tests/test_developer_platform_hardened.py` | PARTIAL (G01) |
| 3 | English correction (Write) | `services/api/app/services/write_service.py:1556` (rule engine) and `:1684` (`improve_text_async`, neural tier with offline rule fallback); `services/api/app/routers/write.py:18`; v2 wrappers `v2_v3.py:610,655` | `POST /api/v1/write`, `/v2/write/rephrase`, `/v2/write/correct`; UI `apps/web/src/pages/Write.tsx:1494` | `tests/unit/test_write_service*.py`, `test_v2_write...` in `tests/integration/test_desi_compatibility.py:74` | CLOSED |
| 4 | Real-time voice translation | `services/api/app/realtime/pipeline.py:34-143` (Listening/Translation/Voice/Supervisor + AgentBus); `services/api/app/realtime/ws.py:198`; session creation `v2_v3.py:1829`, `meetings.py:669` | `POST /v3/voice/realtime`, `/api/v1/voice/session`, `/ws/realtime`; UI `apps/web/src/pages/Voice.tsx:691` and face-to-face STT at `:997-1124` | `tests/unit/test_realtime_*` (12 files), `tests/test_realtime_pipeline_hardened.py` | PARTIAL (G10, G11) |
| 5 | Secure API-key agent | `services/api/app/services/provider_vault.py:84` (save), `:132` (resolve); migration `services/api/alembic/versions/deepl_parity_upgrade_20261025.py:13`; no router/UI | None | None | OPEN (G01, G02) |
| 6 | Context-aware AI agent | `context` accepted and passed at `services/api/app/routers/v2_v3.py:475-482,529`; consumed at `translation_service.py:361-376`; `services/api/app/services/context_service.py:60` is unwired and buggy | `/v2/translate` only; canonical `/api/v1/translate` schema has no `context` (`services/api/app/schemas.py:164-174`); no UI field | `test_v2_translate...` context-conflict test at `tests/integration/test_desi_compatibility.py:448` | PARTIAL (G09) |
| 7 | Multi-agent architecture | `services/api/app/realtime/agents/__init__.py:1-30` (4 agents); `services/api/app/realtime/agents/supervisor.py`; LangGraph control plane `services/api/app/realtime/ws.py:198`; portfolio `multi-agent-portfolio/bridge.py`; `services/api/app/routers/agent_studio.py:277` | `/api/v1/agent-studio/{status,triage,content-pipeline,research-crew}`; UI `apps/web/src/pages/AgentStudio.tsx` | `tests/integration/test_agent_studio.py`, `tests/unit/test_realtime_agents_trace.py` | CLOSED (bridge/LLM optional, honest fallback) |
| 8 | PDF / document translation | `services/api/app/routers/documents.py:40`; pipeline `services/api/app/services/document_service.py:530`; PDF parse/reconstruct `:239,:339`; storage allowlist `services/api/app/storage.py:31-40`; DeepL-shaped endpoint `v2_v3.py:1735` | `/api/v1/documents`; UI `apps/web/src/pages/Documents.tsx:55`; `/v2/document` is a pass-through | `tests/unit/test_document_pdf_geometry_and_ocr.py`, `test_document_parallel_batching.py`, `test_desi_compatibility.py:343` | PARTIAL (G03-G05) |
| 9 | Custom dictionary / glossaries | DB glossaries `services/api/app/routers/customization.py:45`; v2/v3 SDK glossaries `v2_v3.py:945,1075`; per-pair PATCH/PUT `:1188,:1227`; dictionary lookup `routers/write.py:36` | `/api/v1/glossaries`, `/v2/glossaries`, `/v3/glossaries`; UI `apps/web/src/pages/Glossaries.tsx:29` | `test_desi_compatibility.py:140,182` | PARTIAL (G06) |
| 10 | Live subtitles / transcripts | Caption events `services/api/app/realtime/protocol.py:20-60`; transcript/export `services/api/app/routers/meetings.py:533,575`; UI `apps/web/src/pages/MeetingRoom.tsx:260`; VTT client export `apps/web/src/lib/transcriptExporter.ts:116` | `/api/v1/meetings/{id}/transcript/export` (json/txt/srt); client download menu `MeetingRoom.tsx:2659` | `apps/web/src/lib/transcriptExporter.test.ts`, `tests/unit/test_realtime_caption_timeline.py` | PARTIAL (G14, G15) |
| 11 | Language auto-detection | `translation_service.py:285-294`; `services/api/app/ai.py:642`; audio/text detectors `services/api/gt_ai/detection/fasttext.py`, `langdetect_p.py`; endpoint `routers/translate.py:393` | `POST /api/v1/detect-language`; Translate "AUTO" UI with confidence | `tests/unit/test_ai_layer.py`, `test_nllb_coverage.py` | CLOSED |
| 12 | Production testing / optimization | 113 Python test files, 35 Vitest files, CI lanes; docs `docs/TESTING.md` | `.github/workflows/ci.yml`, `.github/workflows/e2e.yml` | See section 5 | PARTIAL (G18-G19; no coverage, broken migration) |

## 3. Gap register vs DeepL

DeepL reference behavior is taken from `deepl_parity/DEEPL_ANALYSIS.md` (voice: lines 73-80; document 3-call: 109-114 and 50K minimum at 119; v3 per-pair glossaries: 125-131).

| ID | Gap | DeepL behavior | Status | Severity | Owning file / evidence |
|---|---|---|---|---|---|
| G01 | BYOK provider-credential stack is unusable: no ORM model, no route, no UI, no provider consumption; `save()` references an unimported class | User-managed provider keys with encrypted storage, rotation, test | OPEN | P0 | `services/api/app/services/provider_vault.py:20-21,84-93`; no `ProviderCredential` in `services/api/app/db/models.py`; no router reference outside the module |
| G02 | Parity migration installs a second Alembic base (`down_revision=None`) and schema objects absent from the ORM | Additive migration on current head, drift-free | OPEN | P0 | `services/api/alembic/versions/deepl_parity_upgrade_20261025.py:6-7`; `voice_sessions` / `provider_credentials` absent from models; document columns absent at `services/api/app/db/models.py:517-553` |
| G03 | `/v2/document` is a fake: upload stores bytes and hard-codes `status="done"`; result returns the original file | Real async translate, poll, one-shot download | OPEN | P0 | `services/api/app/routers/v2_v3.py:1735-1815` (`:1764` status, `:1809-1814` original bytes) |
| G04 | `document_key` is accepted by DeepL clients but never checked server-side | Key-bound one-shot result access | OPEN | P1 | `v2_v3.py:1776-1815` (no `document_key` parameter); `tests/test_cross_tenant_security.py:323` covers org scope only |
| G05 | No per-format document limits or 50K-character billing minimum; fake `billed_characters = len(bytes)//2` | 50K minimum for docx/doc/pptx/xlsx/pdf, per-format caps | OPEN | P1 | `v2_v3.py:1766`; real pipeline records pages at `services/api/app/routers/documents.py:91` |
| G06 | v3 per-pair dictionary API exists but stores records in a process-global dict; glossary is applied by post-hoc substring replacement, not during translation | Persistent per-pair dictionaries enforced by the engine | PARTIAL | P1 | `v2_v3.py:1050` (`_MULTILINGUAL_GLOSSARIES`), `:1188,:1227`, application `:163-185`; lost on restart |
| G07 | v3 translation-memory import/export/jobs are in-memory and not consumed by `/v2/translate` | Persistent TM jobs, TMX import/export, model use | PARTIAL | P1 | `v2_v3.py:1469` (`_TM_JOBS_STORE`), `:1559-1730`; v2 translate never sets `ctx.tm_id` (`:523-532`) |
| G08 | v3 style rules/custom instructions are stored but not enforced; only a hard-coded `can't -> cannot` rewrite when a formal rule is present; `custom_instructions` is validated then dropped | Style rules and up to 10 custom instructions affect output | PARTIAL | P1 | `v2_v3.py:501-521` (validation only), `:570-575` (hard-coded replacement), `_STYLE_RULES_STORE` at `:1299` |
| G09 | `context` works only on `/v2/translate`; canonical API/UI lack it; `context_service.py` is unwired and raises `NameError` (`glossary_terms` undefined) | Context disambiguation across products | PARTIAL | P1 | `v2_v3.py:475-482,529`; `services/api/app/schemas.py:164-174`; `services/api/app/services/context_service.py:60-103` |
| G10 | Voice API shape differs from DeepL: no `source_media_chunk` / `end_of_source_media` / target media members; `message_format=msgpack` is echoed but the socket is JSON; no 50-250 ms cadence contract | Two-step session, source/target media chunks, concluded/tentative updates, one TTS target | PARTIAL | P1 | `services/api/app/realtime/protocol.py:20-90`; `v2_v3.py:1822-1885`; `deepl_parity/DEEPL_ANALYSIS.md:73-80` |
| G11 | No voice-session persistence and no speech-to-speech metering: `voice_sessions` table has no model/writer; `/v2/usage` hard-codes `speech_to_speech_minutes: 0.0`; document/speech billing minimums absent | Conditional speechToSpeech usage and minimums | OPEN | P1 | `deepl_parity_upgrade_20261025.py:35-53`; `v2_v3.py:722`; realtime audio metering at `services/api/app/realtime/pipeline.py:677-689` |
| G12 | Spoken terms collections are stored in memory and never applied to STT/translation | Custom vocabulary affects recognition | PARTIAL | P2 | `v2_v3.py:1939-1965`; no consumer found |
| G13 | Alternatives/variant picking UI is present and wired | Alternatives list in editor | CLOSED | - | `apps/web/src/pages/Translate.tsx:1434,1825`; data from `translation_service.py` result |
| G14 | Server transcript export supports json/txt/srt only; VTT exists only in the browser exporter | VTT subtitle export | PARTIAL | P2 | `services/api/app/routers/meetings.py:575-612`; `apps/web/src/lib/transcriptExporter.ts:116-137`; `MeetingRoom.tsx:299` |
| G15 | `.srt`/`.vtt` are not accepted as document inputs | Subtitle files translated as documents | OPEN | P2 | `services/api/app/storage.py:35` (`ALLOWED_DOC_EXTS`) |
| G16 | No QA/quality-evaluation surface or service: only an admin table read; `quality_eval_service.py` claimed in FINAL_REPORT is absent | Per-segment quality report / QA surface | OPEN | P1 | `services/api/app/routers/platform.py:605-612`; `services/api/app/db/models.py:657`; no service file |
| G17 | Custom-tag analytics returns hard-coded sample numbers | Real usage analytics | OPEN | P2 | `v2_v3.py:1971-2020` (`:1993-2019`) |
| G18 | No coverage measurement or honest parity scorecard; `replica/parity.md` still says 100/100 | Evidence-based production reporting | OPEN | P2 | `replica/parity.md:1`; no `pytest-cov`/`--cov` in `Makefile`, `pyproject.toml`, or CI |
| G19 | The four parity tests named in FINAL_REPORT do not exist; the real parity suite tests the fake document path as success | Tests prove the behavior | OPEN | P1 | missing `tests/unit/test_v2_translate_parity.py`, `test_write_style_tone.py`, `test_provider_vault.py`, `tests/integration/test_provider_keys_flow.py`; `tests/integration/test_desi_compatibility.py:343-366` asserts `done` |
| G20 | Write works offline via the rule engine and degrades honestly when the LLM is absent | Offline usability | CLOSED | - | `services/api/app/services/write_service.py:1684-1727` |
| G21 | Real PDF pipeline preserves geometry/redaction, with pypdf fallback and scanned-page warnings | PDF layout preservation | CLOSED | - | `document_service.py:239-421`; `tests/unit/test_document_pdf_geometry_and_ocr.py:28,66,92` |
| G22 | Text/audio language auto-detection with confidence and honest low-confidence flag | Auto-detect | CLOSED | - | `translation_service.py:285-294`; `ai.py:642`; `translate.py:393` |
| G23 | Four realtime agents, supervisor, LangGraph control plane, and Agent Studio bridge | Multi-agent orchestration | CLOSED | - | `app/realtime/agents/__init__.py`; `agent_studio.py:277`; `ws.py:198` |
| G24 | No offline demo engine / bundled sample corpus; only `dev_echo` and a small canned dictionary | Not a DeepL feature (talkflow2 differentiator) | OPEN | P2 | `services/api/app/ai.py:47`; `v2_v3.py:406-420,2246` |

## 4. Prior claims: verification and correction

| Prior claim | Filesystem reality | Evidence |
|---|---|---|
| FINAL_REPORT lists 12 delivered build artifacts | 6 of 12 files exist, 6 are missing. Of the 6 present: 2 are non-functional, 1 is functional but lacks the claimed additions, and 3 scorecards were never updated. | See below |
| `services/api/app/services/provider_vault.py` delivered | Exists (176 lines) but unusable: `ProviderCredential` is imported only under `TYPE_CHECKING`, so `save()` raises `NameError`; no ORM model exists; never imported by a router. | `provider_vault.py:20-21,84-93` |
| `services/api/app/realtime/voice_session.py` delivered | Missing. | `ls services/api/app/realtime` |
| `services/api/app/realtime/protocol.py` additive members delivered | File exists (174 lines) but none of `SOURCE_MEDIA_CHUNK`, `END_OF_SOURCE_MEDIA`, `SOURCE_TRANSCRIPT_UPDATE`, `TARGET_TRANSCRIPT_UPDATE`, `TARGET_MEDIA_CHUNK`, `END_OF_STREAM` exist. | `services/api/app/realtime/protocol.py:20-90` |
| `services/api/app/services/context_service.py` delivered | Exists (128 lines) but unwired and broken: `_resolve_terms()` returns an undefined `glossary_terms`; `_load_terms()` reads every tenant's terms. | `context_service.py:60-103,106-128` |
| `services/api/app/services/quality_eval_service.py` delivered | Missing. | `ls services/api/app/services` |
| 4 parity test files delivered | All 4 missing. The actual parity coverage is `tests/integration/test_desi_compatibility.py` (14 tests). | `find tests -name 'test_v2_translate_parity.py'` etc. |
| `replica/features.csv` appended 8 rows | File has 19 feature rows; no DeepL-parity rows. | `replica/features.csv` |
| `replica/test-plan.md` appended 19 rows | File has 17 cases total, unchanged. | `replica/test-plan.md:1-30` |
| `scripts/verify_ai_stack.py` extended with parity probes | File exists (336 lines) but has no parity/vault/glossary probes; only a DeepL-key readiness check. | `scripts/verify_ai_stack.py:191-200` |
| FINAL_REPORT: "v3 glossary per-pair dictionaries ... remain gaps" | The endpoint semantics are implemented (`POST/PATCH/PUT/DELETE` dictionaries), but only in memory. The report both understates the code and overstates durability. | `v2_v3.py:1075-1290` |
| TALKFLOW_AUDIT: "SRT/VTT/TXT/JSON export working" | VTT is client-only; the server export pattern is `^(json|txt|srt)$`. SRT exports source text only. | `meetings.py:577`; `transcriptExporter.ts:116` |
| `replica/parity.md`: "Parity: 100.0 / 100" | Static/stale scorecard; no generated evidence, and document parity is fake. | `replica/parity.md:1`; `replica/features.csv` all "yes" |
| Task brief: only 2 of 8 named files exist | Correction: 3 of the 8 code/test files exist (`provider_vault.py`, `context_service.py`, `protocol.py`), but the protocol additions are absent and the other two are non-functional. | Listed above |

The specific claim that survived verification is that all four named parity test files are missing. The filesystem also confirms the two named services and `protocol.py` exist, but not as the working implementations the report described.

## 5. Test inventory and CI reality

### 5.1 Volume

| Suite | Files | Test functions/cases |
|---|---|---|
| `tests/unit` | 34 | 290 |
| `tests/integration` | 5 | 50 (14 in `test_desi_compatibility.py`) |
| `tests/realtime` | 1 test file | 1 (weight-dependent) |
| flat `tests/test_*.py` (hardened) | 70 | 688 |
| `tests/deployment` | 2 | 9 |
| `tests/browser_e2e` harness support | 1 | 0 |
| Python total | 113 `test_*.py` | **1,039** |
| `apps/web/src/**/*.test.ts(x)` | 35 | **272** |
| Playwright `tests/e2e/specs` | 2 | 2 specs |

The browser runner under `tests/browser_e2e/` is a separate harness, not part of pytest CI.

### 5.2 Skips, xfails, deselections

- 4 `pytest.mark.skipif`: `tests/unit/test_document_pdf_geometry_and_ocr.py:27,65,91` (PyMuPDF absent), `tests/unit/test_nllb_coverage.py:24` (checkpoint absent).
- 10 runtime `pytest.skip` call sites: `tests/integration/test_api.py:174,197` (Argos packages), `tests/realtime/test_golden_call.py:104,107` (weights / port), `tests/test_agent_runtime_info_hardened.py:55,76` and `tests/test_copilotkit_auth_hardened.py:98` (optional CopilotKit), `tests/test_outbound_idempotency.py:259` (simulated provider), `tests/test_provider_chain_hardened.py:335` (Argos installed), `tests/unit/test_translation_pipeline.py:392` (network).
- **0** `pytest.mark.xfail`.
- **No** `--deselect`, `addopts`, or ignore list in pytest config.
- CI omission: `tests/test_realtime_security_hardened.py` exists but is deliberately absent from the hardened job, with an inline explanation that it errors on SQLite lock contention (`.github/workflows/ci.yml:70-77`). This is an implicit deselect and should be tracked.

### 5.3 CI lanes

| Lane | What it runs | Needs Docker/Postgres/network? |
|---|---|---|
| `secret-scan` | gitleaks/trufflehog-style scan | network for actions/images |
| `backend` | `pytest tests/unit tests/integration` on SQLite; then 62 hardened files; then `tests/integration` on PostgreSQL + Redis | hardened/files: no Docker; Postgres lane: yes |
| `migrations` | `alembic upgrade head`, `alembic check`, downgrade/upgrade on PostgreSQL | yes (Postgres) |
| `realtime-golden` | `pytest tests/realtime -q -rs` | model weights + free port |
| `frontend` | `npx vitest run` | Node only |
| `docker` | image build | Docker |
| `webrtc-smoke` (`e2e.yml`) | compose stack + Playwright | Docker, LiveKit, network |

### 5.4 Commands runnable without Docker/Postgres/network

```bash
# Python (SQLite/in-memory; some tests skip Argos/weights)
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/integration/test_desi_compatibility.py -q
python -m pytest tests/test_agent_turn_loop.py tests/test_translation_fanout.py -q

# Frontend
cd apps/web && npx vitest run
cd apps/web && npx tsc -b
```

Caveats: `make test` is not an offline command because it appends `tests/realtime` (weights). Some integration tests still touch network-backed providers unless `APP_ENV=test` and the dev provider order are set as CI does.

### 5.5 Commands that cannot run offline

```bash
make test-realtime                 # model weights + port
make migrate                       # PostgreSQL
python -m alembic upgrade head     # PostgreSQL; currently also fails on multiple heads
DATABASE_URL=postgresql+psycopg://... pytest tests/integration -q
docker compose ...                 # docker lane / e2e
cd apps/web && npx playwright test # compose stack + LiveKit
```

### 5.6 Test-health findings

1. The only parity suite passes because `/v2/document` immediately reports `done`; it asserts status and non-empty bytes, not translated content (`tests/integration/test_desi_compatibility.py:343-366`). It locks in the fake.
2. There is no coverage measurement anywhere (`pytest-cov`, `--cov`, vitest coverage config absent).
3. The migration lane cannot be trusted while `deepl_parity_upgrade_20261025.py` declares `down_revision = None` alongside `eae02319e4b2`'s `down_revision = None`; `alembic upgrade head` has multiple heads. The new document columns also do not exist in `models.py`.
4. The new vault/context/quality services have zero tests, matching the missing named test files.
5. Static scorecards (`replica/parity.md`, `replica/test-plan.md`) report 100% and 17/17 with manual rows marked PASS; they are not generated from this test run.

## 6. Recommended talkflow2 differentiators (beyond DeepL)

A clean-room `talkflow2` should keep DeepL's API-shaped surfaces but add offline-first capabilities that this repo lacks:

1. **Evidence-grade parity dashboard, not a static score.** Generate a matrix from executed tests and live endpoint probes, explicitly showing skipped/deselected/unavailable rows. Replace `replica/parity.md:1`-style "100/100" with machine-produced evidence and a non-zero skipped count. This directly addresses G18/G19.
2. **Deterministic offline demo engine.** A first-class `demo` provider with bundled phrase pairs, sample documents, subtitles, and a seeded SQLite database, so the full translate -> write -> document -> subtitles flow works with zero model downloads and zero network. Current `dev_echo` is honest but too thin (`services/api/app/ai.py:47`, `v2_v3.py:406-420`).
3. **Local subtitle pipeline.** Server-side VTT/SRT import and export (translated cues, speaker labels, stable timecodes), plus `.srt`/`.vtt` accepted as document inputs. Current VTT exists only in the browser (`apps/web/src/lib/transcriptExporter.ts:116`) and the server allowlist excludes subtitles (`services/api/app/storage.py:35`).
4. **Conversation mode with graceful Web Speech fallback.** Two-speaker turn-taking that falls back to `SpeechRecognition`/`webkitSpeechRecognition` when server STT is unavailable or models are not cached, with push-to-talk and replayable transcripts. Voice currently requires `getUserMedia` plus server STT (`Voice.tsx:755,997-1124`); Web Speech is used only for Write dictation (`Write.tsx:1706`).
5. **Restart-safe single-process persistence.** SQLite + local file storage + in-process queue for glossaries, TM, style rules, documents, and provider credentials, with export/import. This eliminates the current in-memory parity stores (`v2_v3.py:942,1050,1299,1469,1732,1939`) and the Postgres/Redis/Docker requirement for a demo, while keeping the same API contracts.

## 7. Limitations

- This is a static audit; runtime behavior, model availability, and CI status were not executed.
- Legacy `apps/api` and root `ai/` contain parallel implementations and were intentionally excluded from status decisions.
- The working tree contains unrelated uncommitted edits (`apps/web/src/lib/ws.ts`, `Voice.tsx`, `mediaResilience.test.ts`); they do not affect the findings above.
- Line numbers will drift after edits; IDs and behavior are the durable references.
