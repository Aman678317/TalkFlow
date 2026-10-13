# API Reference (v1)

> **Which server.** This repo ships two backends. The deployed one is **Tree A**
> (`services/api`, `app.*`, port 8088 locally / `$PORT` on Render) and it is the
> subject of this page unless a line says otherwise. **Tree B** (`apps/api`,
> `globaltalk.*`, port 8000, the Makefile + golden-test tree) has a few extra
> internal endpoints, marked **[Tree B]** below — they return 404 on the deployed
> service, so never script a production check against them.

OpenAPI (interactive): `GET /docs` · schema: `GET /openapi.json`.
Base URL: `/api/v1`. Auth: `Authorization: Bearer <JWT>` (users) or `X-API-Key: gtk_…`
(developer keys). Org switcher for multi-org users: `X-Org-Id: <org>`.

## Error contract (every non-2xx)

```json
{"error": {"code": "rate_limited", "message": "…", "request_id": "…", "trace_id": "…",
           "recoverable": true, "details": {}}}
```

Codes include: `not_found`, `unauthorized`, `forbidden`, `tenant_isolation`,
`validation_error`, `rate_limited`, `conflict`, `ai_provider_error`,
`translation_unavailable`, `storage_error`, `unsupported_file_type`, `malware_detected`,
`upload_too_large`, `text_too_long`, `api_key_invalid`, `token_expired`, `refresh_invalid`.

## Authentication

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/signup` | creates user + organization + owner membership + free subscription |
| POST | `/auth/login` | rate-limited; no user enumeration |
| POST | `/auth/refresh` | rotating refresh tokens (hashed at rest, replay fails) |
| POST | `/auth/logout` | revokes refresh token + session |
| GET | `/auth/me` | profile + membership |
| GET | `/auth/sessions` | device/session tracking |
| POST | `/auth/password-reset` (+`/confirm`) | token hashed, 1 h expiry, revokes all sessions; dev returns `dev_token` (non-prod only) |
| POST | `/auth/verify-email` | verification token flow |

OIDC/SAML/MFA: architecture prepared (`User.mfa_enabled`, `Integration.kind`,
`enterprise_sso` flag); providers plug in behind the same Principal resolution.

## Translation

```
POST /translate
{ "text": "…", "source_language": "AUTO", "target_language": "hi",
  "glossary_id": null, "style_profile_id": null, "translation_memory_id": null,
  "domain": "general", "intent": "quality_optimized" }

→ { "translation_id", "source_language", "target_language", "source_text",
    "translated_text", "model", "provider", "latency_ms", "quality_flags",
    "from_translation_memory", "detected_confidence" }
```

Pipeline: glossary → TM (exact then fuzzy ≥0.82 cosine) → Model Router (intent-aware) →
provider chain → glossary enforcement → metering + history. `POST /translate/batch`
(≤64 texts). `POST /detect-language`. `GET /history?q=&source_language=&target_language=`.

`quality_flags` vocabulary: `tm_exact_match`, `tm_fuzzy_match`, `same_language`,
`pivoted_via_intermediate`, `glossary_enforced`, `untranslated_fallback` (+`ai_unavailable`),
`low_language_detection_confidence`.

## Languages / glossaries / TM / styles

- `GET /languages` — validated capability registry (per-deployment truth).
- `POST /languages/refresh` — reconcile registry with provider probes.
- `GET|POST /glossaries`, `GET /glossaries/{id}`, `POST|DELETE /glossaries/{id}/terms[…]`,
  `POST /glossaries/{id}/activate|archive`, `POST /glossaries/{id}/import?csv_text=`,
  `GET /glossaries/{id}/export` (CSV). Versioned; realtime/documents store the version used.
- `GET|POST|DELETE /translation-memories[…]` — exact+fuzzy; embeddings stored
  (pgvector in prod).
- `GET|POST|PUT|DELETE /style-profiles[…]` — versioned; system profiles immutable.

## Documents

`POST /documents` (multipart: file, source_language, target_language, glossary_id,
style_profile_id, domain) → 202. Then:
`GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/status` (stage + progress +
audit log), `POST /documents/{id}/retry`, `GET /documents/{id}/download`, `DELETE`.
Stages: queued → scanning → parsing → translating → reconstructing → quality_check →
ready│review│failed. See DOCUMENTS.md.

## Meetings & realtime

- `POST /meetings` → `{id, room_name, join_token, transport}`.
- `GET /meetings`, `GET /meetings/{id}`, `POST /meetings/{id}/end`.
- `GET /meetings/{id}/participants`; `PUT …/participants/{pid}/preferences`
  ("I speak / I want to hear / audio mode").
- `POST /voice/session?meeting_id=…` → LiveKit token or WS URL.
- `GET /meetings/{id}/transcript` (+`?language=&participant_id=&q=`),
  `GET …/transcript/export?fmt=csv|json`.
- `GET /meetings/{id}/chat?listening_language=hi` — originals + per-language translations.
- `POST /meetings/{id}/summary`, `GET …/summary`, `POST …/ask {question}`.
- WebSocket: `/ws/meetings/{id}` — see REALTIME.md.

## Platform

All paths below are relative to `/api/v1` on **Tree A** unless tagged **[Tree B]**.

- `GET|POST /api-keys`, `POST /api-keys/{id}/rotate|revoke` (secret shown once; hash stored).
- `GET /usage?days=30` (metered totals vs plan limits), `GET /usage/quota`.
- Billing: `GET|POST /billing/subscription`, `GET /billing/events`,
  `GET /billing/preview-invoice`. **[Tree B]** only: `GET /billing/invoices`,
  `POST /billing/checkout-preview`.
- `POST|GET|DELETE /webhooks[…]`, `GET /webhooks/{id}/deliveries`,
  `GET /webhooks/meta/events`. HMAC-SHA256 signature:
  `GlobalTalk-Signature: v1=<hmac(timestamp + "." + body)>`, `GlobalTalk-Timestamp`,
  retries at ~5 s/30 s/2 m/10 m/30 m, SSRF-guarded URLs in production.
- `POST /organizations` (create), `GET /organizations/current`, `GET /roles`,
  `GET|POST /members`, `PUT /members/{id}/role`, `DELETE /members/{id}` (RBAC roles).
  **[Tree B]** path spelling: `GET /org`.
- `GET /search?q=` — meetings/transcripts/messages/documents/glossaries/TM (tenant-scoped).
- `POST /feedback` · `GET /flags` · `GET|POST|DELETE /integrations[…]`.
- **[Tree B]** only: `POST /bridge/turn?agents=agent-a:en,agent-b:ja` — agent-to-agent
  language bridge; every agent projection derives independently from the canonical
  human text. `POST /api/v1/languages/refresh` is also **[Tree B]**; on Tree A the
  startup probe reconciles the registry and an admin changes status with
  `PUT /admin/languages/status`.
- Admin (platform admins): `GET /admin/overview|users|organizations|audit-logs|languages|model-health|quality-evaluations`,
  `PUT /admin/languages/status`, `PUT /admin/flags`, `POST /admin/users/{id}/suspend`.
  (`/admin/security-events`, `/admin/feature-flags/{name}` and
  `/admin/users/{id}/deactivate` were documented here previously and do not exist in
  either tree — the real shapes are the ones above.)

## Ops endpoints

**Tree A (deployed):** `GET /health` (also `/healthz`, `/api/v1/health`) ·
`GET /ready` (deps: database, cache, queue, storage, plus LiveKit when configured —
503 when a required dep is down; also `/readyz`) · `GET /version` ·
`GET /metrics` (Prometheus text; 404 unless `METRICS_ENABLED`, token-gated in
production) · `GET /api/v1/meetings/{id}/realtime/health` (per-meeting stage chain;
see `docs/PRODUCTION_RUNBOOK.md` §5).

**[Tree B]** only — these 404 on the deployed service:
`GET /internal/components` (open-source component health + license review status) ·
`GET /internal/audio-health` (VAD/STT/TTS/queues/GPU).

`/version` answers for every AI task with the provider the configuration prefers
and what this image can actually run it on:

```json
"ai": {"stt": {"provider": "faster_whisper", "runtime": "missing"},
       "mt":   {"provider": "neural_online",  "runtime": "remote"},
       "tts":  {"provider": "dev_tone",       "runtime": "dev_stand_in"}}
```

`runtime` is one of `importable` (the model package is installed), `missing` (it
is not, so this provider will fail over), `remote` (the work happens over the
network), `remote_unconfigured` (it needs a URL or key that is empty),
`dev_stand_in` (a fake: it never recognises speech or produces speech), or
`builtin` (pure-Python, nothing to install). `importable` means the package is
present — weights, voice files and a loadable runtime are only proven once a
stage actually runs. For that, `GET /api/v1/meetings/{id}/realtime/health` gives
per-stage health for a live room, and `/metrics` carries
`gt_stt_latency_ms`, `gt_tts_first_audio_ms`, `gt_e2e_latency_ms` and
`gt_translation_failures_total`.

## Rate limits

`RATE_LIMIT_TRANSLATE` (default 60/min per key/user), `RATE_LIMIT_AUTH` (10/min per
email/IP). 429 responses carry `retry_after_seconds`.

## Versioning & SDK readiness

URI-versioned (`/api/v1`). Flat request/response models (no ORM leakage), explicit enums,
consistent error contract, idempotency-friendly (translation_id deterministic per input+time),
WS protocol versioned (`version: 1`). SDK generation (JS/Python/Go/Java) can build directly
from `openapi.json` + the WS protocol doc.
