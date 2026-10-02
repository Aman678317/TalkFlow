/**
 * GlobalTalkClient — the top-level SDK class.
 *
 * Diagram layer: Client and translation [globaltalkClient.ts]
 *
 * Extends `Translator` (which provides text translation, document translation,
 * language/usage queries, and the writing assistant) and adds:
 *
 *   - **Glossary management** — CRUD + entries + language pairs
 *   - **Translation memories** — create / import TMX / export TMX
 *   - **Style rules** — create / list / delete writing style profiles
 *
 * Construction::
 *
 *   ```ts
 *   import { GlobalTalkClient } from "@globaltalk/sdk";
 *
 *   const client = new GlobalTalkClient({ authKey: "gt-..." });
 *   const [result] = await client.translateText("Hello!", "HI");
 *   console.log(result.text); // नमस्ते!
 *   ```
 */

import { Translator, type TranslatorOptions } from "./translator.js";
import { GlossaryEntries } from "./glossaryEntries.js";
import {
  parseGlossaryInfo,
  parseGlossaryList,
  parseGlossaryEntries,
  parseStyleRule,
  parseTranslationMemoryInfo,
} from "./parsing.js";
import type {
  GlossaryInfo,
  GlossaryEntriesResult,
  GlossaryLanguagePair,
  StyleRule,
  CreateStyleRuleOptions,
  TranslationMemoryInfo,
} from "./types.js";

export class GlobalTalkClient extends Translator {
  constructor(options: TranslatorOptions) {
    super(options);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // GLOSSARY MANAGEMENT
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Create a new glossary.
   *
   * @param name       Human-readable glossary name.
   * @param sourceLang Source language code (e.g. `"EN"`).
   * @param targetLang Target language code (e.g. `"HI"`).
   * @param entries    `GlossaryEntries` object with term pairs.
   *
   * @example
   * ```ts
   * const glossary = await client.createGlossary(
   *   "Product terms", "EN", "HI",
   *   new GlossaryEntries({ GlobalTalk: "ग्लोबलटॉक", Invoice: "चालान" }),
   * );
   * console.log(glossary.glossaryId);
   * ```
   */
  async createGlossary(
    name: string,
    sourceLang: string,
    targetLang: string,
    entries: GlossaryEntries | Record<string, string>,
  ): Promise<GlossaryInfo> {
    const ge = entries instanceof GlossaryEntries
      ? entries
      : new GlossaryEntries(entries);

    const resp = await this.http.post<Record<string, unknown>>("/v2/glossaries", {
      json: {
        name,
        source_lang:    sourceLang.toUpperCase(),
        target_lang:    targetLang.toUpperCase(),
        entries:        ge.toTSV(),
        entries_format: "tsv",
      },
    });
    return parseGlossaryInfo(resp);
  }

  /**
   * List all glossaries for this API key's organization.
   */
  async listGlossaries(): Promise<GlossaryInfo[]> {
    const resp = await this.http.get<Record<string, unknown>>("/v2/glossaries");
    return parseGlossaryList(resp);
  }

  /**
   * Retrieve metadata for a single glossary.
   *
   * @param glossaryId  Glossary UUID.
   */
  async getGlossary(glossaryId: string): Promise<GlossaryInfo> {
    const resp = await this.http.get<Record<string, unknown>>(
      `/v2/glossaries/${glossaryId}`,
    );
    return parseGlossaryInfo(resp);
  }

  /**
   * Retrieve the term pairs for a glossary as a `GlossaryEntriesResult`.
   *
   * @param glossaryId  Glossary UUID.
   */
  async getGlossaryEntries(glossaryId: string): Promise<GlossaryEntriesResult> {
    const tsv = await this.http.get<string>(
      `/v2/glossaries/${glossaryId}/entries`,
      { responseType: "text" },
    );
    return parseGlossaryEntries(tsv);
  }

  /**
   * Delete a glossary by ID.
   *
   * @param glossaryId  Glossary UUID.
   */
  async deleteGlossary(glossaryId: string): Promise<void> {
    await this.http.delete<unknown>(`/v2/glossaries/${glossaryId}`);
  }

  /**
   * Return all supported glossary language pairs.
   */
  async getGlossaryLanguagePairs(): Promise<GlossaryLanguagePair[]> {
    const resp = await this.http.get<{ supported_languages?: unknown[] }>(
      "/v2/glossary-language-pairs",
    );
    const pairs = resp["supported_languages"] ?? [];
    if (!Array.isArray(pairs)) return [];
    return pairs.map((p) => {
      const pair = p as Record<string, string>;
      return {
        sourceLang: (pair["source_lang"] ?? "").toUpperCase(),
        targetLang: (pair["target_lang"] ?? "").toUpperCase(),
      };
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // STYLE RULES
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Create a new style rule profile.
   *
   * Style rules are applied during text translation (via `translateText`
   * option `styleRuleId`) and writing assistant (`rephraseText`).
   *
   * @param options  Name, source language, and rule map.
   */
  async createStyleRule(options: CreateStyleRuleOptions): Promise<StyleRule> {
    const resp = await this.http.post<Record<string, unknown>>("/v3/style-rules", {
      json: {
        name:        options.name,
        source_lang: options.sourceLang.toUpperCase(),
        rules:       options.rules,
      },
    });
    return parseStyleRule(resp);
  }

  /**
   * List all style rules for this organization.
   */
  async listStyleRules(): Promise<StyleRule[]> {
    const resp = await this.http.get<Record<string, unknown>>("/v3/style-rules");
    const items = (resp["style_rules"] as unknown[] | undefined) ?? [];
    if (!Array.isArray(items)) return [];
    return items.map((i) => parseStyleRule(i as Record<string, unknown>));
  }

  /**
   * Delete a style rule by ID.
   *
   * @param styleRuleId  Style rule UUID.
   */
  async deleteStyleRule(styleRuleId: string): Promise<void> {
    await this.http.delete<unknown>(`/v3/style-rules/${styleRuleId}`);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // TRANSLATION MEMORIES
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Create a new (empty) translation memory.
   *
   * @param name        Human-readable name.
   * @param sourceLang  Source language code.
   * @param targetLang  Target language code.
   */
  async createMemory(
    name: string,
    sourceLang: string,
    targetLang: string,
  ): Promise<TranslationMemoryInfo> {
    const resp = await this.http.post<Record<string, unknown>>("/v2/memories", {
      json: {
        name,
        source_lang: sourceLang.toUpperCase(),
        target_lang: targetLang.toUpperCase(),
      },
    });
    return parseTranslationMemoryInfo(resp);
  }

  /**
   * List all translation memories for this organization.
   */
  async listMemories(): Promise<TranslationMemoryInfo[]> {
    const resp = await this.http.get<Record<string, unknown>>("/v2/memories");
    const items = (resp["memories"] as unknown[] | undefined) ?? [];
    if (!Array.isArray(items)) return [];
    return items.map((i) => parseTranslationMemoryInfo(i as Record<string, unknown>));
  }

  /**
   * Import a TMX buffer into an existing translation memory.
   *
   * @param memoryId    Translation memory UUID.
   * @param tmxBuffer   TMX file content as a `Buffer`.
   */
  async importMemory(memoryId: string, tmxBuffer: Buffer): Promise<void> {
    await this.http.postForm<unknown>(`/v2/memories/${memoryId}/import`, {
      file: new Blob([tmxBuffer], { type: "application/x-tmx" }),
    });
  }

  /**
   * Export a translation memory as a TMX `Buffer`.
   *
   * @param memoryId  Translation memory UUID.
   * @returns         TMX file content.
   */
  async exportMemory(memoryId: string): Promise<Buffer> {
    return this.http.download(`/v2/memories/${memoryId}/export`);
  }

  /**
   * Delete a translation memory by ID.
   *
   * @param memoryId  Translation memory UUID.
   */
  async deleteMemory(memoryId: string): Promise<void> {
    await this.http.delete<unknown>(`/v2/memories/${memoryId}`);
  }
}
