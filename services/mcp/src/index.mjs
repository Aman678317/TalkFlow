#!/usr/bin/env node
/**
 * TalkFlow MCP server — stdio transport.
 * Speaks newline-delimited JSON-RPC 2.0 (the MCP stdio framing) on stdin/stdout.
 * Implements: initialize, notifications/initialized, ping, tools/list, tools/call.
 */
import { TOOLS, routeTool } from "./tools.mjs";
import { TalkFlowClient } from "./client.mjs";
import { errorResult, describeError } from "./content.mjs";

const SERVER_INFO = { name: "talkflow-mcp-server", version: "0.1.0" };
const SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];

const client = new TalkFlowClient();

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + "\n");
}

function reply(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function replyError(id, code, message) {
  send({ jsonrpc: "2.0", id, error: { code, message } });
}

async function handleToolsCall(params) {
  const name = params?.name;
  const handler = routeTool(name);
  if (!handler) return errorResult(`Unknown tool: ${name}`);
  try {
    return await handler(client, params?.arguments ?? {});
  } catch (err) {
    return errorResult(describeError(err));
  }
}

async function dispatch(msg) {
  const { id, method, params } = msg;
  const isNotification = id === undefined || id === null;
  switch (method) {
    case "initialize":
      if (isNotification) return;
      return reply(id, {
        protocolVersion: SUPPORTED_PROTOCOLS.includes(params?.protocolVersion)
          ? params.protocolVersion
          : SUPPORTED_PROTOCOLS[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER_INFO,
      });
    case "notifications/initialized":
    case "notifications/cancelled":
      return;
    case "ping":
      if (!isNotification) reply(id, {});
      return;
    case "tools/list":
      if (!isNotification) reply(id, { tools: TOOLS });
      return;
    case "tools/call": {
      if (isNotification) return;
      const result = await handleToolsCall(params);
      return reply(id, result);
    }
    default:
      if (!isNotification) replyError(id, -32601, `Method not found: ${method}`);
      return;
  }
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let idx;
  while ((idx = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, idx).trim();
    buffer = buffer.slice(idx + 1);
    if (!line) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      continue;
    }
    dispatch(msg).catch((err) => {
      if (msg.id !== undefined && msg.id !== null) replyError(msg.id, -32603, err?.message || String(err));
    });
  }
});
process.stdin.on("end", () => process.exit(0));
