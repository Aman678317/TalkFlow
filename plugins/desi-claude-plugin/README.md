# Desi Claude Plugin (`desi-claude-plugin`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Plugin](https://img.shields.io/badge/Claude-Plugin-8A2BE2.svg)](https://anthropic.com/claude)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Standard-009688.svg)](https://modelcontextprotocol.io)

Official **Claude Plugin** that exposes **Desi Language AI** and **GlobalTalk AI** capabilities directly inside Anthropic Claude Desktop and Claude Code: high-precision neural translation across **100+ global languages** and all **22 official Eighth Schedule Indian languages**, 3-tier cultural formality honorifics (*Aap / Tum / Tu*), AI writing enhancement, multilingual glossaries, and layout-preserving document translation.

---

## 🏛️ Architecture Overview

The initiating actor is the user chatting with Claude. Claude inspects the plugin manifest and translation guidance rules (`SKILL.md`), connects through the Model Context Protocol configuration (`.mcp.json`), and accesses the Desi AI Gateway:

```mermaid
flowchart TD

subgraph group_claude_plugin["Claude plugin"]
  node_plugin_manifest["Plugin manifest<br/>[plugin.json]"]
  node_mcp_config["MCP configuration<br/>[.mcp.json]"]
  node_translation_rules["Translation rules<br/>[SKILL.md]"]
end

subgraph group_desi_capabilities["Desi capabilities"]
  node_translation["Translation<br/>[.mcp.json]"]
  node_writing_improvement["Writing improvement<br/>[.mcp.json]"]
  node_glossary["Glossary access<br/>[.mcp.json]"]
  node_document_translation["Document translation<br/>[.mcp.json]"]
  node_indic_honorifics["Indic honorifics & nuances<br/>[.mcp.json]"]
end

node_user(("User"))
node_claude(("Claude"))
node_desi{{"Desi AI Gateway<br/>(GlobalTalk AI)"}}

node_user -->|"requests work"| node_claude
node_claude -->|"uses plugin"| node_plugin_manifest
node_claude -->|"uses guidance"| node_translation_rules
node_claude -->|"connects through"| node_mcp_config
node_mcp_config -->|"enables"| node_translation
node_mcp_config -->|"enables"| node_writing_improvement
node_mcp_config -->|"enables"| node_glossary
node_mcp_config -->|"enables"| node_document_translation
node_mcp_config -->|"enables"| node_indic_honorifics
node_translation -->|"accesses"| node_desi
node_writing_improvement -->|"accesses"| node_desi
node_glossary -->|"accesses"| node_desi
node_document_translation -->|"accesses"| node_desi
node_indic_honorifics -->|"accesses"| node_desi

classDef toneNeutral fill:#f8fafc,stroke:#334155,stroke-width:1.5px,color:#0f172a
classDef toneBlue fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef toneAmber fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef toneMint fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef toneRose fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef toneIndigo fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81
classDef toneTeal fill:#ccfbf1,stroke:#0f766e,stroke-width:1.5px,color:#134e4a

class node_plugin_manifest,node_mcp_config,node_translation_rules,node_user toneBlue
class node_translation,node_writing_improvement,node_glossary,node_document_translation,node_indic_honorifics toneAmber
class node_claude,node_desi toneIndigo
```

---

## 🌟 Capabilities

| Capability | Description | MCP Tools Exposed |
|---|---|---|
| 🌍 **Global Text Translation** | Neural translation across 100+ international languages with formality control (*more*, *less*). | `translate-text`, `get-target-languages`, `get-source-languages` |
| 🇮🇳 **22 Indic Languages & Honorifics** | Cultural formality registers (*Aap / Tum / Tu*), respectful suffixes (*-जी*, *-గారు*, *-அவர்கள்*), and domain styles (*official*, *business*, *colloquial*). | `translate-desi`, `get-desi-languages` |
| ✍️ **Writing Enhancement (Desi Write)** | Tone transformation (*confident*, *diplomatic*, *friendly*), style rephrasing (*business*, *academic*, *casual*, *simple*), and grammar corrections. | `rephrase-text`, `correct-text`, `get-writing-styles`, `get-writing-tones` |
| 📄 **Document Translation** | Layout-preserving asynchronous translation for DOCX, PDF, PPTX, XLSX, HTML, and TXT files. | `translate-document` |
| 📚 **Glossary & Style Rules** | Enterprise dictionary lookup and terminology consistency enforcement. | `list-glossaries`, `get-glossary-info`, `list-style-rules`, `get-style-rule` |
| 🔤 **Transliteration & Normalization** | Converts Romanized Hinglish/Tanglish into native Brahmic scripts and cleans Indic Unicode ZWNJ/Nuktas. | `transliterate-desi`, `normalize-desi` |

---

## 🚀 Setup & Authentication

### 1. First-Time Sign-In & Authentication
Access to Desi services is authorized via the `DESI_API_KEY` environment variable. When Claude first needs to invoke translation or writing enhancement tools, it verifies credentials:

```bash
# Provide your Desi API key
export DESI_API_KEY="gtk_live_your_api_key_here"

# Optional: Point to custom or local GlobalTalk AI instance
export DESI_API_URL="http://127.0.0.1:8088"
```

*(Backwards compatibility: If `GLOBAL_TALK_API_KEY` or `DEEPL_API_KEY` is present in the environment, it is automatically accepted as a fallback).*

### 2. Adding to Claude Code
To register this plugin in Claude Code:

```bash
claude plugin add ./plugins/desi-claude-plugin
```

### 3. Adding to Claude Desktop
Add the following block to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "desi": {
      "command": "node",
      "args": ["<path-to-globaltalk-ai>/mcp/desi-mcp-server/src/index.mjs"],
      "env": {
        "DESI_API_KEY": "gtk_live_your_api_key_here",
        "DESI_API_URL": "http://127.0.0.1:8088"
      }
    }
  }
}
```

---

## 💡 Example User Invocations with Claude

Once installed, Claude automatically applies Desi capabilities when you ask:

- **Indic Honorifics**:
  > *"Claude, translate our welcome email into Hindi using formal honorifics (Aap) and address the user with the respectful suffix -ji."*
- **Tone & Style Adaptation**:
  > *"Claude, rephrase this incident post-mortem into a business-diplomatic tone using Desi Write."*
- **Document Translation**:
  > *"Claude, translate `quarterly_report.docx` to German while keeping tables and formatting intact."*
- **Phonetic Transliteration**:
  > *"Claude, convert 'Aapka bohot bohot dhanyavaad' into Devanagari script."*
- **Enterprise Terminology**:
  > *"Claude, check our customer glossary and translate this API release note to Japanese."*

---

## 📄 License

Licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.  
Copyright (c) 2026 GlobalTalk AI Authors and Contributors.
