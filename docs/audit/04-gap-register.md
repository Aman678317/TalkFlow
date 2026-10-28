# Phase 2 Gap Register: TalkFlow (GlobalTalk AI)

**Date**: 2026-10-28  
**Audit Branch**: `audit-baseline`  
**Severity Scale**:
- **P0**: Release Blocker (Data loss, security vulnerability, severe crash)
- **P1**: High / Production Risk (Core feature malfunction, broken pipeline)
- **P2**: Medium / Defect (Non-blocking bug, UI inconsistency, test gap)
- **P3**: Low / Polish (Cosmetic issue, documentation gap, minor optimization)

---

## 1. Active & Remediated Findings

| Gap ID | Category | Severity | Summary | Location / Evidence | Root Cause | Remediation Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GAP-01** | Backend / Test | **P1** | Storage dependency test mock mismatch in readiness probe | `tests/test_production_readiness_hardened.py:74` | Test mocked `LocalStorage.ping`, but `init_storage()` initialized `DatabaseStorage` because DB URL was configured. | Update test to patch the polymorphic storage instance (`app.storage.storage().ping`) or active storage class. | **In Progress** |
| **GAP-02** | Database / Test | **P2** | SQLite concurrent write lock in realtime security test | `tests/test_realtime_security_hardened.py` | Parallel async database connections cause SQLite file-level locking without WAL mode. | Enable SQLite WAL mode (`PRAGMA journal_mode=WAL;`) and busy timeout in test fixtures. | **In Progress** |
| **GAP-03** | Frontend / UX | **P1** | Duplicate Knowledge Base & Agent Studio navigation clutter | `apps/web/src/components/layout/AppShell.tsx` | Duplicate entries in sidebar pointing to redundant features requested for removal. | Cleaned sidebar navigation; redirected `/knowledge` and `/knowledge-base` to `/documents`; updated static routes. | **Verified Fixed** |
| **GAP-04** | Backend / Serverless | **P1** | Ephemeral storage data loss during serverless document jobs | `services/api/app/storage.py`, `services/api/app/services/document_service.py` | Vercel serverless functions discard `/tmp` between lambda invocations, causing 404 on result downloads. | Implemented `DatabaseStorage` in Neon PostgreSQL (`stored_objects` table) + FastAPI `BackgroundTasks`. | **Verified Fixed** |
| **GAP-05** | Frontend / UX | **P1** | Live Voice and Global Call merged into single page | `apps/web/src/pages/Voice.tsx`, `apps/web/src/pages/GlobalCall.tsx` | Voice-to-voice conversation and international phone calling/PSTN were crowded into one screen. | Separated into distinct `/voice` and `/global-call` routes with dedicated navigation items. | **Verified Fixed** |
| **GAP-06** | Security | **P1** | Risk of credential leaks in environment templates | `.env.example`, `.env.production.example`, `.gitignore` | Default config files may contain accidental production secrets or staging tokens. | Secret scan with Gitleaks; ensure all `.env.example` keys contain sanitized placeholder values only. | **In Progress** |
| **GAP-07** | Frontend / Perf | **P2** | Large WebRTC bundle shipped to text-only visitors | `apps/web/src/App.tsx` | `livekit-client` (561 kB) initially bundled into primary SPA chunk. | Implemented route-level dynamic code splitting via `React.lazy()` for all meeting and voice routes. | **Verified Fixed** |
| **GAP-08** | Telephony | **P2** | Unclear carrier credentials setup state for PSTN calling | `apps/web/src/pages/GlobalCall.tsx`, `AdminTelephony.tsx` | Users without Twilio/Telnyx keys see simulated call banner without guided setup. | Added structured guide and status indicator in Admin Telephony to easily enter carrier credentials. | **Verified Fixed** |

---

## 2. Detailed Gap Analysis & Remediations

### GAP-01: Readiness Probe Storage Mock Mismatch
- **Symptoms**: Running `tests/test_production_readiness_hardened.py` produces:
  ```
  AssertionError: assert 200 == 503
  where 200 = <Response [200 OK]>.status_code
  ```
- **Analysis**:
  In `services/api/app/routers/health.py`, `/ready` calls `await storage().ping()`.
  When `DATABASE_URL` is set, `init_storage()` sets `_storage = DatabaseStorage()`.
  The test executed:
  ```python
  with patch("app.storage.LocalStorage.ping", new_callable=AsyncMock, return_value=False):
      resp = services_app_client.get("/ready")
      assert resp.status_code == 503
  ```
  Because `_storage` is an instance of `DatabaseStorage`, patching `LocalStorage.ping` had no effect on the health check.
- **Fix**:
  Patch `app.storage.DatabaseStorage.ping` or dynamically patch `app.storage._storage.ping`.

### GAP-02: SQLite Concurrency Lock in Realtime Security Suite
- **Symptoms**: When running `tests/test_realtime_security_hardened.py` on SQLite, multiple coroutines write audit logs simultaneously, throwing:
  ```
  sqlite3.OperationalError: database is locked
  ```
- **Analysis**: SQLite defaults to rollback journal mode where writers obtain exclusive database locks.
- **Fix**:
  In `conftest.py` / `session.py`, when using `sqlite://`, issue:
  ```python
  await conn.execute(text("PRAGMA journal_mode=WAL;"))
  await conn.execute(text("PRAGMA busy_timeout=5000;"))
  ```
