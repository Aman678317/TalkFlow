// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

import { LanguageCache } from "./languages.mjs";
import { mcpContentifyText, standardizeLangCase } from "./content.mjs";
import { writingStyles, writingTones } from "./writing.mjs";

export function createHandlers(desiClient) {
  const languages = new LanguageCache(desiClient);

  // ------------------------------------------------------------------------------------------------
  // Indic-Native Handlers
  // ------------------------------------------------------------------------------------------------

  async function translateDesi({
    text,
    targetLang,
    sourceLang = "en",
    honorific = "formal",
    domain = "general",
    respectfulSuffix = false,
  }) {
    try {
      const res = await desiClient.translateDesi({
        text,
        targetLang,
        sourceLang,
        honorific,
        domain,
        respectfulSuffix,
      });

      const translations = res.translations || [];
      const lines = [];
      for (const t of translations) {
        lines.push(t.text);
        lines.push(`Target language: ${t.target_lang} (${t.script} script)`);
        lines.push(`Honorific applied: ${t.honorific_applied}`);
        lines.push(`Domain register: ${t.domain}`);
      }
      return mcpContentifyText(lines);
    } catch (error) {
      throw new Error(`Desi translation failed: ${error.message}`, { cause: error });
    }
  }

  async function transliterateDesi({
    text,
    sourceScript = "latin",
    targetScript = "devanagari",
  }) {
    try {
      const res = await desiClient.transliterateDesi({ text, sourceScript, targetScript });
      const results = res.results || [];
      const lines = results.map(
        (r) => `${r.transliterated_text} [${r.source_script} → ${r.target_script}]`
      );
      return mcpContentifyText(lines);
    } catch (error) {
      throw new Error(`Transliteration failed: ${error.message}`, { cause: error });
    }
  }

  async function normalizeDesi({ text, cleanZwnj = true, fixNuktas = true }) {
    try {
      const res = await desiClient.normalizeDesi({ text, cleanZwnj, fixNuktas });
      return mcpContentifyText([
        `Normalized: ${res.normalized_text}`,
        `Original: ${res.original_text}`,
        `Corrections applied: ${res.corrections_count}`,
        `Script detected: ${res.script}`,
      ]);
    } catch (error) {
      throw new Error(`Unicode normalization failed: ${error.message}`, { cause: error });
    }
  }

  async function getDesiLanguages() {
    try {
      const res = await desiClient.getDesiLanguages();
      const list = res.languages || [];
      const formatted = list.map((l) =>
        `${l.name} (${l.native_name}) - Code: ${l.code}, Script: ${l.script} (${l.script_code}), Family: ${l.family}`
      );
      return mcpContentifyText(formatted);
    } catch (error) {
      throw new Error(`Failed to get Desi languages: ${error.message}`, { cause: error });
    }
  }

  // ------------------------------------------------------------------------------------------------
  // Standard Translation & Language Handlers
  // ------------------------------------------------------------------------------------------------

  async function getSourceLanguages() {
    try {
      const sourceLanguages = await languages.get("source");
      return mcpContentifyText(sourceLanguages.list.map((lang) => JSON.stringify(lang)));
    } catch (error) {
      throw new Error(`Failed to get source languages: ${error.message}`, { cause: error });
    }
  }

  async function getTargetLanguages() {
    try {
      const targetLanguages = await languages.get("target");
      return mcpContentifyText(targetLanguages.list.map((lang) => JSON.stringify(lang)));
    } catch (error) {
      throw new Error(`Failed to get target languages: ${error.message}`, { cause: error });
    }
  }

  async function translateText({
    text,
    sourceLangCode = null,
    targetLangCode,
    formality,
    glossaryId,
    styleId,
    context,
    preserveFormatting,
    splitSentences,
    customInstructions,
  }) {
    if (sourceLangCode) {
      const sourceLanguages = await languages.get("source");
      sourceLangCode = sourceLanguages.normalize(sourceLangCode);
    }

    const targetLanguages = await languages.get("target");
    targetLangCode = targetLanguages.normalize(targetLangCode);

    try {
      const options = { formality };
      if (glossaryId) options.glossary = glossaryId;
      if (styleId) options.styleRule = styleId;
      if (context) options.context = context;
      if (preserveFormatting !== undefined) options.preserveFormatting = preserveFormatting;
      if (splitSentences) options.splitSentences = splitSentences;
      if (customInstructions) options.customInstructions = customInstructions;

      const translations = await desiClient.translateText(text, sourceLangCode, targetLangCode, options);
      const detectedSourceLangs = [...new Set(translations.map((t) => t.detectedSourceLang))];

      return mcpContentifyText([
        ...translations.map((t) => t.text),
        `Detected source language${detectedSourceLangs.length > 1 ? "s" : ""}: ${detectedSourceLangs.join(", ")}`,
        `Target language used: ${targetLangCode}`,
      ]);
    } catch (error) {
      throw new Error(`Translation failed: ${error.message}`, { cause: error });
    }
  }

  async function rephraseText({ text, targetLangCode, style, tone }) {
    if (targetLangCode) {
      const targetLanguages = await languages.get("target");
      targetLangCode = standardizeLangCase(targetLanguages.normalize(targetLangCode));
    }

    try {
      const rephrasings = await desiClient.rephraseText(text, targetLangCode ?? null, style, tone);
      return mcpContentifyText(rephrasings.map((r) => r.text));
    } catch (error) {
      throw new Error(`Rephrasing failed: ${error.message}`, { cause: error });
    }
  }

  async function correctText({ text, targetLangCode }) {
    if (targetLangCode) {
      const targetLanguages = await languages.get("target");
      targetLangCode = standardizeLangCase(targetLanguages.normalize(targetLangCode));
    }

    try {
      const corrections = await desiClient.correctText(text, targetLangCode ?? null);
      return mcpContentifyText(corrections.map((c) => c.text));
    } catch (error) {
      throw new Error(`Correction failed: ${error.message}`, { cause: error });
    }
  }

  async function getWritingStyles() {
    return mcpContentifyText(writingStyles);
  }

  async function getWritingTones() {
    return mcpContentifyText(writingTones);
  }

  async function translateDocument({
    inputFile,
    outputFile,
    sourceLangCode,
    targetLangCode,
    formality,
    glossaryId,
    styleId,
    outputFormat,
  }) {
    if (sourceLangCode) {
      const sourceLanguages = await languages.get("source");
      sourceLangCode = sourceLanguages.normalize(sourceLangCode);
    }

    const targetLanguages = await languages.get("target");
    targetLangCode = targetLanguages.normalize(targetLangCode);

    if (!outputFile) {
      const path = await import("node:path");
      const parsedPath = path.parse(inputFile);
      const extension = outputFormat ? `.${outputFormat.toLowerCase()}` : parsedPath.ext;
      outputFile = path.join(parsedPath.dir, `${parsedPath.name}_${targetLangCode}${extension}`);
    }

    try {
      const options = { formality, glossary: glossaryId, styleRule: styleId, outputFormat };
      const result = await desiClient.translateDocument(inputFile, outputFile, sourceLangCode, targetLangCode, options);

      return mcpContentifyText([
        `Document translated successfully! Status: ${result.status}`,
        `Target language used: ${targetLangCode}`,
        `Characters billed: ${result.billedCharacters}`,
        `Output file: ${outputFile}`,
      ]);
    } catch (error) {
      throw new Error(`Document translation failed: ${error.message}`, { cause: error });
    }
  }

  async function listGlossaries() {
    try {
      const glossaries = await desiClient.listMultilingualGlossaries();
      if (glossaries.length === 0) return mcpContentifyText("No glossaries found");
      return mcpContentifyText(glossaries.map((g) => JSON.stringify(g, null, 2)));
    } catch (error) {
      throw new Error(`Failed to list glossaries: ${error.message}`, { cause: error });
    }
  }

  async function getGlossary({ glossaryId }) {
    try {
      const glossary = await desiClient.getMultilingualGlossary(glossaryId);
      return mcpContentifyText(JSON.stringify(glossary, null, 2));
    } catch (error) {
      throw new Error(`Failed to get glossary: ${error.message}`, { cause: error });
    }
  }

  async function getGlossaryDictionaryEntries({ glossaryId, sourceLangCode, targetLangCode }) {
    try {
      const entries = await desiClient.getMultilingualGlossaryDictionaryEntries(glossaryId, sourceLangCode, targetLangCode);
      return mcpContentifyText([
        `Language pair: ${sourceLangCode} → ${targetLangCode}`,
        JSON.stringify(entries.entries.entries(), null, 2),
      ]);
    } catch (error) {
      throw new Error(`Failed to get glossary dictionary entries: ${error.message}`, { cause: error });
    }
  }

  async function listStyleRules({ page, pageSize, detailed }) {
    try {
      const styleRules = await desiClient.getAllStyleRules(page, pageSize, detailed);
      if (styleRules.length === 0) return mcpContentifyText("No style rules found");
      return mcpContentifyText(styleRules.map((sr) => JSON.stringify(sr, null, 2)));
    } catch (error) {
      throw new Error(`Failed to list style rules: ${error.message}`, { cause: error });
    }
  }

  async function getStyleRule({ styleId }) {
    try {
      const styleRule = await desiClient.getStyleRule(styleId);
      return mcpContentifyText(JSON.stringify(styleRule, null, 2));
    } catch (error) {
      throw new Error(`Failed to get style rule: ${error.message}`, { cause: error });
    }
  }

  async function getCustomInstruction({ styleId, instructionId }) {
    try {
      const instruction = await desiClient.getStyleRuleCustomInstruction(styleId, instructionId);
      return mcpContentifyText(JSON.stringify(instruction, null, 2));
    } catch (error) {
      throw new Error(`Failed to get custom instruction: ${error.message}`, { cause: error });
    }
  }

  return {
    translateDesi,
    transliterateDesi,
    normalizeDesi,
    getDesiLanguages,
    getSourceLanguages,
    getTargetLanguages,
    translateText,
    rephraseText,
    correctText,
    getWritingStyles,
    getWritingTones,
    translateDocument,
    listGlossaries,
    getGlossary,
    getGlossaryDictionaryEntries,
    listStyleRules,
    getStyleRule,
    getCustomInstruction,
  };
}
