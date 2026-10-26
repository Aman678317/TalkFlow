// Context aggregation for the local demo engine.
// Extracts a compact context pack (last line, domain keywords, homograph hints)
// that the translator uses to disambiguate words such as "bank" or "bass".
import { HOMOGRAPHS, FUNCTION_WORDS } from "./lexicon.mjs";

const STOPWORDS = new Set((FUNCTION_WORDS.en || []).map((w) => w.toLowerCase()));
const TOKEN_RE = /[\p{L}\p{M}]+/gu;

function isCapitalized(token) {
  const first = token.charAt(0);
  return first !== first.toLowerCase() && first === first.toUpperCase();
}

export function lastLineOf(text) {
  if (typeof text !== "string") return "";
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : "";
}

// Capitalized or domain words from the context, lowercased, de-duplicated in
// first-seen order. Function words and very short words are dropped.
export function extractKeywords(context) {
  if (typeof context !== "string" || !context.trim()) return [];
  const seen = new Set();
  const keywords = [];
  for (const token of context.match(TOKEN_RE) || []) {
    const lower = token.toLowerCase();
    const meaningful = lower.length >= 3 || isCapitalized(token);
    if (!meaningful || STOPWORDS.has(lower) || seen.has(lower)) continue;
    seen.add(lower);
    keywords.push(lower);
  }
  return keywords;
}

// Pick the sense of a homograph whose trigger keywords appear in the context.
// Highest number of hits wins; on a tie the first sense in data order wins.
export function senseFromKeywords(word, keywords) {
  const senses = HOMOGRAPHS[word];
  if (!senses) return null;
  const haystack = new Set((keywords || []).map((k) => String(k).toLowerCase()));
  let best = null;
  let bestHits = 0;
  for (const [sense, data] of Object.entries(senses)) {
    const hits = (data.keywords || []).reduce(
      (n, kw) => n + (haystack.has(String(kw).toLowerCase()) ? 1 : 0),
      0,
    );
    if (hits > bestHits) {
      best = sense;
      bestHits = hits;
    }
  }
  return best;
}

export function buildContextPack({ text = "", context = "", glossaryEntry = null } = {}) {
  const sourceText = typeof text === "string" ? text : "";
  const contextText = typeof context === "string" ? context : "";
  const keywords = extractKeywords(contextText);
  const homographHints = [];
  if (keywords.length) {
    for (const word of Object.keys(HOMOGRAPHS)) {
      const sense = senseFromKeywords(word, keywords);
      if (sense) homographHints.push({ word, sense });
    }
  }
  // glossaryEntry is accepted for API symmetry with the translate pipeline; the
  // glossary itself is enforced by the translator, not by context keyword choice.
  void glossaryEntry;
  return {
    text: sourceText,
    pack: {
      lastLine: lastLineOf(contextText),
      keywords,
      homographHints,
    },
  };
}

export const CONTEXT_VERSION = "2.0.0";
