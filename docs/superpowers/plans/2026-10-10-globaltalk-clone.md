# GlobalTalk Clone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core GlobalTalk AI clone in the existing repo: authenticated workspace, translation workflows, writing assistant, document translation, real-time voice/meeting flows, and the SaaS admin surfaces needed for a shippable first release.

**Architecture:** The app uses the repo's existing FastAPI backend and React/Vite frontend, with tenant-aware modules for auth, translation, docs, meetings, and admin. Realtime and async jobs are isolated behind service interfaces so the translation pipeline stays canonical and the UI remains loosely coupled from backend complexity.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind, Zustand, TanStack Query, FastAPI, SQLAlchemy 2, PostgreSQL, Redis, object storage, WebSockets, WebRTC-style room signaling, and translated model adapters.

**Spec:** [docs/superpowers/specs/2026-10-10-globaltalk-clone-design.md](../specs/2026-10-10-globaltalk-clone-design.md)

## Global Constraints

- Use the existing repo structure and stack conventions rather than replacing the project runtime.
- Preserve the canonical-source translation model: original text/audio is the source of truth; every target language is translated independently.
- Use tenant-aware data access for all organization-scoped resources.
- Keep all file, API, and state boundaries explicit; do not mix UI logic into domain services.
- Treat async document and meeting jobs as first-class flows with visible status and retry paths.
- Keep feature delivery incremental: ship core translation first, then real-time and monetization features.

## Review Focus

- Auth and RBAC boundaries across org-scoped resources remain strict and testable.
- Unsupported language pairs degrade gracefully without returning a false success.
- Long-form translation and document jobs preserve visible status transitions and recoverability.
- Realtime room participants and chat flows maintain correct room scope and message ownership.
- Admin, usage, and billing surfaces are tightly coupled to actual usage records and not decoupled from their source of truth.

---

### Task 1: Foundation app shell, auth, and workspace navigation

**Files:**
- Create: `apps/web/src/features/auth/*`, `apps/web/src/features/workspace/*`, `services/api/app/auth/*`, `services/api/app/organizations/*`
- Modify: `apps/web/src/main.tsx`, `apps/web/src/App.tsx`, `services/api/app/main.py`, `services/api/app/api/*.py`
- Test: `tests/api/test_auth.py`, `tests/web/test_app_shell.py`

**Interfaces:**
- Consumes: no prior tasks; provides auth/session state and org-aware routing to all later tasks.
- Produces: `login()`, `refreshSession()`, `getCurrentUser()`, `getOrganizations()`, `requireOrgScope()`, `workspaceRoutes`

- [ ] **Step 1: Write the failing tests for auth and app-shell access**

```python
def test_signup_creates_user_and_session():
    payload = {"email": "test@example.com", "password": "StrongPass!123", "name": "Test User"}
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "test@example.com"


def test_auth_required_routes_redirect_to_login():
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in {302, 401}
```

- [ ] **Step 2: Run targeted auth tests to verify they fail**

Run: `pytest tests/api/test_auth.py -q`
Expected: FAIL because the auth routes and shell routes do not exist yet.

- [ ] **Step 3: Implement the auth routes, session model, and org-aware middleware in the API**

Implement `services/api/app/auth/*` and the org-scoped middleware that attaches the current user and organization context. Keep the auth schema consistent with the repo's existing FastAPI pattern and user/session model.

- [ ] **Step 4: Implement the frontend app shell and protected route guards**

Add the route structure in `apps/web/src/main.tsx` and a workspace shell that requires auth and exposes dashboard, landing, and org-scoped navigation components.

- [ ] **Step 5: Run the auth and shell tests to confirm they pass**

Run: `pytest tests/api/test_auth.py -q` and `npm run test -- --run tests/web/test_app_shell.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/main.tsx apps/web/src/App.tsx services/api/app/auth services/api/app/organizations tests/api/test_auth.py tests/web/test_app_shell.py
git commit -m "feat: add auth and workspace shell"
```

### Task 2: Translation and writing workflows with history and glossary support

**Files:**
- Create: `services/api/app/translation/*`, `services/api/app/glossaries/*`, `services/api/app/write/*`, `apps/web/src/features/translate/*`, `apps/web/src/features/write/*`, `apps/web/src/features/history/*`
- Modify: `services/api/app/api/routes.py`, `apps/web/src/features/dashboard/*`
- Test: `tests/api/test_translation.py`, `tests/api/test_glossary.py`, `tests/web/test_translate_flow.py`

**Interfaces:**
- Consumes: `getCurrentUser()`, `requireOrgScope()`, `TranslationJob` contract from Task 1.
- Produces: `translateText()`, `createGlossaryEntry()`, `listHistory()`, `rewriteText()`, `correctText()`

- [ ] **Step 1: Write the failing tests for translation, writing, and glossary behavior**

```python
def test_translate_text_returns_target_output():
    payload = {"source_text": "Hello world", "source_lang": "en", "target_lang": "es"}
    response = client.post("/v2/translate", json=payload)
    assert response.status_code == 200
    assert "text" in response.json()


def test_glossary_entry_is_scoped_to_org():
    response = client.post("/v3/glossaries", json={"source_term": "hello", "target_term": "hola"})
    assert response.status_code == 201
```

- [ ] **Step 2: Run translation tests to verify they fail**

Run: `pytest tests/api/test_translation.py tests/api/test_glossary.py -q`
Expected: FAIL because the translation and glossary APIs are not implemented yet.

- [ ] **Step 3: Implement the translation domain service and API routes**

Add the translation service contract, queue-backed execution path, and org-scoped history storage. Keep the model adapter interface generic so the app can later switch providers without changing the route contracts.

- [ ] **Step 4: Implement the writing assistant and glossary frontend pages**

Build the pages and components for text translation, writing assistant, and glossary management and wire them into the protected dashboard navigation.

- [ ] **Step 5: Run the translation and frontend flow tests**

Run: `pytest tests/api/test_translation.py tests/api/test_glossary.py -q` and `npm run test -- --run tests/web/test_translate_flow.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/translation services/api/app/glossaries services/api/app/write apps/web/src/features/translate apps/web/src/features/write apps/web/src/features/history tests/api/test_translation.py tests/api/test_glossary.py tests/web/test_translate_flow.py
git commit -m "feat: add translation, writing, and glossary workflows"
```

### Task 3: Document translation pipeline and async status handling

**Files:**
- Create: `services/api/app/documents/*`, `apps/web/src/features/documents/*`, `workers/*` or equivalent async job entrypoints
- Modify: `services/api/app/api/routes.py`, `apps/web/src/features/dashboard/*`
- Test: `tests/api/test_documents.py`, `tests/web/test_documents_flow.py`

**Interfaces:**
- Consumes: `getCurrentUser()`, `requireOrgScope()`, object-storage service, translation service adapter.
- Produces: `uploadDocument()`, `pollDocumentJob()`, `downloadTranslatedDocument()`

- [ ] **Step 1: Write failing tests covering document upload and status transitions**

```python
def test_document_upload_creates_job():
    with open("tests/fixtures/sample.txt", "rb") as file:
        response = client.post("/v2/document", files={"file": ("sample.txt", file, "text/plain")})
    assert response.status_code == 201
    assert response.json()["status"] in {"queued", "processing"}
```

- [ ] **Step 2: Run the document tests to verify they fail**

Run: `pytest tests/api/test_documents.py -q`
Expected: FAIL because the document pipeline does not exist.

- [ ] **Step 3: Implement the document upload service and job lifecycle**

Create the document entity, storage layer, and async job transitions (`queued` → `processing` → `complete` / `failed`) with explicit job status endpoints.

- [ ] **Step 4: Implement the document UI and progress states**

Add the upload page, status cards, and download action with consistent loading/error states.

- [ ] **Step 5: Run the document tests and UI flow tests**

Run: `pytest tests/api/test_documents.py -q` and `npm run test -- --run tests/web/test_documents_flow.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/documents apps/web/src/features/documents workers tests/api/test_documents.py tests/web/test_documents_flow.py
git commit -m "feat: add document translation pipeline"
```

### Task 4: Realtime voice, meetings, and chat flow

**Files:**
- Create: `services/api/app/meetings/*`, `services/api/app/chat/*`, `services/api/app/voice/*`, `apps/web/src/features/voice/*`, `apps/web/src/features/meetings/*`, `apps/web/src/features/chat/*`
- Modify: `services/api/app/api/routes.py`, `apps/web/src/main.tsx`
- Test: `tests/api/test_meetings.py`, `tests/api/test_voice.py`, `tests/web/test_meeting_flow.py`

**Interfaces:**
- Consumes: translation and auth contracts; produces `createMeetingRoom()`, `joinMeetingRoom()`, `sendChatMessage()`, `startVoiceSession()`.
- Produces: message rooms, room participants, transcript segments, and voice session state to the UI.

- [ ] **Step 1: Write failing tests for room creation, transcript persistence, and chat message creation**

```python
def test_create_meeting_room_succeeds_for_org_member():
    response = client.post("/meetings", json={"title": "Demo room", "language_pairs": ["en->es"]})
    assert response.status_code == 201
    assert response.json()["title"] == "Demo room"
```

- [ ] **Step 2: Run the realtime tests to verify they fail**

Run: `pytest tests/api/test_meetings.py tests/api/test_voice.py -q`
Expected: FAIL because the realtime room APIs do not exist yet.

- [ ] **Step 3: Implement the room, chat, and voice session services**

Add the meeting room model, participant state, and translation-aware session routes. Keep room membership checkers and transcript persistence separated from the frontend route logic.

- [ ] **Step 4: Implement the UI for room creation, call join flow, live captions, and chat**

Build the meeting room and chat experience with the required states: lobby, active, muted, and error states.

- [ ] **Step 5: Run the realtime and web tests**

Run: `pytest tests/api/test_meetings.py tests/api/test_voice.py -q` and `npm run test -- --run tests/web/test_meeting_flow.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/meetings services/api/app/chat services/api/app/voice apps/web/src/features/voice apps/web/src/features/meetings apps/web/src/features/chat tests/api/test_meetings.py tests/api/test_voice.py tests/web/test_meeting_flow.py
git commit -m "feat: add realtime voice, meetings, and chat"
```

### Task 5: Usage, API keys, team management, billing, and admin dashboards

**Files:**
- Create: `services/api/app/usage/*`, `services/api/app/billing/*`, `services/api/app/admin/*`, `apps/web/src/features/usage/*`, `apps/web/src/features/billing/*`, `apps/web/src/features/team/*`, `apps/web/src/features/admin/*`
- Modify: `services/api/app/api/routes.py`, `apps/web/src/main.tsx`
- Test: `tests/api/test_usage.py`, `tests/api/test_admin.py`, `tests/web/test_admin_flow.py`

**Interfaces:**
- Consumes: auth, org-scoped resource contracts, usage metrics from earlier tasks.
- Produces: `listUsage()`, `createApiKey()`, `listMembers()`, `listInvoices()`, `adminOverview()`

- [ ] **Step 1: Write failing tests for usage accounting, API keys, and admin surfaces**

```python
def test_api_key_creation_is_scoped_to_user_and_org():
    response = client.post("/api", json={"name": "Prod key", "scopes": ["translate"]})
    assert response.status_code == 201
    assert response.json()["name"] == "Prod key"
```

- [ ] **Step 2: Run the usage/admin tests to verify they fail**

Run: `pytest tests/api/test_usage.py tests/api/test_admin.py -q`
Expected: FAIL because the usage and admin surfaces are not implemented yet.

- [ ] **Step 3: Implement billing, usage, API key, and admin services**

Persist usage records, issue API keys with scope metadata, and create admin summary endpoints. Keep billing logic decoupled from the UI and keyed to actual usage events.

- [ ] **Step 4: Build the team, usage, billing, and admin pages in the frontend**

Add the pages that surface org membership, subscriptions, usage charts, and operational visibility.

- [ ] **Step 5: Run the usage and admin tests**

Run: `pytest tests/api/test_usage.py tests/api/test_admin.py -q` and `npm run test -- --run tests/web/test_admin_flow.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/usage services/api/app/billing services/api/app/admin apps/web/src/features/usage apps/web/src/features/billing apps/web/src/features/team apps/web/src/features/admin tests/api/test_usage.py tests/api/test_admin.py tests/web/test_admin_flow.py
git commit -m "feat: add usage, billing, and admin surfaces"
```

### Task 6: Release readiness and production hardening

**Files:**
- Modify: `README.md`, `docs/PRODUCTION_RUNBOOK.md`, deployment config, CI config as needed
- Test: focused smoke tests for auth, translation, document, and meeting flows

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: validated deployment script and runbook.

- [ ] **Step 1: Write the focused smoke-test suite for critical user flows**

Add smoke tests for sign in, translate text, upload document, and create a room.

- [ ] **Step 2: Run the smoke suite and fix failures**

Run: `pytest tests/smoke -q` and `npm run build`
Expected: PASS and build succeeds.

- [ ] **Step 3: Update the runbook and deployment config**

Document env vars, storage requirements, queue setup, and user/admin release gates.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/PRODUCTION_RUNBOOK.md .github/workflows tests/smoke
git commit -m "chore: harden release readiness"
```

## Execution Recommendation

Use the native execution method for the first implementation pass unless the user explicitly wants a subagent-based task pipeline. This plan is modular and interface-driven, so it is a good fit for direct execution in the current session while preserving a clean handoff to a reviewer at the end.
