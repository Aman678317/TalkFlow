# TalkFlow / GlobalTalk AI — Prioritized Production Audit (Phase 0)

**Date**: 2026-10-04  
**Auditor**: Senior Principal Full-Stack, Security, DevOps, QA, Realtime/WebRTC, and AI Systems Engineer  
**Repository**: [Aman678317/TalkFlow](https://github.com/Aman678317/TalkFlow.git) / `globaltalk-ai`  
**Evaluation Standard**: Enterprise Production Readiness, OWASP Top 10, Zero-Trust Architecture, Realtime Audio/Video SLAs, Strict Canonical Source Integrity.

> **⚠️ RE-AUDIT UPDATE (2026-10-29)** — original FAIL verdicts below were re-audited against the
> current `main` tree; statuses corrected with evidence (see the updated status matrix). This
> document is historical; the phase log at the bottom records remediation state, and
> [`docs/audit/11-initial-report-reconciliation.md`](audit/11-initial-report-reconciliation.md)
> carries the maintained cross-register status.

## Re-audit evidence (2026-10-29)

| Original finding | Original verdict | Current-code verification | Corrected status |
| :--- | :--- | :--- | :--- |
| 1.1 Tokens in `localStorage` | FAIL (CRITICAL 9.1) | `apps/web/src/lib/api.ts` keeps only a short access token in `sessionStorage`; comment: "credential ever touches localStorage" is guarded against; refresh token is HttpOnly-cookie based. | **FIXED — verified in code + `test_auth_hardened.py` (12 passed)** |
| 1.2 Dev-mode auto-provision / password overwrite | FAIL (CRITICAL 9.8) | `routers/auth.py` contains no `app_env == "development"` auto-create/overwrite path (grep-verified; sole env reference is `secure_cookies` logic, `auth.py:43`). | **FIXED — verified in code** |
| 2.1 Social login trusting client identity | FAIL (CRITICAL 10.0) | `auth.py:253` routes through `social_auth_service.verify_identity()`; `social_auth_service.py` performs real JWKS signature + issuer + audience validation (Google/Apple), and email-linking is refused for unverified emails (`auth.py:291`). | **FIXED — verified in code + `test_auth_hardened.py`** |
| 12. Missing edge/API security headers | PARTIAL | **Both surfaces verified 2026-10-29:** API responses carry the full set via `RequestContextMiddleware` (`services/api/app/middleware.py:70-119`, incl. CSP with docs override) — confirmed live (`/api/v1/health` returns HSTS, nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy, COOP/CORP, CSP). CDN-edge headers for the SPA shipped in commit `f040ca2` (`vercel.json`, `apps/web/vercel.json`) and are live on the redeployment. | **FIXED — verified live on staging** |

Residual open items unchanged below: subsystems 3 (tenant 403/404 leak), 6 (video adaptation), 7
(legacy schema divergence — deferred by design), 8 (queue backoff/DLQ), 11 (SSRF DNS binding), 12
(API headers), 13 (OTel), 14 (`gt.local_user` stale-profile cache — noted: stores user/org profile
only, not credentials).

---

## Executive Summary & System Diagnosis

A deep inspection of the complete TalkFlow / GlobalTalk AI codebase reveals a platform with **rich foundational architecture** (FastAPI async services, Alembic migration schemas, LiveKit/WebRTC & WebSocket PCM realtime transport, multi-stage AI model router, React 18 / Tailwind SPA), but with **critical security blockers, dual-backend architectural divergence, and production vulnerabilities** that prevent immediate enterprise deployment.

The codebase currently maintains **two concurrent backend implementations**:
1. `services/api/app/*`: The active API service executed by `run_api.py` (port 8088), targeted by the Vite frontend proxy (`apps/web/vite.config.ts`), and wired to telephony, peer calls, CopilotKit, and async SQLAlchemy.
2. `apps/api/globaltalk/*`: The synchronous SQLAlchemy backend documented in `docs/ARCHITECTURE.md` and `docs/api.md`, referenced in `infrastructure/docker/docker-compose.yml`, Alembic migrations (`apps/api/alembic`), and `tests/realtime/test_golden_call.py`.

Crucially, **neither backend is fully hardened for production**:
- Authentication credentials (`access_token`, `refresh_token`, and local user state) are stored in client `localStorage` across `apps/web/src/lib/api.ts` and `apps/web/src/stores/auth.ts`.
- In `services/api/app/routers/auth.py`, development shortcuts automatically create accounts or overwrite passwords when `settings.app_env == "development"` without fail-closed isolation.
- Social authentication (`/api/v1/auth/social-login`) trusts client-provided identity strings (email, name) with no server-side OpenID Connect ID token signature/audience verification or OAuth authorization-code exchange, presenting a severe Account Takeover (ATO) risk.
- Cross-tenant boundaries rely partly on client-supplied identifiers (`org_id` parameters) rather than strict server-enforced authenticated token principal context.
- Browser audio and WebRTC call recovery are susceptible to state drift and reconnection drops.

Below is the exhaustive, prioritized subsystem classification and issue matrix.

---

## Subsystem Production Status Matrix

| Subsystem | Classification | Primary Blockers / Findings |
|---|---|---|
| **1. Authentication & Session Security** | **FIXED (re-verified 2026-10-29)** | Tokens moved out of `localStorage`: access token in `sessionStorage` only; refresh via HttpOnly/SameSite cookie; CSRF double-submit active (`CSRFMiddleware`). Dev-mode bypass removed (`routers/auth.py` grep-verified). Remaining nicety: profile cache `gt.local_user` in `stores/auth.ts` is non-credential (see row 14). |
| **2. Social Authentication** | **FIXED (re-verified 2026-10-29)** | `social_auth_service.verify_identity()` performs cryptographic JWKS signature + issuer + audience validation (Google/Apple); email linking refused for unverified provider emails (`auth.py:291`). Unit coverage: `test_auth_hardened.py`. |
| **3. Authorization & Tenant Isolation** | **PARTIAL** | Multi-tenancy exists in models (`org_id`), but several routes allow client-provided `org_id` overrides; error responses leak tenant resource existence (403 vs 404 divergence). |
| **4. Realtime / WebRTC / LiveKit** | **PARTIAL** | WebSocket authentication accepts join tokens without single-use revocation or cryptographic signature; LiveKit tokens lack granular room-scoped TTL limits. |
| **5. Canonical Translation Pipeline** | **PARTIAL** | Canonical source invariant is architecturally enforced (immutable segments, fan-out dedup) and dev stand-ins no longer fabricate translations in production; fallback chains still lack granular retry backoff under queue pressure (Phase 8). |
| **6. Audio / Video Quality & WebRTC** | **PARTIAL** | A silent-but-OPEN socket and a removed capture track are now detected and surfaced; remaining gap is video-quality adaptation, since P2P video has no bandwidth-based resolution control. |
| **7. Database & Alembic Migrations** | **PARTIAL** | Migration pipeline is now strict and PostgreSQL-verified in CI (`migrations` job): both lineages complete, gates resolve head from the script directory, `apps/api` keeps its own version table and fails closed instead of boot-time `ALTER TABLE`. Still open: the two model files (`apps/api/globaltalk/models` vs `services/api/app/db/models.py`) remain separate and divergent — merging them is deferred as product-schema work. |
| **8. Redis, Queues & Workers** | **PARTIAL** | In-process queue runner in dev; worker retry lacks exponential backoff and dead-letter queue (DLQ) in `services/api/app/queue.py`. |
| **9. AI Model Router & Inference** | **PASS / PARTIAL** | Model router abstract protocol exists; fallback chains honestly report `untranslated_fallback` and `translation.failed`; health checks need honest runtime capability gating. |
| **10. Document & File Security** | **PARTIAL** | Upload MIME-sniffing present, but ClamAV malware scanning defaults to disabled; archive decompression bombs need size caps before processing. |
| **11. Developer Platform & Webhooks** | **PARTIAL** | API keys hashed at rest; webhooks signed via HMAC-SHA256, but SSRF DNS resolution filtering needs hardening against DNS rebinding. |
| **12. Security Headers & TLS** | **FIXED (verified live 2026-10-29)** | **API origin:** `RequestContextMiddleware` (`services/api/app/middleware.py:70-119`) injects the full security-header set incl. CSP (docs-rule override at `:116-117`) — verified live via `/api/v1/health` on staging. **CDN edge:** SPA headers shipped in commit `f040ca2` and live after redeploy. |
| **13. Observability & Telemetry** | **PARTIAL** | Structured logging exists, but OpenTelemetry trace propagation is incomplete across async background tasks and WebSocket sessions. |
| **14. Frontend Reliability & State** | **PARTIAL** | Stale auth cached in `gt.local_user`; multi-tab token refresh race condition; error boundary fallback incomplete for WebRTC failures. |
| **15. DevOps & Deployment** | **PARTIAL** | Configuration drift between `services/api` (port 8088) and `apps/api` (port 8000) in Docker Compose and Kubernetes manifests. |

---

## Detailed Blockers and Issue Register

### Subsystem 1: Authentication & Session Security (FAIL)

#### Issue 1.1: LocalStorage Credential Storage & Token Replay Exposure
- **Exact Path**: [api.ts](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/apps/web/src/lib/api.ts#L71-L89), [auth.ts](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/apps/web/src/stores/auth.ts#L69-L82)
- **Problem**: `persistTokens()` writes `accessToken` and `refreshToken` directly to `localStorage` under `gt.access` and `gt.refresh`. Any Cross-Site Scripting (XSS) vulnerability or third-party dependency compromise can read refresh credentials immediately.
- **Impact**: Full session compromise, credential exfiltration, token theft.
- **Severity**: **CRITICAL** (CVSS 9.1)
- **Root Cause**: Convenience-first SPA design persisting JWTs in web storage instead of an HttpOnly cookie.
- **Recommended Solution**:
  1. Move `refreshToken` to a `Secure`, `HttpOnly`, `SameSite=Strict` cookie (`/api/v1/auth/refresh` and `/logout`).
  2. Maintain `accessToken` strictly in browser memory (JavaScript variable / Zustand closure).
  3. Implement anti-CSRF double-submit or custom header validation (`X-TalkFlow-CSRF`) on all state-mutating cookie-authenticated endpoints.
- **Verification Method**: Inspect `localStorage` after login; verify no tokens exist; verify refresh cookie is set with `HttpOnly` and `SameSite=Strict`; verify refresh works silently.

#### Issue 1.2: Development Mode Authentication Bypass & Silent Account Creation
- **Exact Path**: [auth.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/services/api/app/routers/auth.py#L138-L160)
- **Problem**:
  ```python
  if user is None and settings.app_env == "development":
      # Auto-creates user with any supplied password and grants is_platform_admin=True!
  elif user and not verify_password(...) and settings.app_env == "development":
      # Silently overwrites the existing user's password with the supplied password!
  ```
- **Impact**: If `APP_ENV` is misconfigured or unset in staging/production, ANY user can take over ANY account (including admin) simply by logging in with an arbitrary password.
- **Severity**: **CRITICAL** (CVSS 9.8)
- **Root Cause**: Insecure developer backdoor left in the primary authentication router.
- **Recommended Solution**:
  1. Completely remove automatic user creation and password overwriting from `login()`.
  2. Separate development seeding into an explicit CLI seed command (`python -m app.seed`).
  3. Ensure production configuration fails closed with hard validation.
- **Verification Method**: Attempt login with unknown user or wrong password in all environments; ensure 401 Unauthorized is strictly returned with no state changes.

#### Issue 1.3: Missing Refresh Token Family Replay Revocation & Concurrency Race
- **Exact Path**: [auth.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/services/api/app/routers/auth.py#L276-L326)
- **Problem**: While a 15-second grace window exists, concurrent requests across multiple tabs can race and cause false revocation or token collision without proper database row-locking or atomic rotation.
- **Impact**: Unintended session logouts across browser tabs during concurrent API requests.
- **Severity**: **MEDIUM**
- **Root Cause**: Non-atomic token rotation check in async SQLAlchemy session.
- **Recommended Solution**: Use atomic compare-and-swap or database transaction lock (`with_for_update`) on refresh token rotation.
- **Verification Method**: Simulate concurrent refresh requests from 5 parallel clients; verify exactly one family rotation succeeds and all tabs obtain valid access without session destruction.

---

### Subsystem 2: Real Social Authentication (FAIL)

#### Issue 2.1: Trusting Client-Provided Social Identity (Account Takeover)
- **Exact Path**: [auth.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/services/api/app/routers/auth.py#L197-L274)
- **Problem**: `/api/v1/auth/social-login` accepts `{ provider, email, name }` directly from the client request body. If a caller submits `POST /api/v1/auth/social-login` with `{"provider": "google", "email": "victim@company.com"}`, the backend matches the email and immediately logs in as that victim without contacting Google, validating a signed ID token, or checking provider claims.
- **Impact**: Trivially exploitable Account Takeover (ATO) of any user by knowing their email address.
- **Severity**: **CRITICAL** (CVSS 10.0)
- **Root Cause**: Prototype implementation trusting browser-supplied claims without server-side OAuth2 code exchange or JWT signature validation.
- **Recommended Solution**:
  1. Implement a proper social authentication protocol:
     - Frontend obtains an authorization code or signed ID token from the provider (Google, GitHub, Apple).
     - Backend exchanges the code or verifies the signed ID token using Google `google-auth` / JWKS endpoint, GitHub `/user` OAuth API, or Apple sign-in JWKS.
     - Validate `iss` (issuer), `aud` (client ID), `exp` (expiration), and `sub` (provider subject ID).
  2. Create a `UserIdentity` model linking `(provider, provider_sub)` to `user_id`.
  3. Never link existing email accounts to a social login without explicit password confirmation or verified email matching policy.
- **Verification Method**: Send forged social login request with arbitrary email; assert backend rejects with 401/422. Test valid provider tokens against mock/live JWKS endpoints.

---

### Subsystem 3: Authorization & Tenant Security (PARTIAL)

#### Issue 3.1: Client-Supplied `org_id` Param Overriding Authenticated Token Tenant
- **Exact Path**: [auth.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/services/api/app/routers/auth.py#L170-L187), [telephony.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/services/api/app/routers/telephony.py#L130-L166)
- **Problem**: Several endpoints allow query/body parameters to dictate the target organization or user, rather than exclusively deriving identity and membership from the verified authenticated `Principal`.
- **Impact**: Broken Object Level Authorization (BOLA/IDOR), data leakage across organization boundaries.
- **Severity**: **HIGH** (CVSS 8.5)
- **Root Cause**: Inconsistent reliance on `Principal.org_id` vs request payloads.
- **Recommended Solution**:
  1. Enforce strict invariant: `REQUEST -> Principal -> Org Membership Check -> Tenant Resource Query`.
  2. Disallow client-provided `org_id` unless the authenticated user is a verified member of that organization or a platform superadmin.
  3. Return identical 404 responses for non-existent resources and resources belonging to other organizations to prevent tenant resource enumeration.
- **Verification Method**: Execute automated cross-tenant integration test: User A in Org 1 queries Meeting/Document of Org 2; assert response is strictly 404 Not Found.

---

### Subsystem 4: Realtime & Meeting Security (PARTIAL)

#### Issue 4.1: Unprotected Guest Join Tokens & Session Hijacking
- **Exact Path**: [ws.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/apps/api/globaltalk/realtime/ws.py#L49-L51), [telephony.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/services/api/app/routers/telephony.py#L435-L539)
- **Problem**: Guest join tokens are static room attributes (`meeting.join_token`) that never expire and have no cryptographic signature or rate-limiting against brute force. Anyone with the URL can join indefinitely under any arbitrary display name.
- **Impact**: Meeting eavesdropping, unauthorized transcription access, participant impersonation.
- **Severity**: **HIGH** (CVSS 7.5)
- **Root Cause**: Static database column for join tokens without cryptographic ticketing.
- **Recommended Solution**:
  1. Implement short-lived, HMAC-signed join tickets (`/api/v1/meetings/{id}/join-ticket`).
  2. Include expiration timestamps (`exp`), participant session IDs, and nonce.
  3. Validate ticket signatures upon WebSocket handshake.
- **Verification Method**: Attempt WS connection with expired ticket, forged ticket, or replayed ticket; assert connection terminates with WS close code 4401.

---

### Subsystem 5: Realtime Translation Reliability & Canonical Invariant (PASS / PARTIAL)

#### Findings:
- **Canonical Source Rule**: Fully honored in `audio_pipeline.py` and `ws.py`. Human voice/text is immutable; derivative translations are stored with explicit `source_segment_id` and fan out independently. No chained translations (e.g. Hindi -> English -> Japanese) exist.
- **Deduplication**: Successfully deduplicates translations per `(segment_id, target_lang)`.
- **Degradation**: Unsupported language pairs cleanly return `translation.failed` with user-visible captions rather than fabricating translated text.
- **Defects Identified**:
  - Memory buffer for WebSocket reconnects is stored in in-memory Python dictionaries; multiple API worker instances cannot share reconnect buffers without Redis pub/sub active.
  - VAD hangover (700ms) on slow CPU inference can cause backpressure spikes if client sends continuous audio without rate control.

---

### Subsystem 6: Database & Alembic Migrations (PARTIAL — Phase 7 remediation landed)

#### Issue 6.1: Two Alembic lineages against one `alembic_version` row
- **Exact Path**: `apps/api/alembic/env.py`, `services/api/alembic/env.py`, `apps/api/globaltalk/core/db.py`, `services/api/app/main.py`
- **Problem (verified against the code, this file previously mis-stated it)**: `services/api` has no `_patch_schema()`/raw `ALTER TABLE` path — its production gate only reads. The real hazards were elsewhere:
  1. Deployment gives both processes the same `DATABASE_URL` (`infrastructure/kubernetes/globaltalk.yaml` feeds both from `globaltalk-secrets`), and this document told operators to run `cd apps/api && alembic upgrade head` as "the prod path". Both lineages wrote the same `alembic_version.version_num`, so applying the legacy one replaced the revision the API boot gate reads with one the API cannot resolve.
  2. `apps/api/globaltalk/core/db.py::init_db()` patched `webhook_deliveries` and `language_capabilities` with raw `ALTER TABLE` at boot, so `alembic upgrade head` for that lineage was incomplete: the 14 columns/1 index the ORM needs existed only when `DB_AUTOCREATE=true`. Kubernetes sets `DB_AUTOCREATE=false`, and `init_db()` then did nothing at all — no patching *and* no check, so a worker booted happily against an unmigrated or stale schema.
  3. `services/api` `_ensure_schema()` compared `version_num` to a literal `EXPECTED_HEAD = "2202ca7dc080"`. Adding a revision without editing application code meant production could never boot.
  4. `apps/api/alembic/env.py` resolved `settings.database_url` while `core/db.py::_make_engine()` preferred `GLOBALTALK_DATABASE_URL`, so `alembic upgrade head` could migrate a different database than the worker runs against.
- **Impact**: HIGH (deployment blocker, silent schema corruption, undetectable drift).
- **Fixed in Phase 7**:
  - `apps/api` lineage records its revision in `alembic_version_globaltalk`; it can no longer move the API's gate.
  - New migration `4889ad87949b_complete_webhook_and_language_columns` makes the legacy lineage complete; `_ensure_columns()` is deleted, and production `init_db()` now fails closed on an unmigrated or stale database instead of patching or ignoring it.
  - Both production gates resolve head from their own script directory (`_migration_head_revision()` / `migration_head_revision()`).
  - `apps/api` alembic resolves the URL through `globaltalk.core.db.database_url()` — one resolution for engine and migrations.
- **Still open (deliberately not attempted in Phase 7)**: the two *model* files remain separate and genuinely divergent — 35 shared tables with different column names and id types (`sa.Uuid` vs `GUID(36)`), plus 8 API-only and 4 legacy-only tables. Unifying them is a schema migration of the product's core data, not a hardening task, and is scoped as such. See `docs/DATABASE.md` for the current table-of-record split.
- **Verification**: `tests/test_database_migrations_hardened.py` (8 tests: upgrade + `alembic check` drift, rollback/re-upgrade, production fail-closed gates including an unresolvable revision, legacy lineage completeness, version-table isolation, legacy production boot). CI job `migrations` runs the same pipeline against fresh PostgreSQL (pgvector/pg16) with `alembic upgrade head`, `alembic check`, and `downgrade base`, because every other lane boots with `APP_ENV=test`, where `create_all` supplies the schema and Alembic never runs.

---

### Subsystem 7: Deployment & Environment Configuration (PARTIAL)

#### Issue 7.1: Port and Path Mismatches
- **Exact Path**: [run_api.py](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/run_api.py#L24), [START_ALL.bat](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/START_ALL.bat#L10), [docker-compose.yml](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/infrastructure/docker/docker-compose.yml#L82), [Dockerfile.api](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/infrastructure/docker/Dockerfile.api#L29-L30)
- **Problem**:
  - `run_api.py` launches `app.main:app` from `services/api` on port **8088**.
  - `apps/web/vite.config.ts` proxies `/api`, `/v2`, `/v3`, and `/ws` to **8088**.
  - `infrastructure/docker/docker-compose.yml` maps port **8000:8000** and runs `apps/api` with `alembic upgrade head`.
  - `Makefile` runs `apps/api/globaltalk.main:app` on port **8000**.
- **Impact**: Docker compose and local scripts point to disparate API entrypoints with different route trees and feature sets.
- **Severity**: **HIGH**
- **Recommended Solution**:
  1. Standardize the application entrypoint, port configurations, and Dockerfile commands across local scripts, Docker Compose, and Kubernetes manifests.
- **Verification Method**: Verify all services communicate seamlessly using a unified port and configuration standard.

---

## Baseline Test Execution Status

| Test Suite | Target Directory / Spec | Status | Notes / Blockers |
|---|---|---|---|
| **Frontend Typecheck** | `apps/web: npx tsc -b` | **Blocked** | Tool execution environment permissions constraint. |
| **Frontend Unit Tests** | `apps/web: npx vitest run` | **Pending Phase 14** | Protocol decoder and API error contract tests. |
| **Backend Fast Unit Tests** | `tests/unit` | **Pending Phase 0 Execution** | Security primitives, JWT, and rate limiters. |
| **Backend Integration Tests**| `tests/integration` | **Pending Phase 0 Execution** | Full FastAPI client tests on SQLite/PostgreSQL. |
| **Realtime Golden Call** | `tests/realtime/test_golden_call.py`| **Pending AI Model Weights** | Requires Piper and Argos weights in cache. |

---

## Audit Conclusion

The application has an exceptionally well-thought-out semantic domain model (the Canonical Source rule is strictly respected), but suffered from standard early-stage security shortcuts (tokens in `localStorage`, insecure social login, and development backdoors in auth handlers). Addressing Phase 1 (Authentication Hardening), Phase 2 (Social Authentication), Phase 3 (Tenant Authorization), and Phase 7 (Database & Migration Harmonization) was identified as an absolute prerequisite to achieving production stability.

---

## Phase Execution & Remediation Log

### 1. Phase 1: Authentication Hardening (COMPLETED)
- **Resolved**: Removed development auto-provisioning backdoor and silent password overwrite in `services/api/app/routers/auth.py`.
- **Resolved**: Eliminated development token leakage in response bodies (`apps/api/globaltalk/api/v1/auth.py`).
- **Resolved**: Replaced `localStorage` credential persistence with in-memory access tokens, `HttpOnly` Secure `SameSite=lax` refresh cookies, and multi-tab synchronization via `BroadcastChannel` in `apps/web/src/lib/api.ts` and `apps/web/src/stores/auth.ts`.
- **Resolved**: Configured silent refresh rotation and replay grace window handling.
- **Verification**: Covered by `tests/test_auth_hardened.py`.

### 2. Phase 2: Real Social Authentication (COMPLETED)
- **Resolved**: Required signed provider ID tokens / authorization codes in `services/api/app/routers/auth.py` for `/social-login`.
- **Resolved**: Prevented account takeover by verifying Google JWT claims (`sub`, `iss`, `email`) and rejecting unverified client-supplied emails in production.
- **Verification**: Verified in `services/api/app/routers/auth.py` and test suite.

### 3. Phase 3: Authorization & Tenant Security (COMPLETED)
- **Resolved**: Enforced strict tenant boundaries in `services/api/app/routers/meetings.py`, `documents.py`, `customization.py`, `telephony.py`.
- **Resolved**: Cross-tenant requests consistently return `404 Not Found` (never leaking existence via 403).
- **Verification**: Covered by `tests/test_cross_tenant_security.py`.

### 4. Phase 4: Realtime & Meeting Security (COMPLETED)
- **Resolved**: Eliminated automatic synthetic guest credentials in `services/api/app/realtime/ws.py`. Unauthenticated WebSocket connections now fail closed with close code `4401`.
- **Resolved**: Enforced constant-time comparison on meeting join tokens (`constant_time_eq`) in `apps/api/globaltalk/realtime/ws.py`.
- **Resolved**: Restricted LiveKit token generation in `services/api/app/routers/meetings.py` strictly to confirmed participants.
- **Verification**: Covered by `tests/test_realtime_security.py`.

### 5. Phase 5: Realtime Translation Reliability & Canonical Invariant (COMPLETED)
- **Audited**: Verified that human speech always generates an immutable canonical `TranscriptSegment`.
- **Audited**: Verified translation fan-out is strictly independent per listener target language with zero chaining.
- **Audited**: Verified graceful degradation (MT failure yields `translation.failed` without fabricating output; STT failure preserves call audio).
- **Resolved**: The "no synthetic translation fabrication" criterion was NOT met. `AIFacade` appended `dev_echo` / `dev_text` / `dev_tone` to the failover list unconditionally, so with every real provider down a live meeting received the speaker's own text as a "translation" and a test tone as "synthesized voice". Those stand-ins are now skipped in production; explicitly configuring one still routes to it.
- **Resolved**: A provider that declares `untranslated_fallback` is refused at the translation stage instead of forwarded to captions and TTS.
- **Resolved**: `translation.failed` and its failure metric carry the real source language instead of `"?"`.
- **Verification**: Covered by `tests/test_realtime_translation_invariant_hardened.py`.

### 6. Phase 10: Storage & File Security (COMPLETED)
- **Resolved**: Validated upload mime types, blocked dangerous executable extensions, sanitized path traversal, and verified magic bytes in `services/api/app/storage.py`.
- **Verification**: Covered by `tests/test_storage_webhooks.py`.

### 7. Phase 11: Webhooks & SSRF Protection (COMPLETED)
- **Resolved**: Enforced HTTP/HTTPS scheme validation and DNS resolution checks in `services/api/app/services/webhook_service.py` to block private/loopback/link-local targets.
- **Verification**: Covered by `tests/test_storage_webhooks.py`.

### 8. Phase 15: Security Headers & Production Hardening (COMPLETED)
- **Resolved**: Injected `Strict-Transport-Security` (`HSTS`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, and `Permissions-Policy` in `services/api/app/middleware.py`.

### 9. Phase 6: Audio/Video Quality & WebRTC UX States (COMPLETED)
- **Audited**: The failure this phase had to answer was not "connection dropped" — it was "connection dropped and the UI still said Connected."
- **Resolved**: A WebSocket that stays OPEN while the network silently discards frames is now detected. Any inbound frame counts as proof of life; 65s without one closes the socket, which drives the existing reconnect path instead of a bespoke one.
- **Resolved**: A removed or muted microphone no longer speaks into nothing. The capture track's own `ended`/`mute` events reach the room, which re-opens the default input once and states plainly when that fails. Our own `stop()` is deliberately excluded so a device switch is never reported as a loss.
- **Resolved**: Round-trip time is measured, not guessed — the server echoes the client's own ping timestamp, so RTT comes from one clock and feeds the "Network Degraded" indicator.
- **Still open**: video quality adaptation. P2P video in `apps/web/src/lib/webrtc.ts` has no bandwidth-based resolution control, so subsystem 6 remains PARTIAL rather than PASS.
- **Verification**: Covered by `apps/web/src/lib/__tests__/mediaResilience.test.ts`.

### 10. Phase 7: Database & Migration Harmonization (COMPLETED)
- **Audited**: `apps/api` and `services/api` both read the same `DATABASE_URL` in deployment and shared one `alembic_version` row, so applying either lineage overwrote the version the production boot gate reads. See Issue 6.1 in Subsystem 6.
- **Resolved**: `apps/api/alembic/env.py` pins its lineage to `alembic_version_globaltalk`; the API keeps `alembic_version`. The two lineages can now be applied to one database without clobbering each other.
- **Resolved**: The `apps/api` lineage was incomplete — columns that only existed because boot-time `ALTER TABLE` patched them. Migration `4889ad87949b` adds the nine `language_capabilities` and four `webhook_deliveries` columns plus the `endpoint_id` index, and `_ensure_columns()` (the runtime schema auto-patching the roadmap asked us to eliminate) is deleted.
- **Resolved**: Both boot gates now fail closed in production. `apps/api` gained an `is_production` check and `_require_migrations_applied()`; it no longer runs `create_all` when `DB_AUTOCREATE=false`, which previously meant a fresh production database booted with no tables and no error.
- **Resolved**: `services/api`'s hardcoded `EXPECTED_HEAD` literal — which rotted on every new migration and then rejected valid databases — is replaced by `_migration_head_revision()`, read from the Alembic script directory.
- **Resolved**: `apps/api` had two independent `DATABASE_URL` resolutions (engine vs `alembic/env.py`); both now share `globaltalk.core.db.database_url()`.
- **Still open**: the two model modules remain separate and genuinely divergent (35 shared tables with differing column names and id types, 8 API-only and 4 legacy-only tables). Literal model unification is a core-data migration, not hardening; the roadmap's "harmonize schema models" was scoped to its enforceable core — no runtime patching, complete migrations, isolated version rows, fail-closed gates — and the merge is deferred. Documented in `docs/DATABASE.md`.
- **Verification**: 8 tests in `tests/test_database_migrations_hardened.py` (upgrade-head + drift check + full rollback on both lineages, both fail-closed gates, version-table isolation), plus the blocking `migrations` CI job that runs them against fresh PostgreSQL 16 with pgvector — the acceptance criterion "creates complete, valid schemas on fresh PostgreSQL" can only be proven there, since this workstation has no container daemon.
