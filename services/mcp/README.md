# TalkFlow MCP Server (`@globaltalk/mcp-server`)

A **stdio MCP server** that exposes GlobalTalk AI (TalkFlow) capabilities to any MCP
client (Claude Desktop, Cursor, Qoder, …). It is a thin, dependency-free bridge:
MCP tool calls are normalized, forwarded to the TalkFlow backend
(`services/api`) over REST, and the responses are formatted as MCP text content.

Architecture (same shape as common MCP translation servers, implemented from scratch):

```
MCP client ──stdio──▶ src/index.mjs (transport + JSON-RPC server)
                          │ routes tool calls
                          ▼
                     src/tools.mjs (tool registry: schemas + routing)
                          │
                          ▼
                     src/handlers.mjs (per-tool logic + formatting)
                          │        │            │
                          ▼        ▼            ▼
                  src/client.mjs  src/languages.mjs  src/writing.mjs
                  (REST + auth)   (language cache)   (style/tone enums)
                          │
                          ▼
                  TalkFlow backend  /api/v1/*
```

## Tools

| Tool | Purpose |
|---|---|
| `talkflow_translate_text` | Text translation (source auto-detect, formality, glossary/style profile, domain) |
| `talkflow_detect_language` | Language detection |
| `talkflow_list_languages` | Supported languages + translation/speech capabilities |
| `talkflow_rephrase_text` | Writing companion: grammar/style/tone improvement with change list |
| `talkflow_translate_document` | Upload a local file, wait for processing, write translated file, return output path |
| `talkflow_list_glossaries` / `talkflow_get_glossary` | Terminology glossary lookup |
| `talkflow_list_style_profiles` | Style-rule lookup |

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `TALKFLOW_API_BASE` | `http://127.0.0.1:8088` | Backend base URL |
| `TALKFLOW_TOKEN` | – | Pre-issued bearer token (skips login) |
| `TALKFLOW_EMAIL` / `TALKFLOW_PASSWORD` | demo workspace account | Login credentials used to obtain a token |

## Run

```bash
node services/mcp/src/index.mjs          # stdio server
node services/mcp/test/smoke.mjs         # live smoke test vs a running backend
```

Example MCP client config (Claude Desktop / any stdio client):

```json
{
  "mcpServers": {
    "talkflow": {
      "command": "node",
      "args": ["/path/to/repo/services/mcp/src/index.mjs"],
      "env": { "TALKFLOW_API_BASE": "http://127.0.0.1:8088" }
    }
  }
}
```

No runtime dependencies; Node >= 18 (uses global `fetch`, `FormData`, `Blob`).
