# GlobalTalk AI / Desi Developer Documentation

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OpenAPI 3.1](https://img.shields.io/badge/OpenAPI-3.1.0-green.svg)](api-reference/openapi.yaml)
[![AsyncAPI 2.6](https://img.shields.io/badge/AsyncAPI-2.6.0-orange.svg)](api-reference/voice.asyncapi.yaml)
[![Mintlify](https://img.shields.io/badge/docs-Mintlify-blueviolet.svg)](https://mintlify.com)

Welcome to the official developer documentation and authoritative API specification repository for **GlobalTalk AI** and the **Desi Language AI** platform.

GlobalTalk AI provides real-time speech and document translation across **100+ world languages** and all **22 official Eighth Schedule Indian (Indic) languages**, featuring culturally accurate honorific controls (*Aap / Tum / Tu*), phonetic transliteration (Hinglish/Tanglish), and Unicode normalization.

---

## 🚀 Local Development & Preview

The documentation is built with [Mintlify](https://mintlify.com).

### Prerequisites

- Node.js 18.0.0 or higher
- npm or pnpm

### Quickstart

1. Install the Mintlify CLI globally:
   ```bash
   npm install -g mint
   ```
   *(If you previously installed the legacy `mintlify` package, run `npm uninstall -g mintlify` first).*

2. Navigate to this directory and start the local development server:
   ```bash
   mint dev
   ```

3. Open your browser at [http://localhost:3000](http://localhost:3000) to view the hot-reloading documentation.

---

## 📁 Repository Structure

```
developer-docs/
├── docs.json                      # Mintlify site configuration, styling, and navigation
├── LICENSE                        # Pure MIT License (Copyright 2026 GlobalTalk AI Authors)
├── README.md                      # This documentation guide
├── CLAUDE.md                      # AI assistant & maintainer instructions
├── api-reference/                 # Authoritative specifications and interactive API pages
│   ├── openapi.yaml               # OpenAPI 3.1.0 specification (REST endpoints)
│   ├── voice.asyncapi.yaml        # AsyncAPI 2.6.0 specification (Real-Time Voice Streaming)
│   ├── overview.mdx               # API overview, authentication, and headers
│   ├── translate.mdx              # v2 text translation with formality & glossaries
│   ├── desi-translate.mdx         # v2 Indic translation with honorifics & suffixes
│   ├── desi-transliterate.mdx     # v2 phonetic transliteration (Hinglish -> Devanagari)
│   ├── desi-normalize.mdx         # v2 Indic Unicode sanitization (ZWNJ, Nuktas)
│   ├── desi-languages.mdx         # v2 22 Eighth Schedule Indic languages catalog
│   ├── documents.mdx              # v2 asynchronous document translation pipeline
│   ├── write-rephrase.mdx         # v2 writing assistant rephrasing & styles
│   ├── write-correct.mdx          # v2 grammar and spelling correction
│   ├── glossaries.mdx             # v2 & v3 multilingual glossaries
│   ├── style-rules.mdx            # v3 style rules & custom brand instructions
│   ├── translation-memories.mdx   # v3 translation memory segment storage & matching
│   ├── voice-realtime.mdx         # v3 real-time voice streaming session handshake
│   ├── usage.mdx                  # v2 usage, quota, and character metering
│   └── languages.mdx              # v2 & v3 language discovery endpoints
└── documentation/                 # Architectural guides, tutorials, and SDK docs
    ├── introduction.mdx           # Platform overview and zero-copyright clean room
    ├── quickstart.mdx             # 5-minute multi-language quickstart guide
    ├── authentication.mdx         # API keys, headers, key rotation, and rate limits
    ├── languages.mdx              # 100+ global languages & 22 Indic languages directory
    ├── indic-features.mdx         # Desi Indic AI deep dive (Honorifics, Transliteration)
    ├── canonical-source.mdx       # The Canonical Source Invariant & Real-Time Flow
    ├── sdks-and-tools.mdx         # Client SDKs (Java, .NET, Python, Node.js)
    └── mcp-server.mdx             # Stdio MCP Server for Claude Code, Cursor, and VS Code
```

---

## 🏛️ Key Architectural Principles

1. **The Canonical Source Invariant**:
   In all multi-party spoken conversations and document processing, the human voice or human text is the **sole semantic source of truth**. Translations fan out independently to each listener (`Human Hindi` $\to$ `English`, `Human Hindi` $\to$ `Japanese`, `Human Hindi` $\to$ `Tamil`). Translation chains ($A \to B \to C$) are strictly prohibited to prevent hallucination compounding.

2. **Clean-Room & Zero Third-Party Liabilities**:
   All specifications, client libraries, and documentation are original, clean-room implementations released under the standard **MIT License**, free of third-party proprietary dependencies or trademark encumbrances.

3. **Production-Ready & Fully Typed**:
   Every endpoint and tool conforms strictly to OpenAPI 3.1.0 and MCP 1.0 JSON-RPC standards, supporting resilient HTTP/2 connection pooling, exponential backoff with jitter, and structured operational error reporting.

---

## 📄 License

This documentation and all associated specifications are released under the [MIT License](LICENSE).  
Copyright (c) 2026 GlobalTalk AI Authors and Contributors.
