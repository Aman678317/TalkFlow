/**
 * Honest word-diff percentage for the Write panel.
 *
 * The panel used to render "(N% word diff)" from a WORD-COUNT delta:
 * `(improved words - original words) / original words`. For the most common
 * case — spelling and grammar fixes — the word count does not change, so a
 * draft with five applied corrections reported "0% word diff" while the
 * panel right above it said "5 improvements applied" (2026-10-20 localhost
 * audit).
 *
 * This computes the real share of words that changed: everything outside the
 * longest common subsequence of the two texts, relative to the original word
 * count. A replacement ("recieved" -> "received") counts as one changed
 * word; an insertion or a deletion counts as one too.
 */

function tokenize(text: string): string[] {
  return (text || "").trim().split(/\s+/).filter(Boolean);
}

/** Length of the longest common subsequence (rolling two-row DP). */
function lcsLength(a: string[], b: string[]): number {
  let prev = new Array<number>(b.length + 1).fill(0);
  let cur = new Array<number>(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    cur[0] = 0;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    const swap = prev;
    prev = cur;
    cur = swap;
  }
  return prev[b.length];
}

/** Share of the original words that are not part of the common subsequence. */
export function wordDiffPercent(original: string, improved: string): number {
  const a = tokenize(original);
  const b = tokenize(improved);
  if (a.length === 0) return b.length === 0 ? 0 : 100;
  if (a.length * b.length > 250_000) {
    // Guard for very long drafts: fall back to a positional comparison
    // instead of an O(n*m) DP.
    let changed = Math.abs(a.length - b.length);
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      if (a[i] !== b[i]) changed++;
    }
    return Math.round((changed / a.length) * 100);
  }
  const common = lcsLength(a, b);
  const changed = Math.max(a.length, b.length) - common;
  return Math.round((changed / a.length) * 100);
}
