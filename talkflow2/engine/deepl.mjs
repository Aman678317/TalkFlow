// DeepL HTTP client (global fetch only; no Node imports).
// UI talks to DeepL exclusively through the server proxy; this module is the
// server-side (or trusted-script) transport. Keys are never logged or echoed.

import { FREE_HOST, PRO_HOST, maskKey, redactKeys } from "./security.mjs";

const TRANSLATE_PATH = "/v2/translate";
const USAGE_PATH = "/v2/usage";
const CORRECT_PATH = "/v2/write/correct";
const REPHRASE_PATH = "/v2/write/rephrase";

export class DeepLError extends Error {
  constructor(status, httpStatus = null, message = status) {
    super(message);
    this.name = "DeepLError";
    this.status = status;
    this.httpStatus = httpStatus;
  }
}

function isAuthTarget(value) {
  if (typeof value !== "string") return false;
  const clean = value.trim().toLowerCase();
  return clean === "free" || clean === "pro" || clean === FREE_HOST || clean === PRO_HOST;
}

export function hostFor(keyOrTier) {
  if (keyOrTier && typeof keyOrTier === "object") {
    for (const candidate of [keyOrTier.host, keyOrTier.tier, keyOrTier.key]) {
      if (typeof candidate === "string" && candidate.trim()) return hostFor(candidate);
    }
    return PRO_HOST;
  }
  if (typeof keyOrTier !== "string") return PRO_HOST;
  const value = keyOrTier.trim().toLowerCase();
  if (!value) return PRO_HOST;
  if (value === "free" || value === FREE_HOST) return FREE_HOST;
  if (value === "pro" || value === PRO_HOST) return PRO_HOST;
  return value.endsWith(":fx") ? FREE_HOST : PRO_HOST;
}

function resolveAuth(options = {}) {
  let key = "";
  if (typeof options.key === "string" && options.key.trim()) {
    key = options.key.trim();
  } else if (
    typeof options.keyHost === "string" &&
    options.keyHost.trim() &&
    !isAuthTarget(options.keyHost)
  ) {
    key = options.keyHost.trim();
  }

  let host = PRO_HOST;
  if (isAuthTarget(options.host)) host = hostFor(options.host);
  else if (isAuthTarget(options.keyHost)) host = hostFor(options.keyHost);
  else if (isAuthTarget(options.tier)) host = hostFor(options.tier);
  else if (key) host = hostFor(key);

  if (!key) {
    throw new DeepLError("missing_key", null, "A DeepL API key is required");
  }
  return { key, host };
}

function sanitizeDetail(value, key) {
  let text = redactKeys(String(value ?? ""));
  if (key) text = text.split(key).join(maskKey(key));
  return text.replace(/\s+/g, " ").trim().slice(0, 240);
}

function mapHttpStatus(httpStatus) {
  if (httpStatus === 456) return "quota_exhausted";
  if (httpStatus === 429) return "throttled";
  if (httpStatus === 401 || httpStatus === 403) return "auth_invalid";
  if (httpStatus === 400) return "bad_request";
  if (httpStatus === 404) return "not_found";
  if (httpStatus === 413 || httpStatus === 414) return "text_too_large";
  if (httpStatus >= 500 && httpStatus <= 599) return "upstream_error";
  if (httpStatus >= 400) return "client_error";
  return "unknown_error";
}

async function request(url, { method = "GET", key, body, fetchImpl, signal } = {}) {
  const fetchFn = fetchImpl || globalThis.fetch;
  if (typeof fetchFn !== "function") {
    throw new DeepLError("network_unavailable", null, "fetch is not available");
  }

  const headers = {
    Authorization: `DeepL-Auth-Key ${key}`,
    Accept: "application/json",
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetchFn(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    throw new DeepLError(
      "network_error",
      null,
      `DeepL request failed: ${sanitizeDetail(error?.message || error, key)}`,
    );
  }

  let raw = "";
  let data = null;
  try {
    if (response && typeof response.text === "function") {
      raw = await response.text();
      if (raw) data = JSON.parse(raw);
    } else if (response && typeof response.json === "function") {
      data = await response.json();
    }
  } catch {
    data = null;
  }

  const httpStatus = Number(response?.status) || 0;
  const ok = response?.ok ?? (httpStatus >= 200 && httpStatus < 300);
  if (!ok) {
    const detail =
      data && typeof data === "object"
        ? Array.isArray(data.message)
          ? data.message.join("; ")
          : data.message
        : typeof raw === "string"
          ? raw
          : "";
    const status = mapHttpStatus(httpStatus);
    const suffix = detail ? `: ${sanitizeDetail(detail, key)}` : "";
    throw new DeepLError(status, response?.status ?? null, `DeepL ${status} (HTTP ${httpStatus})${suffix}`);
  }
  if (!data || typeof data !== "object") {
    throw new DeepLError("bad_response", response?.status ?? null, "DeepL returned a non-JSON response");
  }
  return data;
}

function normalizeTexts(text) {
  const list = Array.isArray(text) ? text : [text];
  const out = list.filter((item) => typeof item === "string" && item.trim() !== "");
  if (!out.length) {
    throw new DeepLError("bad_request", null, "Text is required");
  }
  if (out.length > 50) {
    throw new DeepLError("bad_request", null, "At most 50 text blocks per request");
  }
  return out;
}

function normalizeLang(value) {
  return String(value ?? "").trim().toUpperCase();
}

export async function translate(options = {}) {
  const auth = resolveAuth(options);
  const texts = normalizeTexts(options.text);
  const body = {
    text: texts,
    target_lang: normalizeLang(options.targetLang || "DE"),
  };
  if (options.sourceLang && String(options.sourceLang).toLowerCase() !== "auto") {
    body.source_lang = normalizeLang(options.sourceLang);
  }
  if (options.formality) body.formality = String(options.formality);
  if (options.context) body.context = String(options.context);
  if (options.glossaryId) body.glossary_id = String(options.glossaryId);

  const data = await request(`https://${auth.host}${TRANSLATE_PATH}`, {
    method: "POST",
    key: auth.key,
    body,
    fetchImpl: options.fetchImpl,
    signal: options.signal,
  });

  const translations = Array.isArray(data.translations)
    ? data.translations.map((item) => ({
        detected_source_language: item?.detected_source_language || null,
        text: typeof item?.text === "string" ? item.text : "",
      }))
    : [];
  const first = translations[0] || {};
  const billed = typeof data.billed_characters === "number" ? data.billed_characters : null;

  return {
    text: first.text ?? "",
    texts: translations.map((item) => item.text),
    translations,
    detected_source_language: first.detected_source_language || null,
    detectedSourceLanguage: first.detected_source_language || null,
    billed_characters: billed,
    billedCharacters: billed,
    host: auth.host,
  };
}

export async function usage(options = {}) {
  const auth = resolveAuth(options);
  const data = await request(`https://${auth.host}${USAGE_PATH}`, {
    method: "GET",
    key: auth.key,
    fetchImpl: options.fetchImpl,
    signal: options.signal,
  });
  return { ...data, host: auth.host };
}

async function writeRequest(path, options) {
  const auth = resolveAuth(options);
  const texts = normalizeTexts(options.text);
  const body = {
    text: texts,
    target_lang: normalizeLang(options.targetLang || "EN-US"),
  };
  if (path === REPHRASE_PATH) {
    const style = options.writingStyle ?? options.style;
    if (style) body.writing_style = String(style);
    if (options.tone) body.tone = String(options.tone);
  }

  const data = await request(`https://${auth.host}${path}`, {
    method: "POST",
    key: auth.key,
    body,
    fetchImpl: options.fetchImpl,
    signal: options.signal,
  });

  const improvements = Array.isArray(data.improvements)
    ? data.improvements.map((item) => ({
        text: typeof item?.text === "string" ? item.text : "",
        detected_source_language: item?.detected_source_language || null,
        target_language: item?.target_language || null,
      }))
    : [];
  const original = texts.length === 1 ? texts[0] : texts;
  const corrected = improvements[0]?.text ?? (texts.length === 1 ? texts[0] : "");

  return {
    original,
    corrected,
    rephrased: corrected,
    improvements,
    detected_source_language: improvements[0]?.detected_source_language || null,
    target_language: improvements[0]?.target_language || body.target_lang,
    host: auth.host,
  };
}

export async function writeCorrect(options = {}) {
  return writeRequest(CORRECT_PATH, options);
}

export async function writeRephrase(options = {}) {
  return writeRequest(REPHRASE_PATH, options);
}
