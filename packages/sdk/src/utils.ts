/**
 * Shared utilities — internal helpers used across the SDK.
 *
 * Diagram layer: Shared Internals [utils.ts]
 *
 * Nothing in this file is part of the public API surface.
 * Re-export nothing from index.ts.
 */

/** Promise-based sleep. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Calculate exponential back-off delay.
 *
 * @param attempt  Zero-indexed retry attempt (0 = first retry).
 * @param baseMs   Base delay in ms (default 400).
 * @param capMs    Maximum delay cap in ms (default 30 000).
 */
export function backoffMs(attempt: number, baseMs = 400, capMs = 30_000): number {
  return Math.min(baseMs * 2 ** attempt, capMs);
}

/**
 * Build a URL query string from a params object.
 * Skips `undefined` and `null` values. Arrays are repeated: `key=a&key=b`.
 */
export function buildQuery(params: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const v of value) parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(v))}`);
    } else {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
    }
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

/**
 * Validate a language code (ISO 639-1 or BCP-47 with region).
 * Returns true for "AUTO" (case-insensitive), "en", "EN", "en-US", "zh-CN", etc.
 */
export function isValidLanguageCode(code: string): boolean {
  if (!code) return false;
  if (code.toUpperCase() === "AUTO") return true;
  return /^[a-zA-Z]{2,3}(-[a-zA-Z]{2,3})?$/.test(code);
}

/** Normalise a language code to uppercase (e.g. "en-us" → "EN-US"). */
export function normaliseLang(code: string): string {
  if (!code) return code;
  if (code.toUpperCase() === "AUTO") return "AUTO";
  return code.toUpperCase();
}

/**
 * Consume a Node.js `ReadableStream` or `AsyncIterable<Uint8Array>` into a Buffer.
 * Used when the API returns the translated document as a streaming response body.
 */
export async function streamToBuffer(
  stream: AsyncIterable<Uint8Array>,
): Promise<Buffer> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

/**
 * Create an AbortSignal that fires after `ms` milliseconds.
 * Polyfill for environments where `AbortSignal.timeout()` is not available.
 */
export function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

/** Safely parse a JSON string; return `null` on failure. */
export function safeJson(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text) as unknown;
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}
