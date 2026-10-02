# Changelog

All notable changes to `desi-mcp-server` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-29

### Added
- **MCP Server for Desi Language AI / GlobalTalk AI**:
  - Full stdio transport integration with `@modelcontextprotocol/sdk`.
  - Zero third-party proprietary client dependencies (direct native HTTP transport).
- **Desi Indic-Native MCP Tools**:
  - `translate-desi`: Cultural honorific registers (*Aap*, *Tum*, *Tu*, *-ji*) and domain styles.
  - `transliterate-desi`: Phonetic script transliteration (Latin/Hinglish ↔ Devanagari, Gurmukhi, Tamil, etc.).
  - `normalize-desi`: Indic Unicode normalization (Nukta fixing & ZWNJ/ZWJ cleanup).
  - `get-desi-languages`: Official 22 Eighth Schedule Indian languages catalog.
- **Enterprise Language Features**:
  - `translate-text`: Global translation across 100+ languages.
  - `translate-document`: Document translation with automated path resolution.
  - `rephrase-text` & `correct-text`: Desi Write style and grammar improvements.
  - `list-glossaries`, `get-glossary-info`, `get-glossary-dictionary-entries`.
  - `list-style-rules`, `get-style-rule`, `get-custom-instruction`.
- **Licensing**:
  - 100% clean MIT License under GlobalTalk AI Authors.
