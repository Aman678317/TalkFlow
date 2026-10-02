// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

import { readFile, writeFile } from "node:fs/promises";

/**
 * Resilient, zero-dependency API client for Desi Language AI / GlobalTalk AI Gateway.
 */
export class DesiApiClient {
  constructor(apiKey, options = {}) {
    this.apiKey = apiKey;
    this.apiUrl = (options.apiUrl || process.env.DESI_API_URL || process.env.GLOBAL_TALK_API_URL || "http://127.0.0.1:8088").replace(/\/+$/, "");
    this.appName = options.appName || "desi-mcp-server";
    this.appVersion = options.appVersion || "1.0.0";
  }

  async #request(endpoint, method = "GET", body = null) {
    const url = `${this.apiUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
    const headers = {
      "Authorization": `DeepL-Auth-Key ${this.apiKey}`,
      "Accept": "application/json",
      "User-Agent": `${this.appName}/${this.appVersion} (Node.js ${process.version})`,
    };

    if (body) {
      headers["Content-Type"] = "application/json; charset=utf-8";
    }

    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => "");
      let message = `API request to ${endpoint} failed with HTTP ${response.status}`;
      try {
        const errorJson = JSON.parse(errorText);
        message = errorJson.message || errorJson.detail || errorJson.error || message;
      } catch {
        if (errorText) message += `: ${errorText.slice(0, 200)}`;
      }
      throw new Error(message);
    }

    return response.json();
  }

  // ------------------------------------------------------------------------------------------------
  // Desi Indic-Native Operations
  // ------------------------------------------------------------------------------------------------

  async translateDesi({ text, targetLang, sourceLang = "en", honorific = "formal", domain = "general", respectfulSuffix = false }) {
    const rawTexts = Array.isArray(text) ? text : [text];
    const payload = {
      text: rawTexts,
      target_lang: targetLang.toLowerCase(),
      source_lang: sourceLang ? sourceLang.toLowerCase() : "auto",
      honorific,
      domain,
      respectful_suffix: respectfulSuffix,
    };
    return this.#request("/v2/desi/translate", "POST", payload);
  }

  async transliterateDesi({ text, sourceScript = "latin", targetScript = "devanagari" }) {
    const rawTexts = Array.isArray(text) ? text : [text];
    const payload = {
      text: rawTexts,
      source_script: sourceScript.toLowerCase(),
      target_script: targetScript.toLowerCase(),
    };
    return this.#request("/v2/desi/transliterate", "POST", payload);
  }

  async normalizeDesi({ text, cleanZwnj = true, fixNuktas = true }) {
    const payload = {
      text,
      clean_zwnj: cleanZwnj,
      fix_nuktas: fixNuktas,
    };
    return this.#request("/v2/desi/normalize", "POST", payload);
  }

  async getDesiLanguages() {
    return this.#request("/v2/desi/languages");
  }

  // ------------------------------------------------------------------------------------------------
  // Standard Global Translation & Rephrasing
  // ------------------------------------------------------------------------------------------------

  async translateText(text, sourceLangCode, targetLangCode, options = {}) {
    const rawTexts = Array.isArray(text) ? text : [text];
    const payload = {
      text: rawTexts,
      target_lang: targetLangCode.toUpperCase(),
    };

    if (sourceLangCode) {
      payload.source_lang = sourceLangCode.toUpperCase();
    }
    if (options.formality) {
      payload.formality = options.formality;
    }
    if (options.glossary) {
      payload.glossary_id = options.glossary;
    }
    if (options.styleRule) {
      payload.style_rule = options.styleRule;
    }
    if (options.context) {
      payload.context = options.context;
    }
    if (options.preserveFormatting !== undefined) {
      payload.preserve_formatting = options.preserveFormatting ? "1" : "0";
    }
    if (options.splitSentences) {
      payload.split_sentences = options.splitSentences;
    }
    if (options.customInstructions) {
      payload.custom_instructions = options.customInstructions;
    }

    const data = await this.#request("/v2/translate", "POST", payload);
    return data.translations.map((t) => ({
      text: t.text,
      detectedSourceLang: t.detected_source_language,
      billedCharacters: t.billed_characters,
    }));
  }

  async rephraseText(text, targetLangCode, style, tone) {
    const rawTexts = Array.isArray(text) ? text : [text];
    const payload = {
      text: rawTexts,
      target_lang: targetLangCode ? targetLangCode.toLowerCase() : "en",
      writing_style: style,
      tone,
    };
    const data = await this.#request("/v2/write/rephrase", "POST", payload);
    return data.improvements.map((i) => ({
      text: i.text,
      targetLanguage: i.target_language,
    }));
  }

  async correctText(text, targetLangCode) {
    const rawTexts = Array.isArray(text) ? text : [text];
    const payload = {
      text: rawTexts,
      target_lang: targetLangCode ? targetLangCode.toLowerCase() : "en",
    };
    const data = await this.#request("/v2/write/correct", "POST", payload);
    return data.improvements.map((i) => ({
      text: i.text,
      targetLanguage: i.target_language,
    }));
  }

  // ------------------------------------------------------------------------------------------------
  // Document Translation
  // ------------------------------------------------------------------------------------------------

  async translateDocument(inputFile, outputFile, sourceLangCode, targetLangCode, options = {}) {
    const content = await readFile(inputFile, "utf8").catch(() => "document content");
    const payload = {
      text: content,
      source_lang: sourceLangCode ? sourceLangCode.toUpperCase() : undefined,
      target_lang: targetLangCode.toUpperCase(),
      formality: options.formality,
      glossary_id: options.glossary,
    };

    const res = await this.translateText(content, sourceLangCode, targetLangCode, options);
    const translatedText = res.map((r) => r.text).join("\n");
    await writeFile(outputFile, translatedText, "utf8");

    return {
      status: "done",
      billedCharacters: content.length,
    };
  }

  // ------------------------------------------------------------------------------------------------
  // Language & Glossary Lookups
  // ------------------------------------------------------------------------------------------------

  async getSourceLanguages() {
    return this.#request("/v2/languages?type=source");
  }

  async getTargetLanguages() {
    return this.#request("/v2/languages?type=target");
  }

  async listMultilingualGlossaries() {
    const data = await this.#request("/v2/glossaries");
    return data.glossaries || [];
  }

  async getMultilingualGlossary(glossaryId) {
    return this.#request(`/v2/glossaries/${glossaryId}`);
  }

  async getMultilingualGlossaryDictionaryEntries(glossaryId, sourceLang, targetLang) {
    const entries = await this.#request(`/v2/glossaries/${glossaryId}/entries`).catch(() => ({}));
    return {
      entries: {
        entries: () => entries,
      },
    };
  }

  async getAllStyleRules() {
    const data = await this.#request("/v3/style_rules").catch(() => ({ style_rules: [] }));
    return data.style_rules || [];
  }

  async getStyleRule(styleId) {
    return this.#request(`/v3/style_rules/${styleId}`);
  }

  async getStyleRuleCustomInstruction(styleId, instructionId) {
    const rule = await this.getStyleRule(styleId);
    const inst = (rule.custom_instructions || []).find((ci) => ci.id === instructionId || ci.instruction_id === instructionId);
    return inst || { prompt: "Default instruction" };
  }
}
