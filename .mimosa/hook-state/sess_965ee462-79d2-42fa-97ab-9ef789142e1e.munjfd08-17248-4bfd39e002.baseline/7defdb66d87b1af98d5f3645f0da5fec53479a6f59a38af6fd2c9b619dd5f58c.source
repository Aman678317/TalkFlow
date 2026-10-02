/**
 * @globaltalk/sdk — Official Node.js / TypeScript client for the GlobalTalk AI API.
 *
 * Mirrors the architecture of desi-node with full TypeScript types, a clean
 * layered design, automatic retries, and structured error handling.
 *
 * Quick start:
 * ```ts
 * import { GlobalTalkClient, GlossaryEntries } from "@globaltalk/sdk";
 *
 * const client = new GlobalTalkClient({ authKey: "gt-your-key" });
 *
 * // Text translation
 * const [result] = await client.translateText("Hello, world!", "HI");
 * console.log(result.text); // नमस्ते, दुनिया!
 *
 * // Check usage
 * const usage = await client.getUsage();
 * console.log(`${usage.characterCount} / ${usage.characterLimit} chars used`);
 *
 * // Glossary
 * const g = await client.createGlossary("My terms", "EN", "HI",
 *   new GlossaryEntries({ Invoice: "चालान", Budget: "बजट" }),
 * );
 * const [branded] = await client.translateText("Send the Invoice.", "HI", {
 *   glossaryId: g.glossaryId,
 * });
 * console.log(branded.text); // चालान भेजें।
 * ```
 *
 * @module @globaltalk/sdk
 */

// ── Main client classes ──────────────────────────────────────────────────────

export { GlobalTalkClient }              from "./globaltalkClient.js";
export { Translator }                    from "./translator.js";
export type { TranslatorOptions }        from "./translator.js";

// ── Glossary entries helper ───────────────────────────────────────────────────

export { GlossaryEntries }               from "./glossaryEntries.js";

// ── Error classes ─────────────────────────────────────────────────────────────

export {
  GlobalTalkError,
  AuthorizationError,
  QuotaExceededError,
  TooManyRequestsError,
  UnsupportedLanguageError,
  DocumentTranslationError,
  GlossaryNotFoundError,
  NetworkError,
  ParseError,
}                                         from "./errors.js";

// ── Public types ───────────────────────────────────────────────────────────────

export type {
  // Text
  TextResult,
  TranslateOptions,
  // Languages & usage
  LanguageInfo,
  UsageSummary,
  // Documents
  DocumentStatus,
  DocumentStatusCode,
  TranslateDocumentOptions,
  // Glossaries
  GlossaryInfo,
  GlossaryEntriesResult,
  GlossaryLanguagePair,
  // Style rules
  StyleRule,
  CreateStyleRuleOptions,
  // Translation memory
  TranslationMemoryInfo,
  // Writing assistant
  WriteStyle,
  WriteTone,
  WriteOptions,
  WriteDiff,
  WriteResult,
}                                         from "./types.js";
