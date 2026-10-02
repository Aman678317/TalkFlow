# Changelog

All notable changes to GlobalTalk AI are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Full Desi API v2/v3 standard conformance router (`/v2/translate`, `/v2/write/*`, `/v3/voice/*`, `/v2/document`, `/v2/glossaries`, `/v3/spoken-terms`, admin analytics)
- `friendlyMessage()` utility exported from `@/lib/api` for normalized error display
- BCP-47 language code normalization (`toBCP47()`) in Voice Studio to prevent Chrome speech recognition network errors
- `currentSpokenTextRef` buffer in Voice Studio to prevent dropped speech utterances on mic toggle
- Graceful backend translation fallback — shows original text if API is unreachable
- Vite proxy entries for `/v2` and `/v3` routes
- `START_ALL.bat` — one-click Windows launcher for backend + frontend
- `CREATE_ZIP.bat` + `make_zip.py` — portable full-stack archive creator
- `.github/` community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `PULL_REQUEST_TEMPLATE.md`, issue templates
- `.vscode/settings.json` with proper Tailwind CSS, Python, and TypeScript settings
- MIT `LICENSE`

### Fixed
- `@vitejs/plugin-react` dynamic import with fallback to native esbuild JSX
- `cors_origins` Pydantic parsing crash — now accepts comma-separated strings and JSON arrays
- SQLAlchemy async driver mismatch — auto-upgrades `sqlite://` to `sqlite+aiosqlite://`
- `ToastHost` missing export from `stores/toast`
- `changes_count: int` TypeScript type error in `Write.tsx` (changed to `number`)
- All legacy DeepL branding replaced with **Desi** / **GlobalTalk AI** / **GlobalTalk Voice** / **GlobalTalk Write**

---

## [0.1.0] — 2026-09-27

### Added
- Initial full-stack release
- Real-time multilingual voice translation (WebSocket PCM + LiveKit adapter)
- Text translation with offline NMT (Argos), TM, glossaries, formality, style profiles
- Document translation (DOCX, PPTX, XLSX, PDF, TXT, HTML)
- AI Writing Assistant (style/tone rewrite + grammar correction)
- Meetings with per-participant translated audio and captions
- Multilingual chat (per-listener translation)
- Auth (JWT + refresh rotation), organizations, RBAC, audit logs
- Developer API with API keys, metering, webhooks, usage analytics
- Admin dashboard
- Golden call acceptance test (`tests/realtime/test_golden_call.py`)
- Full documentation suite in `docs/`
