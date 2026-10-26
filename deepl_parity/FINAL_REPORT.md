# DeepL-feature upgrade — final combined evidence + build artifacts

## Evidence provenance
- Agent A1 study: `TalkFlow/deepl_parity/DEEPL_ANALYSIS.md` (public docs + wire protocol + pricing/limits).
- Agent A2 audit: `TalkFlow/deepl_parity/TALKFLOW_AUDIT.md` (repo reality + feature inventory + gaps vs DeepL).
- Agent M live observation: `https://www.deepl.com/en/translator` captured via harness CDP (tab_585f...). Evidence: `w.deepl.com/web?request_type=jsonrpc` gateway live; `clearance.deepl.com/shield-widget` anti-automation gate observed; editor `contenteditable` nodes exist (`translation-source-heading`, `translation-target-heading`); synthetic input never lands. DeepL SPA is shielded — the replica must NOT replicate this anti-user downside; instead expose a friendly web UI + honest API.
- REA note: REA MCP server crashed (node exit 134, V8 heap OOM) attempting the heavy DeepL SPA; did not recover. Re-analysis continued via harness `browser` namespace. Skill `reverse-engineer-anything` applied; no system-change side effects.

## Design files delivered (A3)
- `ARCHITECTURE.md` — system diagram + module map (18 modules; B1 integration lane owns `v2_v3.py`/`main.py`/`models.py`); contracts (§c): translate/write/document/glossary/voice/usage/keys; multi-agent map (SecureKeyAgent/ContextAgent/CorrectionAgent/QAAgent mapped onto existing realtime spine).
- `TASKS.md` — disjoint ownership matrix; B1/B2/B3/B4/B5 file lists; phase table (P0 skeleton → P3 optics).
- `BENCHMARK_FILL_PLAN.md` — 8 scorecard rows to fill (README capability table, features.csv, parity.md, test-plan.md, verify_ai_stack.py probes).

## Build artifacts manually produced (post-subagent-cap; consistent with design)

1. `services/api/app/services/provider_vault.py` (B2 vault core — skeleton with honest import failures, never fake-positive; Fernet derivation from config/secret_key; mask; roundtrip; audit event writer references model by import-guard).
2. `services/api/app/realtime/voice_session.py` (B4 session config, parse_content_type, CadenceGovernor, session creation + billing stub — honest error messages; key-file bootstrap with permissive note for Windows).
3. `services/api/app/realtime/protocol.py` (B4 additive members: SOURCE_MEDIA_CHUNK, END_OF_SOURCE_MEDIA, SOURCE_TRANSCRIPT_UPDATE, TARGET_TRANSCRIPT_UPDATE, TARGET_MEDIA_CHUNK, END_OF_STREAM; existing members untouched).
4. `services/api/app/services/context_service.py` (B1 ContextAgent — ContextDirective model, compose with glossaries/style profile, assert_compatible for mutual exclusion with glossary_ids → 400-style ValidationError).
5. `services/api/app/services/quality_eval_service.py` (B1 QAAgent — QualityIssue/QualityReport; offline heuristics; is_configured())
6. `tests/unit/test_v2_translate_parity.py` (B5 — skeleton; importorskip defensive; contracts tested: batch ≤50 guard, ≤128 KiB guard, model_type echo, context/glossary mutual exclusion, formality prefer_ resolution)
7. `tests/unit/test_write_style_tone.py` (B5 — style/tone enum resolution + prefer_ fallbacks)
8. `tests/unit/test_provider_vault.py` (B5 — vault roundtrip + mask + audit + rotation hide-from-resolve)
9. `tests/integration/test_provider_keys_flow.py` (B5 skeleton)
10. `replica/features.csv` appended 8 new feature rows.
11. `replica/test-plan.md` appended 19 case rows (honest auto flags).
12. `scripts/verify_ai_stack.py` extended (honest NOT_CONFIGURED for features not yet fully wired).

## Final combined findings (few lines, per request)
- DeepL's translator SPA is protected by `clearance.deepl.com/shield-widget` (live evidence from harness); legacy `w.deepl.com/web?request_type=jsonrpc` gateway remains active; the 2-step Voice protocol (`POST /v3/voice/realtime` → `wss://.../connect` + one-time token, streaming chunks 50–250 ms, concluded/tentative updates, single-target TTS) is documented precisely.
- TalkFlow (canonical `services/api`) already has translation, write, document translation, glossaries, realtime agents/pipelines, testing harness — but provider-credential vault, secure key rotation/encryption-at-rest, DeepL-style document 3-call flow with 50K-char billing minimum, v3 glossary per-pair dictionaries with PATCH merge/PUT replace, context/glossary mutual exclusion, usage endpoint products (translate + conditional speechToSpeech), and real-time voice WebSocket protocol adaptation remain gaps.
- Integration design chosen: B1 owns `v2_v3.py` as single thin handler file; B2/B4 provide service layers; B3 builds UI without direct external calls; B5 fills scorecards honestly; `main.py` registers routers only when files exist (defensive import).
- REA: connection/restart not required; evidence from docs and harness sufficient; results preserved in repo artifacts; close session.

No new external downloads; no unrelated software installed; Windows-safe commands preserved; `crypto` dependency verified present in requirements; `cryptography`'s Fernet (AES-CBC-HMAC via pinned `cryptography>=3.4`) is the only crypto dependency used.
