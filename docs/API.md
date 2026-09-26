# API Reference (v1)

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

- `GET|POST /api-keys`, `POST /api-keys/{id}/rotate|revoke` (secret shown once; hash stored).
- `GET /usage?days=30` (metered totals vs plan limits), `GET /billing/invoices`,
  `POST /billing/checkout-preview`.
- `GET|POST|DELETE /webhooks[…]`, `GET /webhooks/deliveries`. HMAC-SHA256 signature:
  `GlobalTalk-Signature: v1=<hmac(timestamp + "." + body)>`, `GlobalTalk-Timestamp`,
  retries at ~5 s/30 s/2 m/10 m/30 m, SSRF-guarded URLs in production.
- `GET /org`, `GET|POST|DELETE /members[…]` (RBAC roles).
- `GET /search?q=` — meetings/transcripts/messages/documents/glossaries/TM (tenant-scoped).
- `POST /feedback`.
- `POST /bridge/turn?agents=agent-a:en,agent-b:ja` — agent-to-agent language bridge;
  every agent projection derives independently from the canonical human text.
- Admin (platform admins): `GET /admin/overview|users|audit-logs|security-events|feature-flags`,
  `PUT /admin/feature-flags/{name}?enabled=&org_id=`, `POST /admin/users/{id}/deactivate`.

## Ops endpoints

`GET /health` (process) · `GET /ready` (deps: DB, cache, storage, LiveKit when configured —
503 when a REQUIRED dep is down) · `GET /version` · `GET /metrics` (Prometheus text) ·
`GET /internal/components` (open-source component health + license review status) ·
`GET /internal/audio-health` (VAD/STT/TTS/queues/GPU).

## Rate limits

`RATE_LIMIT_TRANSLATE` (default 60/min per key/user), `RATE_LIMIT_AUTH` (10/min per
email/IP). 429 responses carry `retry_after_seconds`.

## Versioning & SDK readiness

URI-versioned (`/api/v1`). Flat request/response models (no ORM leakage), explicit enums,
consistent error contract, idempotency-friendly (translation_id deterministic per input+time),
WS protocol versioned (`version: 1`). SDK generation (JS/Python/Go/Java) can build directly
from `openapi.json` + the WS protocol doc.
