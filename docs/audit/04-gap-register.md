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
| **GAP-01** | Backend / Test | **P1** | Storage dependency test mock mismatch in readiness probe | `tests/test_production_readiness_hardened.py:74` | Test mocked `LocalStorage.ping`, but `init_storage()` initialized `DatabaseStorage` because DB URL was configured. | Update test to patch the polymorphic storage instance (`app.storage.storage().ping`) or active storage class. | **Verified Fixed** |
| **GAP-02** | Database / Test | **P2** | SQLite concurrent write lock in realtime security test | `tests/test_realtime_security_hardened.py` | Parallel async database connections cause SQLite file-level locking without WAL mode. | Enable SQLite WAL mode (`PRAGMA journal_mode=WAL;`) and busy timeout in test fixtures. | **Verified Fixed** |
| **GAP-03** | Frontend / UX | **P1** | Duplicate Knowledge Base & Agent Studio navigation clutter | `apps/web/src/components/layout/AppShell.tsx` | Duplicate entries in sidebar pointing to redundant features requested for removal. | Cleaned sidebar navigation; redirected `/knowledge` and `/knowledge-base` to `/documents`; updated static routes. | **Verified Fixed** |
| **GAP-04** | Backend / Serverless | **P1** | Ephemeral storage data loss during serverless document jobs | `services/api/app/storage.py`, `services/api/app/services/document_service.py` | Vercel serverless functions discard `/tmp` between lambda invocations, causing 404 on result downloads. | Implemented `DatabaseStorage` in Neon PostgreSQL (`stored_objects` table) + FastAPI `BackgroundTasks`. | **Verified Fixed** |
| **GAP-05** | Frontend / UX | **P1** | Live Voice and Global Call merged into single page | `apps/web/src/pages/Voice.tsx`, `apps/web/src/pages/GlobalCall.tsx` | Voice-to-voice conversation and international phone calling/PSTN were crowded into one screen. | Separated into distinct `/voice` and `/global-call` routes with dedicated navigation items. | **Verified Fixed** |
| **GAP-06** | Security | **P1** | Risk of credential leaks in environment templates | `.env.example`, `.env.production.example`, `.gitignore` | Default config files may contain accidental production secrets or staging tokens. | Secret scan with Gitleaks; ensure all `.env.example` keys contain sanitized placeholder values only. | **Verified Fixed** |
| **GAP-07** | Frontend / Perf | **P2** | Large WebRTC bundle shipped to text-only visitors | `apps/web/src/App.tsx` | `livekit-client` (561 kB) initially bundled into primary SPA chunk. | Implemented route-level dynamic code splitting via `React.lazy()` for all meeting and voice routes. | **Verified Fixed** |
| **GAP-08** | Telephony | **P2** | Unclear carrier credentials setup state for PSTN calling | `apps/web/src/pages/GlobalCall.tsx`, `AdminTelephony.tsx` | Users without Twilio/Telnyx keys see simulated call banner without guided setup. | Added structured guide and status indicator in Admin Telephony to easily enter carrier credentials. | **Verified Fixed** |
| **GAP-09** | Backend / GMeet | **P1** | Invalid Meeting column instantiation in Google Meet bridge router | `services/api/app/routers/google_meet.py:91` | Instantiating `M.Meeting(enable_captions=True)` threw internal 500 error because settings belong in `settings_json` and `org_id` was unassigned. | Rewrote Meeting & Participant creation to store settings in `settings_json` and preferences in `ParticipantPreference`. Added unit tests. | **Verified Fixed** |

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

### GAP-03: Duplicate Knowledge Base & Navigation Clutter
- **Symptoms**: The main application shell sidebar contained duplicate and redundant links to "Knowledge Base" and unfinished "Agent Studio" sections, creating user confusion.
- **Analysis**: Legacy sidebar configuration in `AppShell.tsx` had multiple navigation entries pointing to overlapping features (`/knowledge`, `/knowledge-base`, `/agents`).
- **Fix**:
  - Streamlined sidebar navigation in `apps/web/src/components/layout/AppShell.tsx`.
  - Consolidated document and knowledge base functionality into the unified `/documents` hub.
  - Implemented automatic redirects from legacy `/knowledge` and `/knowledge-base` paths to `/documents`.
  - Added static routing fallback entries in `scripts/generate-spa-routes.js`.

### GAP-04: Ephemeral Storage Data Loss During Serverless Document Jobs
- **Symptoms**: Asynchronous document translation requests intermittently returned 404 on `/v2/document/{id}/result` downloads after serverless lambda instances were recycled by Vercel.
- **Analysis**: File buffers were written to the ephemeral `/tmp` filesystem of the serverless function container, which does not persist across container scale-down events.
- **Fix**:
  - Engineered `DatabaseStorage` driver in `services/api/app/storage.py` leveraging Neon PostgreSQL's `stored_objects` table.
  - Configured `init_storage()` to automatically bind `DatabaseStorage` whenever `DATABASE_URL` is configured.
  - Updated background translation tasks to stream completed binary outputs directly into the database blob store.

### GAP-05: Merged Live Voice and Global Call Interface
- **Symptoms**: Face-to-face peer speech translation and international telephony (PSTN) dialers were merged into a single `/voice` page, degrading usability.
- **Analysis**: Two distinct communication paradigms (browser WebRTC microphone sharing vs. carrier telephone routing) were coupled without separate route boundaries.
- **Fix**:
  - Separated into two distinct top-level pages:
    - `/voice`: Dedicated Face-to-Face Live Voice speech translator (`Voice.tsx`).
    - `/global-call`: Dedicated International Phone Calling / PSTN dialer (`GlobalCall.tsx`).
  - Added dedicated navigation items, breadcrumbs, and active state indicators in `AppShell.tsx`.

### GAP-06: Credential Exposure Risk in Environment Templates
- **Symptoms**: Risk of accidental exposure of live tokens or credentials in development `.env.example` templates.
- **Analysis**: Multiple service configurations could lead to developers inadvertently committing staging credentials.
- **Fix**:
  - Sanitized all `.env.example` and `.env.production.example` files to contain placeholder values only.
  - Executed automated secret scanning across git history using Gitleaks patterns.
  - Standardized `.gitignore` to prevent any untracked `.env*` or secret files from entering version control.

### GAP-07: Monolithic WebRTC Bundle Shipped to Text-Only Visitors
- **Symptoms**: Initial page load performance suffered due to eager bundling of heavy WebRTC client libraries (`livekit-client`, ~561 kB).
- **Analysis**: Static imports in `App.tsx` forced the browser to download real-time voice and meeting dependencies even for users visiting text translation or document workflows.
- **Fix**:
  - Applied route-level dynamic code-splitting via `React.lazy()` and `<Suspense>` across all real-time meeting and voice pages (`MeetCompanion`, `LiveStudio`, `GlobalCall`, `Voice`).
  - WebRTC assets are now loaded on-demand only when a user navigates into voice or meeting routes.

### GAP-08: Unclear Carrier Credentials Setup State for PSTN Calling
- **Symptoms**: Users attempting phone calls without carrier keys configured saw a generic simulated call banner without guidance on connecting Twilio or Telnyx.
- **Analysis**: Disconnect between the user-facing phone dialer and the administrative telephony credential configuration panel.
- **Fix**:
  - Added interactive carrier setup alert banner in `PhoneCallingTab.tsx` with a direct `<Link to="/admin/telephony">`.
  - Built comprehensive Admin Telephony management interface in `AdminTelephony.tsx` with carrier selection, credential validation, and status diagnostics.
  - Added `admin/telephony` static route stub in `scripts/generate-spa-routes.js` to prevent 404s on hard refresh.

### GAP-09: Invalid Meeting Column Instantiation in Google Meet Bridge
- **Symptoms**: Initiating Google Meet bridge connection from `/meet-companion` triggered an unhandled 500 error: `Internal server error: 'enable_captions' is an invalid keyword argument for Meeting`.
- **Analysis**: In `services/api/app/routers/google_meet.py`, the backend passed runtime toggles (`enable_captions`, `target_language`, `formality`) as direct keyword arguments to `M.Meeting()`. The SQLAlchemy model defines these under `settings_json` (JSONB) and requires an explicit `org_id`.
- **Fix**:
  - Refactored `google_meet.py` to serialize toggle settings into `settings_json` and assign a default `org_id`.
  - Created associated `ParticipantPreference` records for user configuration.
  - Added automated unit test suite in `tests/unit/test_google_meet_bridge.py` verifying error-free bridge creation.

---

## 3. Live Staging Verification & Evidence

All resolved gaps were verified through automated end-to-end tests and interactive browser inspection on the staging environment (`https://feat-vercel-multi-service.vercel.app`):

| Gap ID | Description | Live Verification Path | Verified Result | Evidence Artifact |
| :--- | :--- | :--- | :--- | :--- |
| **GAP-03** | Sidebar Navigation Clutter | `/dashboard` | Single unified navigation tree; duplicate knowledge base and agent studio entries removed; clean route transitions. | `gap_03_clean_sidebar.png` |
| **GAP-05** | Split Voice vs. Global Call | `/voice` & `/global-call` | Distinct routes: `/voice` dedicated to dual-speaker live conversation; `/global-call` dedicated to international PSTN dialer with cost metering. | `gap_05_global_call_separated.png` |
| **GAP-08** | Telephony Setup Guidance | `/global-call` & `/admin/telephony` | Carrier unconfigured banner guides user with direct CTA link to `/admin/telephony`; admin panel provides carrier checklist and diagnostics. | `gap_08_admin_telephony_guidance.png` |
| **GAP-09** | Google Meet Bridge Error | `/meet-companion?meet_code=itg-pefc-aef` | Room pre-fill functions properly; bridge settings stored in `settings_json` without `enable_captions` runtime error; live subtitle stream ready. | `gap_09_meet_companion_ready.png` |



