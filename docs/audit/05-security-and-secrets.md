# Phase 3 Technical Audit: Security, Secrets & Access Control

**Date**: 2026-10-28  
**Audit Branch**: `audit-baseline`  
**Primary Reviewer**: Application Security & Infrastructure Architect  

---

## 1. Authentication & Session Lifecycles

### 1.1 Credential & Password Storage
- **Algorithm**: `bcrypt` with adaptive salt rounds (`settings.bcrypt_rounds`, default 12 in production, 4 in test for performance).
- **Password Policy**: Enforced on signup and password update (`security.password_policy_ok`): minimum 8 characters, maximum 256 characters, requiring mixed alphanumeric characters. Plaintext passwords are never logged, stored, or returned in API responses.
- **Timing Attack Mitigation**: Password and API key validations utilize constant-time comparison via `hmac.compare_digest`.

### 1.2 Token Architecture (JWT Dual-Token Model)
- **Access Tokens**: Short-lived (default 15 minutes), signed using `HS256` with strict payload claims (`sub`, `type="access"`, `jti`, `iat`, `exp`, `iss="globaltalk-ai"`).
- **Refresh Tokens**: Long-lived (default 30 days) stored hashed in the `refresh_tokens` database table with device footprint metadata (`user_agent`, `ip_address`). Each refresh rotates the token pair and invalidates the previous refresh token.
- **Revocation**: Calling `/api/v1/auth/logout` or `/api/v1/auth/logout-all` immediately revokes all active refresh tokens and sessions in the database.

### 1.3 CSRF Protection (`CSRFMiddleware`)
- **Mechanism**: Double-submit cookie protection.
- State-changing requests (`POST`, `PUT`, `DELETE`, `PATCH`) that rely on browser cookies must supply the matching `X-TalkFlow-CSRF` header against the `csrf_token` cookie.
- Safe methods (`GET`, `HEAD`, `OPTIONS`) and server-to-server API requests authenticating via `Authorization: Bearer <API_KEY>` or `<JWT>` are exempt.

---

## 2. API Key Management & Developer Scopes

- **Key Format**: `gt_live_<40 hex characters>` generated using cryptographically secure random bytes (`secrets.token_hex(24)`).
- **Storage Policy**: Plaintext keys are presented exactly once upon creation. Only the SHA-256 hash (`hash_api_key`) and the key prefix (`gt_live_...` first 12 characters) are stored in the `api_keys` table.
- **Permissions**: Keys are scoped by organization ID and role (`admin`, `read_write`, `read_only`).

---

## 3. Tenancy & Isolation Boundaries

- **Object-Level Authorization**: Every table housing user or enterprise assets (`documents`, `meetings`, `glossaries`, `style_profiles`, `call_sessions`, `usage_records`) contains a foreign key to `org_id` / `tenant_id`.
- **Query Scoping**: Enforced via FastAPI dependencies (`deps.get_current_org`, `deps.get_current_user`). Repositories filter explicitly with `where(Model.org_id == org.id)`.
- **Cross-Tenant IDOR Prevention**: Tests in `tests/test_cross_tenant_security.py` and `tests/test_tenant_security_extended.py` verify that tenant A cannot access, edit, or delete tenant B's resources even when possessing the exact resource UUID.

---

## 4. Secrets Management & Environment Hygiene

- **Repository Hygiene**: Full git history scanned using Gitleaks (`ghcr.io/gitleaks/gitleaks:v8.30.1`).
- **Templates**: `.env.example` and `.env.production.example` verified free of active credentials. All secrets are formatted as empty strings or placeholders (`replace-with-...`).
- **Client/Server Secret Boundary**: Frontend client code (`apps/web`) only receives environment variables prefixed with `VITE_`. Server secrets (Azure keys, OpenAI tokens, LiveKit secrets, database connection strings) are strictly isolated to `services/api` and cannot be accessed by browser bundles.

---

## 5. Network, CORS & Denial of Service Safeguards

- **CORS Configuration**: Explicit origin whitelist (`settings.allowed_origins`). Wildcard `*` is prohibited in production.
- **Rate Limiting**: Configured using SlowAPI with token-bucket limits:
  - Auth endpoints (`/login`, `/signup`): 10 requests / minute per IP.
  - Translation endpoints: Tiered by organization subscription limits (e.g. 100,000 / min in enterprise, 60 / min on free tier).
  - Telephony dialing: Idempotency keys required on `/api/v1/telephony/calls` to prevent accidental double-dialing.
