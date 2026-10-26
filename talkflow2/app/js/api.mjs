// Shared fetch wrapper + tiny DOM helpers used by every view.
// All endpoints are same-origin /api/*; the only non-API imports are absolute /engine/*.mjs modules.
export const LANGS = {
  EN: "English", DE: "German", FR: "French", ES: "Spanish", IT: "Italian",
  PT: "Portuguese", HI: "Hindi", JA: "Japanese", ZH: "Chinese",
};

const DEFAULT_TIMEOUT = 20000;

export async function api(path, { method = "GET", body = null, key = null, timeoutMs = DEFAULT_TIMEOUT } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const headers = {};
  if (body !== null) headers["Content-Type"] = "application/json";
  // DeepL keys travel in a header only — never in a URL, never in a query string.
  if (key) headers["X-Deepl-Key"] = key;
  try {
    const res = await fetch(path, {
      method,
      headers,
      signal: ctrl.signal,
      body: body === null ? undefined : JSON.stringify(body),
    });
    const raw = await res.text();
    let data = {};
    try { data = raw ? JSON.parse(raw) : {}; }
    catch { data = { error: raw.slice(0, 300) || `HTTP ${res.status}` }; }
    if (!res.ok) {
      const message = typeof data.error === "string" && data.error ? data.error : `HTTP ${res.status}`;
      const err = new Error(message);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  } catch (e) {
    if (e && e.name === "AbortError") throw new Error(`Request timed out after ${timeoutMs} ms`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const apiGet = (path, opts = {}) => api(path, { ...opts, method: "GET" });
export const apiPost = (path, body, opts = {}) => api(path, { ...opts, method: "POST", body });
export const apiDelete = (path, opts = {}) => api(path, { ...opts, method: "DELETE" });

const ERROR_HINTS = {
  no_key: "No DeepL key available — unlock your key in Settings, or use the Demo provider.",
  invalid_key: "DeepL rejected that key — check it in Settings.",
  invalid_key_format: "Key format looks invalid (needs 32+ characters; free keys end with :fx).",
  missing_text: "Enter some text first.",
  missing_target_lang: "Choose a target language.",
  missing_name: "Enter a glossary name first.",
  invalid_entry: "Both a source term and a target term are required.",
  invalid_segments: "No transcript segments to export yet.",
  unsupported_format: "That export format is not supported.",
  body_too_large: "The request body is too large.",
  document_too_large: "That document exceeds the 5 MB limit.",
  no_text_extracted: "No text could be extracted from that file.",
  empty_content: "That file is empty.",
  invalid_content_base64: "The file could not be read.",
  missing_filename: "Could not read the file name.",
  quota_exhausted: "DeepL quota is exhausted for this key.",
  throttled: "DeepL rate limit reached — try again shortly.",
  auth_invalid: "DeepL rejected the key (authentication failed).",
  not_found: "The server could not find that resource.",
  glossary_not_found: "That glossary no longer exists — refresh the list.",
};

/** Turn an api() error into a short, actionable sentence for the UI. */
export function humanError(err) {
  const code = String(err?.message ?? "").trim();
  const reason = err?.data?.reason;
  if (ERROR_HINTS[code]) {
    if (code === "invalid_key_format" && reason) return `${ERROR_HINTS[code]} (${reason})`;
    return ERROR_HINTS[code];
  }
  if (code === "invalid_key") return `DeepL key rejected${reason ? ` (${reason})` : ""} — check it in Settings.`;
  if (err?.data?.valid === false) return `The DeepL key was rejected${reason ? ` (${reason})` : ""}.`;
  if (reason) return `${code || "Request failed"} (${reason})`;
  if (!code || /failed to fetch|load failed|networkerror/i.test(code)) {
    return "Server unreachable — start TalkFlow with `npm start` in talkflow2/.";
  }
  return code;
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

export function download(content, filename, mime = "text/plain;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([String(content)], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString() : "—";
}

export function fmtClock(ms) {
  const v = Math.max(0, Math.round(Number(ms) || 0));
  const p = (n, w) => String(n).padStart(w, "0");
  return `${p(Math.floor(v / 60000), 2)}:${p(Math.floor((v % 60000) / 1000), 2)}.${p(v % 1000, 3)}`;
}

export function langName(code) {
  const c = String(code || "").toUpperCase();
  return LANGS[c] || c || "Unknown";
}

const BCP47 = {
  EN: "en-US", DE: "de", FR: "fr-FR", ES: "es-ES", IT: "it-IT",
  PT: "pt-PT", HI: "hi-IN", JA: "ja-JP", ZH: "zh-CN",
};

/** Speech API language tag for the nine DeepL languages. */
export function bcp47(code) {
  const c = String(code || "").toUpperCase();
  return BCP47[c] || (c ? c.toLowerCase() : "en-US");
}

let cachedLangs = null;
export async function getLangs() {
  if (cachedLangs) return cachedLangs;
  try {
    const data = await apiGet("/api/languages");
    const arr = Array.isArray(data) ? data : data.languages || [];
    if (arr.length >= 9) { cachedLangs = arr; return arr; }
  } catch { /* fall back to the static language set below */ }
  cachedLangs = Object.entries(LANGS).map(([code, name]) => ({ code, name }));
  return cachedLangs;
}

/**
 * Populate a language <select> from /api/languages.
 * `baseOnly` keeps just the nine primary languages (used for source/voice/glossary).
 */
export async function fillLangSelect(select, { auto = false, selected = null, skip = null, baseOnly = false } = {}) {
  const langs = (await getLangs()).filter((l) => !baseOnly || !String(l.code).includes("-"));
  const opts = [];
  if (auto) opts.push({ code: "AUTO", name: "Auto-detect" });
  for (const l of langs) if (String(l.code).toUpperCase() !== String(skip || "").toUpperCase()) opts.push(l);
  select.innerHTML = opts.map((l) => `<option value="${esc(l.code)}">${esc(l.code)} — ${esc(l.name)}</option>`).join("");
  const wanted = selected != null && opts.some((o) => String(o.code) === String(selected));
  if (wanted) select.value = String(selected);
  else select.selectedIndex = 0;
  return select;
}
