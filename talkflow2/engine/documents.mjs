/**
 * TalkFlow 2.0 — document ingestion + document translation (SERVER-ONLY).
 *
 * `extractText({ filename, bytes })` supports txt/md/html/srt/vtt/json and a
 * heuristic PDF reader (FlateDecode streams + Tj/TJ text operators). The PDF
 * reader never executes document content; it only inflates streams with
 * node:zlib and scans text-showing operators.
 *
 * `translateDocument({ text, meta }, opts, translateChunk)` translates text /
 * HTML documents while preserving HTML tags and layout.
 *
 * node:zlib is loaded lazily inside the extraction path (never at module load)
 * so importing this module stays cheap and browser-safe errors are obvious.
 */

import { createRequire } from "node:module";

const NODE_REQUIRE = createRequire(import.meta.url);
const EXT_KIND = Object.freeze({
  pdf: "pdf",
  txt: "txt",
  text: "txt",
  md: "md",
  markdown: "md",
  html: "html",
  htm: "html",
  srt: "srt",
  vtt: "vtt",
  json: "json",
});
const ALLOWED_KINDS = new Set(["pdf", "txt", "html", "md", "srt", "vtt", "json"]);
const SKIP_HTML_TAGS = new Set(["script", "style", "noscript", "template"]);

let zlibModule = null;

/** Load node:zlib lazily, synchronously (extractText is a sync API). */
function getZlib() {
  if (zlibModule) return zlibModule;
  try {
    if (typeof process !== "undefined" && typeof process.getBuiltinModule === "function") {
      zlibModule = process.getBuiltinModule("node:zlib") || null;
    }
  } catch {
    zlibModule = null;
  }
  if (!zlibModule) {
    try {
      zlibModule = NODE_REQUIRE("node:zlib");
    } catch (err) {
      throw new Error(
        `PDF extraction is unavailable: node:zlib could not be loaded (${err?.message ?? err})`,
      );
    }
  }
  if (typeof zlibModule.inflateSync !== "function") {
    throw new Error("PDF extraction is unavailable: node:zlib.inflateSync is missing");
  }
  return zlibModule;
}

/* ------------------------------------------------------------------ *
 * Small helpers
 * ------------------------------------------------------------------ */

function baseName(filename) {
  return String(filename).split(/[\\/]/).pop() || String(filename);
}

function extOf(filename) {
  const m = baseName(filename).match(/\.([A-Za-z0-9]+)$/);
  return m ? m[1].toLowerCase() : "";
}

function asBuffer(bytes) {
  if (Buffer.isBuffer(bytes)) return bytes;
  if (bytes instanceof Uint8Array) {
    return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  }
  if (bytes instanceof ArrayBuffer) return Buffer.from(bytes);
  if (ArrayBuffer.isView(bytes)) {
    return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  }
  return null;
}

const ENTITY_MAP = Object.freeze({
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  "#39": "'",
  "#x27": "'",
});

export function decodeEntities(input) {
  if (typeof input !== "string" || !input.includes("&")) return String(input ?? "");
  return input.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (full, body) => {
    const key = String(body).toLowerCase();
    if (Object.prototype.hasOwnProperty.call(ENTITY_MAP, key)) return ENTITY_MAP[key];
    let code = NaN;
    if (key.startsWith("#x")) code = Number.parseInt(key.slice(2), 16);
    else if (key.startsWith("#")) code = Number.parseInt(key.slice(1), 10);
    if (Number.isFinite(code) && code > 0 && code <= 0x10ffff) {
      try {
        return String.fromCodePoint(code);
      } catch {
        return full;
      }
    }
    return full;
  });
}

function escapeHtmlText(value) {
  return String(value)
    .replace(/&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#x[0-9a-fA-F]+);)/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function normalizeBlankLines(value) {
  return String(value)
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/* ------------------------------------------------------------------ *
 * Kind sniffing
 * ------------------------------------------------------------------ */

function sniffKind(buf) {
  const head = buf.subarray(0, 512).toString("latin1").replace(/^\uFEFF/, "").trimStart();
  if (head.startsWith("%PDF")) return "pdf";
  if (/^WEBVTT\b/i.test(head)) return "vtt";
  if (/^\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->/.test(head)) return "srt";
  if (/^<!doctype\s+html/i.test(head) || /^<html[\s>]/i.test(head) || /^<body[\s>]/i.test(head)) {
    return "html";
  }
  if (head.startsWith("{") || head.startsWith("[")) return "json";
  return "txt";
}

/* ------------------------------------------------------------------ *
 * HTML
 * ------------------------------------------------------------------ */

function htmlToText(html) {
  const warnings = [];
  let s = String(html).replace(/^\uFEFF/, "");
  s = s.replace(/<!--[\s\S]*?-->/g, " ");
  s = s.replace(/<(script|style|noscript|template)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, " ");
  s = s.replace(/<br\s*\/?>/gi, "\n");
  s = s.replace(/<\/(p|div|li|h[1-6]|tr|section|article|blockquote|pre|table|ul|ol)\s*>/gi, "\n");
  s = s.replace(/<[^>]*>/g, " ");
  s = decodeEntities(s);
  s = s
    .replace(/[ \t\f\v]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!s) warnings.push("No visible text found in this HTML document");
  return { text: s, warnings };
}

/* ------------------------------------------------------------------ *
 * SRT / VTT
 * ------------------------------------------------------------------ */

function srtToText(input) {
  const lines = String(input).replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const t = raw.trim();
    if (!t) {
      out.push("");
      continue;
    }
    if (/^\d+$/.test(t)) continue; // cue index
    if (t.includes("-->") && /\d{1,2}:\d{2}/.test(t)) continue; // timecode
    out.push(t);
  }
  return normalizeBlankLines(out.join("\n"));
}

function vttToText(input) {
  const lines = String(input).replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const t = raw.trim();
    if (!t) {
      out.push("");
      continue;
    }
    if (/^(WEBVTT|NOTE|STYLE|REGION)\b/i.test(t)) continue;
    if (t.includes("-->")) continue;
    const next = lines[i + 1] ?? "";
    if (next.includes("-->")) continue; // cue identifier line
    const cleaned = decodeEntities(t.replace(/<[^>]*>/g, "")).trim();
    if (cleaned) out.push(cleaned);
  }
  return normalizeBlankLines(out.join("\n"));
}

/* ------------------------------------------------------------------ *
 * JSON
 * ------------------------------------------------------------------ */

function collectJsonStrings(value, out, depth = 0) {
  if (depth > 64) return;
  if (typeof value === "string") {
    const t = value.trim();
    if (t) out.push(t);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectJsonStrings(item, out, depth + 1);
    return;
  }
  if (value && typeof value === "object") {
    for (const item of Object.values(value)) collectJsonStrings(item, out, depth + 1);
  }
}

function jsonToText(input) {
  const warnings = [];
  try {
    const parsed = JSON.parse(String(input).replace(/^\uFEFF/, ""));
    const strings = [];
    collectJsonStrings(parsed, strings);
    if (!strings.length) warnings.push("No string values found in JSON document");
    return { text: strings.join("\n"), warnings };
  } catch (err) {
    warnings.push(`Invalid JSON (${err?.message ?? "parse error"}); extracted raw text instead`);
    return { text: normalizeBlankLines(input), warnings };
  }
}

/* ------------------------------------------------------------------ *
 * PDF (heuristic)
 * ------------------------------------------------------------------ */

function readPdfLiteral(src, start) {
  let i = start + 1;
  let depth = 1;
  let value = "";
  while (i < src.length && depth > 0) {
    const ch = src[i];
    if (ch === "\\") {
      const next = src[i + 1];
      if (next === undefined) {
        i += 1;
        break;
      }
      switch (next) {
        case "n":
          value += "\n";
          i += 2;
          break;
        case "r":
          value += "\r";
          i += 2;
          break;
        case "t":
          value += "\t";
          i += 2;
          break;
        case "b":
          value += "\b";
          i += 2;
          break;
        case "f":
          value += "\f";
          i += 2;
          break;
        case "(":
          value += "(";
          i += 2;
          break;
        case ")":
          value += ")";
          i += 2;
          break;
        case "\\":
          value += "\\";
          i += 2;
          break;
        case "\r":
          i += src[i + 2] === "\n" ? 3 : 2; // line continuation
          break;
        case "\n":
          i += 2;
          break;
        default:
          if (/[0-7]/.test(next)) {
            let octal = next;
            let k = i + 2;
            while (octal.length < 3 && /[0-7]/.test(src[k] ?? "")) {
              octal += src[k];
              k += 1;
            }
            value += String.fromCharCode(Number.parseInt(octal, 8));
            i = k;
          } else {
            value += next;
            i += 2;
          }
      }
      continue;
    }
    if (ch === "(") {
      depth += 1;
      value += ch;
      i += 1;
      continue;
    }
    if (ch === ")") {
      depth -= 1;
      if (depth > 0) value += ch;
      i += 1;
      continue;
    }
    value += ch;
    i += 1;
  }
  return { value, next: i };
}

function pdfHexToString(hex) {
  const clean = hex.length % 2 ? `${hex}0` : hex;
  let out = "";
  for (let i = 0; i < clean.length; i += 2) {
    out += String.fromCharCode(Number.parseInt(clean.slice(i, i + 2), 16));
  }
  return out;
}

function decodePdfString(raw) {
  if (typeof raw !== "string" || raw.length < 2) return raw;
  if (raw.charCodeAt(0) === 0xfe && raw.charCodeAt(1) === 0xff) {
    try {
      const body = Buffer.from(raw.slice(2), "latin1");
      if (body.length % 2) return body.swap16().toString("utf16le") + "\uFFFD";
      return body.swap16().toString("utf16le");
    } catch {
      return raw;
    }
  }
  return raw;
}

/** Collect visible text from one (decompressed) PDF content stream. */
export function extractPdfContentText(content) {
  const src = typeof content === "string" ? content : String(content ?? "");
  const lines = [];
  let line = "";
  let pending = [];

  const flushPending = (withSpace) => {
    if (!pending.length) return;
    const joined = pending.join("");
    pending = [];
    if (!joined) return;
    if (withSpace && line && !/\s$/.test(line) && !/^\s/.test(joined)) line += " ";
    line += joined;
  };
  const pushLine = () => {
    flushPending(false);
    const trimmed = line.trim();
    if (trimmed) lines.push(trimmed);
    line = "";
  };

  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (ch === "(") {
      const literal = readPdfLiteral(src, i);
      pending.push(decodePdfString(literal.value));
      i = literal.next;
      continue;
    }
    if (ch === "<" && src[i + 1] !== "<") {
      const close = src.indexOf(">", i + 1);
      if (close > i) {
        const hex = src.slice(i + 1, close).replace(/\s+/g, "");
        if (/^[0-9A-Fa-f]+$/.test(hex)) {
          pending.push(decodePdfString(pdfHexToString(hex)));
          i = close + 1;
          continue;
        }
      }
    }
    if (ch === "%") {
      const nl = src.indexOf("\n", i);
      i = nl < 0 ? src.length : nl + 1;
      continue;
    }
    if (/[A-Za-z'"]/.test(ch)) {
      let j = i + 1;
      while (j < src.length && /[A-Za-z0-9'"*]/.test(src[j])) j += 1;
      const op = src.slice(i, j);
      if (op === "Tj" || op === "TJ" || op === "'" || op === '"') {
        flushPending(true);
        if (op === "'" || op === '"') pushLine();
      } else if (op === "Td" || op === "TD" || op === "T*" || op === "ET") {
        pushLine();
        if (op === "ET" && lines.length) lines.push("");
      }
      i = j;
      continue;
    }
    i += 1;
  }
  pushLine();
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function looksLikeContentStream(sample) {
  return /\bBT\b|\bTj\b|\bTJ\b/.test(sample) && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(sample);
}

function extractPdf(buf) {
  const warnings = [];
  const latin = buf.toString("latin1");
  if (!latin.startsWith("%PDF")) {
    throw new Error('Invalid PDF: missing "%PDF" header');
  }
  const pages = Math.max(1, (latin.match(/\/Type\s*\/Page(?![A-Za-z])/g) || []).length);
  const texts = [];
  let decoded = 0;
  let failed = 0;

  const streamRe = /(?:^|[^\w])stream(?:\r\n|\n|\r)/g;
  let match;
  while ((match = streamRe.exec(latin))) {
    const start = match.index + match[0].length;
    if (start >= latin.length) break;

    const dictFrom = Math.max(0, match.index - 4096);
    const dict = latin.slice(dictFrom, match.index);
    const lengthMatches = [...dict.matchAll(/\/Length\s+(\d+)/g)];
    const declared = lengthMatches.length
      ? Number(lengthMatches[lengthMatches.length - 1][1])
      : NaN;

    let end = -1;
    if (Number.isFinite(declared) && declared > 0 && start + declared <= latin.length) {
      const after = latin.slice(start + declared, start + declared + 32);
      if (/^\s*endstream/.test(after)) end = start + declared;
    }
    if (end < 0) {
      const found = latin.indexOf("endstream", start);
      if (found < 0) break;
      end = found;
    }

    let raw = buf.subarray(start, end);
    while (raw.length && (raw[raw.length - 1] === 0x0a || raw[raw.length - 1] === 0x0d)) {
      raw = raw.subarray(0, raw.length - 1);
    }
    streamRe.lastIndex = Math.max(streamRe.lastIndex, end);
    if (!raw.length) continue;

    let content = null;
    const zlib = getZlib();
    for (const inflate of [zlib.inflateSync, zlib.inflateRawSync]) {
      if (typeof inflate !== "function") continue;
      try {
        content = inflate(raw).toString("latin1");
        break;
      } catch {
        content = null;
      }
    }
    if (content === null) {
      const plain = raw.toString("latin1");
      if (looksLikeContentStream(plain.slice(0, 4096))) content = plain;
    }
    if (content === null) {
      failed += 1;
      continue;
    }
    decoded += 1;
    const text = extractPdfContentText(content);
    if (text) texts.push(text);
  }

  const text = texts.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
  warnings.push("Heuristic PDF text extraction (demo)");
  if (failed) warnings.push(`${failed} PDF stream(s) could not be decompressed`);
  if (!decoded) warnings.push("No decodable content streams were found");
  if (!text) {
    warnings.push("No extractable text found (the PDF may be scanned or use an unsupported encoding)");
  } else if (text.length / pages < 40) {
    warnings.push("Low text density — extraction may be incomplete");
  }
  return { text, meta: { kind: "pdf", pages, warnings } };
}

/* ------------------------------------------------------------------ *
 * Public: extractText
 * ------------------------------------------------------------------ */

/**
 * Extract readable text from an uploaded document.
 * @param {{filename: string, bytes: Buffer|Uint8Array|ArrayBuffer}} input
 * @returns {{text: string, meta: {kind: string, pages?: number, warnings: string[]}}}
 */
export function extractText(input) {
  const { filename, bytes } = input ?? {};
  const name = typeof filename === "string" ? filename.trim() : "";
  if (!name) throw new Error("extractText: missing filename");
  const buf = asBuffer(bytes);
  if (!buf) throw new Error("extractText: bytes must be a Buffer, Uint8Array, or ArrayBuffer");
  if (!buf.length) throw new Error(`extractText: empty content for "${baseName(name)}"`);

  const ext = extOf(name);
  const kind = EXT_KIND[ext] ?? sniffKind(buf);

  if (kind === "pdf") return extractPdf(buf);

  const raw = buf.toString("utf8").replace(/^\uFEFF/, "");
  if (!raw.trim()) throw new Error(`extractText: "${baseName(name)}" contains no text`);

  if (kind === "html") {
    const { text, warnings } = htmlToText(raw);
    return { text, meta: { kind: "html", warnings } };
  }
  if (kind === "srt") {
    return { text: srtToText(raw), meta: { kind: "srt", warnings: [] } };
  }
  if (kind === "vtt") {
    return { text: vttToText(raw), meta: { kind: "vtt", warnings: [] } };
  }
  if (kind === "json") {
    const { text, warnings } = jsonToText(raw);
    return { text, meta: { kind: "json", warnings } };
  }

  const normalizedKind = ALLOWED_KINDS.has(kind) ? kind : "txt";
  const warnings = ext && !EXT_KIND[ext] ? [`Unknown extension ".${ext}"; treated as plain text`] : [];
  return { text: raw, meta: { kind: normalizedKind, warnings } };
}

/* ------------------------------------------------------------------ *
 * Public: chunkSentences
 * ------------------------------------------------------------------ */

/**
 * Split prose into sentence-sized chunks. Very short fragments are merged into
 * a neighbour so translators do not see fragments like "Ok." on their own.
 * @param {string} text
 * @returns {string[]}
 */
export function chunkSentences(text) {
  if (typeof text !== "string") return [];
  const norm = text.replace(/\r\n?/g, "\n").trim();
  if (!norm) return [];
  const pieces = norm
    .split(/(?<=[.!?。！？])\s+|\n+/)
    .map((p) => p.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean);

  const chunks = [];
  let carry = "";
  for (const piece of pieces) {
    const candidate = carry ? `${carry} ${piece}` : piece;
    carry = "";
    if (candidate.length < 4) {
      carry = candidate;
      continue;
    }
    chunks.push(candidate);
  }
  if (carry) {
    if (chunks.length) chunks[chunks.length - 1] = `${chunks[chunks.length - 1]} ${carry}`;
    else chunks.push(carry);
  }
  return chunks;
}

/* ------------------------------------------------------------------ *
 * Public: translateDocument
 * ------------------------------------------------------------------ */

function splitHtmlTokens(html) {
  const tokens = [];
  const re = /<[^>]*>/g;
  let last = 0;
  let match;
  while ((match = re.exec(html))) {
    if (match.index > last) tokens.push({ type: "text", value: html.slice(last, match.index) });
    tokens.push({ type: "tag", value: match[0] });
    last = match.index + match[0].length;
  }
  if (last < html.length) tokens.push({ type: "text", value: html.slice(last) });
  return tokens;
}

async function translateHtml(html, run) {
  const tokens = splitHtmlTokens(html);
  let output = "";
  let skipTag = null;
  for (const token of tokens) {
    if (token.type === "tag") {
      output += token.value;
      const m = /^<\s*(\/?)\s*([A-Za-z0-9]+)/.exec(token.value);
      if (m) {
        const closing = Boolean(m[1]);
        const tag = m[2].toLowerCase();
        if (!closing && SKIP_HTML_TAGS.has(tag) && !/\/>\s*$/.test(token.value)) {
          skipTag = skipTag ?? tag;
        } else if (closing && skipTag === tag) {
          skipTag = null;
        }
      }
      continue;
    }
    if (skipTag || !token.value.trim()) {
      output += token.value;
      continue;
    }
    const lead = (token.value.match(/^\s*/) || [""])[0];
    const trail = (token.value.match(/\s*$/) || [""])[0];
    const core = token.value.slice(lead.length, token.value.length - trail.length);
    if (!core || !/[A-Za-z\u00c0-\uffff]/.test(core)) {
      output += token.value;
      continue;
    }
    const decoded = decodeEntities(core);
    const target = await run(decoded);
    output += lead + escapeHtmlText(target) + trail;
  }
  return output;
}

/**
 * Translate a document while preserving structure.
 * @param {{text: string, meta?: {kind?: string}}} doc
 * @param {{sourceLang?: string, targetLang?: string, formality?: string}} opts
 * @param {(chunk: string, index: number, opts: object) => (string|{text: string}|Promise<string|{text: string}>)} translateChunk
 * @returns {Promise<{segments: {source: string, target: string}[], output: string, kind: string}>}
 */
export async function translateDocument(doc, opts, translateChunk) {
  const { text, meta } = doc ?? {};
  if (typeof text !== "string") throw new TypeError("translateDocument: text must be a string");
  if (typeof translateChunk !== "function") {
    throw new TypeError("translateDocument: translateChunk must be a function");
  }
  const kind = meta && ALLOWED_KINDS.has(String(meta.kind)) ? String(meta.kind) : "txt";
  const segments = [];
  let index = 0;

  const run = async (source) => {
    const sentIdx = index++;
    let translated;
    try {
      translated = await translateChunk(source, sentIdx, opts ?? {});
    } catch (err) {
      throw new Error(`translateDocument: chunk ${sentIdx} failed: ${err?.message ?? err}`);
    }
    const target =
      typeof translated === "string"
        ? translated
        : translated && typeof translated.text === "string"
          ? translated.text
          : String(translated ?? "");
    segments.push({ source, target });
    return target;
  };

  if (!text.trim()) return { segments: [], output: text, kind };

  if (kind === "html") {
    const output = await translateHtml(text, run);
    return { segments, output, kind };
  }

  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const outputLines = [];
  for (const line of lines) {
    if (!line.trim()) {
      outputLines.push("");
      continue;
    }
    const chunks = chunkSentences(line);
    const targets = [];
    for (const chunk of chunks) targets.push(await run(chunk));
    outputLines.push(targets.join(" "));
  }
  const output = normalizeBlankLines(outputLines.join("\n"));
  return { segments, output, kind };
}

export const DOCUMENTS_VERSION = "2.0.0";
