// Language auto-detection: script ranges first, then Latin function-word scoring.
import { FUNCTION_WORDS } from "./lexicon.mjs";

export const SUPPORTED = ["en", "de", "fr", "es", "it", "pt", "hi", "ja", "zh"];

const SCRIPTS = [
  { lang: "ja", re: /[\u3040-\u309f\u30a0-\u30ff]/gu, weight: 2 },
  { lang: "zh", re: /[\u4e00-\u9fff]/gu, weight: 2 },
  { lang: "hi", re: /[\u0900-\u097f]/gu, weight: 2 },
];

const DIACRITICS = {
  de: { re: /[äöüßÄÖÜ]/g, weight: 3 },
  fr: { re: /[àâçéèêëîïôùûœÀÂÇÉÈÊËÎÏÔÙÛ]/g, weight: 1 },
  es: { re: /[áéíñóúü¿¡ÁÉÍÑÓÚÜ]/g, weight: 1 },
  it: { re: /[àèéìòùÀÈÌÒÙ]/g, weight: 1 },
  pt: { re: /[ãõáâêçÃÕÁÂÊÇ]/g, weight: 1 },
};

function tokenize(text) {
  return text.toLowerCase().match(/[\p{L}\p{M}]+/gu) || [];
}

export function detectLanguage(text) {
  const result = {
    lang: null,
    confidence: 0,
    status: "no_language_detected",
    scores: Object.fromEntries(SUPPORTED.map((l) => [l, 0])),
  };
  if (typeof text !== "string") return result;
  const trimmed = text.trim();
  if (!trimmed) return result;

  // 1) Script detection wins outright.
  let scriptFound = false;
  for (const s of SCRIPTS) {
    const hits = (trimmed.match(s.re) || []).length;
    if (hits > 0) {
      result.lang = s.lang;
      result.scores[s.lang] = Math.min(1, hits * s.weight);
      scriptFound = true;
      break;
    }
  }
  if (scriptFound) {
    result.confidence = Math.min(0.99, 0.75 + Math.min(0.24, result.scores[result.lang] / 10));
    result.status = "success";
    return result;
  }

  // 2) Latin scoring: function-word matches + diacritic boosts.
  const tokens = tokenize(trimmed);
  for (const lang of SUPPORTED) {
    const set = FUNCTION_WORDS[lang] || [];
    let hits = 0;
    for (const t of tokens) if (set.includes(t)) hits++;
    result.scores[lang] = hits;
  }
  for (const [lang, d] of Object.entries(DIACRITICS)) {
    const hits = (trimmed.match(d.re) || []).length;
    if (hits > 0) result.scores[lang] += hits * d.weight;
  }

  const ranked = SUPPORTED.map((l) => [l, result.scores[l]]).sort((a, b) => b[1] - a[1]);
  const [topLang, top] = ranked[0];
  const second = ranked[1] ? ranked[1][1] : 0;

  if (top === 0) {
    // No signal at all.
    if (trimmed.length <= 12) {
      result.lang = "en";
      result.status = "insufficient_confidence";
      result.confidence = 0.3;
    } else {
      result.status = "no_language_detected";
    }
    return result;
  }

  if (trimmed.length <= 12) {
    result.lang = result.scores[topLang] > 0 ? topLang : null;
    result.status = "insufficient_confidence";
    result.confidence = Math.min(0.45, 0.25 + top * 0.05);
    if (!result.lang) result.status = "no_language_detected";
    return result;
  }

  const ratio = second === 0 ? 1 : top / (top + second);
  result.lang = topLang;
  result.confidence = Math.max(0.35, Math.min(0.99, 0.35 + 0.64 * ratio));
  result.status = "success";
  return result;
}
