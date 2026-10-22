# Translation acceptance — the pair-matrix record

Created day-3 (2026-10-23), as the output the 30-day roadmap names for the
language-pair work (`docs/30-DAY-ROADMAP.md`). Every claim here points at a
pin that fails if the claim becomes false. Nothing here is marketing.

## The source of truth

`services/api/gt_ai/capabilities.py::DEFAULT_LANGUAGES` — 20 languages with
**independent** per-capability statuses
(`EXPERIMENTAL < BETA < SUPPORTED < PRODUCTION`) and the provider names that
serve them. The database (`language_capabilities` table, seeded at startup)
is the runtime truth; the module is the seed and the code-level mirror. A
language is never "fully supported" just because a model claims it.

## How each surface serves a pair

| Surface | Pair gate | Reference |
|---|---|---|
| Canonical text (`/api/v1/translate`) | `validate_pair` — target must exist in the registry and not be `EXPERIMENTAL`; glossary mismatch surfaces as `glossary_note` | `app/services/translation_service.py:110-132` |
| Realtime meeting pipeline | same service gate per segment; echo/empty results re-fail and flag `untranslated_fallback` instead of shipping | `app/realtime/agents/translation.py:60-163` |
| Documents | per-segment failure keeps the segment **missing** so the quality gate fails the job honestly (never "ready with source text") | `app/services/document_service.py:612-648` |
| Phone bridge | registry check at **call creation** (both sides), then the bridge's own per-segment degradation; detected-language override is carried in-bridge | `app/telephony/call_service.py`, `app/telephony/bidirectional_bridge.py:241-289` |
| v2/v3 compatibility surface | registry-derived language lists; formality claimed only where `FORMALITY_RULES` exist (de / es / fr) | `app/routers/v2_v3.py` |
| Frontend pickers | filter on `*/supported` booleans from `/api/v1/languages` (the registry) | `apps/web/src/hooks/useLanguages.ts` |

## What is NOT servable today (recorded honestly)

- **Speech output (TTS)** is claimed only where the registry's BETA+ voice
  coverage matches an actual voice adapter: kokoro's voice set covers
  en / hi / ja / zh / es / fr / de / pt; `mr`, `bn`, `ta`, `te`, `gu`, `kn`,
  `ml`, `pa`, `ur`, `ar`, `ru`, `ko` stay `EXPERIMENTAL` (dev/http adapter
  until a validated voice exists). Captions remain available for all.
- **Formality** is a real transformation today only for **de / es / fr**
  (the language set of `FORMALITY_RULES` in `gt_ai/translation/neural_online.py`).
- The v2 compat surface no longer advertises Latin / Esperanto / Amharic or
  any of the other ~80 unservable codes; `la` (beta) and `sa` (external)
  surface **only** behind an explicit `?include=beta,external` query flag —
  never in the default list.
- Diagnostics (`/ready?diagnostics=true`, `/api/v1/system/diagnostics`)
  report the pair matrix **derived from the registry** (hub-and-spoke
  `en<->X` for every translation-supported language) and never load model
  weights to do it.

## Degradation contract (what a client sees when a pair cannot be served)

- `422` with `unsupported_language` when a requested language is not in the
  registry: at **call creation** on the phone lane (before any provider or
  meeting work) and at request time on the canonical surfaces. The v2
  compatibility surface keeps its DeepL-shaped contract and answers the
  degraded item honestly instead: `text: ""` + `untranslated_fallback`.
- A provider that fails, or answers with the source text again, is treated as
  a failed attempt: the response carries `untranslated_fallback` (realtime)
  or `text: ""` + `untranslated_fallback` (v2 compat) — never a fabricated
  translation, never the source labelled translated.
- Private-only promises are never silently downgraded (`gt_ai/types.py:121-128`,
  pinned by `tests/test_private_only_guarantee_hardened.py`).

## Verification pins (evidence, not claims)

- `tests/unit/test_readiness_diagnostics.py::test_the_diagnostics_pair_matrix_is_the_capability_registry`
  — the diagnostics matrix is the registry, not a frozen sample.
- `tests/test_v2_v3_surface_auth_hardened.py` (day-3 honesty block) — the v2
  language list serves only registry languages, formality is claimed only
  where rules exist, a real provider result is never replaced by the
  dictionary, and a failed provider answers with a flag, not a fabrication
  (both `/v2/translate` and `/v2/desi/translate`).
- `tests/unit/test_translation_pipeline.py` (day-3 echo-guard tests) — the
  guard compares text even when the source is unknown; an all-echo chain
  fails closed on Latin-script targets exactly where the old guard leaked.
- `tests/test_outbound_idempotency.py::test_a_call_in_an_unregistered_language_is_rejected`
  — the phone lane validates both languages at creation.
- `tests/unit/test_document_parallel_batching.py::test_a_failed_segment_never_ships_as_its_own_translation`
  — a failed segment stays missing and the document does not claim ready.
- `tests/integration/test_desi_compatibility.py::test_v3_languages_and_resources_conformance`
  — the compat surface's shape contract holds (registry-derived lists,
  `la`/`sa` only behind explicit include).

## Day-3 plan checklist (30-DAY-ROADMAP §Day 3 vs shipped PR #132, 2026-10-23)

| Plan item (Day 3) | Status | Evidence |
|---|---|---|
| Deterministic language-pair matrix (en↔hi, hi↔en, en↔mr, code-switch→en, one unsupported pair) | **PASS for the matrix itself** (registry-derived, 20 languages, 38 hub pairs, diagnostics mirror); **partial** for the raw-input matrix cases — en↔hi pinned end-to-end, en↔mr pinned at registry/diagnostics level, code-switch (Hinglish) cases are open and belong to the day-6 string sweep | `TRANSLATION_ACCEPTANCE.md` + `tests/unit/test_readiness_diagnostics.py`, `tests/integration/test_desi_compatibility.py` |
| One unsupported pair behaves honestly | **PASS** | phone `xx`/`zz` → 422 (`test_a_call_in_an_unregistered_language_is_rejected`); v2 `XX` → `text:""` + `untranslated_fallback` |
| Test provider-down and timeouts | **PASS** (existing pins + new) | chain deadline failover (`tests/test_provider_chain_hardened.py`), all-echo chain fails closed (`tests/unit/test_translation_pipeline.py`), failed provider → honest flag (`tests/test_v2_v3_surface_auth_hardened.py`) |
| Results record source/target, provider/model, latency, flags, fallback status | **PASS** | `TranslationResult` carries `source_lang/target_lang/model/provider/latency_ms/quality_flags` (`gt_ai/types.py:44-57`); v2 items surface `quality_flags`/`untranslated_fallback`; realtime events carry per-segment provenance |
| Never a false "success translation" | **PASS** | the 10 red proofs → echo guard, v2 fabrication removal, dictionary provenance, document segment honesty (`docs/ARCHITECTURE_OWNERSHIP.md` B-7…B-10, O-13, O-14) |
| Launch-plan Day-3: record unsupported pairs + disabled features | **PASS** | this document's "What is NOT servable today" section |
| Launch-plan Day-3: full clean-browser sign-off journey | **OPEN** (documented scope exclusion) | API-path truth proven live on localhost (:8000) this PR; the browser journey is the launch sign-off exit checklist, scheduled with the staging deployment round |

## Localhost verification (2026-10-23, live, canonical backend on :8000)

Boot contract per `scripts/run_dev.sh` (`#130`): canonical backend
(`app.main:app`, PYTHONPATH `services/api:apps/api:ai:.`), API :8000. Probes
against the running server through the product's real HTTP stack (traces and
output below are verbatim):

- `GET /health` → `200` `{"status":"ok","version":"0.1.0",…}`.
- `GET /readyz` → `{"ready":true,"checks":{"database":true,"cache":true,
  "queue":true,"storage":true}}` — the readiness probe reports
  **infrastructure**, it does not claim AI readiness.
- `GET /ready?diagnostics=true` → `diagnostics.status="degraded"` (no
  production provider configured — honest), `tasks.mt.healthy=false`,
  `language_pairs.supported_count=38`, `languages=` all twenty registry
  codes (**bn, ta, te, gu, kn, ml, pa, ur, pt, ar, ko included** — they were
  invisible in the frozen pre-repair matrix).
- `GET /api/v1/system/diagnostics` → same registry-derived matrix
  (`en->hi`, `hi->en`, … `en->ko`, `ko->en`, 38 pairs), `overall="degraded"`.
- `GET /api/v1/languages` → 20 registry entries.
- `GET /v2/languages?type=target` → exactly the 20 registry codes
  (EN,HI,MR,BN,TA,TE,GU,KN,ML,PA,UR,JA,ZH,ES,FR,DE,PT,RU,AR,KO);
  `supports_formality` only for ES,FR,DE; no Latin/Esperanto/Amharic.
- `GET /v2/glossary-language-pairs` → 38 registry-hub pairs (EN <-> every
  other registry language), not the frozen ten-language list.
- `POST /v2/translate` (`"hello world"`, EN→DE) →
  `{"text":"Hallo Welt","quality_flags":["dev_provider","neural_mt"]}` —
  a real translation with explicit provenance flags; no `"[DE] text"` tag,
  no unflagged dictionary swap.
- `POST /v2/translate` (EN→`XX`, unregistered target) →
  `{"text":"","untranslated_fallback":true}` `200` — the honest empty
  degradation in the DeepL-shaped contract, nothing fabricated.
- `POST /v2/desi/translate` (en→hi) →
  `"नमस्ते दुनिया"` with `"translated_by":"dictionary"` — the phrase
  dictionary announces itself.

Authed mutation probes (call creation against the registry, 422 mapping) are
pinned deterministically in `tests/test_outbound_idempotency.py`; visible
degradation here is recorded above.

