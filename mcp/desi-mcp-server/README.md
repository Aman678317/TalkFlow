# Desi MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-blueviolet.svg)](LICENSE)

A Model Context Protocol (MCP) server that exposes **Desi Language AI** and **GlobalTalk AI** text translation, Indic-native honorific transformation, cross-script phonetic transliteration, Unicode normalization, document translation, rephrasing, and enterprise glossary/style lookups as MCP tools.

---

## Architecture Overview

```mermaid
flowchart TD

subgraph group_mcp["MCP Runtime"]
  node_stdio["stdio transport<br/>[index.mjs]"]
  node_server["MCP server<br/>[index.mjs]"]
  node_tools["Tool registry<br/>[tools.mjs]"]
end

subgraph group_operations["Translation & Linguistic Operations"]
  node_handlers["Tool handlers<br/>[handlers.mjs]"]
  node_desi["Indic honorifics & nuances<br/>[translate-desi]"]
  node_translit["Script transliteration & normalizer<br/>[transliterate-desi]"]
  node_text["Global text translation<br/>[translate-text]"]
  node_document["Document translation<br/>[translate-document]"]
  node_rephrase["Text rephrasing & correction<br/>[rephrase-text]"]
  node_apiclient["Desi API client<br/>[client.mjs]"]
end

subgraph group_lookups["Language & Resource Lookup"]
  node_languagecache["Language cache<br/>[languages.mjs]"]
  node_desilangs["22 Scheduled Indic languages<br/>[get-desi-languages]"]
  node_resourcequeries["Glossary & style lookups<br/>[handlers.mjs]"]
end

subgraph group_shared["Shared Utilities"]
  node_content["MCP text formatting<br/>[content.mjs]"]
  node_writing["Writing & honorific enums<br/>[writing.mjs]"]
end

node_client(("MCP Client<br/>(Claude / Cursor / VS Code)"))
node_gateway{{"GlobalTalk AI API Gateway<br/>(http://127.0.0.1:8088)"}}
node_localfiles["Local Documents"]

node_client -->|"sends requests"| node_stdio
node_stdio -->|"carries JSON-RPC"| node_server
node_server -->|"routes tool calls"| node_tools
node_server -->|"connects transport"| node_stdio
node_tools -->|"registers callbacks"| node_handlers
node_handlers -->|"handles Indic requests"| node_desi
node_handlers -->|"handles script conversion"| node_translit
node_handlers -->|"handles global translation"| node_text
node_handlers -->|"handles file translation"| node_document
node_handlers -->|"handles style improvement"| node_rephrase
node_handlers -->|"handles resource queries"| node_resourcequeries
node_handlers -->|"queries Indic catalog"| node_desilangs
node_handlers -->|"reads languages"| node_languagecache
node_handlers -->|"delegates to"| node_apiclient
node_apiclient -->|"sends HTTP requests"| node_gateway
node_handlers -->|"reads and writes"| node_localfiles
node_handlers -->|"formats responses"| node_content
node_tools -->|"uses option schemas"| node_writing

classDef toneBlue fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef toneAmber fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef toneMint fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef toneRose fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef toneIndigo fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81

class node_stdio,node_server,node_tools,node_client toneBlue
class node_handlers,node_desi,node_translit,node_text,node_document,node_rephrase,node_apiclient toneAmber
class node_languagecache,node_desilangs,node_resourcequeries,node_gateway toneMint
class node_content,node_writing toneRose
class node_localfiles toneIndigo
```

---

## Quick Start

You need **Node.js 18 or newer**.

### Directly with Node:

```bash
DESI_API_KEY=your-api-key node src/index.mjs
```

Or point to a custom GlobalTalk AI Gateway instance:

```bash
DESI_API_URL=http://127.0.0.1:8088 DESI_API_KEY=gtk_demo_key:fx node src/index.mjs
```

---

## MCP Client Configuration

### Claude Code

```bash
claude mcp add desi --env DESI_API_KEY=your-api-key --env DESI_API_URL=http://127.0.0.1:8088 -- node <path-to-desi-mcp-server>/src/index.mjs
```

### Claude Desktop / Cursor / VS Code (`claude_desktop_config.json` or `mcpServers` settings)

```json
{
  "mcpServers": {
    "desi": {
      "command": "node",
      "args": ["<path-to-desi-mcp-server>/src/index.mjs"],
      "env": {
        "DESI_API_KEY": "gtk_demo_key:fx",
        "DESI_API_URL": "http://127.0.0.1:8088"
      }
    }
  }
}
```

---

## Available Tools

### 1. Desi Indic-Native Tools

| Tool | Description | Parameters |
| :--- | :--- | :--- |
| `translate-desi` | Translates text into Indic languages with cultural honorifics (*Aap*, *Tum*, *Tu*, *-ji*) and domain registers. | `text`, `targetLang`, `sourceLang?`, `honorific?`, `domain?`, `respectfulSuffix?` |
| `transliterate-desi` | Phonetically converts text between Latin/Hinglish and Indic scripts (Devanagari, Gurmukhi, Tamil, etc.). | `text`, `sourceScript?`, `targetScript?` |
| `normalize-desi` | Cleans Indic Unicode anomalies, fixing Nuktas and removing stray ZWNJ / ZWJ codepoints. | `text`, `cleanZwnj?`, `fixNuktas?` |
| `get-desi-languages` | Returns the complete catalog of all 22 official Eighth Schedule Indian languages. | *none* |

### 2. Global Translation & Style Tools

| Tool | Description | Parameters |
| :--- | :--- | :--- |
| `translate-text` | Translates text into 100+ global world languages using the GlobalTalk AI engine. | `text`, `targetLangCode`, `sourceLangCode?`, `formality?`, `glossaryId?`, `styleId?`, `context?`, `preserveFormatting?`, `splitSentences?`, `customInstructions?` |
| `translate-document` | Translates a document file (PDF, DOCX, PPTX, XLSX, HTML, TXT) and writes the result to disk. | `inputFile`, `targetLangCode`, `outputFile?`, `sourceLangCode?`, `formality?`, `glossaryId?`, `styleId?`, `outputFormat?` |
| `rephrase-text` | Rephrases text for style, tone, or fluency, optionally into another target language. | `text`, `targetLangCode?`, `style?`, `tone?` |
| `correct-text` | Corrections-only mode for fixing spelling and grammar without changing style. | `text`, `targetLangCode?` |
| `get-source-languages` | Lists all supported source language codes. | *none* |
| `get-target-languages` | Lists all supported target language codes. | *none* |
| `get-writing-styles` | Lists supported writing styles (`academic`, `business`, `casual`, `simple`, `default`). | *none* |
| `get-writing-tones` | Lists supported tones (`confident`, `diplomatic`, `enthusiastic`, `friendly`, `passive`). | *none* |

### 3. Enterprise Resource Lookups

| Tool | Description | Parameters |
| :--- | :--- | :--- |
| `list-glossaries` | Lists all multilingual and bilingual glossaries in the account. | *none* |
| `get-glossary-info` | Returns metadata for a single glossary by ID. | `glossaryId` |
| `get-glossary-dictionary-entries` | Returns term pairs for a specific language pair within a glossary. | `glossaryId`, `sourceLangCode`, `targetLangCode` |
| `list-style-rules` | Lists enterprise style rules with IDs and timestamps. | `page?`, `pageSize?`, `detailed?` |
| `get-style-rule` | Returns full details of a style rule including configured rules and custom instructions. | `styleId` |
| `get-custom-instruction` | Returns a single custom instruction belonging to a style rule. | `styleId`, `instructionId` |

---

## License

Licensed under the [MIT License](LICENSE).
Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
