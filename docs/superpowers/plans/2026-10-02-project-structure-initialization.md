# Project Structure Initialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize and unify the GlobalTalk AI monorepo structure across all official client SDKs (Python, TypeScript, Java, .NET), the Web application (`apps/web`), the CLI (`cli/desi-cli`), and documentation portals.

**Architecture:** Maintain strict clean boundaries between control/data plane services, frontend apps, client SDKs, and developer documentation. Implement the missing Python 3.9+ and TypeScript/Node SDKs with zero third-party license encumbrances, wire root npm workspaces to orchestrate web, CLI, and TypeScript SDK builds, and wire web app developer routes and documentation cross-references.

**Tech Stack:** Python 3.9+ (`httpx`, `pytest`), TypeScript 5+ / Node 18+ (`vitest`), React 18 / Vite / Tailwind CSS, Java 11 (`java.net.http`), .NET (`netstandard2.0`), Mintlify (`docs.json`, MDX).

**Spec:** [`docs/superpowers/specs/2026-10-02-project-structure-initialization-design.md`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/docs/superpowers/specs/2026-10-02-project-structure-initialization-design.md)

## Global Constraints

- Canonical Source Invariant: Human speech/text is the immutable root semantic source; no translation chains or recursive AI loops.
- Standard API Wire Conformance: All SDKs conform to OpenAPI 3.1.0 Desi v2/v3 endpoint paths (`/v2/translate`, `/v2/desi/*`, `/v2/write/*`, `/v2/document`, `/v3/glossaries`, `/v3/style_rules`).
- License: Pure MIT License with zero proprietary or third-party trademark restrictions.
- Package Names: Python SDK published as `desi-python`, TypeScript SDK published as `@globaltalk/sdk`.

## Review Focus

- HTTP error parsing: Server errors returning standard `{"error": {"code": "...", "message": "...", "recoverable": bool}}` format must map to typed SDK exceptions across sync and async clients.
- Trailing slashes and base URL normalization: Setting `server_url="http://127.0.0.1:8088/"` vs `"http://127.0.0.1:8088"` must resolve endpoint paths reliably.
- Missing credentials: SDK clients initialized without an API key or auth token must fail fast with clear guidance.
- Safe browser fallback in web app: Direct navigation to `/docs` or `/api/docs` in `apps/web` must show an in-app developer portal rather than bouncing users back to `/`.
- Root build script isolation: Root `package.json` build/test scripts must run without cross-polluting package node_modules or crashing when run concurrently.

---

### Task 1: Initialize Python Client SDK (`sdk/python/desi-python`)

**Files:**
- Create: `sdk/python/desi-python/pyproject.toml`
- Create: `sdk/python/desi-python/setup.py`
- Create: `sdk/python/desi-python/README.md`
- Create: `sdk/python/desi-python/desi/__init__.py`
- Create: `sdk/python/desi-python/desi/py.typed`
- Create: `sdk/python/desi-python/desi/exceptions.py`
- Create: `sdk/python/desi-python/desi/constants.py`
- Create: `sdk/python/desi-python/desi/models.py`
- Create: `sdk/python/desi-python/desi/client.py`
- Create: `sdk/python/desi-python/desi/async_client.py`
- Create: `sdk/python/desi-python/tests/__init__.py`
- Create: `sdk/python/desi-python/tests/test_client.py`

**Interfaces:**
- Produces:
  - `desi.DesiClient(auth_key: str, options: DesiClientOptions = None)`
  - `desi.AsyncDesiClient(auth_key: str, options: DesiClientOptions = None)`
  - Methods: `translate_text()`, `translate_desi()`, `transliterate_desi()`, `normalize_desi_text()`, `get_languages()`, `get_desi_languages()`, `rephrase_text()`, `correct_text()`, `translate_document()`, `get_usage()`

- [ ] **Step 1: Write test cases in `tests/test_client.py`**
  Write tests for `DesiClient` and `AsyncDesiClient` initialization, custom base URL stripping, header creation (`X-API-Key`), query/payload construction, and response parsing.

- [ ] **Step 2: Create `pyproject.toml`, `setup.py`, and `py.typed`**
  Define build metadata (`name = "desi-python"`, `version = "2.1.0"`), Python 3.9+ compatibility, and `httpx>=0.24.0` dependency.

- [ ] **Step 3: Implement `exceptions.py` and `constants.py`**
  Implement `DesiError`, `AuthenticationError`, `RateLimitError`, `BadRequestError`, `QuotaExceededError`, and language constants (22 Indic Eighth Schedule codes, scripts, and formality tiers).

- [ ] **Step 4: Implement `models.py`**
  Dataclasses for `TextResult`, `DesiTextResult`, `TransliterationResult`, `NormalizationResult`, `LanguageInfo`, `GlossaryInfo`, `UsageResult`, and `DesiClientOptions`.

- [ ] **Step 5: Implement `client.py` (Synchronous) and `async_client.py` (Asynchronous)**
  HTTP client classes wrapping `httpx.Client` and `httpx.AsyncClient` with exponential backoff retries, JSON serialization, and error mapping.

- [ ] **Step 6: Create `desi/__init__.py` and `README.md`**
  Export all public symbols in `__init__.py` and provide full documentation and quickstart examples in `README.md`.

---

### Task 2: Initialize TypeScript / Node.js Client SDK (`sdk/typescript`)

**Files:**
- Create: `sdk/typescript/package.json`
- Create: `sdk/typescript/tsconfig.json`
- Create: `sdk/typescript/README.md`
- Create: `sdk/typescript/src/constants.ts`
- Create: `sdk/typescript/src/errors.ts`
- Create: `sdk/typescript/src/types.ts`
- Create: `sdk/typescript/src/client.ts`
- Create: `sdk/typescript/src/index.ts`
- Create: `sdk/typescript/tests/client.test.ts`

**Interfaces:**
- Produces:
  - `@globaltalk/sdk`
  - `export class DesiClient { constructor(options: DesiClientConfig); translate(params); transliterate(params); normalize(params); rephrase(params); correct(params); getLanguages(); getDesiLanguages(); getUsage(); }`

- [ ] **Step 1: Write unit tests in `sdk/typescript/tests/client.test.ts`**
  Test client instantiation, default options, custom `baseUrl`, and mocked responses for translate, transliterate, and normalize.

- [ ] **Step 2: Create `package.json` and `tsconfig.json`**
  Configure package name `@globaltalk/sdk`, version `2.1.0`, types export `./dist/index.d.ts`, ESM/CJS exports, and strict TypeScript compiler options.

- [ ] **Step 3: Implement `constants.ts` and `errors.ts`**
  Define `DEFAULT_BASE_URL = "https://api.globaltalk.ai"`, 22 Indic language codes, formality registers, and `DesiClientError`, `DesiApiError` classes.

- [ ] **Step 4: Implement `types.ts`**
  Type interfaces: `DesiClientConfig`, `TranslateOptions`, `TranslateResult`, `TransliterateOptions`, `NormalizeOptions`, `WriteOptions`, `GlossaryOptions`.

- [ ] **Step 5: Implement `client.ts` and `index.ts`**
  Universal fetch client compatible with Node.js 18+ and browsers, supporting `translate`, `transliterate`, `normalize`, `write`, `document`, and usage endpoints.

- [ ] **Step 6: Create `sdk/typescript/README.md`**
  Document package installation, Node.js and browser usage, TypeScript typings, and configuration.

---

### Task 3: Create SDK Directory Catalog & Matrix (`sdk/README.md`)

**Files:**
- Create: `sdk/README.md`

**Interfaces:**
- Consumes: Specifications and implementations from Python, TypeScript, Java, and .NET SDKs.
- Produces: Unified developer overview and feature parity matrix.

- [ ] **Step 1: Author `sdk/README.md`**
  Include:
  - Architecture overview table (Java 11+, .NET standard2.0/net6/net8, Python 3.9+, TypeScript Node/Browser).
  - Feature parity matrix (100+ global languages, 22 Indic languages, honorifics, transliteration, unicode normalization, document translation, write assistant, glossaries, voice streaming).
  - Quickstart copy-paste snippet for all 4 languages.
  - License and contribution guidelines.

---

### Task 4: Web Application Route Fixes & Developer Hub (`apps/web`)

**Files:**
- Create: `apps/web/src/pages/DocsPage.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/pages/ApiKeys.tsx`
- Modify: `apps/web/src/components/layout/AppShell.tsx`

**Interfaces:**
- Consumes: SDK installation commands, CLI usage syntax, and API endpoint details.
- Produces: In-app `/docs` and `/api/docs` developer routes and multi-language quickstart tabs in API keys view.

- [ ] **Step 1: Create `apps/web/src/pages/DocsPage.tsx`**
  Interactive developer portal page presenting:
  - Getting started overview with Desi API & GlobalTalk AI.
  - Interactive tabs for CLI, Python SDK, TypeScript SDK, Java, .NET, and cURL.
  - Links to OpenAPI schema and local/cloud endpoints.

- [ ] **Step 2: Add `/docs` and `/api/docs` routes in `apps/web/src/App.tsx`**
  Register routes `<Route path="/docs" element={<DocsPage />} />` and `<Route path="/api/docs" element={<DocsPage />} />` so navigation links never bounce to landing page.

- [ ] **Step 3: Update `apps/web/src/pages/ApiKeys.tsx` with multi-language quickstart**
  Add interactive code snippet switcher on the Quick Start card allowing developers to toggle between CLI, TypeScript, Python, and cURL examples using their active API key.

---

### Task 5: Documentation Expansion with CLI & SDK Cross-References (`developer-docs`)

**Files:**
- Create: `developer-docs/documentation/desi-cli.mdx`
- Modify: `developer-docs/docs.json`
- Modify: `developer-docs/documentation/sdks-and-tools.mdx`
- Modify: `developer-docs/documentation/quickstart.mdx`

**Interfaces:**
- Consumes: `@globaltalk-ai/desi-cli` command specifications and SDK documentation.
- Produces: Comprehensive Mintlify documentation pages for the CLI and cross-references.

- [ ] **Step 1: Create `developer-docs/documentation/desi-cli.mdx`**
  Full reference guide covering:
  - Installation: `npm install -g @globaltalk-ai/desi-cli`
  - Dual binaries: `desi` and `globaltalk`
  - Commands: `translate`, `transliterate`, `normalize`, `write`, `correct`, `voice`, `document`, `sync`, `languages`, `usage`, `cache`, `config`.
  - Continuous localization sync workflows.

- [ ] **Step 2: Register `documentation/desi-cli` in `developer-docs/docs.json`**
  Add `"documentation/desi-cli"` to the `SDKs & Integration` navigation array.

- [ ] **Step 3: Update `developer-docs/documentation/sdks-and-tools.mdx` and `quickstart.mdx`**
  Add banner and cross-links to `@globaltalk-ai/desi-cli` alongside the 4 official SDKs.

---

### Task 6: Monorepo Root Workspace Configuration & Verification (`package.json`)

**Files:**
- Modify: `package.json`

**Interfaces:**
- Consumes: `apps/*`, `cli/desi-cli`, `sdk/typescript`, `developer-docs`.
- Produces: Monorepo workspace commands (`build:all`, `test:all`, `lint:all`, `dev:all`).

- [ ] **Step 1: Update root `package.json` workspaces**
  Ensure npm workspaces array contains:
  ```json
  "workspaces": [
    "apps/*",
    "apps/amazon-connect-v2v/webapp",
    "cli/desi-cli",
    "sdk/typescript",
    "developer-docs"
  ]
  ```

- [ ] **Step 2: Update root `package.json` scripts**
  Add:
  - `"dev"`: `"npm --prefix apps/web run dev"`
  - `"dev:cli"`: `"npm --prefix cli/desi-cli run dev"`
  - `"build:sdk"`: `"npm --prefix sdk/typescript run build"`
  - `"build:all"`: Build web, cli, and sdk
  - `"test:all"`: Test web, cli, and sdk

- [ ] **Step 3: Verify all files and syntax**
  Check that JSON files are valid and all paths and imports resolve correctly.
