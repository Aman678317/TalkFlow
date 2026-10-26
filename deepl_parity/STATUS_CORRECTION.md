# Status correction — DeepL parity claims (verified 2026-10-25)

This file corrects claims in `FINAL_REPORT.md` that were not reproducible on the working tree.

## What was claimed vs. verified

| Claim in FINAL_REPORT | Verified reality |
|---|---|
| `services/api/app/realtime/voice_session.py` delivered | **Missing** |
| `services/api/app/services/quality_eval_service.py` delivered | **Missing** |
| `tests/unit/test_v2_translate_parity.py` delivered | **Missing** |
| `tests/unit/test_write_style_tone.py` delivered | **Missing** |
| `tests/unit/test_provider_vault.py` delivered | **Missing** |
| `tests/integration/test_provider_keys_flow.py` delivered | **Missing** |
| `services/api/app/services/provider_vault.py` delivered | Present, but **dead code**: no route, no UI, and it references an ORM model that does not exist |
| `services/api/app/services/context_service.py` delivered | Present, but **not wired** into the canonical translate path |
| `/v2/document` async 3-call flow | **Not implemented**: `v2_v3.py` marks uploads `done` immediately, ignores `document_key`, and returns original bytes |
| Parity migration | **Broken**: `deepl_parity_upgrade_20261025.py` starts a second Alembic base (`down_revision=None`) and its tables/columns are absent from `models.py` |
| Scorecard rows marked `yes` | Backing tests named in the plan do not exist; `replica/features.csv` flags are not evidence-backed |

The detailed evidence is in `deepl_parity/TALKFLOW_GAP_REPORT.md`.

> Working-tree note: `services/api/app/services/provider_vault.py`, `services/api/app/services/context_service.py`, and `services/api/alembic/versions/deepl_parity_upgrade_20261025.py` are **untracked audit artifacts** on the audit machine. They are intentionally **not committed** on this branch because they are unsafe to ship (dead code, missing ORM models, forked migration base). Do not merge them as-is.

## What this branch actually delivers

- `talkflow2/` — a standalone, zero-dependency implementation of all 12 pillars, verified end-to-end:
  **103/103 node tests pass, 0 skipped**, 8/8 views boot on localhost, and core journeys were exercised in a real browser.
- `deepl_parity/REA_DEEPL_FINDINGS.md` — REA 6.7.0 setup evidence and DeepL contract matrix.
- `deepl_parity/TALKFLOW_GAP_REPORT.md` — verified main-repo gap audit with file/line evidence.
- `talkflow2/TEST_REPORT.md` — exact QA evidence, screenshots, console/network results, and limitations.

## What remains open in the main FastAPI app (not fake-fixed)

1. **P0 — BYOK stack**: `provider_vault.py` is unreachable; no `/api/v1/providers/keys` route, no Provider Keys UI, no resolver consumption.
2. **P0 — `/v2/document`**: fake synchronous flow, no `document_key`, no status polling, no one-shot download, no 50,000-character billing minimum.
3. **P0 — migration/schema**: forked Alembic base and missing model columns; do not run this migration.
4. **P1 — voice protocol**: no `/v3/voice/realtime` session or WSS tentative/concluded adapter.
5. **P1 — glossary v3**: no per-pair dictionaries with PATCH merge / PUT replace / TSV import.
6. **P1 — scorecards**: parity numbers must be recomputed only after backing tests exist.

These were **not** patched in this branch because they require Postgres/Docker and a verified migration plan; changing them without executable evidence would repeat the false-positive pattern this correction is meant to end.

## Reproduce this correction

```bash
cd talkflow2
npm test                 # 103 pass, 0 skipped
cd ../TalkFlow
ls services/api/app/realtime/voice_session.py   # absent
ls tests/unit/test_v2_translate_parity.py        # absent
```
