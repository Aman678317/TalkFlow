# Vercel Multi-Service Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the main web app, FastAPI API, and Amazon Connect V2V frontend as three independently built Vercel services sharing one domain.

**Architecture:** Define Vercel services for `web` (`apps/web`), `api` (`services/api`), and `connect` (`apps/amazon-connect-v2v/webapp`). Route API paths to the API service, `/connect/` paths to the Connect static service's root route, and other paths to the main web app. Keep browser API calls same-origin and do not add service bindings.

**Tech Stack:** Vercel Services (`vercel.json`), FastAPI/Python, Vite, pytest, npm.

**Spec:** [2026-10-08-vercel-multi-service-design.md](../specs/2026-10-08-vercel-multi-service-design.md)

## Global Constraints

- The service names are `web`, `api`, and `connect`, with roots `apps/web`, `services/api`, and `apps/amazon-connect-v2v/webapp`.
- Top-level rewrites send API routes to `api`, `/connect/*` to `connect`, then all remaining paths to `web`; specific routes precede the catch-all.
- The `/connect/:path*` rewrite selects `/:path*` inside the static service while preserving the browser-visible `/connect/` prefix.
- No service bindings are added; browser code must not consume service-binding variables.
- The Connect Vite build uses `/connect/` as its asset base.
- The API service installs the repository-local AI Python package as a dependency, not as a separate network service.

## Review Focus

- API, v2/v3, and websocket requests must not fall through to the web SPA; pin the exact prefixes and ordering in the Vercel config test.
- Health/readiness/metrics endpoints must reach FastAPI rather than the frontend; pin the exact endpoint rewrites in the config test.
- Connect root and nested asset requests must resolve inside the static service while retaining `/connect/` URLs; test the route lookup mapping and inspect built asset URLs.
- The API build must be able to import repository-local `gt_ai`; validate the configured install command and exercise the service with `vercel dev`.
- Browser clients must not rely on build-time service bindings; assert there are no bindings and document required external AWS Lambda environment values.

---

### Task 1: Define and test the Vercel services and routing

**Files:**
- Create: `tests/deployment/test_vercel_services.py`
- Create: `vercel.json`
- Modify: `services/api/pyproject.toml`
- Modify: `apps/web/src/App.tsx`

**Interfaces:**
- Consumes: The service names, roots, frameworks, public path families, and no-binding decision in the spec.
- Produces: A top-level Vercel Services config with `web`, `api`, and `connect`; `api` uses `services/api` and `app.main:app`; rewrites preserve API paths and select root-relative paths for `/connect/`.

- [x] **Step 1: Write failing config assertions**

Add `test_vercel_services_have_expected_roots_and_frameworks`, asserting the exact three service names, roots, framework slugs, and FastAPI entrypoint.
Add `test_vercel_rewrites_route_specific_paths_before_web_catchall`, asserting `/api/`, `/api-docs`, `/v2/`, `/v3/`, `/ws/`, `/health`, `/healthz`, `/ready`, `/readyz`, and `/metrics` target `api`; `/connect` and `/connect/:path*` target `connect`; the latter selects `/:path*`; and the final rule sends all other paths to `web`.
Add `test_services_do_not_define_unneeded_bindings`, asserting that none of these three services declares service bindings.
Add `test_api_resolves_gt_ai_from_the_repository_source`, asserting that the `gt-ai` uv source is `../../ai` and resolves to the repository's `ai` project directory.
Add `test_web_copilotkit_defaults_to_the_public_api_route` and `test_api_declares_dependencies_for_the_copilotkit_endpoint` to keep browser and API runtime routing aligned.

- [x] **Step 2: Run the tests and confirm the missing-config failure**

Run: `python -m pytest tests/deployment/test_vercel_services.py -q`
Expected: FAIL because `vercel.json` does not exist yet.

- [x] **Step 3: Implement `vercel.json`**

Set the service roots/frameworks from the spec and use `entrypoint: "app.main:app"` for `api`. In `services/api/pyproject.toml`, map the declared `gt-ai` dependency to the repository-local `../../ai` project using `[tool.uv.sources]`. Add the API and Connect rewrites before the final web catch-all. For the Connect route, use the service destination path `/:path*` for internal route selection.
Declare the LangChain and LangGraph dependencies used by the API's CopilotKit endpoint and default the web client to the public same-origin `/api/copilotkit` route.

- [x] **Step 4: Run the config tests**

Run: `python -m pytest tests/deployment/test_vercel_services.py -q`
Expected: PASS.

- [ ] **Step 5: Verify Vercel's local service build and routing**

Run: `npx --yes vercel@latest dev --yes`
Expected: Vercel builds the three configured services; API paths reach FastAPI, `/connect/` serves the Connect app, and an ordinary root path reaches the main web app. Record any environment values required by the local API rather than substituting public defaults.
Observed: the CLI parsed all three services, but its local Vite services did not start because the isolated worktree's generated Node/Rollup install was incomplete; live rewrite routing remains unverified. The API app was independently verified to register its CopilotKit routes.

- [ ] **Step 6: Commit the service configuration**

```bash
git add vercel.json tests/deployment/test_vercel_services.py
git commit -m "feat: configure Vercel multi-service routing"
```

### Task 2: Mount the Connect Vite app under `/connect/`

**Files:**
- Modify: `apps/amazon-connect-v2v/webapp/vite.config.js`

**Interfaces:**
- Consumes: Task 1's public `/connect/` route and root-relative service route selection.
- Produces: A Vite production build whose browser asset URLs are prefixed with `/connect/`.

- [x] **Step 1: Set the Vite base**

Set the Vite `base` option to `/connect/`, preserving the existing plugins, development HTTPS configuration, and asset-copy behavior.

- [x] **Step 2: Build and inspect the mounted app**

Run: `npm --prefix apps/amazon-connect-v2v/webapp run build`
Expected: PASS; `dist/index.html` references built assets under `/connect/`, and copied public assets remain present.

- [ ] **Step 3: Commit the Connect path change**

```bash
git add apps/amazon-connect-v2v/webapp/vite.config.js
git commit -m "fix: mount Connect web app under Vercel path"
```

### Task 3: Document Vercel setup and deployment environment

**Files:**
- Modify: `docs/DEPLOYMENT.md`

**Interfaces:**
- Consumes: The service names, paths, and external AWS Lambda configuration established in Tasks 1 and 2.
- Produces: A Vercel deployment section describing the three services, public paths, and required `VITE_GET_LANGUAGES_PROXY` and `VITE_REQUEST_SESSION_PROXY` build-time values for the Connect app.

- [x] **Step 1: Document service routing and setup**

Add a Vercel section to `docs/DEPLOYMENT.md` that names the three service roots, describes API and `/connect/` routing, explains that the AI package is installed with the API, lists the Connect AWS Lambda build variables and API production runtime variables, and states that no service bindings are currently required.

- [x] **Step 2: Run final targeted validation**

Run:
`python -m pytest tests/deployment/test_vercel_services.py tests/integration/test_api.py -q`
`npm --prefix apps/web run build`
`npm --prefix apps/amazon-connect-v2v/webapp run build`
Expected: all tests and builds pass; API tests that require external services or secrets must report their precise unmet prerequisites.

- [ ] **Step 3: Commit deployment documentation**

```bash
git add docs/DEPLOYMENT.md
git commit -m "docs: describe Vercel multi-service deployment"
```

## Self-Review

- **Spec coverage:** Three services, public routing order, Connect path selection/base, API-local AI package installation, no bindings, and Vercel/AWS environment setup each have an owning task.
- **Step scan:** Config tests precede configuration; each build or test has a command and a measurable expected result; docs are updated after the implementation values are fixed.
- **Type consistency:** The FastAPI entrypoint is `app.main:app`; Vercel service destinations refer only to the declared service names `api`, `connect`, and `web`.
- **Review focus:** Each of the five listed path, environment, and package failure modes maps to an explicit config assertion or build/routing verification.
- **Proportion:** Three tasks cover the single deployment topology without creating additional services or changing existing API contracts.
