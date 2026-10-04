# GlobalTalk AI — Production Roadmap

**Date:** 2026-10-04  
**Based on:** Phase 0 Production Audit (`docs/PRODUCTION_AUDIT.md`)  
**Status:** Planning Phase

---

## Roadmap Overview

This roadmap transforms the existing TalkFlow repository into a production-ready platform through 19 phases, aligned with the original requirements. Each phase has clear acceptance criteria and dependencies.

### Phase Sequencing Logic

1. **Phase 0 (Complete):** Audit and baseline — DONE
2. **Phase 1-3 (Security Foundation):** Auth hardening → Social auth → Authorization — these must be done first as they affect all other security
3. **Phase 4-6 (Realtime Hardening):** WebSocket security → Translation reliability → Audio/video quality
4. **Phase 7-11 (Infrastructure Hardening):** Database → Redis/queues → AI router → Documents → API/webhooks
5. **Phase 12-14 (Platform Hardening):** Security headers → Observability → Frontend hardening
6. **Phase 15-17 (Validation):** QA/testing → DevOps → Performance
7. **Phase 18-19 (Polish & Gate):** Product improvements → Final production gate

---

## Detailed Phase Plans

### PHASE 1: Authentication Hardening

**Priority:** CRITICAL  
**Duration:** Estimated 3-5 days  
**Dependencies:** None

#### Objectives
- Replace localStorage token storage with secure cookie-based sessions
- Implement CSRF protection
- Add refresh token rotation with family tracking
- Ensure production fails closed

#### Tasks

1. **Implement secure session cookies**
   - Access token: memory-only in JavaScript
   - Refresh credential: HttpOnly + Secure + SameSite=Lax cookie
   - Cookie settings: `httponly=true, secure=true, samesite=lax, path=/api`
   - File: `services/api/app/routers/auth.py` — modify token issuance
   - File: `services/api/app/config.py` — add cookie settings

2. **Implement CSRF protection**
   - Double-submit cookie pattern
   - CSRF token in meta tag or endpoint
   - Validate CSRF token on all state-changing requests
   - File: `services/api/app/middleware.py` — add CSRF middleware
   - File: `apps/web/src/lib/api.ts` — add CSRF token handling

3. **Enhance refresh token security**
   - Add refresh token family tracking
   - Tighten grace window (15s → 5s or remove)
   - Add specific rate limit for refresh endpoint
   - File: `services/api/app/routers/auth.py`

4. **Remove development authentication shortcuts**
   - Remove auto-provisioning on login
   - Remove password update on failed login
   - Remove fallback principal for non-production
   - File: `services/api/app/routers/auth.py`
   - File: `services/api/app/deps.py`

5. **Session revocation improvements**
   - Logout invalidates refresh token regardless of access token state
   - Password change invalidates all sessions
   - Password reset invalidates all sessions (already done)
   - File: `services/api/app/routers/auth.py`

#### Acceptance Criteria
- [ ] Access tokens not stored in localStorage
- [ ] Refresh token in HttpOnly cookie
- [ ] CSRF protection on all mutations
- [ ] No development authentication shortcuts
- [ ] Logout works with expired access token
- [ ] Password change revokes all sessions
- [ ] Production config fails closed

---

### PHASE 2: Real Social Authentication

**Priority:** CRITICAL  
**Duration:** Estimated 5-7 days  
**Dependencies:** Phase 1

#### Objectives
- Implement proper OAuth flow for social providers
- Never trust browser-supplied identity
- Add user identity linkage model

#### Tasks

1. **Create user_identities table**
   - Store provider linkage (provider, provider_subject, provider_email)
   - File: New migration `add_user_identities_table.py`
   - Model: `services/api/app/db/models.py`

2. **Implement OAuth flow**
   - Frontend initiates OAuth (redirect to provider)
   - Provider returns authorization code
   - Backend exchanges code for tokens
   - Backend verifies ID token (signature, issuer, audience, nonce)
   - Backend extracts provider subject
   - File: `services/api/app/routers/auth.py` — new OAuth endpoints

3. **Provider verification**
   - Google: Verify ID token with Google's libraries
   - GitHub: Verify code exchange, get user info from API
   - Apple: Verify ID token with Apple's public keys
   - File: `services/api/app/services/` — provider verification services

4. **Account linking logic**
   - If provider subject exists → login
   - If email matches existing unlinked account → link (with verification)
   - Otherwise → create new account with provider identity
   - Never trust client-provided email for account creation
   - File: `services/api/app/routers/auth.py`

5. **State/nonce management**
   - Generate nonce per OAuth initiation
   - Store in cache with expiry
   - Verify on callback
   - File: `services/api/app/routers/auth.py`

#### Acceptance Criteria
- [ ] Social login requires OAuth flow (not just POST with email)
- [ ] ID tokens verified with provider
- [ ] Provider subject used for identity, not email
- [ ] Cannot create account with arbitrary email via social login
- [ ] Account takeover via email manipulation prevented

---

### PHASE 3: Authorization / Tenant Security

**Priority:** HIGH  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 1, Phase 2

#### Objectives
- Verify all endpoints properly enforce tenant isolation
- Add automated cross-tenant tests
- Ensure no IDOR vulnerabilities

#### Tasks

1. **Endpoint audit**
   - Review every protected endpoint for proper tenant filtering
   - Verify org_id comes from authenticated principal, not client
   - File: All router files in `services/api/app/routers/`

2. **Cross-tenant automated tests**
   - Add test for each resource type:
     - Meetings
     - Documents
     - Glossaries
     - Translation memories
     - Style profiles
     - API keys
     - Webhooks
     - Transcripts
     - Chat messages
   - File: `tests/integration/test_tenant_isolation.py` (new)

3. **Unified error responses**
   - Ensure "not found" and "other tenant" return identical responses
   - File: All resource lookup functions

#### Acceptance Criteria
- [ ] Every endpoint uses principal's org_id, not client-supplied
- [ ] Cross-tenant test covers all resource types
- [ ] Identical 404 for not-found vs other-tenant
- [ ] No resource leaks existence to other tenants

---

### PHASE 4: Realtime / Meeting Security

**Priority:** HIGH  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 1

#### Objectives
- Verify WebSocket authentication is robust
- Ensure guest credentials are properly scoped
- Prevent participant impersonation

#### Tasks

1. **Guest token audit**
   - Verify guest join tokens are:
     - Short-lived (meeting duration + small buffer)
     - Single meeting scoped
     - Participant-scoped
     - Not reusable
   - File: `services/api/app/routers/meetings.py`

2. **Participant authorization**
   - Verify participant can only access their own data
   - Prevent participant ID manipulation
   - File: `services/api/app/realtime/ws.py`

3. **Session ticket hardening**
   - Reduce default TTL if appropriate
   - Add rate limiting on ticket issuance
   - File: `services/api/app/security.py`, `services/api/app/realtime/ws.py`

#### Acceptance Criteria
- [ ] Guest tokens expire after meeting ends
- [ ] Guest tokens cannot be used for other meetings
- [ ] Participant cannot impersonate other participants
- [ ] Ticket issuance rate limited

---

### PHASE 5: Realtime Translation Reliability

**Priority:** HIGH  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 4

#### Objectives
- Verify all degradation paths work correctly
- Add additional reliability tests
- Ensure no translation fabrication

#### Tasks

1. **Failure path testing**
   - Test STT failure → original audio continues
   - Test MT failure → translation.failed event
   - Test TTS failure → captions continue
   - File: `tests/realtime/test_degradation.py` (new)

2. **Reconnect reliability**
   - Test reconnect with preferences preserved
   - Test reconnect with transcript preserved
   - Test reconnect during active translation
   - File: Enhance existing reconnect tests

3. **Edge case handling**
   - Participant leave during translation
   - Participant rejoin with new preferences
   - Room shutdown during active session
   - File: `tests/realtime/test_edge_cases.py` (new)

#### Acceptance Criteria
- [ ] STT failure doesn't break meeting
- [ ] MT failure sends translation.failed
- [ ] TTS failure doesn't break captions
- [ ] Reconnect preserves state correctly
- [ ] No translation fabrication in any failure mode

---

### PHASE 6: Audio/Video Quality

**Priority:** MEDIUM  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 5

#### Objectives
- Add visible connection states
- Improve device handling
- Add network quality indicators

#### Tasks

1. **Connection state visibility**
   - connecting / connected / reconnecting / degraded / disconnected states
   - File: `apps/web/src/pages/MeetingRoom.tsx`

2. **Device permission handling**
   - Clear messages for denied permissions
   - Device switching UI
   - File: `apps/web/src/pages/MeetingRoom.tsx`

3. **Network quality indicator**
   - Show reconnect status
   - Show translation delay status
   - File: `apps/web/src/components/meeting/`

#### Acceptance Criteria
- [ ] Clear connection state visible to users
- [ ] Permission denied handled gracefully
- [ ] Reconnecting state shown
- [ ] Translation unavailable state shown

---

### PHASE 7: Database / Migrations

**Priority:** MEDIUM  
**Duration:** Estimated 1-2 days  
**Dependencies:** None

#### Objectives
- Ensure migration CI works
- Add migration validation
- Fix any transaction issues

#### Tasks

1. **Migration CI**
   - Add migration test to CI
   - Test upgrade from initial schema
   - Test downgrade where applicable
   - File: CI configuration

2. **Startup schema verification**
   - Already implemented in production
   - Verify it works correctly
   - File: `services/api/app/main.py`

3. **Transaction review**
   - Review critical paths for atomicity
   - Add transactions where needed
   - File: Service layer files

#### Acceptance Criteria
- [ ] Migrations run automatically in deploy
- [ ] Production fails if schema missing
- [ ] Critical paths are atomic

---

### PHASE 8: Redis / Queues / Workers

**Priority:** MEDIUM  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 7

#### Objectives
- Add job leasing
- Add idempotency
- Improve worker reliability

#### Tasks

1. **Job leasing**
   - Add job-in-progress state
   - Add lease timeout
   - Requeue stuck jobs
   - File: `services/api/app/queue.py`

2. **Idempotency**
   - Add idempotency keys to jobs
   - Check for existing processing
   - File: Worker handlers

3. **Graceful shutdown**
   - Add drain period
   - Finish current job before stopping
   - File: `services/api/app/queue.py`

#### Acceptance Criteria
- [ ] Jobs don't get lost on worker crash
- [ ] Duplicate jobs don't cause duplicate work
- [ ] Workers drain gracefully on shutdown

---

### PHASE 9: AI Provider / Model Router

**Priority:** LOW  
**Duration:** Estimated 1-2 days  
**Dependencies:** None

#### Objectives
- Verify model health reporting is honest
- Ensure fallback chains work

#### Tasks

1. **Health probe verification**
   - Verify probes don't load full models
   - Verify failed models excluded from routing
   - File: `ai/model_router/`, health endpoints

2. **Fallback chain testing**
   - Test each fallback triggers correctly
   - File: `tests/unit/test_fallbacks.py` (enhance)

#### Acceptance Criteria
- [ ] Unavailable models not reported as available
- [ ] Fallback chains trigger correctly
- [ ] Passthrough flagged correctly

---

### PHASE 10: Document / File Security

**Priority:** MEDIUM  
**Duration:** Estimated 1-2 days  
**Dependencies:** Phase 7

#### Objectives
- Verify upload validation is comprehensive
- Ensure storage isolation
- Add malware scanning configuration

#### Tasks

1. **Upload validation audit**
   - Verify magic byte checking
   - Verify extension spoofing protection
   - Verify size limits
   - File: `services/api/app/storage.py`

2. **Storage isolation**
   - Verify tenant-scoped keys
   - Verify download authorization
   - File: Document endpoints

3. **Malware scanning**
   - Document ClamAV setup
   - Add configuration for production
   - File: Configuration, documentation

#### Acceptance Criteria
- [ ] Executable files rejected
- [ ] Extension spoofing prevented
- [ ] Size limits enforced
- [ ] Tenant isolation in storage
- [ ] Download authorization verified

---

### PHASE 11: API / Webhook / Developer Platform

**Priority:** MEDIUM  
**Duration:** Estimated 1-2 days  
**Dependencies:** Phase 10

#### Objectives
- Verify webhook security
- Add webhook replay protection
- Ensure API key rotation works

#### Tasks

1. **Webhook security audit**
   - Verify SSRF protection
   - Add idempotency keys to payloads
   - File: `services/api/app/services/webhook_service.py`

2. **API key enhancements**
   - Verify rotation invalidates old key immediately
   - Verify last-used tracking works
   - File: API key endpoints

#### Acceptance Criteria
- [ ] Webhook URLs validated for SSRF
- [ ] Webhook payloads have idempotency keys
- [ ] API key rotation works correctly
- [ ] Revoked keys rejected immediately

---

### PHASE 12: Security Hardening

**Priority:** HIGH  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 1, Phase 3

#### Objectives
- Add missing security headers
- Implement CSP
- Add HSTS
- Run secret scanning

#### Tasks

1. **Security headers**
   - Add HSTS header (production only)
   - Add CSP header appropriate for SPA
   - File: `services/api/app/middleware.py`

2. **Secret scanning**
   - Run secret scanning on repository
   - Remove any found secrets
   - Add pre-commit hook for secret scanning

3. **Production configuration validation**
   - Verify all required secrets are set
   - Verify TLS is configured
   - File: Deployment configuration

#### Acceptance Criteria
- [ ] HSTS header present in production
- [ ] CSP header present and appropriate
- [ ] No secrets in source code
- [ ] Production config validated on startup

---

### PHASE 13: Observability

**Priority:** MEDIUM  
**Duration:** Estimated 1-2 days  
**Dependencies:** None

#### Objectives
- Verify observability is comprehensive
- Add missing metrics
- Ensure logs are appropriate

#### Tasks

1. **Metrics review**
   - Verify all required metrics present
   - Add any missing TalkFlow-specific metrics
   - File: `services/api/app/metrics.py`

2. **Log review**
   - Verify sensitive data redacted
   - Verify context included (request_id, trace_id, tenant, user)
   - File: Logging configuration

#### Acceptance Criteria
- [ ] Request tracing works
- [ ] TalkFlow metrics present
- [ ] Sensitive data redacted from logs
- [ ] /metrics endpoint accessible

---

### PHASE 14: Frontend Production Hardening

**Priority:** HIGH  
**Duration:** Estimated 3-5 days  
**Dependencies:** Phase 1, Phase 2

#### Objectives
- Fix frontend auth handling
- Improve error handling
- Add proper loading/error states

#### Tasks

1. **Auth state management**
   - Remove localStorage for auth state
   - Verify server on load before restoring state
   - Handle token expiration properly
   - File: `apps/web/src/stores/auth.ts`

2. **API client improvements**
   - CSRF token handling
   - Proper error state handling
   - File: `apps/web/src/lib/api.ts`

3. **Route guards**
   - Verify all protected routes have auth guards
   - Add loading states
   - Add error states
   - File: `apps/web/src/App.tsx`, page components

4. **Multi-tab coordination**
   - Use BroadcastChannel for auth state sync
   - File: `apps/web/src/stores/auth.ts`

#### Acceptance Criteria
- [ ] No auth state in localStorage
- [ ] Server verification on load
- [ ] Proper error states on all pages
- [ ] Auth state synced across tabs
- [ ] Stale identity not displayed after server rejection

---

### PHASE 15: Full QA / Browser Validation

**Priority:** HIGH  
**Duration:** Estimated 5-7 days  
**Dependencies:** Phase 1-14

#### Objectives
- Implement comprehensive E2E tests
- Run full browser validation
- Verify all workflows

#### Tasks

1. **Playwright test infrastructure**
   - Set up Playwright if not already configured
   - File: `tests/e2e/`

2. **Authentication E2E tests**
   - Signup flow
   - Login flow
   - Protected route access
   - Token expiry and refresh
   - Logout
   - Session revocation
   - Password reset
   - Multi-tab scenarios

3. **Meeting E2E tests**
   - Create meeting
   - Join meeting
   - Microphone/camera
   - Speech and translation
   - Chat
   - Disconnect/reconnect
   - End meeting

4. **Translation E2E tests**
   - Text translation
   - Language detection
   - Glossary application
   - History

5. **Document E2E tests**
   - Upload
   - Processing
   - Download
   - Unauthorized download attempt

6. **API E2E tests**
   - API key creation
   - Authorized operation
   - Forbidden scope
   - Revoked key

#### Acceptance Criteria
- [ ] All auth flows tested
- [ ] Meeting flows tested
- [ ] Translation flows tested
- [ ] Document flows tested
- [ ] API flows tested
- [ ] Tests run on multiple browsers

---

### PHASE 16: DevOps / Deployment

**Priority:** MEDIUM  
**Duration:** Estimated 2-3 days  
**Dependencies:** Phase 7, Phase 12

#### Objectives
- Verify deployment configuration
- Fix any deployment issues
- Document deployment process

#### Tasks

1. **Docker validation**
   - Build Docker images
   - Verify health checks
   - Verify migrations run
   - File: Docker configuration

2. **Kubernetes validation**
   - Verify manifests are correct
   - Verify probes work
   - Verify secret configuration
   - File: K8s manifests

3. **Environment documentation**
   - Document all required environment variables
   - Document secret requirements
   - File: `docs/DEPLOYMENT.md`

#### Acceptance Criteria
- [ ] Docker images build successfully
- [ ] Health checks pass
- [ ] Migrations run in deploy
- [ ] K8s manifests valid
- [ ] Deployment documented

---

### PHASE 17: Performance / Load / Failure Testing

**Priority:** LOW  
**Duration:** Estimated 3-5 days  
**Dependencies:** Phase 15, Phase 16

#### Objectives
- Measure performance under load
- Identify bottlenecks
- Verify failure recovery

#### Tasks

1. **Load testing**
   - Concurrent users
   - Multiple meetings
   - Translation load
   - Queue pressure

2. **Failure testing**
   - Redis failure
   - Database failure
   - Worker failure
   - LiveKit failure

3. **Bottleneck identification**
   - Profile slow paths
   - Optimize measured bottlenecks

#### Acceptance Criteria
- [ ] Performance measured under load
- [ ] Bottlenecks identified
- [ ] Failure recovery verified

---

### PHASE 18: Product Quality Improvements

**Priority:** LOW  
**Duration:** Estimated 3-5 days  
**Dependencies:** Phase 15

#### Objectives
- Add quality-of-life improvements
- Improve user experience
- Only add features that don't destabilize

#### Tasks

1. **Language detection**
   - Auto-detect spoken language
   - File: Meeting preferences

2. **Per-participant languages**
   - Speak language / hear language per participant
   - File: Meeting UI

3. **Audio modes**
   - Original / translated / mixed
   - File: Meeting UI

4. **Quality indicators**
   - Network quality
   - Translation latency
   - Translation quality
   - File: Meeting UI

5. **Transcript features**
   - Searchable transcripts
   - Export options
   - File: Transcript UI

#### Acceptance Criteria
- [ ] Features work without destabilizing
- [ ] UX improvements implemented

---

### PHASE 19: Final Production Gate

**Priority:** CRITICAL  
**Duration:** Estimated 1-2 days  
**Dependencies:** All previous phases

#### Objectives
- Verify all production gates pass
- Final security review
- Sign off for production

#### Required Gates

1. [ ] Frontend build PASS
2. [ ] Backend tests PASS
3. [ ] Integration tests PASS
4. [ ] Realtime tests PASS
5. [ ] Playwright/E2E PASS
6. [ ] Type checks PASS
7. [ ] Lint PASS
8. [ ] Dependency/security scan PASS
9. [ ] Migration validation PASS
10. [ ] Docker build PASS
11. [ ] Production configuration validation PASS
12. [ ] Authentication security review PASS
13. [ ] Tenant isolation PASS
14. [ ] Realtime reconnect test PASS
15. [ ] Failure/degradation tests PASS
16. [ ] Browser smoke tests PASS
17. [ ] Secrets scan PASS
18. [ ] Deployment smoke test PASS

#### Acceptance Criteria
- [ ] All gates pass
- [ ] No critical or high severity issues remaining
- [ ] Security review completed
- [ ] Documentation complete

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Social auth implementation complexity | Medium | High | Use established libraries, thorough testing |
| Frontend auth rewrite breaks UX | Medium | Medium | Incremental changes, thorough testing |
| Test environment differences | Medium | Medium | Document environment requirements |
| Model weight availability for tests | High | Medium | Use dev providers for most tests |
| Performance issues under load | Medium | High | Load testing in Phase 17 |
| Secret leakage in git history | Low | High | Secret scanning, consider history rewrite if found |

---

## Dependencies Graph

```
Phase 0 (Audit) ────────────────────────────────────────────────── DONE
    │
    ├─→ Phase 1 (Auth Hardening) ──→ Phase 2 (Social Auth) ──→ Phase 3 (Authorization)
    │         │                          │                          │
    │         └─→ Phase 4 (Realtime Sec) ←──┘                          │
    │                                 │                                  │
    ├─→ Phase 7 (DB/Migrations) ──────┼──→ Phase 8 (Queues)          │
    │                                 │                                  │
    └─→ Phase 12 (Security Headers) ──┼──→ Phase 14 (Frontend) ──────┼──→ Phase 15 (QA)
                                      │                                  │
    Phase 5 (Translation Reliability) ─┘                                  │
    Phase 6 (A/V Quality) ───────────────────────────────────────────────┘
    Phase 9 (AI Router) ──────────────────────────────────────────────────→ Phase 17 (Perf)
    Phase 10 (Documents) ─────────────────────────────────────────────────┤
    Phase 11 (API/Webhooks) ──────────────────────────────────────────────┘
    Phase 13 (Observability) ─────────────────────────────────────────────┘
    Phase 16 (DevOps) ────────────────────────────────────────────────────┘
```

---

## Environment Requirements

For full testing, the following are required:

- Python 3.11+
- Node.js 20+
- PostgreSQL (for production-style tests)
- Redis (for queue/caching tests)
- AI model weights (for realtime tests)
  - Piper voices
  - Argos translation packages
  - faster-whisper models

---

## Documentation Deliverables

Each phase should update relevant documentation:

- `docs/PRODUCTION_AUDIT.md` — This audit (Phase 0, DONE)
- `docs/PRODUCTION_ROADMAP.md` — This roadmap (Phase 0, DONE)
- `docs/PRODUCTION_AUTH.md` — Auth flow documentation (Phase 1-2)
- `docs/REALTIME_PRODUCTION.md` — Realtime production guide (Phase 4-6)
- `docs/DEPLOYMENT.md` — Deployment guide (Phase 16)
- `docs/SECURITY.md` — Security documentation (Phase 12)
- `docs/TROUBLESHOOTING.md` — Troubleshooting guide (Ongoing)
- `docs/PRODUCTION_RUNBOOK.md` — Operations runbook (Phase 16-19)

---

*End of Phase 0 Roadmap*
