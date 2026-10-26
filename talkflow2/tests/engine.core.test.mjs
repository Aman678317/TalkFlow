// Engine core tests: demo translator pipeline, context pack, lexicon minimums.
import test from "node:test";
import assert from "node:assert/strict";

import { translatePipeline } from "../engine/translator.mjs";
import { buildContextPack } from "../engine/context.mjs";
import { detectLanguage } from "../engine/detect.mjs";
import {
  PHRASES,
  WORDS,
  FUNCTION_WORDS,
  HOMOGRAPHS,
  FORMALITY_HINTS,
  LANGUAGES,
} from "../engine/lexicon.mjs";

const COVERAGE_NOTE_RE = /^Demo engine: partial coverage \(\d+%\); add a DeepL API key for full quality$/;

test("phrase table translates a whole sentence with full coverage", () => {
  const result = translatePipeline("Hello", { targetLang: "de" });
  assert.equal(result.text, "Hallo");
  assert.equal(result.detectedSourceLanguage, "en");
  assert.equal(result.coverage, 1);
  assert.equal(result.usedFallback, false);
  assert.deepEqual(result.notes, []);
});

test("phrase lookup is case-insensitive, whitespace- and punctuation-tolerant", () => {
  const result = translatePipeline("  HELLO!  ", { targetLang: "de" });
  assert.equal(result.text, "Hallo!");
  assert.equal(result.coverage, 1);
});

test("phrase table works in reverse direction and auto-detects German", () => {
  const result = translatePipeline("Wie geht es dir?", { targetLang: "en" });
  assert.equal(result.text, "How are you?");
  assert.equal(result.detectedSourceLanguage, "de");
  assert.equal(result.coverage, 1);
});

test("word map preserves word count, capitalization, numbers and punctuation", () => {
  const result = translatePipeline("The price is 42 dollars!", { targetLang: "de" });
  const sourceWords = "The price is 42 dollars!".split(/\s+/);
  const targetWords = result.text.split(/\s+/);
  assert.equal(targetWords.length, sourceWords.length);
  assert.match(result.text, /^Der /);
  assert.match(result.text, /\b42\b/);
  assert.ok(result.text.endsWith("!"));
  assert.match(result.text, /Preis/);
});

test("word map covers common words (water/good) at full coverage", () => {
  const result = translatePipeline("The water is good", { targetLang: "de" });
  assert.equal(result.text, "Der Wasser ist gut");
  assert.equal(result.coverage, 1);
  assert.equal(result.usedFallback, false);
});

test("partial coverage below 0.6 sets usedFallback and pushes honest note", () => {
  const result = translatePipeline("The quantum flux is beautiful", { targetLang: "de" });
  assert.ok(result.coverage < 0.6, `coverage ${result.coverage}`);
  assert.equal(result.usedFallback, true);
  assert.equal(result.notes.length, 1);
  assert.match(result.notes[0], COVERAGE_NOTE_RE);
});

test("partial coverage above 0.6 still notes without fallback", () => {
  const result = translatePipeline("The beautiful water is wonderful", { targetLang: "de" });
  assert.ok(result.coverage >= 0.6 && result.coverage < 1, `coverage ${result.coverage}`);
  assert.equal(result.usedFallback, false);
  assert.equal(result.notes.length, 1);
  assert.match(result.notes[0], COVERAGE_NOTE_RE);
});

test("pipeline is deterministic (identical input gives identical output)", () => {
  const input = "The bank is good.";
  const a = translatePipeline(input, { context: "We walked along the river.", targetLang: "de" });
  const b = translatePipeline(input, { context: "We walked along the river.", targetLang: "de" });
  assert.deepEqual(a, b);
  assert.equal(JSON.stringify(a), JSON.stringify(b));
});

test("auto-detect English", () => {
  const result = translatePipeline("Hello", { sourceLang: "auto", targetLang: "de" });
  assert.equal(result.detectedSourceLanguage, "en");
  assert.equal(result.text, "Hallo");
});

test("auto-detect Japanese (kana)", () => {
  const result = translatePipeline("こんにちは", { targetLang: "en" });
  assert.equal(result.detectedSourceLanguage, "ja");
  assert.equal(result.text, "Hello");
});

test("auto-detect Chinese (CJK)", () => {
  const result = translatePipeline("你好", { targetLang: "en" });
  assert.equal(result.detectedSourceLanguage, "zh");
  assert.equal(result.text, "Hello");
});

test("auto-detect Hindi (Devanagari)", () => {
  const result = translatePipeline("नमस्ते", { targetLang: "en" });
  assert.equal(result.detectedSourceLanguage, "hi");
  assert.equal(result.text, "Hello");
});

test("context keywords resolve the river sense of 'bank'", () => {
  const result = translatePipeline("The bank is good.", {
    targetLang: "de",
    context: "We walked along the river shore.",
  });
  assert.match(result.text, /Ufer/);
  assert.doesNotMatch(result.text, /\bBank\b/);
  const translatorStep = result.agentTrace.find((s) => s.agent === "translator");
  assert.match(translatorStep.decision, /bank→river/);
});

test("context keywords resolve the finance sense of 'bank'", () => {
  const result = translatePipeline("The bank is good.", {
    targetLang: "de",
    context: "Please check the money and the loan.",
  });
  assert.match(result.text, /Bank/);
  assert.doesNotMatch(result.text, /Ufer/);
});

test("glossary entry is protected inline and restored as the target term", () => {
  const glossaryEntry = {
    sourceTerm: "bank account",
    targetTerm: "Bankkonto",
    sourceLang: "en",
    targetLang: "de",
  };
  const result = translatePipeline("The bank account is closed.", {
    targetLang: "de",
    glossaryEntry,
  });
  assert.match(result.text, /Bankkonto/);
  assert.doesNotMatch(result.text, /⟦/);
  assert.doesNotMatch(result.text, /bank account/i);
  const glossaryStep = result.agentTrace.find((s) => s.agent === "glossary");
  assert.match(glossaryStep.decision, /protected/);
});

test("existing glossary placeholders survive inline protection", () => {
  const result = translatePipeline("The ⟦g1⟧ is good.", {
    targetLang: "de",
    glossaryEntry: { sourceTerm: "good", targetTerm: "prima" },
  });
  assert.match(result.text, /⟦g1⟧/);
  assert.match(result.text, /prima/);
  assert.doesNotMatch(result.text, /⟦g2⟧/);
});

test("formality replacement applies register-specific pronouns", () => {
  const informal = translatePipeline("you are good", { targetLang: "de", formality: "informal" });
  const formal = translatePipeline("you are good", { targetLang: "de", formality: "formal" });
  assert.match(informal.text, /^du /);
  assert.doesNotMatch(informal.text, /Sie/);
  assert.match(formal.text, /^Sie /);
  assert.notEqual(informal.text, formal.text);
  assert.equal(informal.coverage, 1);
});

test("charsBilled counts source characters, not translated output", () => {
  assert.equal(translatePipeline("Hello", { targetLang: "de" }).charsBilled, 5);
  assert.equal(translatePipeline("  hello!  ", { targetLang: "de" }).charsBilled, 10);
  assert.equal(translatePipeline("こんにちは", { targetLang: "en" }).charsBilled, 5);
});

test("result shape and agent trace are well formed", () => {
  const result = translatePipeline("Hello", { targetLang: "de" });
  assert.deepEqual(Object.keys(result).sort(), [
    "agentTrace",
    "charsBilled",
    "coverage",
    "detectedSourceLanguage",
    "notes",
    "text",
    "usedFallback",
  ]);
  assert.ok(Array.isArray(result.agentTrace) && result.agentTrace.length >= 5);
  for (const step of result.agentTrace) {
    assert.equal(typeof step.agent, "string");
    assert.ok(step.agent.length > 0);
    assert.equal(typeof step.decision, "string");
    assert.equal(typeof step.ms, "number");
  }
  const agents = new Set(result.agentTrace.map((s) => s.agent));
  for (const expected of ["detector", "context", "glossary", "translator", "formality", "quality-guard"]) {
    assert.ok(agents.has(expected), `missing agent ${expected}`);
  }
  assert.ok(Array.isArray(result.notes));
  assert.equal(typeof result.coverage, "number");
  assert.equal(typeof result.usedFallback, "boolean");
});

test("engine never invents translations for unknown words", () => {
  const result = translatePipeline("The quantum flux is beautiful", { targetLang: "de" });
  assert.match(result.text, /\bquantum\b/);
  assert.match(result.text, /\bflux\b/);
});

test("buildContextPack returns last line, keywords and homograph hints", () => {
  const { text, pack } = buildContextPack({
    text: "The bank is closed.",
    context: "We met at the river shore.\nThe water was cold.",
  });
  assert.equal(text, "The bank is closed.");
  assert.equal(pack.lastLine, "The water was cold.");
  assert.ok(pack.keywords.includes("river"));
  assert.ok(pack.keywords.includes("shore"));
  assert.deepEqual(pack.homographHints, [{ word: "bank", sense: "river" }]);
});

test("buildContextPack handles empty context", () => {
  const { pack } = buildContextPack({ text: "Hello" });
  assert.deepEqual(pack, { lastLine: "", keywords: [], homographHints: [] });
});

test("detectLanguage keeps the spec return shape and short-text behavior", () => {
  const result = detectLanguage("Hi");
  assert.deepEqual(Object.keys(result).sort(), ["confidence", "lang", "scores", "status"]);
  assert.equal(result.status, "insufficient_confidence");
  assert.ok(result.confidence >= 0 && result.confidence <= 1);
  assert.ok(LANGUAGES.includes(result.lang));
  const none = detectLanguage("");
  assert.equal(none.status, "no_language_detected");
  const german = detectLanguage("Der Hund und die Katze sind sehr schön.");
  assert.equal(german.lang, "de");
  assert.equal(german.status, "success");
});

test("lexicon meets spec minimums and keeps homograph keyword triggers", () => {
  assert.ok(Object.keys(PHRASES).length >= 20, "PHRASES >= 20");
  assert.ok(Object.keys(WORDS).length >= 120, "WORDS >= 120");
  for (const lang of LANGUAGES) {
    assert.ok(Array.isArray(FUNCTION_WORDS[lang]), `FUNCTION_WORDS.${lang} missing`);
    assert.ok(FUNCTION_WORDS[lang].length >= 20, `FUNCTION_WORDS.${lang} >= 20`);
  }
  assert.ok(Object.keys(HOMOGRAPHS).length >= 3, "HOMOGRAPHS >= 3");
  for (const [word, senses] of Object.entries(HOMOGRAPHS)) {
    assert.ok(Object.keys(senses).length >= 2, `${word} needs two senses`);
    for (const [sense, data] of Object.entries(senses)) {
      assert.ok(Array.isArray(data.keywords) && data.keywords.length > 0, `${word}.${sense} keywords`);
      for (const lang of LANGUAGES.filter((l) => l !== "en")) {
        assert.equal(typeof data[lang], "string", `${word}.${sense}.${lang}`);
      }
    }
  }
  assert.deepEqual(FORMALITY_HINTS.you.de, { informal: "du", formal: "Sie" });
});
