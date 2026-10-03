# Design Specification: Project Structure Initialization with SDKs, Web App, CLI, and Documentation

- **Date**: 2026-10-02
- **Topic**: Monorepo Project Structure Initialization (SDKs, Web Application, CLI, Documentation)
- **Status**: Approved

---

## 1. Context & Motivation

GlobalTalk AI is an open-source, production-ready multilingual communication platform supporting real-time voice translation, text translation, document translation, and AI writing assistance across 100+ global languages and all 22 official Eighth Schedule Indian languages.

While the FastAPI backend (`services/api`), React 18 web application (`apps/web`), Command Line Interface (`cli/desi-cli`), Java SDK (`sdk/java/desi-java`), and .NET SDK (`sdk/dotnet/Desi`) are established, the project lacks a complete, unified monorepo structure with:
1. An official **Python Client SDK** (`sdk/python/desi-python`) supporting synchronous and asynchronous clients.
2. An official **TypeScript / Node.js Client SDK** (`sdk/typescript`) supporting browser and server environments.
3. A centralized **SDK Catalog & Index** (`sdk/README.md`) mapping capabilities across all four client libraries.
4. Cohesive **Root Workspace Configuration** (`package.json`) linking `apps/*`, `cli/*`, `sdk/typescript`, and documentation with unified dev, build, and test scripts.

---

## 2. Invariants & Guarantees

1. **The Canonical Source Invariant**:
   - Human speech or human text is the only semantic source of truth.
   - Translation fan-out occurs per listener independently.
   - Translation chains ($A \to B \to C$) and AI summary recursion are prohibited.
2. **Standard API & Wire Protocol Conformance**:
   - All SDKs conform strictly to OpenAPI 3.1.0 specifications for Desi v2 and v3 endpoints (`/v2/translate`, `/v2/desi/*`, `/v2/write/*`, `/v2/document`, `/v3/glossaries`, `/v3/style_rules`).
3. **Zero Third-Party Licensing Encumbrances**:
   - All client SDKs, CLI utilities, web app components, and docs are released under the permissive MIT License.

---

## 3. Architecture & Repository Layout

```
globaltalk-ai/
├── apps/
│   ├── web/                      # React 18 + Vite + Tailwind CSS web application
│   └── amazon-connect-v2v/       # Amazon Connect Voice-to-Voice integration
├── cli/
│   └── desi-cli/                 # Node.js/TypeScript CLI (commander, chalk, ws, axios)
├── sdk/
│   ├── README.md                 # Unified SDK directory index & matrix
│   ├── python/desi-python/       # Official Python 3.9+ SDK (sync & async, httpx)
│   │   ├── pyproject.toml
│   │   ├── setup.py
│   │   ├── README.md
│   │   ├── desi/
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   ├── async_client.py
│   │   │   ├── models.py
│   │   │   ├── exceptions.py
│   │   │   ├── constants.py
│   │   │   └── py.typed
│   │   └── tests/
│   │       ├── __init__.py
│   │       └── test_client.py
│   ├── typescript/               # Official TypeScript / Node.js SDK (@globaltalk/sdk)
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   ├── README.md
│   │   ├── src/
│   │   │   ├── index.ts
│   │   │   ├── client.ts
│   │   │   ├── types.ts
│   │   │   ├── errors.ts
│   │   │   └── constants.ts
│   │   └── tests/
│   │       └── client.test.ts
│   ├── java/desi-java/           # Official Java 11+ SDK (com.desi.api:desi-java)
│   └── dotnet/Desi/              # Official .NET SDK (netstandard2.0, net6.0, net8.0)
├── services/
│   └── api/                      # FastAPI core backend (REST v2/v3, WebSockets, DB, auth)
├── ai/                           # AI provider adapters & model router
├── developer-docs/               # Mintlify documentation portal & MDX guides
├── api-specs/                    # OpenAPI 3.1.0 & AsyncAPI 2.6.0 authoritative schemas
├── docs/                         # Architectural & operational technical guides
└── package.json                  # Root npm workspaces config (apps/*, cli/*, sdk/typescript)
```

---

## 4. Component Specifications

### 4.1 Python SDK (`sdk/python/desi-python`)
- **Package Name**: `desi-python` (import as `desi` or `from desi import DesiClient, AsyncDesiClient`)
- **Runtime**: Python >= 3.9
- **Dependencies**: `httpx>=0.24.0` (zero heavy machine learning dependencies)
- **Exported Classes**:
  - `DesiClient`: Synchronous client with connection pooling and retry jitter.
  - `AsyncDesiClient`: Asynchronous `asyncio` client for FastAPI/Tornado/AsyncIO applications.
  - `DesiClientOptions`: Configuration dataclass (server_url, timeout, max_retries, proxy).
- **Core Methods**:
  - `translate_text(text, target_lang, source_lang=None, formality=None, ...)`
  - `translate_desi(text, target_lang, honorific="formal", respectful_suffix=False, domain="general")`
  - `transliterate_desi(text, target_script="devanagari", source_script="latin")`
  - `normalize_desi_text(text, clean_zwnj=True, fix_nuktas=True)`
  - `get_desi_languages()`, `get_languages(type="source")`
  - `translate_document(file_path, target_lang, output_path=None, ...)`
  - `rephrase_text(text, target_lang="en", style="business", tone="diplomatic")`
  - `correct_text(text)`
  - `create_glossary()`, `list_glossaries()`, `get_glossary()`, `delete_glossary()`
  - `create_style_rule()`, `list_style_rules()`
  - `get_usage()`

### 4.2 TypeScript SDK (`sdk/typescript`)
- **Package Name**: `@globaltalk/sdk`
- **Runtime**: Node.js >= 18.0.0 and modern browsers (universal `fetch`)
- **Module Formats**: ESM and CommonJS support with TypeScript declaration files (`.d.ts`).
- **Core Methods**:
  - `translate(options)`: Standard & Indic translation.
  - `transliterate(options)`: Script transliteration.
  - `normalize(text)`: Indic Unicode sanitization.
  - `rephrase(options)` & `correct(options)`: Writing assistant.
  - `getLanguages()` & `getDesiLanguages()`: Language discovery.
  - `uploadDocument()`, `checkDocumentStatus()`, `downloadDocumentResult()`: Async documents.
  - `glossaries`: Glossary sub-client.
  - `styleRules`: Style rule sub-client.

### 4.3 Web Application Developer Experience (`apps/web`)
- **Route Additions**:
  - Add `/docs` and `/api/docs` routes in `apps/web/src/App.tsx` with an interactive Developer & SDK Quickstart view and external redirect fallback, preventing broken link bounces to `/`.
- **ApiKeys Page Enhancement**:
  - Update `apps/web/src/pages/ApiKeys.tsx` Quick Start card with multi-tab code snippets:
    - **CLI**: `npm i -g @globaltalk-ai/desi-cli && desi translate "Hello" --to hi`
    - **Python**: `pip install desi-python` snippet
    - **Node.js / TS**: `npm i @globaltalk/sdk` snippet
    - **cURL**: Existing REST API example

### 4.4 Documentation Expansion (`developer-docs`)
- **CLI Reference Page**:
  - Create `developer-docs/documentation/desi-cli.mdx` detailing commands (`translate`, `transliterate`, `normalize`, `write`, `correct`, `voice`, `sync`).
  - Add `"documentation/desi-cli"` to `developer-docs/docs.json` under `SDKs & Integration`.
- **SDK & Platform Cross-References**:
  - Update `developer-docs/documentation/sdks-and-tools.mdx` and `quickstart.mdx` to cross-reference `@globaltalk-ai/desi-cli` alongside the 4 SDKs.

### 4.5 Root Monorepo Orchestration
- Update root `package.json`:
  - Workspaces: `["apps/*", "cli/desi-cli", "sdk/typescript", "developer-docs"]`
  - Unified scripts:
    - `"dev"`: Runs the web client dev server.
    - `"build"`: Builds web client, CLI, and TypeScript SDK.
    - `"build:all"`: Builds all Node-based packages in dependency order.
    - `"test:all"`: Runs test suites across web, CLI, and SDK.
    - `"lint:all"`: Lints web, CLI, and SDK source directories.

### 4.6 SDK Directory Catalog (`sdk/README.md`)
- Central README in `sdk/` outlining:
  - SDK Matrix across Java, .NET, Python, and TypeScript.
  - Feature parity checklist (Indic honorifics, transliteration, normalization, documents, glossaries, voice).
  - Quickstart snippet for each language.

---

## 5. Verification & Testing Strategy

1. **Python Unit Tests**:
   - `tests/test_client.py`: Tests client initialization, mock translation response parsing, error code translation (`rate_limited`, `not_found`), and custom options.
2. **TypeScript Unit Tests**:
   - `tests/client.test.ts`: Verifies client instantiation, header setting, URL resolution, and translation methods with mock HTTP responses.
3. **Web App Build & Route Check**:
   - Verify that `apps/web` builds cleanly with new `/docs` and `/api/docs` routes and enhanced ApiKeys tabs.
4. **Workspace Integrity Check**:
   - Validate root `package.json` syntax and verify that `apps/web`, `cli/desi-cli`, and `sdk/typescript` are resolved by npm.
