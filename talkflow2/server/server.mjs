/**
 * TalkFlow 2.0 — HTTP server (owned by build-server).
 *
 * Pure `node:http` + `node:url` + `node:path` + `node:fs`. ESM. Zero npm deps.
 * The whole engine surface is imported through the single aggregate `engine/engine.mjs`
 * (see SPEC.md — engine re-exports every symbol named below).
 *
 * Glossary persistence lives here (SPEC): `../data/glossaries.json`, mkdir on write,
 * loaded at boot, tolerant to a missing/corrupt file.
 */

import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

import {
  Coordinator,
  makeLocalCoordinator,
  AGENT_MANIFEST,
  VERSION,
  detectLanguage,
  extractText,
  chunkSentences,
  translateDocument,
  validateKeyFormat,
  maskKey,
  redactKeys,
  translate as deeplTranslate,
  usage as deeplUsage,
  writeCorrect as deeplWriteCorrect,
  writeRephrase as deeplWriteRephrase,
  hostFor,
} from "../engine/engine.mjs";

/* ------------------------------------------------------------------ *
 * Fixed paths / constants
 * ------------------------------------------------------------------ */

const HERE_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(HERE_DIR, ".."); // talkflow2 root
const APP_DIR = path.join(ROOT_DIR, "app");
const ENGINE_DIR = path.join(ROOT_DIR, "engine");
const DATA_DIR = path.join(ROOT_DIR, "data");
const DATA_FILE = path.join(DATA_DIR, "glossaries.json");

const BODY_CAP_BYTES = 10 * 1024 * 1024; // JSON body cap: 10 MB → else 413
const DOC_CAP_BYTES = 5 * 1024 * 1024;   // decoded document cap: 5 MB → else 413
const BOOT_TS = Date.now();
const DEFAULT_PORT = 8096;

const LANGUAGES = [
  { code: "EN", name: "English" },
  { code: "DE", name: "German" },
  { code: "FR", name: "French" },
  { code: "ES", name: "Spanish" },
  { code: "IT", name: "Italian" },
  { code: "PT", name: "Portuguese" },
  { code: "HI", name: "Hindi" },
  { code: "JA", name: "Japanese" },
  { code: "ZH", name: "Chinese" },
];
const TARGET_EXTRA = [
  { code: "EN-US", name: "English (American)" },
  { code: "EN-GB", name: "English (British)" },
  { code: "PT-BR", name: "Portuguese (Brazilian)" },
  { code: "PT-PT", name: "Portuguese (European)" },
];
const LANGUAGE_LIST = [...LANGUAGES, ...TARGET_EXTRA];
const LANGUAGE_LOOKUP = new Map(LANGUAGE_LIST.map((l) => [l.code.toLowerCase(), l.code]));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
};

const SUPPORTED_LANG_CODES = new Set([...LANGUAGES.map((l) => l.code), "EN-US", "EN-GB", "PT-BR", "PT-PT"]);

/* ------------------------------------------------------------------ *
 * Small helpers
 * ------------------------------------------------------------------ */

class HttpError extends Error {
  constructor(status, payload) {
    super(`talkflow_http_error_${status}`);
    this.status = status;
    this.payload = payload && typeof payload === "object" ? payload : { error: String(payload) };
  }
}

function fail(status, error, extra) {
  throw new HttpError(status, extra ? { error, ...extra } : { error });
}

function coerceNumber(v, fallback = 0) {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** maskKey() surrogate that never throws and never returns a raw key. */
function maskKeySafe(key) {
  try {
    if (!key) return null;
    const m = maskKey ? maskKey(key) : "…";
    return m && !m.includes(key) ? m : "…";
  } catch {
    return "…";
  }
}

/** Header-only DeepL key accessor (never the JSON body). */
function keyFromHeader(req) {
  const v = req.headers["x-deepl-key"];
  const s = Array.isArray(v) ? v[0] : v;
  return typeof s === "string" && s.trim() ? s.trim() : null;
}

function envKey() {
  const v = process.env.DEEPL_API_KEY;
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/** Key for validate/usage endpoints: body {key} → header → env fallback (SPEC). */
function keyFromBodyHeaderEnv(body, req) {
  if (body && typeof body.key === "string" && body.key.trim()) return body.key.trim();
  return keyFromHeader(req) ?? envKey();
}

function hostForKey(key) {
  const chk = validateKeyFormat(key);
  if (chk?.host) return chk.host;
  try {
    return hostFor(key) ?? "api-free.deepl.com";
  } catch {
    return "api-free.deepl.com";
  }
}

/** Resolve any source/target language token to a DeepL-style uppercase code. */
function langCode(value, fallback = null) {
  if (typeof value !== "string" || !value.trim()) return fallback;
  const v = value.trim();
  const upper = v.toUpperCase();
  if (SUPPORTED_LANG_CODES.has(upper)) return upper;
  if (/^[A-Z]{2}([-_][A-Z]{2})?$/.test(upper)) return upper.replace("_", "-");
  return LANGUAGE_LOOKUP.get(v.toLowerCase()) ?? fallback;
}

function anyFormality(v) {
  return typeof v === "string" && v.trim() ? v.trim() : "default";
}

/* ------------------------------------------------------------------ *
 * Glossary persistence (server-side, per SPEC)
 * ------------------------------------------------------------------ */

class ServerGlossaryStore {
  constructor(file = DATA_FILE) {
    this.file = file;
    this.stores = [];
    this.nextId = 1;
  }

  async load() {
    try {
      const raw = await fs.promises.readFile(this.file, "utf8");
      const parsed = JSON.parse(raw);
      const list = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.stores) ? parsed.stores : null;
      if (list) {
        this.stores = list.map((s) => this.#normalize(s)).filter((s) => s.id);
        this.nextId =
          coerceNumber(parsed?.nextId, 0) > 0
            ? Math.floor(parsed.nextId)
            : this.#maxId() + 1;
      }
    } catch {
      /* tolerant to missing/corrupt file at boot */
    }
  }

  async save() {
    try {
      await fs.promises.mkdir(path.dirname(this.file), { recursive: true });
      await fs.promises.writeFile(
        this.file,
        JSON.stringify({ nextId: this.nextId, stores: this.stores }, null, 2),
        "utf8"
      );
    } catch {
      /* persistence must never break the API */
    }
  }

  #normalize(s) {
    const entries = Array.isArray(s?.entries) ? s.entries : [];
    return {
      id: String(s?.id ?? ""),
      name: String(s?.name ?? ""),
      entries: entries
        .map((e) => ({
          source_term: String(e?.source_term ?? e?.sourceTerm ?? ""),
          target_term: String(e?.target_term ?? e?.targetTerm ?? ""),
          source_lang: langCode(e?.source_lang ?? e?.sourceLang, "EN") ?? "EN",
          target_lang: langCode(e?.target_lang ?? e?.targetLang, "DE") ?? "DE",
        }))
        .filter((e) => e.source_term && e.target_term),
    };
  }

  #maxId() {
    return this.stores.reduce((m, s) => Math.max(m, Number.parseInt(s.id, 10) || 0), 0);
  }

  create(name) {
    const id = String(this.nextId++);
    this.stores.push({ id, name: String(name).trim(), entries: [] });
    void this.save();
    return id;
  }

  remove(id) {
    const i = this.stores.findIndex((s) => s.id === String(id));
    if (i < 0) return false;
    this.stores.splice(i, 1);
    void this.save();
    return true;
  }

  clearAll() {
    const removed = this.stores.length;
    this.stores = [];
    void this.save();
    return removed;
  }

  get(id) {
    return this.stores.find((s) => s.id === String(id)) ?? null;
  }

  list() {
    return this.stores.map((s) => ({ id: s.id, name: s.name, entries: s.entries.slice() }));
  }

  add(id, entry) {
    const st = this.get(id);
    if (!st) return null;
    const e = {
      source_term: String(entry?.source_term ?? entry?.sourceTerm ?? "").trim(),
      target_term: String(entry?.target_term ?? entry?.targetTerm ?? "").trim(),
      source_lang: langCode(entry?.source_lang ?? entry?.sourceLang, "EN") ?? "EN",
      target_lang: langCode(entry?.target_lang ?? entry?.targetLang, "DE") ?? "DE",
    };
    if (!e.source_term || !e.target_term) return null;
    st.entries.push(e);
    void this.save();
    return e;
  }
}

const glossaryStore = new ServerGlossaryStore();
/** Local-provider coordinator wired to the persisted glossary store. */
const coordinator = new Coordinator({ store: glossaryStore });

const usageCounters = { charsToday: 0, translations: 0, corrections: 0 };

/* ------------------------------------------------------------------ *
 * HTTP plumbing: CORS, JSON body, send
 * ------------------------------------------------------------------ */

function applyCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Deepl-Key, Authorization");
  res.setHeader("Access-Control-Max-Age", "600");
}

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload ?? {});
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

async function readJsonBody(req) {
  const declared = Number(req.headers["content-length"] ?? 0);
  if (Number.isFinite(declared) && declared > BODY_CAP_BYTES) {
    req.resume(); // drain so the client can finish writing
    fail(413, "body_too_large", { limit_bytes: BODY_CAP_BYTES });
  }

  const chunks = [];
  let total = 0;
  let overflow = false;
  await new Promise((resolve, reject) => {
    req.on("data", (c) => {
      if (overflow) return;
      total += c.length;
      if (total > BODY_CAP_BYTES) {
        overflow = true;
        req.resume(); // keep draining, we no longer need the data
        reject(new HttpError(413, { error: "body_too_large", limit_bytes: BODY_CAP_BYTES }));
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve());
    req.on("error", (e) => reject(e));
  });

  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw.trim()) return {};
  try {
    return JSON.parse(raw);
  } catch {
    fail(400, "invalid_json");
  }
}

/* ------------------------------------------------------------------ *
 * DeepL error mapping → 456 / 429 / 503 passthrough {error, provider}
 * ------------------------------------------------------------------ */

function mapDeeplErrorStatus(err) {
  const raw = err?.httpStatus ?? err?.status ?? err?.statusCode ?? null;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    if (raw === 429 || raw === 456 || raw === 503) return raw; // passthrough
    if (raw >= 400 && raw <= 599) return raw; // engine-preserved HTTP status
    return 503;
  }
  const s = String(raw ?? "").toLowerCase();
  if (s.includes("quota") || s === "456") return 456;
  if (s.includes("throttl") || s === "429" || s.includes("429")) return 429;
  if (s.includes("auth") || s.includes("invalid") || s.includes("key")) return 403;
  return 503;
}

function rethrowDeeplError(err) {
  const status = mapDeeplErrorStatus(err);
  const rawMsg =
    typeof err === "string" ? err : err?.error ?? err?.message ?? "deepl_error";
  const detail = typeof err?.status === "string" ? err.status : typeof err?.phrase === "string" ? err.phrase : null;
  fail(status, redactKeys(String(rawMsg)).slice(0, 300) || "deepl_error", {
    provider: "deepl",
    ...(detail ? { upstream_status: detail } : {}),
  });
}

/* ------------------------------------------------------------------ *
 * Engine payload shapers (tolerant to camel/snake variants)
 * ------------------------------------------------------------------ */

function extractTranslation(deeplResponse) {
  let tr = null;
  if (deeplResponse && Array.isArray(deeplResponse.translations) && deeplResponse.translations.length) {
    tr = deeplResponse.translations[0];
  } else if (
    deeplResponse &&
    (typeof deeplResponse.text === "string" || typeof deeplResponse.detected_source_language === "string")
  ) {
    tr = deeplResponse;
  } else if (typeof deeplResponse === "string") {
    tr = { text: deeplResponse };
  }
  return {
    text: String(tr?.text ?? ""),
    detected_source_language: String(tr?.detected_source_language ?? tr?.detectedSourceLanguage ?? ""),
  };
}

/** Pull a usable "corrected" string out of a DeepL Write response or engine result. */
function extractCorrected(resp, fallback) {
  if (resp == null) return fallback;
  if (typeof resp === "string") return resp;
  if (typeof resp.corrected === "string") return resp.corrected;
  if (typeof resp.improvement_text === "string") return resp.improvement_text;
  if (typeof resp.text === "string") return resp.text;
  if (Array.isArray(resp.improvements) && resp.improvements.length) {
    const first = resp.improvements[0];
    if (typeof first === "string") return first;
    if (typeof first?.corrected === "string") return first.corrected;
    if (typeof first?.s !== "undefined") {
      let rebuilt = "";
      for (const seg of Array.isArray(first.s) ? first.s : [first.s]) {
        if (typeof seg === "string") rebuilt += seg;
        else if (seg && typeof seg === "object") rebuilt += typeof seg.to === "string" && seg.to ? seg.to : String(seg.value ?? "");
      }
      if (rebuilt) return rebuilt;
    }
  }
  return fallback;
}

async function liveUsageOrNull(key) {
  if (!key) return null;
  const chk = validateKeyFormat(key);
  if (!chk?.valid) return { live_check: "failed", reason: "invalid_key_format" };
  try {
    const u = await deeplUsage({ key });
    const live = {
      character_count: coerceNumber(u?.character_count, 0),
      character_limit: coerceNumber(u?.character_limit, 0),
      tier: chk.tier ?? null,
      host: chk.host ?? null,
    };
    if (u && typeof u.live_check !== "undefined") live.live_check = u.live_check;
    return live;
  } catch {
    return { live_check: "failed" };
  }
}

/* ------------------------------------------------------------------ *
 * Document translation helpers
 * ------------------------------------------------------------------ */

function kindFromFilename(filename) {
  const m = String(filename ?? "").match(/\.([A-Za-z0-9]+)$/);
  const ext = (m?.[1] ?? "txt").toLowerCase();
  return ["pdf", "txt", "html", "md", "srt", "vtt", "json"].includes(ext) ? ext : "txt";
}

function translatedFilename(filename) {
  const base = String(filename ?? "document").replace(/\.[^.]*$/, "");
  const ext = ((String(filename ?? "").match(/\.([A-Za-z0-9]+)$/)?.[1]) ?? "txt").toLowerCase();
  return `${base}-translated.${ext}`;
}

/** Sequential chunk translator driven by the local Coordinator pipeline. */
async function translateChunkSequentially(chunk, targetLang, coord) {
  const rr = await coord.runTranslate({
    text: String(chunk ?? ""),
    sourceLang: "auto",
    targetLang,
    formality: "default",
    context: "",
    glossaryId: null,
  });
  return String(rr?.result?.text ?? "");
}

/* ------------------------------------------------------------------ *
 * Voice export formatting (server-side SRT/VTT/TXT/JSON builders)
 * ------------------------------------------------------------------ */

function hhmmss(totalMs) {
  const ms = Math.max(0, Math.round(coerceNumber(totalMs, 0)));
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const mmm = ms % 1000;
  const p = (n, w) => String(n).padStart(w, "0");
  return `${p(h, 2)}:${p(m, 2)}:${p(s, 2)}.${p(mmm, 3)}`;
}

function segmentText(s) {
  if (!s || typeof s !== "object") return "";
  if (typeof s.text === "string" && s.text.trim()) return s.text;
  const pairs = Array.isArray(s.sourceTargetPairs) ? s.sourceTargetPairs : null;
  if (pairs && pairs.length) {
    return pairs
      .map((p) => [typeof p?.source === "string" ? p.source : null, typeof p?.target === "string" ? p.target : null].filter(Boolean).join(" → ") || p?.target || p?.source || "")
      .filter(Boolean)
      .join("\n");
  }
  return [typeof s?.source === "string" ? s.source : "", typeof s?.target === "string" ? s.target : ""].filter(Boolean).join(" → ");
}

function buildVoiceExport(segments, format) {
  const norm = segments.map((s, i) => ({
    index: i + 1,
    startMs: coerceNumber(s?.startMs ?? s?.start_ms, 0),
    endMs: coerceNumber(
      s?.endMs ?? s?.end_ms,
      (coerceNumber(s?.startMs ?? s?.start_ms, 0) + 1200)
    ),
    text: segmentText(s).trim(),
  }));
  if (format === "json") return JSON.stringify(norm, null, 2);
  if (format === "txt") return norm.filter((s) => s.text).map((s) => s.text).join("\n") + (norm.some((s) => s.text) ? "\n" : "");
  const sep = format === "vtt" ? "." : ",";
  const blocks = norm.map((s) => {
    const times = `${hhmmss(s.startMs).replace(".", sep)} --> ${hhmmss(s.endMs).replace(".", sep)}`;
    return `${format === "srt" ? `${s.index}\n` : ""}${times}\n${s.text}`;
  });
  const head = format === "vtt" ? "WEBVTT\n\n" : "";
  return head + blocks.join("\n\n") + (blocks.length ? "\n\n" : "");
}

/* ------------------------------------------------------------------ *
 * Request router
 * ------------------------------------------------------------------ */

function resolveStaticPath(pathname) {
  let targetBase = null;
  let rel = null;

  if (pathname === "/" || pathname === "/index.html") {
    targetBase = APP_DIR;
    rel = "index.html";
  } else if (pathname === "/styles.css") {
    targetBase = APP_DIR;
    rel = "styles.css";
  } else if (pathname === "/styles.css.map") {
    targetBase = APP_DIR;
    rel = "styles.css.map";
  } else if (pathname.startsWith("/js/")) {
    targetBase = path.join(APP_DIR, "js");
    rel = pathname.slice("/js/".length);
  } else if (pathname.startsWith("/engine/")) {
    targetBase = ENGINE_DIR;
    rel = pathname.slice("/engine/".length);
  } else {
    return null;
  }

  // path traversal guard: no ".." components, no backslashes, must stay inside base
  if (!rel || rel.includes("..") || rel.includes("\\") || path.isAbsolute(rel)) return null;
  const resolved = path.resolve(targetBase, rel);
  if (resolved !== targetBase && !resolved.startsWith(targetBase + path.sep)) return null;
  return resolved;
}

async function serveStatic(res, method, targetPath, started, pathname) {
  if (method !== "GET" && method !== "HEAD") {
    sendJson(res, 405, { error: "method_not_allowed" });
    return 405;
  }
  try {
    const data = await fs.promises.readFile(targetPath);
    const mime = MIME[path.extname(targetPath).toLowerCase()] ?? "application/octet-stream";
    res.writeHead(200, {
      "Content-Type": mime,
      "Content-Length": data.length,
      "Cache-Control": "no-cache",
    });
    res.end(method === "HEAD" ? undefined : data);
    return 200;
  } catch (err) {
    const status = err?.code === "ENOENT" ? 404 : 405;
    res.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", "Content-Length": 9 });
    res.end(status === 404 ? "Not found" : "Forbidden");
    return status;
  } finally {
    logRequestStartedAt(pathname, started);
  }
}

function noteLatency(started) {
  return Date.now() - started;
}

/* ------------------------------------------------------------------ */

async function handleApi(req, res, pathname, started) {
  const method = req.method ?? "GET";
  const parts = pathname.replace(/^\/api\/?/, "").split("/").filter(Boolean);
  const [section, ...rest] = parts;

  /* ---------------- agents / health / languages / usage counters ---- */

  if (section === "health" && method === "GET") {
    sendJson(res, 200, {
      status: "ok",
      version: String(VERSION ?? "2.0.0"),
      uptime_ms: Date.now() - BOOT_TS,
      agents: Array.isArray(AGENT_MANIFEST) ? AGENT_MANIFEST.length : 0,
    });
    return;
  }

  if (section === "agents" && method === "GET") {
    const manifest = Array.isArray(AGENT_MANIFEST) ? AGENT_MANIFEST : [AGENT_MANIFEST].filter(Boolean);
    sendJson(res, 200, { agents: manifest, count: manifest.length, version: String(VERSION ?? "2.0.0") });
    return;
  }

  if (section === "languages" && method === "GET") {
    sendJson(res, 200, { languages: [...LANGUAGE_LIST], detectable: [...LANGUAGES] });
    return;
  }

  if (section === "usage" && method === "GET") {
    const liveKey = keyFromHeader(req) ?? envKey();
    const live = liveKey ? await liveUsageOrNull(liveKey) : null;
    sendJson(res, 200, {
      local: {
        chars_today: usageCounters.charsToday,
        translations: usageCounters.translations,
        corrections: usageCounters.corrections,
      },
      ...(live ? { live } : {}),
    });
    return;
  }

  /* ---------------- /api/detect ------------------------------------ */

  if (section === "detect" && method === "POST") {
    const body = await readJsonBody(req);
    const text = typeof body.text === "string" ? body.text : "";
    if (!text.trim()) fail(400, "missing_text");
    const d = detectLanguage(text);
    sendJson(res, 200, {
      lang: String(d?.lang ?? ""),
      confidence: coerceNumber(d?.confidence, 0),
      status: String(d?.status ?? "success"),
      scores: d?.scores && typeof d.scores === "object" ? d.scores : {},
    });
    return;
  }

  /* ---------------- /api/translate --------------------------------- */

  if (section === "translate" && method === "POST") {
    const body = await readJsonBody(req);
    const text = typeof body.text === "string" ? body.text : "";
    if (!text.trim()) fail(400, "missing_text");
    const provider = typeof body.provider === "string" && body.provider.trim() ? body.provider.trim().toLowerCase() : "local";
    const targetLang = langCode(body.target_lang ?? body.targetLang, null);
    if (!targetLang) fail(400, "missing_target_lang");
    const sourceLang = langCode(body.source_lang ?? body.sourceLang, "AUTO") ?? "AUTO";
    const formality = anyFormality(body.formality ?? body.writing_style);
    const context = typeof body.context === "string" ? body.context : "";
    const glossaryId = body.glossary_id == null ? null : String(body.glossary_id);

    if (provider === "deepl") {
      const key = keyFromHeader(req) ?? envKey();
      if (!key) fail(400, "no_key");
      const chk = validateKeyFormat(key);
      if (!chk?.valid) fail(400, "invalid_key", { reason: chk?.reason ?? null });
      try {
        const out = await deeplTranslate({
          key,
          host: hostForKey(key),
          text,
          targetLang,
          sourceLang: sourceLang === "AUTO" ? undefined : sourceLang,
          formality,
          context,
        });
        const t = extractTranslation(out);
        sendJson(res, 200, {
          text: t.text,
          detected_source_language: t.detected_source_language,
          provider: "deepl",
          latency_ms: noteLatency(started),
          chars_billed: coerceNumber(
            out?.chars_billed ?? out?.billed_characters,
            text.length
          ),
        });
        usageCounters.translations += 1;
      } catch (err) {
        rethrowDeeplError(err);
      }
      return;
    }

    const r = await coordinator.runTranslate({
      text,
      sourceLang,
      targetLang,
      formality,
      context,
      glossaryId,
    });
    const outcome = r?.result ?? {};
    const trace = Array.isArray(r?.trace)
      ? r.trace
      : Array.isArray(outcome.agentTrace)
        ? outcome.agentTrace
        : [];
    sendJson(res, 200, {
      text: String(outcome.text ?? ""),
      detected_source_language: String(
        outcome.detected_source_language ?? outcome.detectedSourceLanguage ?? ""
      ),
      coverage: coerceNumber(outcome.coverage, 0),
      notes: Array.isArray(outcome.notes) ? outcome.notes.map(String) : [],
      agent_trace: trace,
      latency_ms: coerceNumber(outcome.latency_ms, noteLatency(started)),
      provider: "local",
    });
    usageCounters.translations += 1;
    usageCounters.charsToday += text.length;
    return;
  }

  /* ---------------- /api/write ------------------------------------- */

  if (section === "write" && method === "POST") {
    const body = await readJsonBody(req);
    const text = typeof body.text === "string" ? body.text : "";
    if (!text.trim()) fail(400, "missing_text");
    const mode = body.mode === "rephrase" ? "rephrase" : "correct";
    const style = anyFormality(body.style ?? body.writing_style);
    const provider = typeof body.provider === "string" && body.provider.trim() ? body.provider.trim().toLowerCase() : "local";

    if (provider === "deepl") {
      const key = keyFromHeader(req) ?? envKey();
      if (!key) fail(400, "no_key");
      const chk = validateKeyFormat(key);
      if (!chk?.valid) fail(400, "invalid_key", { reason: chk?.reason ?? null });
      try {
        const call =
          mode === "rephrase"
            ? deeplWriteRephrase({ key, host: hostForKey(key), text, targetLang: "EN-US", writingStyle: style })
            : deeplWriteCorrect({ key, host: hostForKey(key), text, targetLang: "EN-US" });
        const out = await call;
        sendJson(res, 200, {
          original: text,
          corrected: extractCorrected(out, text),
          changes: [],
          diff: [],
          latency_ms: noteLatency(started),
          provider: "deepl",
        });
      } catch (err) {
        rethrowDeeplError(err);
      }
      return;
    }

    const r = await coordinator.runCorrect({ text, style, mode });
    const outcome = r?.result ?? {};
    sendJson(res, 200, {
      original: String(outcome.original ?? text),
      corrected: String(outcome.corrected ?? ""),
      changes: Array.isArray(outcome.changes) ? outcome.changes : [],
      diff: Array.isArray(outcome.diff) ? outcome.diff : [],
      latency_ms: coerceNumber(outcome.latency_ms, noteLatency(started)),
      provider: "local",
    });
    usageCounters.corrections += 1;
    usageCounters.charsToday += text.length;
    return;
  }

  /* ---------------- /api/deepl/validate + /api/deepl/usage --------- */

  if (section === "deepl" && (rest[0] === "validate" || rest[0] === "usage") && method === "POST") {
    const body = await readJsonBody(req);
    const key = keyFromBodyHeaderEnv(body, req);
    if (!key) fail(400, "no_key");
    const chk = validateKeyFormat(key);
    if (!chk?.valid) {
      sendJson(res, 400, { valid: false, reason: chk?.reason ?? "invalid_key_format", ...deMaskedNote() });
      return;
    }
    const live = await liveUsageOrNull(key);
    if (rest[0] === "usage") {
      sendJson(res, 200, {
        character_count: live?.character_count ?? null,
        character_limit: live?.character_limit ?? null,
        tier: chk.tier ?? null,
        host: chk.host ?? null,
        ...(live?.live_check ? { live_check: live.live_check } : {}),
      });
      return;
    }
    sendJson(res, live?.live_check && !("character_count" in (live ?? {})) ? 200 : 200, {
      valid: true,
      tier: chk.tier ?? null,
      host: chk.host ?? null,
      character_count: live?.character_count ?? null,
      character_limit: live?.character_limit ?? null,
      ...(live?.live_check ? { live_check: live.live_check } : {}),
    });
    return;
  }

  /* ---------------- /api/glossary ---------------------------------- */

  if (section === "glossary") {
    const id = rest[0] ? String(rest[0]) : null;
    const sub = rest[1] ? String(rest[1]) : null;

    if (!id) {
      if (method === "GET") {
        sendJson(res, 200, { glossaries: glossaryStore.list(), stores: glossaryStore.list() });
        return;
      }
      if (method === "POST") {
        const body = await readJsonBody(req);
        const name = typeof body.name === "string" ? body.name.trim() : "";
        if (!name) fail(400, "missing_name");
        const newId = glossaryStore.create(name);
        const st = glossaryStore.get(newId);
        sendJson(res, 200, { id: newId, name: st?.name ?? name, entries: st?.entries ?? [] });
        return;
      }
      if (method === "DELETE") {
        const removed = glossaryStore.clearAll();
        sendJson(res, 200, { ok: true, removed });
        return;
      }
      fail(405, "method_not_allowed");
      return;
    }

    if (method === "GET" && !sub) {
      const st = glossaryStore.get(id);
      if (!st) fail(404, "glossary_not_found");
      sendJson(res, 200, { id: st.id, name: st.name, entries: st.entries });
      return;
    }

    if (method === "DELETE" && !sub) {
      if (!glossaryStore.remove(id)) fail(404, "glossary_not_found");
      res.writeHead(204, { "Content-Length": 0 });
      res.end();
      return;
    }

    if (method === "POST" && sub === "entries") {
      const body = await readJsonBody(req);
      const entry = glossaryStore.add(id, body);
      if (!entry) {
        const st = glossaryStore.get(id);
        if (!st) fail(404, "glossary_not_found");
        fail(400, "invalid_entry");
      }
      sendJson(res, 200, { ok: true, id, entry });
      return;
    }

    fail(404, "not_found");
    return;
  }

  /* ---------------- /api/document ---------------------------------- */

  if (section === "document" && method === "POST") {
    const body = await readJsonBody(req);
    const filename = typeof body.filename === "string" && body.filename.trim() ? body.filename.trim() : "";
    if (!filename) fail(400, "missing_filename");
    const rawB64 = typeof body.content_base64 === "string" ? body.content_base64 : "";
    if (!rawB64.trim()) fail(400, "missing_content_base64");

    const b64 = rawB64.replace(/\s+/g, "");
    if (!/^[A-Za-z0-9+/=\-_]+$/.test(b64)) fail(400, "invalid_content_base64");
    const bytes = Buffer.from(b64.replace(/-/g, "+").replace(/_/g, "/"), "base64");
    if (bytes.length === 0) fail(400, "empty_content");
    if (bytes.length > DOC_CAP_BYTES) {
      fail(413, "document_too_large", { limit_bytes: DOC_CAP_BYTES, bytes: bytes.length });
    }

    const targetLang = langCode(body.target_lang ?? body.targetLang, "DE") ?? "DE";

    let extracted;
    try {
      extracted = extractText({ filename, bytes });
    } catch (err) {
      fail(400, redactKeys(String(err?.message ?? err ?? "extraction_failed")).slice(0, 300), {
        stage: "extract",
      });
    }
    const srcText = typeof extracted?.text === "string" ? extracted.text : "";
    if (!srcText.trim()) fail(400, "no_text_extracted", { stage: "extract" });
    const meta =
      extracted?.meta && typeof extracted.meta === "object"
        ? { kind: extracted.meta.kind ?? kindFromFilename(filename), warnings: Array.isArray(extracted.meta.warnings) ? extracted.meta.warnings.slice() : [] }
        : { kind: kindFromFilename(filename), warnings: [] };

    const coord = makeLocalCoordinator();
    const chunkFn = (chunk, idx) => translateChunkSequentially(chunk, targetLang, coord ?? coordinator);

    let sourceText = srcText;

    let out = null;
    try {
      out = await translateDocument(
        { text: srcText, meta },
        { sourceLang: "auto", targetLang },
        chunkFn
      );
    } catch (err) {
      out = null;
    }

    const outValid =
      out &&
      Array.isArray(out.segments) &&
      out.segments.length > 0 &&
      typeof out.output === "string" &&
      out.segments.every((s) => s && typeof s.target === "string" && !s.target.includes("Promise"));

    if (!outValid) {
      // Fallback: sequential sentence-chunk translation done locally in the server.
      try {
        const chunks = chunkSentences(srcText);
        const segments = [];
        for (let i = 0; i < chunks.length; i++) {
          const target = await chunkFn(chunks[i], i);
          segments.push({ source: chunks[i], target });
        }
        if (!segments.length) fail(400, "no_chunks", { stage: "translate" });
        out = {
          segments,
          output: segments.map((s) => s.target).join(" "),
          kind: meta.kind,
        };
      } catch (err) {
        fail(400, redactKeys(String(err?.message ?? err ?? "translation_failed")).slice(0, 300), {
          stage: "translate",
        });
      }
    }

    sendJson(res, 200, {
      filename: translatedFilename(filename),
      kind: out.kind ?? meta.kind,
      text: out.output,
      segments: out.segments,
      meta,
      latency_ms: noteLatency(started),
    });
    usageCounters.translations += 1;
    usageCounters.charsToday += String(sourceText).length;
    return;
  }

  /* ---------------- /api/voice/export ------------------------------ */

  if (section === "voice" && rest[0] === "export" && method === "POST") {
    const body = await readJsonBody(req);
    if (!Array.isArray(body.segments)) fail(400, "invalid_segments");
    const format = typeof body.format === "string" ? body.format.toLowerCase() : "srt";
    if (!["srt", "vtt", "txt", "json"].includes(format)) {
      fail(400, "unsupported_format", { supported: ["srt", "vtt", "txt", "json"] });
    }
    sendJson(res, 200, {
      content: buildVoiceExport(body.segments, format),
      format,
      count: body.segments.length,
    });
    return;
  }

  fail(404, "not_found");
}

/* ------------------------------------------------------------------ *
 * Server entry point
 * ------------------------------------------------------------------ */

const requestLogger = (method, pathname, status, started, apiKeyHeader) => {
  const t = new Date().toISOString().slice(11, 19);
  const ms = Date.now() - started;
  const masked = maskKeySafe(apiKeyHeader);
  const line = `[${t}] ${method} ${pathname} → ${status} (${ms} ms)${masked ? ` key=${masked}` : ""}`;
  console.log(line);
};

async function route(req, res) {
  const started = Date.now();
  let pathname;
  try {
    const u = new URL(req.url ?? "/", "http://localhost");
    pathname = decodeURIComponent(u.pathname);
  } catch {
    pathname = String(req.url ?? "/");
  }
  const method = req.method ?? "GET";
  const apiKeyHeader = keyFromHeader(req);

  try {
    if (pathname.includes("..") || pathname.includes("\\")) {
      fail(404, "not_found");
    }

    if (method === "OPTIONS") {
      applyCors(res);
      res.writeHead(204, { "Content-Length": 0 });
      res.end();
      return 204;
    }

    if (pathname === "/api" || pathname.startsWith("/api/")) {
      applyCors(res);
      await handleApi(req, res, pathname, started);
      return;
    }

    const staticTarget = resolveStaticPath(pathname);
    if (staticTarget) {
      applyCors(res);
      return await serveStatic(res, method, staticTarget, started, pathname);
    }

    sendJson(res, 404, { error: "not_found" });
    return;
  } catch (err) {
    if (err instanceof HttpError || (err && err.status && err.payload)) {
      const e = err instanceof HttpError ? err : new HttpError(err.status, err.payload);
      applyCors(res);
      sendJson(res, e.status, e.payload);
      return;
    }
    applyCors(res);
    sendJson(res, 500, { error: redactKeys(String(err?.message ?? err ?? "internal_error")).slice(0, 300) });
  } finally {
    requestLogger(method, pathname, res.statusCode, started, apiKeyHeader);
  }
}

/**
 * Start the HTTP server.
 * @param {{port?: number}} [opts]
 * @returns {Promise<{server: import("node:http").Server, port: number}>}
 */
export async function startServer({ port } = {}) {
  const envPort = Number.parseInt(process.env.PORT ?? "", 10);
  const resolvedPort = port ?? (Number.isFinite(envPort) ? envPort : DEFAULT_PORT);

  await glossaryStore.load();

  const server = http.createServer((req, res) => {
    route(req, res).catch((err) => {
      try {
        if (!res.headersSent) {
          sendJson(res, 500, { error: redactKeys(String(err?.message ?? err ?? "internal_error")) });
        } else {
          res.end();
        }
      } catch {
        /* socket already gone */
      }
    });
  });
  server.keepAliveTimeout = 5000;
  server.requestTimeout = 60_000;

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(resolvedPort, () => resolve());
  });

  const actualPort = server.address()?.port ?? resolvedPort;
  return { server, port: actualPort };
}

/* CLI: `node server/server.mjs` runs the server; importing (tests) does not. */
if (process.argv[1] && process.argv[1].endsWith("server.mjs")) {
  startServer()
    .then(({ port }) => {
      const env = envKey();
      console.log(
        `[talkflow] TalkFlow ${String(VERSION ?? "2.0.0")} listening on http://127.0.0.1:${port} — ` +
          `deepl key: ${env ? `${maskKeySafe(env)} (from DEEPL_API_KEY)` : "not set (demo/local engine only)"}`
      );
    })
    .catch((err) => {
      console.error(`[talkflow] server failed to start: ${redactKeysSafe(err)}`);
      process.exitCode = 1;
    });
}

function redactKeysSafe(err) {
  try {
    return redactKeys(String(err?.message ?? err ?? "unknown"));
  } catch {
    return "unknown";
  }
}

function deMaskedNote() {
  try {
    return typeof maskKey === "function" ? {} : {};
  } catch {
    return {};
  }
}

function logRequestStartedAt(pathname, started) {
  try {
    if (!pathname.startsWith("/api")) return;
  } catch {
    /* noop */
  }
}
