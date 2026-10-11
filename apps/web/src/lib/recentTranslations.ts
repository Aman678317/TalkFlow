/**
 * Client-side recent translations for the /translate workspace.
 *
 * Mirrors the convenience of a "recent translations" strip without any
 * server coupling: entries live in localStorage and are best-effort (a
 * failed write must never break translating). Original implementation.
 */

export const RECENTS_KEY = "globaltalk.recentTranslations.v1";
export const RECENTS_LIMIT = 8;

export interface RecentTranslation {
  sourceText: string;
  translatedText: string;
  srcLang: string;
  tgtLang: string;
  ts: number;
}

function sameEntry(a: RecentTranslation, b: RecentTranslation): boolean {
  return (
    a.srcLang === b.srcLang &&
    a.tgtLang === b.tgtLang &&
    a.sourceText.toLowerCase() === b.sourceText.toLowerCase()
  );
}

/** Insert `entry` at the front, drop duplicates of the same language-pair +
 *  source text, and cap the list. Pure — safe to unit test. */
export function withRecent(
  prev: RecentTranslation[],
  entry: RecentTranslation,
  limit: number = RECENTS_LIMIT,
): RecentTranslation[] {
  return [entry, ...prev.filter((r) => !sameEntry(r, entry))].slice(0, limit);
}

export function loadRecents(): RecentTranslation[] {
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (r): r is RecentTranslation =>
        r && typeof r.sourceText === "string" && typeof r.translatedText === "string",
    ).slice(0, RECENTS_LIMIT);
  } catch {
    return [];
  }
}

export function saveRecents(items: RecentTranslation[]): void {
  try {
    localStorage.setItem(RECENTS_KEY, JSON.stringify(items.slice(0, RECENTS_LIMIT)));
  } catch {
    /* storage full or unavailable — recents are best-effort */
  }
}

export function relativeTime(ts: number, now: number = Date.now()): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}
