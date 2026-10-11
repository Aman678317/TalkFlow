/**
 * Smoke test: spawns the MCP server over stdio and exercises the real
 * protocol handshake plus live tool calls against a running TalkFlow backend
 * (default http://127.0.0.1:8088, override with TALKFLOW_API_BASE).
 */
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const entry = path.join(here, "..", "src", "index.mjs");

const child = spawn(process.execPath, [entry], { stdio: ["pipe", "pipe", "inherit"] });

let buf = "";
const pending = new Map();
child.stdout.on("data", (chunk) => {
  buf += chunk.toString("utf8");
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (!line) continue;
    try {
      const msg = JSON.parse(line);
      if (msg.id !== undefined && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      }
    } catch {}
  }
});

let nextId = 1;
function rpc(method, params) {
  const id = nextId++;
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`timeout: ${method}`)), 60_000);
    pending.set(id, (msg) => {
      clearTimeout(t);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    });
  });
}

function fail(msg) {
  console.error("SMOKE FAIL:", msg);
  child.kill();
  process.exit(1);
}

try {
  const init = await rpc("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "smoke", version: "0" } });
  console.log("initialize ok:", init.serverInfo.name, init.protocolVersion);
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");

  const list = await rpc("tools/list", {});
  console.log("tools/list ok:", list.tools.map((t) => t.name).join(", "));
  if (list.tools.length < 8) fail("expected >= 8 tools");

  const tr = await rpc("tools/call", {
    name: "talkflow_translate_text",
    arguments: { text: "Hello, welcome to GlobalTalk AI.", target_language: "hi" },
  });
  console.log("translate_text ->", tr.content?.[0]?.text?.split("\n").slice(0, 2).join(" | "));
  if (tr.isError) fail("translate_text errored");

  const det = await rpc("tools/call", { name: "talkflow_detect_language", arguments: { text: "नमस्ते दुनिया" } });
  console.log("detect_language ->", det.content?.[0]?.text?.replace(/\n/g, " | "));

  const langs = await rpc("tools/call", { name: "talkflow_list_languages", arguments: {} });
  console.log("list_languages ->", langs.content?.[0]?.text?.split("\n")[0]);

  const rep = await rpc("tools/call", {
    name: "talkflow_rephrase_text",
    arguments: { text: "we is going to meeting tomorrow for discuss about plan", style: "business" },
  });
  console.log("rephrase_text ->", rep.content?.[0]?.text?.split("\n").slice(0, 2).join(" | "));

  console.log("SMOKE PASS");
  child.kill();
  process.exit(0);
} catch (err) {
  fail(err?.message || String(err));
}
