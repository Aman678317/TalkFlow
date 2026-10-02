# Desi & GlobalTalk AI Specifications

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OpenAPI 3.1](https://img.shields.io/badge/OpenAPI-3.1.0-green.svg)](openapi.yaml)
[![AsyncAPI 3.0](https://img.shields.io/badge/AsyncAPI-3.0.0-orange.svg)](voice.asyncapi.yaml)

This repository contains the authoritative [OpenAPI][openapi-specification] and [AsyncAPI][asyncapi-specification] specifications for the **Desi Language AI** and **GlobalTalk AI** platform, in both YAML and JSON formats.

---

## 🌐 Public Specifications Mirror

These specifications define the full capabilities of the platform across two primary surfaces:

- [`openapi.yaml`](openapi.yaml) / [`openapi.json`](openapi.json) — **Desi REST API**:
  - Neural text translation across **100+ global world languages** and all **22 official Eighth Schedule Indian languages**.
  - **Desi Indic AI Engine**: 3-tier cultural honorifics (*Aap / Tum / Tu* and respectful suffixes *-ji / -garu / -avargal*), phonetic script transliteration (Hinglish/Tanglish $\leftrightarrow$ Indic scripts), and Indic Unicode sanitization (composed nuktas and ZWNJ/ZWJ normalization).
  - Asynchronous, layout-preserving document translation (PDF, DOCX, PPTX, XLSX, HTML, TXT).
  - Writing assistance (Desi Write rephrasing, styles, tones, and grammar/spelling correction).
  - Multilingual custom glossaries, translation memories (TM), and brand style rules.
  - Real-time voice session negotiation.

- [`voice.asyncapi.yaml`](voice.asyncapi.yaml) / [`voice.asyncapi.json`](voice.asyncapi.json) — **Desi Voice API (WebSocket Streaming)**:
  - Full-duplex, low-latency (<800ms) speech-to-speech and speech-to-text streaming over WebSocket.
  - Streaming PCM16 and Opus audio chunk transmission with base64 and binary MessagePack framing.
  - Real-time incremental source transcript updates (concluded vs. tentative segments).
  - Direct fan-out target translations enforcing the **Canonical Source Invariant**.
  - Synthesized speech audio packets with timestamp synchronization for live captions.

---

## 🛠️ Usage & Tooling Integration

You can use these specifications to explore endpoints, simulate traffic, and automatically generate client SDKs:

### 1. API Exploration & Mocking
- **[Postman][postman]**: Import `openapi.yaml` or `voice.asyncapi.yaml` directly into Postman to generate interactive request collections.
- **[Swagger Editor][swagger-editor]**: Paste or import `openapi.yaml` to preview and test REST endpoints interactively.
- **[AsyncAPI Studio][asyncapi-studio]**: Visualize channels, message schemas, and client-server workflows for real-time streaming audio.

### 2. Client SDK Generation
Use [OpenAPI Generator][openapi-generator] to generate strongly typed client libraries in any programming language:

```bash
# Generate Python SDK
npx @openapitools/openapi-generator-cli generate \
  -i openapi.yaml \
  -g python \
  -o ./generated/desi-python

# Generate TypeScript / Node.js SDK
npx @openapitools/openapi-generator-cli generate \
  -i openapi.yaml \
  -g typescript-axios \
  -o ./generated/desi-ts

# Generate Go SDK
npx @openapitools/openapi-generator-cli generate \
  -i openapi.yaml \
  -g go \
  -o ./generated/desi-go
```

---

## 🏛️ Base Servers

| Surface | Protocol | Production Endpoint | Local Dev / Edge |
|---|---|---|---|
| **REST API** | HTTPS | `https://api.globaltalk.ai` | `http://127.0.0.1:8088` |
| **Voice Streaming** | WSS / WS | `wss://api.globaltalk.ai/v3/voice/realtime/connect` | `ws://127.0.0.1:8088/v3/voice/realtime/connect` |

---

## 📄 License

This repository and all specifications are licensed under the [MIT License](LICENSE).  
Copyright (c) 2026 GlobalTalk AI Authors and Contributors.

[asyncapi-specification]: https://www.asyncapi.com/
[asyncapi-studio]: https://studio.asyncapi.com/
[openapi-generator]: https://openapi-generator.tech/
[openapi-specification]: https://openapis.org/
[postman]: https://www.postman.com/
[swagger-editor]: https://editor.swagger.io/
