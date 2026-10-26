/**
 * TalkFlow 2.0 — subtitle/transcript serialization.
 *
 * Segments use `{ startMs, endMs, text, sourceTargetPairs? }` (camelCase is
 * canonical; snake_case and `start`/`end` aliases are accepted for tolerance).
 *
 * SRT: comma milliseconds + numeric cue index. VTT: `WEBVTT` header + dot
 * milliseconds. All parsers are defensive: malformed cues/timestamps are
 * skipped or given sane defaults, never thrown.
 */

const MAX_HOURS = 999;

function toMs(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  }
  if (typeof value === "string") {
    const parsed = parseTimeStr(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

/**
 * Parse an SRT/VTT timestamp into milliseconds.
 * Accepts `HH:MM:SS,mmm`, `HH:MM:SS.mmm`, `MM:SS.mmm`, `HH:MM:SS`, `MM:SS`.
 * Fractions of 1-3 digits are scaled right (`1,5` → 500 ms).
 * @param {string|number} value
 * @returns {number} milliseconds, or NaN when unparseable
 */
export function parseTimeStr(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? Math.max(0, Math.round(value)) : NaN;
  }
  if (typeof value !== "string") return NaN;
  const s = value.trim().replace(",", ".");
  if (!s) return NaN;

  const m = /^(?:(\d{1,4}):)?(\d{1,3}):(\d{1,2})(?:\.(\d{1,3}))?$/.exec(s);
  if (!m) return NaN;

  const hours = m[1] !== undefined ? Number(m[1]) : 0;
  const minutes = Number(m[2]);
  const seconds = Number(m[3]);
  const fraction = m[4] !== undefined ? Number(m[4].padEnd(3, "0")) : 0;
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) {
    return NaN;
  }
  if (minutes > 59 || seconds > 59) return NaN;
  if (hours > MAX_HOURS) return NaN;
  return Math.max(0, ((hours * 60 + minutes) * 60 + seconds) * 1000 + fraction);
}

/**
 * Format milliseconds as `HH:MM:SS,mmm` (SRT) or `HH:MM:SS.mmm` (VTT).
 * @param {number} ms
 * @param {","|"."} [sep]
 */
export function formatTimeStr(ms, sep = ",") {
  const total = Math.max(0, Math.round(Number(ms) || 0));
  const hours = Math.floor(total / 3600000);
  const minutes = Math.floor((total % 3600000) / 60000);
  const seconds = Math.floor((total % 60000) / 1000);
  const millis = total % 1000;
  const pad = (n, width) => String(n).padStart(width, "0");
  return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(seconds, 2)}${sep}${pad(millis, 3)}`;
}

function pairText(seg) {
  const pairs = Array.isArray(seg?.sourceTargetPairs)
    ? seg.sourceTargetPairs
    : Array.isArray(seg?.pairs)
      ? seg.pairs
      : null;
  if (!pairs || !pairs.length) return "";
  return pairs
    .map((pair) => {
      const source = typeof pair?.source === "string" ? pair.source.trim() : "";
      const target = typeof pair?.target === "string" ? pair.target.trim() : "";
      return [source, target].filter(Boolean).join(" → ");
    })
    .filter(Boolean)
    .join("\n");
}

function segmentText(seg) {
  if (!seg || typeof seg !== "object") return "";
  if (typeof seg.text === "string" && seg.text.trim()) {
    return seg.text.replace(/\r\n?/g, "\n").trim();
  }
  const pairs = pairText(seg);
  if (pairs) return pairs;
  const parts = [seg.source, seg.target].filter(
    (v) => typeof v === "string" && v.trim(),
  );
  return parts.map((v) => v.trim()).join(" → ");
}

function normalizeSegment(seg, index) {
  const s = seg && typeof seg === "object" ? seg : {};
  const startMs = toMs(s.startMs ?? s.start_ms ?? s.start);
  const rawEnd = s.endMs ?? s.end_ms ?? s.end;
  let endMs = rawEnd === undefined || rawEnd === null ? startMs + 1200 : toMs(rawEnd);
  if (!Number.isFinite(endMs) || endMs < startMs) endMs = startMs + 1200;
  return { index: index + 1, startMs, endMs, text: segmentText(s) };
}

function asList(segments) {
  return Array.isArray(segments) ? segments : [];
}

/**
 * Build SRT text: `1\n00:00:00,000 --> 00:00:01,500\ntext\n\n`
 * @param {Array<object>} segments
 * @returns {string}
 */
export function toSrt(segments) {
  const blocks = asList(segments)
    .map((seg, i) => normalizeSegment(seg, i))
    .map(
      (seg) =>
        `${seg.index}\n${formatTimeStr(seg.startMs, ",")} --> ${formatTimeStr(seg.endMs, ",")}\n${seg.text}`,
    );
  return blocks.length ? `${blocks.join("\n\n")}\n` : "";
}

/**
 * Build WebVTT text (dot milliseconds, `WEBVTT` header).
 * @param {Array<object>} segments
 * @returns {string}
 */
export function toVtt(segments) {
  const blocks = asList(segments)
    .map((seg, i) => normalizeSegment(seg, i))
    .map(
      (seg) =>
        `${formatTimeStr(seg.startMs, ".")} --> ${formatTimeStr(seg.endMs, ".")}\n${seg.text}`,
    );
  return `WEBVTT\n\n${blocks.length ? `${blocks.join("\n\n")}\n` : ""}`;
}

/**
 * Plain transcript: one segment per line.
 * @param {Array<object>} segments
 * @returns {string}
 */
export function toTxt(segments) {
  const lines = asList(segments)
    .map((seg, i) => normalizeSegment(seg, i).text)
    .filter(Boolean);
  return lines.length ? `${lines.join("\n")}\n` : "";
}

/**
 * JSON transcript with stable `{index,startMs,endMs,text}` entries.
 * @param {Array<object>} segments
 * @returns {string}
 */
export function toJson(segments) {
  const list = asList(segments);
  const payload = list.map((seg, i) => {
    const norm = normalizeSegment(seg, i);
    const obj = {
      index: norm.index,
      startMs: norm.startMs,
      endMs: norm.endMs,
      text: norm.text,
    };
    if (Array.isArray(seg?.sourceTargetPairs) && seg.sourceTargetPairs.length) {
      obj.sourceTargetPairs = seg.sourceTargetPairs.map((pair) => ({
        source: String(pair?.source ?? ""),
        target: String(pair?.target ?? ""),
      }));
    }
    return obj;
  });
  return JSON.stringify(payload, null, 2);
}

/**
 * Tolerant SRT (and basic WebVTT) parser. Cues without a usable timecode are
 * skipped; one malformed bound is repaired instead of failing the document.
 * @param {string} input
 * @returns {{startMs: number, endMs: number, text: string}[]}
 */
export function parseSrt(input) {
  if (typeof input !== "string") return [];
  const text = input.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
  if (!text.trim()) return [];

  const blocks = text.split(/\n{2,}/);
  const cues = [];
  for (const block of blocks) {
    const lines = block.split("\n").map((line) => line.trimEnd());
    const timeIdx = lines.findIndex((line) => line.includes("-->"));
    if (timeIdx < 0) continue;

    const [rawStart, rawEnd] = lines[timeIdx].split("-->");
    const startToken = String(rawStart ?? "").trim().split(/\s+/)[0] ?? "";
    const endToken = String(rawEnd ?? "").trim().split(/\s+/)[0] ?? "";
    let startMs = parseTimeStr(startToken);
    let endMs = parseTimeStr(endToken);

    if (!Number.isFinite(startMs) && !Number.isFinite(endMs)) continue;
    if (!Number.isFinite(startMs)) startMs = Math.max(0, (Number.isFinite(endMs) ? endMs : 0) - 1200);
    if (!Number.isFinite(endMs) || endMs < startMs) endMs = startMs + 1200;

    const textLines = lines
      .slice(timeIdx + 1)
      .map((line) => line.replace(/<[^>]*>/g, "").trim())
      .filter(Boolean);
    const cueText = textLines.join("\n").trim();
    if (!cueText) continue;

    cues.push({ startMs, endMs, text: cueText });
  }
  return cues;
}

export const SUBTITLES_VERSION = "2.0.0";
