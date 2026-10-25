// API key hygiene: format validation, masking and redaction.
// Never returns a raw key from maskKey()/redactKeys().

export const FREE_HOST = "api-free.deepl.com";
export const PRO_HOST = "api.deepl.com";

// DeepL API keys: at least 32 characters of [A-Za-z0-9_-], free keys end in ":fx".
const KEY_BODY = /^[\w-]{32,}$/;
const KEY_LIKE = /\b[\w-]{32,}(?::fx)?\b/g;

function invalid(reason) {
  return { valid: false, tier: null, host: null, reason };
}

export function validateKeyFormat(key) {
  if (typeof key !== "string") return invalid("Key must be a string");
  const value = key.trim();
  if (!value) return invalid("Key is empty");
  if (/\s/.test(value)) return invalid("Key must not contain whitespace");

  const free = value.endsWith(":fx");
  const body = free ? value.slice(0, -3) : value;

  if (body.length < 32) {
    return invalid(`Key is too short (${body.length} of 32 minimum characters)`);
  }
  if (!KEY_BODY.test(body)) {
    return invalid("Key contains invalid characters");
  }

  return {
    valid: true,
    tier: free ? "free" : "pro",
    host: free ? FREE_HOST : PRO_HOST,
  };
}

export function maskKey(key) {
  if (typeof key !== "string" || key.length === 0) return "";
  if (key.length < 8) return "•".repeat(key.length);
  return `${key.slice(0, 2)}…${key.slice(-2)}`;
}

export function isKeyLike(value) {
  if (typeof value !== "string" || !value) return false;
  const re = new RegExp(KEY_LIKE.source);
  return re.test(value);
}

export function redactKeys(text) {
  if (typeof text !== "string" || !text) return "";
  return text.replace(KEY_LIKE, (match) => maskKey(match));
}
