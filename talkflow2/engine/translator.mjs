// Deterministic offline translation pipeline for the TalkFlow 2.0 demo engine.
// Order of operations: detect -> context pack -> glossary protection ->
// whole-phrase table -> word map (homographs + formality) -> coverage gate.
import { PHRASES, WORDS, HOMOGRAPHS, FORMALITY_HINTS, LANGUAGES } from "./lexicon.mjs";
import { detectLanguage } from "./detect.mjs";
import { buildContextPack, senseFromKeywords } from "./context.mjs";

const PLACEHOLDER_RE = /⟦g\d+⟧/u;
const PLACEHOLDER_ALL_RE = /⟦g\d+⟧/gu;
const TOKEN_RE = /⟦g\d+⟧|\p{L}[\p{L}\p{M}'’-]*|\p{N}+|\s+|[^\s\p{L}\p{M}\p{N}]/gu;
const WORD_RE = /^\p{L}[\p{L}\p{M}'’-]*$/u;
const PUNCT_RE = /[.,!?;:¿¡。！？、，；：""''«»()\[\]{}…—–-]/gu;
const TRAILING_PUNCT_RE = /([.!?。！？])\s*$/u;
const HAS_END_PUNCT_RE = /[.!?。！？]\s*$/u;

function countLetters(value) {
  return (String(value).match(/\p{L}/gu) || []).length;
}

function normalizePhrase(value) {
  return String(value)
    .toLowerCase()
    .replace(PUNCT_RE, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Phrase indexes are built once and are deterministic (insertion order wins).
const PHRASE_BY_LANG = Object.fromEntries(LANGUAGES.map((lang) => [lang, new Map()]));
const PHRASE_ANY = new Map();
for (const [key, entry] of Object.entries(PHRASES)) {
  for (const lang of LANGUAGES) {
    const value = entry[lang];
    if (typeof value !== "string" || !value.trim()) continue;
    const normalized = normalizePhrase(value);
    if (!normalized) continue;
    if (!PHRASE_BY_LANG[lang].has(normalized)) {
      PHRASE_BY_LANG[lang].set(normalized, { key, entry, matchedLang: lang });
    }
    if (!PHRASE_ANY.has(normalized)) {
      PHRASE_ANY.set(normalized, { key, entry, matchedLang: lang });
    }
  }
}

function lookupPhrase(text, sourceLang) {
  const normalized = normalizePhrase(text);
  if (!normalized) return null;
  const own = PHRASE_BY_LANG[sourceLang] && PHRASE_BY_LANG[sourceLang].get(normalized);
  return own || PHRASE_ANY.get(normalized) || null;
}

function withTerminalPunctuation(target, sourceText) {
  if (typeof target !== "string") return "";
  const trailing = sourceText.match(TRAILING_PUNCT_RE);
  if (!trailing || HAS_END_PUNCT_RE.test(target)) return target;
  return target + trailing[1];
}

function applyCase(target, sourceToken) {
  if (typeof target !== "string" || !target) return target;
  const letters = sourceToken.match(/\p{L}/gu) || [];
  if (!letters.length) return target;
  const upper = (c) => c === c.toUpperCase() && c !== c.toLowerCase();
  if (letters.length > 1 && letters.every((c) => c === c.toUpperCase() && c !== c.toLowerCase())) {
    return target.toUpperCase();
  }
  if (upper(letters[0])) return target.charAt(0).toUpperCase() + target.slice(1);
  return target;
}

function normalizeLang(value) {
  if (typeof value !== "string") return null;
  const lower = value.trim().toLowerCase();
  return LANGUAGES.includes(lower) ? lower : null;
}

function normalizeFormality(value) {
  const raw = typeof value === "string" ? value.trim().toLowerCase() : "default";
  if (raw === "formal" || raw === "more") return "formal";
  if (raw === "informal" || raw === "less") return "informal";
  return "default";
}

// --- glossary protection (single inline entry; glossary.mjs is not imported) ---

function protectGlossary(text, glossaryEntry) {
  const result = { text, count: 0, coveredLetters: 0, map: new Map(), term: "", token: "" };
  if (!glossaryEntry || typeof glossaryEntry !== "object") return result;
  const sourceTerm =
    typeof glossaryEntry.sourceTerm === "string"
      ? glossaryEntry.sourceTerm
      : typeof glossaryEntry.term === "string"
        ? glossaryEntry.term
        : "";
  const targetTerm =
    typeof glossaryEntry.targetTerm === "string"
      ? glossaryEntry.targetTerm
      : typeof glossaryEntry.translation === "string"
        ? glossaryEntry.translation
        : "";
  if (!sourceTerm.trim() || !targetTerm.trim()) return result;

  const escaped = sourceTerm.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let re;
  try {
    re = new RegExp(`(?<![\\p{L}\\p{M}])${escaped}(?![\\p{L}\\p{M}])`, "giu");
  } catch {
    return result;
  }
  // Pick a token id that does not collide with placeholders already in the text
  // (e.g. ones produced by engine/glossary.mjs applyPre).
  const used = new Set([...text.matchAll(PLACEHOLDER_ALL_RE)].map((m) => m[0]));
  let id = 1;
  while (used.has(`⟦g${id}⟧`)) id += 1;
  const token = `⟦g${id}⟧`;

  let covered = 0;
  let hits = 0;
  const protectedText = text.replace(re, (match) => {
    hits += 1;
    covered += countLetters(match);
    return token;
  });
  if (!hits) return result;
  result.text = protectedText;
  result.count = hits;
  result.coveredLetters = covered;
  result.term = sourceTerm.trim();
  result.token = token;
  result.map.set(token, targetTerm);
  return result;
}

function restoreGlossary(text, map) {
  if (!map || map.size === 0) return text;
  let out = text;
  for (const [token, target] of map) out = out.split(token).join(target);
  return out;
}

// --- word-level translation ---

function translateWords(text, { targetLang, formalityMode, hints, keywords }) {
  const tokens = text.match(TOKEN_RE) || [];
  const hintMap = new Map((hints || []).map((h) => [h.word, h.sense]));
  let out = "";
  let coveredLetters = 0;
  let translatedWords = 0;
  let totalWords = 0;
  let formalityUsed = 0;
  const homographs = [];

  for (const token of tokens) {
    if (PLACEHOLDER_RE.test(token) || !WORD_RE.test(token)) {
      out += token;
      continue;
    }
    totalWords += 1;
    const lower = token.toLowerCase();
    let replacement = null;

    const hint = hintMap.get(lower) || senseFromKeywords(lower, keywords) || null;
    if (hint) {
      const sense = HOMOGRAPHS[lower] && HOMOGRAPHS[lower][hint];
      if (sense && typeof sense[targetLang] === "string") {
        replacement = sense[targetLang];
        homographs.push(`${lower}→${hint}`);
      }
    }
    if (replacement === null && formalityMode !== "default") {
      const formal = FORMALITY_HINTS[lower];
      const variant = formal && formal[targetLang] ? formal[targetLang][formalityMode] : null;
      if (typeof variant === "string") {
        replacement = variant;
        formalityUsed += 1;
      }
    }
    if (replacement === null) {
      const entry = WORDS[lower];
      if (entry && typeof entry[targetLang] === "string") replacement = entry[targetLang];
    }
    if (replacement === null) {
      out += token;
      continue;
    }
    translatedWords += 1;
    coveredLetters += countLetters(token);
    out += applyCase(replacement, token);
  }

  return { text: out, coveredLetters, translatedWords, totalWords, formalityUsed, homographs };
}

export function translatePipeline(text, options = {}) {
  const input = typeof text === "string" ? text : text == null ? "" : String(text);
  const opts = options && typeof options === "object" ? options : {};
  const targetLang = normalizeLang(opts.targetLang) || "de";
  const requestedSource =
    typeof opts.sourceLang === "string" ? opts.sourceLang.trim().toLowerCase() : "auto";
  const formalityMode = normalizeFormality(opts.formality);
  const contextText = typeof opts.context === "string" ? opts.context : "";
  const glossaryEntry =
    opts.glossaryEntry && typeof opts.glossaryEntry === "object" ? opts.glossaryEntry : null;

  const agentTrace = [];
  const note = (agent, decision) => agentTrace.push({ agent, decision, ms: 0 });

  if (!input.trim()) {
    note("detector", "empty input — nothing to translate");
    note("quality-guard", "coverage 0%; no fallback");
    return {
      text: "",
      detectedSourceLanguage: normalizeLang(requestedSource) || "",
      coverage: 0,
      usedFallback: false,
      notes: [],
      charsBilled: 0,
      agentTrace,
    };
  }

  // (1) Detection (only when sourceLang is "auto", per spec).
  let sourceLang;
  if (requestedSource === "auto" || !LANGUAGES.includes(requestedSource)) {
    const detected = detectLanguage(input);
    sourceLang = detected.lang || "en";
    note(
      "detector",
      `auto → ${sourceLang} (confidence ${detected.confidence}, ${detected.status})`,
    );
  } else {
    sourceLang = requestedSource;
    note("detector", `provided source language ${sourceLang}`);
  }

  const charsBilled = [...input].length;

  if (sourceLang === targetLang) {
    note("translator", "source equals target — passthrough");
    note("quality-guard", "coverage 100%; no fallback");
    return {
      text: input,
      detectedSourceLanguage: sourceLang,
      coverage: 1,
      usedFallback: false,
      notes: [],
      charsBilled,
      agentTrace,
    };
  }

  // (2) Context pack (keywords + homograph hints).
  const { pack } = buildContextPack({ text: input, context: contextText, glossaryEntry });
  const hintLabel = pack.homographHints.map((h) => `${h.word}:${h.sense}`).join(", ");
  note(
    "context",
    pack.keywords.length
      ? `context keywords ${pack.keywords.length}${hintLabel ? `; homograph hints ${hintLabel}` : ""}`
      : "no context provided",
  );

  // (3) Glossary protection (inline placeholder, restored after translation).
  const protection = protectGlossary(input, glossaryEntry);
  if (protection.count) {
    note(
      "glossary",
      `protected "${protection.term}" → ${protection.token} (${protection.count} occurrence${protection.count === 1 ? "" : "s"})`,
    );
  } else {
    note("glossary", glossaryEntry ? "glossary term not present in source" : "no glossary entry");
  }

  const totalLetters = countLetters(input);
  let coveredLetters = protection.coveredLetters;
  let output;
  let homographs = [];
  let formalityUsed = 0;

  // (4) Whole-phrase table first, then the word map.
  const phrase = protection.count ? null : lookupPhrase(protection.text, sourceLang);
  const phraseTarget = phrase ? phrase.entry[targetLang] : null;
  if (phrase && typeof phraseTarget === "string") {
    output = withTerminalPunctuation(phraseTarget, protection.text);
    coveredLetters = totalLetters;
    note("translator", `phrase-table hit "${phrase.key}" (${phrase.matchedLang})`);
  } else {
    const mapped = translateWords(protection.text, {
      targetLang,
      formalityMode,
      hints: pack.homographHints,
      keywords: pack.keywords,
    });
    output = mapped.text;
    coveredLetters += mapped.coveredLetters;
    homographs = mapped.homographs;
    formalityUsed = mapped.formalityUsed;
    note(
      "translator",
      `word-map ${mapped.translatedWords}/${mapped.totalWords} words` +
        (homographs.length ? `; homographs ${homographs.join(", ")}` : ""),
    );
  }

  output = restoreGlossary(output, protection.map);

  // (5) Formality trace.
  if (phrase) {
    note("formality", "phrase-table output used as-is");
  } else if (formalityMode !== "default") {
    note(
      "formality",
      formalityUsed
        ? `applied ${formalityMode} register (${formalityUsed} pronoun${formalityUsed === 1 ? "" : "s"})`
        : `${formalityMode} register requested; no affected pronouns`,
    );
  } else {
    note("formality", "default register");
  }

  // (6) Coverage gate + honest notes.
  let coverage = totalLetters ? Math.round((coveredLetters / totalLetters) * 1000) / 1000 : 0;
  coverage = Math.max(0, Math.min(1, coverage));
  const usedFallback = coverage < 0.6;
  const notes = [];
  if (coverage < 1) {
    const pct = Math.min(99, Math.round(coverage * 100));
    notes.push(`Demo engine: partial coverage (${pct}%); add a DeepL API key for full quality`);
  }
  note(
    "quality-guard",
    `coverage ${Math.round(coverage * 100)}%${usedFallback ? "; fallback recommended" : "; no fallback"}`,
  );

  return {
    text: output,
    detectedSourceLanguage: sourceLang,
    coverage,
    usedFallback,
    notes,
    charsBilled,
    agentTrace,
  };
}
