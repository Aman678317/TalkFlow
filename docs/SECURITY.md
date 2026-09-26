# Security & Privacy

## Threat model coverage (OWASP Top 10 mapping)

| Risk | Control |
|---|---|
| Broken access control / IDOR | every query tenant-filtered (`org_id`); `ensure_org_member` at service boundaries; identical 404 for "not found" vs "other tenant"; cross-tenant integration test |
| Cryptographic failures | bcrypt(12) passwords; refresh tokens & API keys stored as SHA-256 hashes; TLS-ready (ingress/nginx); secrets via env/Secrets Manager only |
| Injection | SQLAlchemy bound parameters everywhere; no shell interpolation of user data; subprocess calls use argument arrays (never `shell=True`) |
| Insecure design | canonical-source invariants; fallback chains degrade honestly; rate limits on auth+translate; rotating refresh tokens with replay detection |
| Security misconfiguration | `/ready` fails closed on required deps; security headers (nosniff, DENY frame, referrer, permissions-policy); CORS allowlist |
| Vulnerable components | pinned versions + lockfiles; `third_party_components.yaml` license/security review status; CI dependency install from pinned requirements |
| Auth failures | JWT typ/alg pinned (HS256), short-lived access (30 m), refresh rotation, session revocation on password reset, MFA field + SSO flag ready |
| Software/data integrity | SHA-256 checksums on uploads & stored objects (verified before processing); signed webhooks (HMAC-SHA256 v1 scheme); migration-gated schema |
| Logging/monitoring | structured JSON logs with request_id/trace_id/tenant/user; sensitive keys redacted (`SENSITIVE_KEYS`); audit_logs for all mutations; /metrics Prometheus |
| SSRF | webhook URLs scheme-checked, DNS-resolved and private/loopback/link-local ranges blocked in production; redirects disabled |

## Upload safety

Magic-byte MIME sniffing (extension/client header ignored) · size cap · optional ClamAV
INSTREAM scan (fail-closed when required) · storage keys namespaced by org+checksum ·
path-traversal guard on local storage backend.

## WebSocket authorization

JWT (org membership verified) or meeting join_token (guest scope: that meeting only).
Close codes: 4401 unauthorized, 4404 not found, 4408 join timeout. No secrets in URLs
besides the scoped join token; tokens are single-meeting and rotatable.

## API keys

`gtk_…` prefix, 256-bit entropy, shown exactly once, stored hashed, scoped
(translate/detect/documents/glossaries/meetings/usage/admin), rotatable (old revoked +
webhook `api_key.revoked`), last_used tracked, revocation audited.

## Privacy (section 40)

Per-org retention policy (audio/transcripts/documents) enforced by the cleanup worker;
originals and derivatives stored separately; user/org deletion cascades via FKs +
storage sweep; voice preservation requires explicit revocable consent with audit trail
(`voice_consents`); synthetic audio always flagged in metadata/events.

## Production hardening checklist

- [ ] Rotate all default secrets (JWT_SECRET, SECRET_KEY, DB, MinIO, LiveKit)
- [ ] Enable MALWARE_SCAN_ENABLED with ClamAV sidecar
- [ ] TLS at ingress (cert-manager), HSTS via ingress annotation
- [ ] Postgres: TLS + least-privilege role; backups (pg_basebackup/WAL-G) + restore drills
- [ ] Redis: AUTH + TLS; S3: bucket policy + SSE-KMS
- [ ] Per-package Argos model license review before commercial routing (NLLB CC-BY-NC!)
- [ ] Silero VAD model license (CC-BY-NC) review before enabling — energy VAD is default
- [ ] Sentry/OTEL wired (SENTRY_DSN, OTEL_ENDPOINT)
- [ ] Rate limits tuned per plan; admin endpoints behind platform-admin + IP allowlist
