/**
 * Client-side preparation of a pasted web-page URL.
 *
 * The server does the real validation (scheme, public-address resolution,
 * size cap, redirects). This only helps the user: it turns what people
 * actually paste into a usable URL and refuses the obvious nonsense before a
 * round trip.
 */

/** Normalise a pasted URL, or return null when it cannot be one. */
export function normalizePageUrl(input: string): string | null {
  const raw = (input || "").trim();
  if (!raw) return null;
  // People paste "example.com/article" far more often than a full URL.
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(raw) ? raw : `https://${raw}`;
  let parsed: URL;
  try {
    parsed = new URL(withScheme);
  } catch {
    return null;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  if (!parsed.hostname || !parsed.hostname.includes(".")) return null;
  return parsed.toString();
}

/** Why a pasted URL cannot be used (null when it is fine). */
export function pageUrlProblem(input: string): string | null {
  const raw = (input || "").trim();
  if (!raw) return "Paste a link to the page you want translated.";
  if (normalizePageUrl(raw) === null) {
    return "That does not look like a web address — use something like https://example.com/article";
  }
  return null;
}
