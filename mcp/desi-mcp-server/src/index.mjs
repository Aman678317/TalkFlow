#!/usr/bin/env node

// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { DesiApiClient } from "./client.mjs";
import { createHandlers } from "./handlers.mjs";
import { registerTools } from "./tools.mjs";

const DESI_API_KEY = process.env.DESI_API_KEY || process.env.GLOBAL_TALK_API_KEY || process.env.DEEPL_API_KEY;

if (!DESI_API_KEY) {
  console.error(
    "DESI_API_KEY is not set. Provide an API key via the DESI_API_KEY environment variable.",
  );
  process.exit(1);
}

const client = new DesiApiClient(DESI_API_KEY, {
  apiUrl: process.env.DESI_API_URL || process.env.GLOBAL_TALK_API_URL || "http://127.0.0.1:8088",
  appName: "desi-mcp-server",
  appVersion: "1.0.0",
});

const server = new McpServer({
  name: "desi-mcp-server",
  version: "1.0.0",
});

registerTools(server, createHandlers(client));

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Desi MCP Server running on stdio (GlobalTalk AI)");
}

main().catch((error) => {
  console.error("Fatal error in Desi MCP server:", error);
  process.exit(1);
});
