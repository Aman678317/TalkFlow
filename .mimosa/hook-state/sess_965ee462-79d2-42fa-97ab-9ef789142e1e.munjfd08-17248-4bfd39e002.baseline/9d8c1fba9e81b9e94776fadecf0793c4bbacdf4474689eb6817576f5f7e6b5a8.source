/**
 * Shared types for the GlobalTalk AI Node.js SDK.
 *
 * All public-facing types are defined here and re-exported from `index.ts`.
 * Internal types (parser intermediate shapes, raw API bodies) live in their
 * respective modules to keep this file focused on the SDK contract.
 */

// ── Text translation ─────────────────────────────────────────────────────────

export interface TextResult {
  /** The translated text. */
  text: string;
  /** Detected or forced source language code (uppercase BCP-47, e.g. `"EN"`). */
  detectedSourceLang: string;
  /** Identifier of the model that produced this translation. */
  modelUsed: string;
}

export interface TranslateOptions {
  /** Source language code or `"AUTO"` for auto-detection. */
  sourceLang?:          string;
  /** Formality: `"default"` | `"more"` | `"less"`. */
  formality?:           "default" | "more" | "less";
  /** Glossary ID to enforce term pairs. */
  glossaryId?:          string;
  /** Tag handling: `"off"` | `"xml"` | `"html"`. */
  tagHandling?:         "off" | "xml" | "html";
  /** Split sentences: `"0"` (never) | `"1"` (default) | `"nonewlines"`. */
  splitSentences?:      "0" | "1" | "nonewlines";
  /** Preserve source document formatting. */
  preserveFormatting?:  boolean;
  /** Surrounding context string for disambiguation. */
  context?:             string;
  /** Style rule ID to apply. */
  styleRuleId?:         string;
  /** Translation memory ID. */
  translationMemoryId?: string;
}

// ── Languages & usage ────────────────────────────────────────────────────────

export interface LanguageInfo {
  /** BCP-47 language code (uppercase, e.g. `"EN"`, `"HI"`, `"ZH"`). */
  language: string;
  /** Human-readable language name. */
  name: string;
  supportsFormality: boolean;
  supportsWrite:     boolean;
  supportsVoice:     boolean;
}

export interface UsageSummary {
  characterCount:   number;
  characterLimit:   number;
  sttSeconds:       number;
  sttLimitSeconds:  number;
  ttsSeconds:       number;
  ttsLimitSeconds:  number;
}

// ── Document translation ──────────────────────────────────────────────────────

export type DocumentStatusCode = "queued" | "processing" | "done" | "error";

export interface DocumentStatus {
  documentId:       string;
  status:           DocumentStatusCode;
  secondsRemaining: number;
  billedCharacters: number;
  errorMessage:     string;
}

export interface TranslateDocumentOptions {
  sourceLang?:  string;
  glossaryId?:  string;
  /** Poll interval override in ms (default 2 000). */
  pollMs?:      number;
  /** Maximum wait time in ms (default 300 000 / 5 min). */
  maxWaitMs?:   number;
  /** Skip document minifier pre-processing. */
  skipMinify?:  boolean;
}

// ── Glossaries ─────────────────────────────────────────────────────────────────

export interface GlossaryInfo {
  glossaryId:   string;
  name:         string;
  ready:        boolean;
  sourceLang:   string;
  targetLang:   string;
  creationTime: string;
  entryCount:   number;
}

export interface GlossaryEntriesResult {
  entries: Record<string, string>;
  count:   number;
}

export interface GlossaryLanguagePair {
  sourceLang: string;
  targetLang: string;
}

// ── Style rules ───────────────────────────────────────────────────────────────

export interface StyleRule {
  id:         string;
  name:       string;
  sourceLang: string;
  createdAt:  string;
}

export interface CreateStyleRuleOptions {
  name:       string;
  sourceLang: string;
  rules:      Record<string, string>;
}

// ── Translation memory ────────────────────────────────────────────────────────

export interface TranslationMemoryInfo {
  id:         string;
  name:       string;
  sourceLang: string;
  targetLang: string;
  entryCount: number;
  createdAt:  string;
}

// ── Writing assistant ─────────────────────────────────────────────────────────

export type WriteStyle = "business" | "academic" | "casual" | "simple" | "creative";
export type WriteTone  = "professional" | "friendly" | "confident" | "diplomatic" | "direct";

export interface WriteOptions {
  style?: WriteStyle;
  tone?:  WriteTone;
  lang?:  string;
}

export interface WriteDiff {
  start:       number;
  end:         number;
  original:    string;
  replacement: string;
  changeType:  "grammar" | "style" | "vocabulary" | "tone" | "spelling";
  explanation: string;
}

export interface WriteResult {
  text:         string;
  original:     string;
  changesCount: number;
  diffs:        WriteDiff[];
  alternatives: string[];
  style:        string;
  tone:         string;
}
