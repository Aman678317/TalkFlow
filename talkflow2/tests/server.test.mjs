/**
 * Server / HTTP API tests (build-server).
 *
 * The real server is started on an ephemeral port (0) so the suite never
 * collides with a developer instance on 8096. No outbound network: DeepL
 * endpoints are only exercised on local validation failures, and the only key
 * transmitted is a fake one whose non-echo (response + log) is asserted.
 */
import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { startServer } from "../server/server.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HELLO_FIXTURE = path.join(HERE, "fixtures", "hello.txt");
const DATA_FILE = path.resolve(HERE, "..", "data", "glossaries.json");

// Snapshot glossary persistence so the suite leaves the working tree untouched.
const DATA_EXISTED = fs.existsSync(DATA_FILE);
const ORIGINAL_DATA = DATA_EXISTED ? fs.readFileSync(DATA_FILE) : null;

let server = null;
let port = 0;
let baseUrl = "";
const sockets = new Set();
const createdGlossaries = new Set();

/* ------------------------------------------------------------------ *
 * Small HTTP helpers
 * ------------------------------------------------------------------ */

async function request(pathname, { method = "GET", body, headers } = {}) {
  const opts = { method, headers: { ...(headers ?? {}) } };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${baseUrl}${pathname}`, opts);
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON response body */
  }
  return { status: res.status, headers: res.headers, text, json };
}

/** Raw request: lets us send un-normalized paths like `/../package.json`. */
function rawGet(rawPath) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: "127.0.0.1", port, path: rawPath, method: "GET" },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () =>
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body: Buffer.concat(chunks).toString("utf8"),
          }),
        );
      },
    );
    req.on("error", reject);
    req.end();
  });
}

/* ------------------------------------------------------------------ *
 * Server lifecycle
 * ------------------------------------------------------------------ */

before(async () => {
  const started = await startServer({ port: 0 });
  server = started.server;
  port = started.port;
  baseUrl = `http://127.0.0.1:${port}`;
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
  });
});

after(async () => {
  // Best-effort removal of anything a failed test may have left behind.
  for (const id of createdGlossaries) {
    try {
      await request(`/api/glossary/${id}`, { method: "DELETE" });
    } catch {
      /* server may already be unavailable */
    }
  }
  if (server) {
    server.closeAllConnections?.();
    for (const socket of sockets) socket.destroy();
    await new Promise((resolve) => server.close(() => resolve()));
  }
  // Let fire-and-forget persistence writes settle, then restore the snapshot.
  await new Promise((resolve) => setTimeout(resolve, 25));
  try {
    if (DATA_EXISTED && ORIGINAL_DATA) fs.writeFileSync(DATA_FILE, ORIGINAL_DATA);
    else if (!DATA_EXISTED && fs.existsSync(DATA_FILE)) fs.unlinkSync(DATA_FILE);
  } catch {
    /* snapshot restore is best effort */
  }
});

/* ------------------------------------------------------------------ *
 * Metadata endpoints
 * ------------------------------------------------------------------ */

test("GET /api/health returns ok, version, uptime and 8 agents", async () => {
  const res = await request("/api/health");
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type") ?? "", /^application\/json/);
  assert.equal(res.headers.get("access-control-allow-origin"), "*");
  assert.equal(res.json.status, "ok");
  assert.equal(res.json.version, "2.0.0");
  assert.equal(res.json.agents, 8);
  assert.equal(typeof res.json.uptime_ms, "number");
  assert.ok(res.json.uptime_ms >= 0);
});

test("GET /api/languages lists all 9 source languages plus target variants", async () => {
  const res = await request("/api/languages");
  assert.equal(res.status, 200);
  assert.ok(Array.isArray(res.json.languages));
  assert.ok(res.json.languages.length >= 9);
  const codes = res.json.languages.map((lang) => lang.code);
  for (const expected of ["EN", "DE", "FR", "ES", "IT", "PT", "HI", "JA", "ZH"]) {
    assert.ok(codes.includes(expected), `missing language ${expected}`);
  }
  for (const lang of res.json.languages) {
    assert.equal(typeof lang.code, "string");
    assert.equal(typeof lang.name, "string");
    assert.ok(lang.code.length >= 2 && lang.name.length > 0);
  }
  assert.ok(Array.isArray(res.json.detectable));
  assert.equal(res.json.detectable.length, 9);
});

test("GET /api/agents exposes 8 unique manifest entries", async () => {
  const res = await request("/api/agents");
  assert.equal(res.status, 200);
  assert.equal(res.json.count, 8);
  assert.ok(Array.isArray(res.json.agents));
  assert.equal(res.json.agents.length, 8);
  const ids = res.json.agents.map((agent) => agent.id);
  assert.equal(new Set(ids).size, 8);
  for (const expected of ["detector", "translator", "corrector", "quality-guard", "security"]) {
    assert.ok(ids.includes(expected), `missing agent ${expected}`);
  }
  for (const agent of res.json.agents) {
    assert.equal(typeof agent.id, "string");
    assert.ok(agent.id.length > 0);
    assert.equal(typeof agent.name, "string");
    assert.equal(typeof agent.description, "string");
    assert.equal(agent.version, "2.0.0");
  }
});

/* ------------------------------------------------------------------ *
 * Translation
 * ------------------------------------------------------------------ */

test("POST /api/translate local EN→DE returns the documented shape", async () => {
  const res = await request("/api/translate", {
    method: "POST",
    body: {
      text: "Hello world. How are you today?",
      source_lang: "EN",
      target_lang: "DE",
    },
  });
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type") ?? "", /^application\/json/);
  const body = res.json;
  assert.equal(typeof body.text, "string");
  assert.ok(body.text.trim().length > 0);
  assert.equal(body.provider, "local");
  assert.ok(typeof body.detected_source_language === "string");
  assert.match(body.detected_source_language, /^[a-z]{2}$/);
  assert.equal(typeof body.coverage, "number");
  assert.ok(body.coverage >= 0 && body.coverage <= 1, `coverage ${body.coverage}`);
  assert.ok(Array.isArray(body.notes));
  assert.equal(typeof body.latency_ms, "number");
  assert.ok(Array.isArray(body.agent_trace));
  assert.ok(body.agent_trace.length >= 6, `trace length ${body.agent_trace.length}`);
  for (const step of body.agent_trace) {
    assert.equal(typeof step.agent, "string");
    assert.ok(step.agent.length > 0);
    assert.equal(typeof step.decision, "string");
    assert.ok(step.decision.length > 0);
    assert.equal(typeof step.ms, "number");
    assert.ok(step.ms >= 0);
  }
  const agents = new Set(body.agent_trace.map((step) => step.agent));
  for (const expected of ["security", "detector", "translator", "quality-guard"]) {
    assert.ok(agents.has(expected), `missing trace agent ${expected}`);
  }
});

test("POST /api/translate applies glossary target terms", async () => {
  const created = await request("/api/glossary", {
    method: "POST",
    body: { name: `server-glossary-${Date.now()}` },
  });
  assert.equal(created.status, 200);
  const id = created.json.id;
  createdGlossaries.add(id);

  const added = await request(`/api/glossary/${id}/entries`, {
    method: "POST",
    body: {
      source_term: "Hello",
      target_term: "Moin",
      source_lang: "EN",
      target_lang: "DE",
    },
  });
  assert.equal(added.status, 200);
  assert.equal(added.json.entry.target_term, "Moin");

  const res = await request("/api/translate", {
    method: "POST",
    body: {
      text: "Hello world",
      source_lang: "EN",
      target_lang: "DE",
      glossary_id: id,
    },
  });
  assert.equal(res.status, 200);
  assert.match(res.json.text, /Moin/, `glossary target missing: ${res.json.text}`);
  assert.doesNotMatch(res.json.text, /⟦/, "placeholder leaked into output");

  const steps = res.json.agent_trace.filter((step) => step.agent === "glossary-enforcer");
  assert.equal(steps.length, 2, "expected pre and post glossary trace entries");
  assert.ok(Number(steps[0].fields?.terms ?? 0) >= 1, JSON.stringify(steps[0]));
  assert.ok(Number(steps[1].fields?.hits ?? 0) >= 1, JSON.stringify(steps[1]));
});

test("POST /api/translate provider=deepl without a key returns 400 no_key", async () => {
  const res = await request("/api/translate", {
    method: "POST",
    body: { text: "Hello", target_lang: "DE", provider: "deepl" },
  });
  assert.equal(res.status, 400);
  assert.equal(res.json.error, "no_key");
});

test("POST /api/translate validates text and target language", async () => {
  const noText = await request("/api/translate", {
    method: "POST",
    body: { target_lang: "DE" },
  });
  assert.equal(noText.status, 400);
  assert.equal(noText.json.error, "missing_text");

  const noTarget = await request("/api/translate", {
    method: "POST",
    body: { text: "Hello" },
  });
  assert.equal(noTarget.status, 400);
  assert.equal(noTarget.json.error, "missing_target_lang");
});

/* ------------------------------------------------------------------ *
 * Detection / writing
 * ------------------------------------------------------------------ */

test("POST /api/detect returns lang, confidence and status", async () => {
  const res = await request("/api/detect", {
    method: "POST",
    body: { text: "This is a longer English sentence used to test detection." },
  });
  assert.equal(res.status, 200);
  assert.equal(res.json.lang, "en");
  assert.equal(typeof res.json.confidence, "number");
  assert.ok(res.json.confidence >= 0 && res.json.confidence <= 1);
  assert.ok(
    ["success", "insufficient_confidence", "no_language_detected"].includes(res.json.status),
    `unexpected status ${res.json.status}`,
  );
  assert.equal(typeof res.json.scores, "object");
});

test("POST /api/write local correct returns corrected text and a diff", async () => {
  const input = "teh world is definately good";
  const res = await request("/api/write", {
    method: "POST",
    body: { text: input, mode: "correct" },
  });
  assert.equal(res.status, 200);
  assert.equal(res.json.provider, "local");
  assert.equal(res.json.original, input);
  assert.equal(typeof res.json.corrected, "string");
  assert.match(res.json.corrected, /definitely/);
  assert.doesNotMatch(res.json.corrected.toLowerCase(), /\bteh\b/);
  assert.ok(Array.isArray(res.json.diff));
  assert.ok(res.json.diff.length > 0);
  for (const part of res.json.diff) {
    assert.ok(["eq", "del", "ins"].includes(part.kind), `bad diff kind ${part.kind}`);
    assert.equal(typeof part.value, "string");
  }
  assert.ok(Array.isArray(res.json.changes));
  assert.ok(res.json.changes.length >= 2);
  assert.equal(typeof res.json.latency_ms, "number");
});

test("POST /api/write local rephrase applies the business style", async () => {
  const input = "I won't go to the meeting because it is not good.";
  const res = await request("/api/write", {
    method: "POST",
    body: { text: input, mode: "rephrase", style: "business" },
  });
  assert.equal(res.status, 200);
  assert.equal(res.json.provider, "local");
  assert.equal(typeof res.json.corrected, "string");
  assert.match(res.json.corrected, /will not/);
  assert.ok(Array.isArray(res.json.diff) && res.json.diff.length > 0);
  assert.ok(Array.isArray(res.json.changes));
  assert.ok(res.json.changes.some((change) => change.type === "style"));
});

/* ------------------------------------------------------------------ *
 * Glossary CRUD
 * ------------------------------------------------------------------ */

test("glossary CRUD roundtrip: create, add entry, list, detail, delete 204", async () => {
  const name = `crud-glossary-${Date.now()}`;
  const created = await request("/api/glossary", { method: "POST", body: { name } });
  assert.equal(created.status, 200);
  assert.equal(typeof created.json.id, "string");
  assert.ok(created.json.id.length > 0);
  const id = created.json.id;
  createdGlossaries.add(id);

  const added = await request(`/api/glossary/${id}/entries`, {
    method: "POST",
    body: {
      source_term: "team",
      target_term: "Mannschaft",
      source_lang: "EN",
      target_lang: "DE",
    },
  });
  assert.equal(added.status, 200);
  assert.equal(added.json.ok, true);
  assert.equal(added.json.entry.source_term, "team");
  assert.equal(added.json.entry.target_term, "Mannschaft");

  const list = await request("/api/glossary");
  assert.equal(list.status, 200);
  assert.ok(Array.isArray(list.json.glossaries));
  const listed = list.json.glossaries.find((store) => store.id === id);
  assert.ok(listed, "created glossary missing from the list");
  assert.equal(listed.name, name);
  assert.equal(listed.entries.length, 1);

  const detail = await request(`/api/glossary/${id}`);
  assert.equal(detail.status, 200);
  assert.equal(detail.json.id, id);
  assert.equal(detail.json.entries.length, 1);
  assert.equal(detail.json.entries[0].target_term, "Mannschaft");

  const missing = await request("/api/glossary/does-not-exist");
  assert.equal(missing.status, 404);
  assert.equal(missing.json.error, "glossary_not_found");

  const deleted = await request(`/api/glossary/${id}`, { method: "DELETE" });
  assert.equal(deleted.status, 204);
  assert.equal(deleted.text, "");
  createdGlossaries.delete(id);

  const gone = await request(`/api/glossary/${id}`);
  assert.equal(gone.status, 404);
  const deletedAgain = await request(`/api/glossary/${id}`, { method: "DELETE" });
  assert.equal(deletedAgain.status, 404);
});

/* ------------------------------------------------------------------ *
 * Documents
 * ------------------------------------------------------------------ */

test("POST /api/document translates the hello.txt fixture", async () => {
  const contentBase64 = fs.readFileSync(HELLO_FIXTURE).toString("base64");
  const res = await request("/api/document", {
    method: "POST",
    body: {
      filename: "hello.txt",
      content_base64: contentBase64,
      target_lang: "DE",
    },
  });
  assert.equal(res.status, 200);
  assert.equal(res.json.filename, "hello-translated.txt");
  assert.equal(res.json.kind, "txt");
  assert.equal(typeof res.json.text, "string");
  assert.ok(res.json.text.trim().length > 0);
  assert.ok(Array.isArray(res.json.segments));
  assert.ok(res.json.segments.length >= 1);
  for (const segment of res.json.segments) {
    assert.equal(typeof segment.source, "string");
    assert.equal(typeof segment.target, "string");
  }
  assert.equal(res.json.meta.kind, "txt");
  assert.equal(typeof res.json.latency_ms, "number");
});

test("POST /api/document rejects invalid base64 with a 400", async () => {
  const res = await request("/api/document", {
    method: "POST",
    body: {
      filename: "broken.txt",
      content_base64: "!!!!not-base64!!!!",
      target_lang: "DE",
    },
  });
  assert.equal(res.status, 400);
  assert.match(res.headers.get("content-type") ?? "", /^application\/json/);
  assert.equal(res.json.error, "invalid_content_base64");
});

/* ------------------------------------------------------------------ *
 * Voice export
 * ------------------------------------------------------------------ */

const VOICE_SEGMENTS = [
  { startMs: 0, endMs: 1500, text: "Hello" },
  { startMs: 2000, endMs: 3600250, text: "World" },
];

test("POST /api/voice/export builds SRT with comma milliseconds and cue indexes", async () => {
  const res = await request("/api/voice/export", {
    method: "POST",
    body: { segments: VOICE_SEGMENTS, format: "srt" },
  });
  assert.equal(res.status, 200);
  assert.equal(res.json.format, "srt");
  const content = res.json.content;
  assert.ok(
    content.startsWith("1\n00:00:00,000 --> 00:00:01,500\nHello\n\n"),
    JSON.stringify(content),
  );
  assert.ok(content.includes("2\n00:00:02,000 --> 01:00:00,250\nWorld"));
  assert.ok(!content.includes("00:00:01.500"), "SRT must use comma milliseconds");
});

test("POST /api/voice/export builds WebVTT with the WEBVTT header and dots", async () => {
  const res = await request("/api/voice/export", {
    method: "POST",
    body: { segments: VOICE_SEGMENTS, format: "vtt" },
  });
  assert.equal(res.status, 200);
  assert.equal(res.json.format, "vtt");
  const content = res.json.content;
  assert.equal(content.indexOf("WEBVTT"), 0);
  assert.ok(content.includes("00:00:00.000 --> 00:00:01.500"));
  assert.ok(content.includes("01:00:00.250"));
  assert.ok(!content.includes("00:00:01,500"), "VTT must use dot milliseconds");
});

test("POST /api/voice/export builds TXT and JSON transcripts", async () => {
  const txt = await request("/api/voice/export", {
    method: "POST",
    body: { segments: VOICE_SEGMENTS, format: "txt" },
  });
  assert.equal(txt.status, 200);
  assert.equal(txt.json.content, "Hello\nWorld\n");

  const json = await request("/api/voice/export", {
    method: "POST",
    body: { segments: VOICE_SEGMENTS, format: "json" },
  });
  assert.equal(json.status, 200);
  const parsed = JSON.parse(json.json.content);
  assert.equal(parsed.length, 2);
  assert.deepEqual(parsed[0], { index: 1, startMs: 0, endMs: 1500, text: "Hello" });
  assert.equal(parsed[1].endMs, 3600250);
});

/* ------------------------------------------------------------------ *
 * Key hygiene
 * ------------------------------------------------------------------ */

test("POST /api/deepl/validate rejects a malformed key locally", async () => {
  const res = await request("/api/deepl/validate", {
    method: "POST",
    body: { key: "too-short-key" },
  });
  assert.equal(res.status, 400);
  assert.equal(res.json.valid, false);
  assert.equal(typeof res.json.reason, "string");
  assert.ok(!res.text.includes("too-short-key"));
});

/* ------------------------------------------------------------------ *
 * Static files, 404s, traversal and CORS
 * ------------------------------------------------------------------ */

test("GET /api/nope returns JSON 404", async () => {
  const res = await request("/api/nope");
  assert.equal(res.status, 404);
  assert.match(res.headers.get("content-type") ?? "", /^application\/json/);
  assert.equal(res.json.error, "not_found");
});

test("GET / serves the app shell and GET /styles.css serves CSS", async () => {
  const index = await request("/");
  assert.equal(index.status, 200);
  assert.match(index.headers.get("content-type") ?? "", /^text\/html/);
  assert.ok(index.text.includes('<div id="app">'), "app shell missing");

  const css = await request("/styles.css");
  assert.equal(css.status, 200);
  assert.match(css.headers.get("content-type") ?? "", /^text\/css/);
  assert.ok(css.text.length > 0);
});

test("path traversal attempts never expose package.json", async () => {
  for (const rawPath of [
    "/../package.json",
    "/js/../../package.json",
    "/engine/../../package.json",
    "/%2e%2e/package.json",
  ]) {
    const res = await rawGet(rawPath);
    assert.equal(res.status, 404, `${rawPath} returned ${res.status}`);
    assert.ok(!res.body.includes('"name"'), `${rawPath} leaked package.json`);
    assert.ok(!res.body.includes("talkflow2"), `${rawPath} leaked package.json`);
  }
});

test("OPTIONS /api/translate returns 204 with CORS headers", async () => {
  const res = await fetch(`${baseUrl}/api/translate`, { method: "OPTIONS" });
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("access-control-allow-origin"), "*");
  assert.match(res.headers.get("access-control-allow-methods") ?? "", /DELETE/);
  assert.match(res.headers.get("access-control-allow-headers") ?? "", /X-Deepl-Key/i);
  assert.equal(await res.text(), "");
});

test("local translate never echoes a supplied DeepL key in response or log", async () => {
  const fakeKey = "talkflow-test-key-not-real-000000000000:fx";
  const captured = [];
  const originalLog = console.log;
  console.log = (...args) => {
    captured.push(args.map((arg) => String(arg)).join(" "));
  };

  let res;
  try {
    res = await request("/api/translate", {
      method: "POST",
      headers: { "X-Deepl-Key": fakeKey },
      body: { text: "Hello", source_lang: "EN", target_lang: "DE", provider: "local" },
    });
    // The request logger runs in the router's `finally`, right after res.end().
    await new Promise((resolve) => setTimeout(resolve, 25));
  } finally {
    console.log = originalLog;
  }

  assert.equal(res.status, 200);
  assert.ok(!res.text.includes(fakeKey), "response body leaked the raw key");
  assert.ok(!JSON.stringify(res.json).includes(fakeKey));

  assert.ok(captured.length > 0, "expected at least one server log line");
  const logText = captured.join("\n");
  assert.ok(!logText.includes(fakeKey), "server log leaked the raw key");
  assert.ok(logText.includes("key="), "masked key marker missing from the log");
  assert.ok(logText.includes("ta…fx"), "log should contain the maskKey() form");
});
