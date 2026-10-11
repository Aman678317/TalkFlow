/**
 * Language discovery with a small in-process cache.
 * Languages are fetched from the TalkFlow backend and cached for a short TTL
 * so repeated tool calls do not hammer the API.
 */

const TTL_MS = 5 * 60 * 1000;
let cache = null;
let cachedAt = 0;

export async function listLanguages(client, { force = false } = {}) {
  const now = Date.now();
  if (!force && cache && now - cachedAt < TTL_MS) return cache;
  const rows = await client.get("/api/v1/languages");
  cache = (Array.isArray(rows) ? rows : []).map((r) => ({
    code: r.code,
    name: r.name,
    native_name: r.native_name,
    script: r.script,
    rtl: Boolean(r.rtl),
    translation_supported: Boolean(r.translation_supported),
    speech_input_supported: Boolean(r.speech_input_supported),
    speech_output_supported: Boolean(r.speech_output_supported),
  }));
  cachedAt = now;
  return cache;
}

export async function findLanguage(client, codeOrName) {
  const langs = await listLanguages(client);
  const needle = String(codeOrName ?? "").trim().toLowerCase();
  if (!needle) return null;
  return (
    langs.find((l) => l.code?.toLowerCase() === needle) ||
    langs.find((l) => l.name?.toLowerCase() === needle) ||
    langs.find((l) => l.native_name?.toLowerCase() === needle) ||
    null
  );
}
