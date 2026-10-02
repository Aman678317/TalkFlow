# GlobalTalk AI / Desi Developer Docs Guide

This repository contains the developer documentation and authoritative OpenAPI / AsyncAPI specifications for **GlobalTalk AI** and **Desi Language AI**.

## Development Commands

- **Preview documentation locally**:
  ```bash
  npm i -g mint
  mint dev
  ```
  Runs the local preview server at `http://localhost:3000`. Hot-reloads on file changes.

- **Check broken links & validate syntax**:
  ```bash
  mint broken-links
  ```

- **OpenAPI validation**:
  ```bash
  npx @redocly/cli lint api-reference/openapi.yaml
  ```

---

## Architectural & Content Guidelines

### 1. The Canonical Source Invariant
- Whenever documenting real-time voice translation or multi-party chat, always emphasize that the **human speaker is the sole semantic source of truth**.
- Translations fan out independently to target languages. Never suggest or document chained translations (e.g. Hindi -> English -> Japanese).

### 2. Desi Indic AI Linguistic Requirements
- Document all 22 official Eighth Schedule Indian languages.
- Clearly describe the 3-tier formality system:
  - `formal` (*Aap* / आप / நீங்கள் / మీరు) - For professional, business, and elder conversations.
  - `familiar` (*Tum* / तुम / நீ / నువ్వు) - For peers and informal colleagues.
  - `intimate` (*Tu* / तू) - For close family and childhood friends.
  - Respectful suffixes (`-ji` in Hindi/Punjabi, `-garu` in Telugu, `-avargal` in Tamil).
- Detail script transliteration rules (Latin/Roman phonetic Hinglish/Tanglish $\leftrightarrow$ Indic native scripts).
- Detail Unicode normalization rules (Devanagari Nukta composition, Zero-Width Joiner/Non-Joiner sanitization).

### 3. API & Code Formatting
- Code examples must include practical snippets across:
  - **cURL**
  - **Java** (`com.desi.api:desi-java`)
  - **.NET / C#** (`GlobalTalk.Desi`)
  - **Python** (`desi-python`)
  - **Node.js / TypeScript** (`@globaltalk/sdk`)
- Always use environment variables for keys: `GTK_API_KEY` or `DESI_API_KEY`.
- Base URL conventions:
  - Production: `https://api.globaltalk.ai`
  - Local Edge / Dev: `http://127.0.0.1:8088`

### 4. Zero Third-Party Copyright Claims
- Clean-room implementation: Do not include proprietary trademarks, third-party corporate logos, or proprietary tracking scripts.
- Pure standard MIT License: Attributed solely to `GlobalTalk AI Authors and Contributors`.
