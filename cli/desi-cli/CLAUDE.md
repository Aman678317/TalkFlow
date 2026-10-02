# Desi CLI Developer Guidelines

## Project Overview

**Desi CLI** (`desi` / `globaltalk`) is the official command-line interface for **Desi Language AI** and **GlobalTalk AI**.
It provides production translation across **100+ global world languages** and all **22 official Eighth Schedule Indian languages**, cultural honorific controls (*Aap / Tum / Tu*), phonetic transliteration, continuous localization sync, writing enhancement (Desi Write), and real-time streaming voice translation.

### Architecture

```
CLI Commands (translate, indic, write, correct, voice, sync, watch, glossary, tm, …)
           ↓
Service Layer (Translation, Indic, Write, Voice, VoiceStreamSession, Document,
               Sync, Watch, Glossary, TranslationMemory, StyleRules, Usage, Detect, Languages)
           ↓                         ↓
Sync Engine (src/sync)         Format Parsers (src/formats — JSON, YAML, PO, XLIFF, Android XML)
           ↓                         ↓
API Client (DesiClient, TranslationClient, IndicClient, WriteClient, VoiceClient, DocumentClient)
           ↓
Storage (SQLite Cache, XDG Config) + Static Data (Language Registry, Indic Languages)
```

### Configuration & Paths

- **Config**: XDG default `~/.config/desi-cli/config.json`, fallback `~/.desi-cli/config.json`
- **Cache**: XDG default `~/.cache/desi-cli/cache.db`, fallback `~/.desi-cli/cache.db`
- **Path priority**: `DESI_CONFIG_DIR` > XDG env vars > XDG defaults
- **Environment Variables**:
  - `DESI_API_KEY` or `GLOBAL_TALK_API_KEY` (or legacy `DEEPL_API_KEY` for backwards compatibility)
  - `DESI_API_URL` (default: `https://api.globaltalk.ai`)
  - `DESI_CONFIG_DIR` (override config and cache directory)

## Development Workflow & Testing

- **TDD (Test-Driven Development)**:
  - Unit tests: `tests/unit/`
  - Integration tests: `tests/integration/`
  - E2E tests: `tests/e2e/`
- **Commands**:
  - `npm test` - Run tests
  - `npm run lint` - Check linting
  - `npm run type-check` - Verify TypeScript compiler
  - `npm run build` - Build dist bundle
