/**
 * Response parsing — converts raw API JSON into typed SDK objects.
 *
 * Diagram layer: Shared Internals [parsing.ts]
 *
 * Central location for all API contract enforcement.  Every parser:
 *   1. Validates required fields (throws `ParseError` if missing).
 *   2. Coerces/normalises values to SDK types.
 *   3. Never leaks raw `unknown` types to callers.
 */

import { ParseError } from "./errors.js";
import type {
  TextResult,
  LanguageInfo,
  UsageSummary,
  GlossaryInfo,
  GlossaryEntriesResult,
  DocumentStatus,
  StyleRule,
  TranslationMemoryInfo,
} from "./types.js";

// ─── helpers ────────────────────────────────────────────────────────────────

function req<T>(obj: Record<string, unknown>, key: string, requestId?: string): T {
  if (!(key in obj) || obj[key] === undefined || obj[key] === null) {
    throw new ParseError(`API response missing required field: "${key}"`, requestId);
  }
  return obj[key] as T;
}

// ─── Text translation ────────────────────────────────────────────────────────

/**
 * Parse the response body of `POST /v2/translate`.
 *
 * Expected shape:
 * ```json
 * { "translations": [{ "detected_source_language": "EN", "text": "..." }] }
 * ```
 */
export function parseTranslateResponse(
  body: Record<string, unknown>,
  requestId?: string,
): TextResult[] {
  const translations = req<unknown[]>(body, "translations", requestId);
  if (!Array.isArray(translations)) {
    throw new ParseError("translations field must be an array", requestId);
  }
  return translations.map((item, idx) => {
    if (typeof item !== "object" || !item) {
      throw new ParseError(`translations[${idx}] is not an object`, requestId);
    }
    const t = item as Record<string, unknown>;
    return {
      text: req<string>(t, "text", requestId),
      detectedSourceLang: (t["detected_source_language"] as string | undefined)?.toUpperCase() ?? "AUTO",
      modelUsed: (t["model_used"] as string | undefined) ?? "",
    };
  });
}

// ─── Languages ───────────────────────────────────────────────────────────────

/**
 * Parse the response body of `GET /v2/languages`.
 */
export function parseLanguages(
  body: unknown,
  requestId?: string,
): LanguageInfo[] {
  if (!Array.isArray(body)) {
    throw new ParseError("Expected an array from /v2/languages", requestId);
  }
  return body.map((item) => {
    const lang = item as Record<string, unknown>;
    return {
      language:         req<string>(lang, "language", requestId).toUpperCase(),
      name:             req<string>(lang, "name", requestId),
      supportsFormality: Boolean(lang["supports_formality"]),
      supportsWrite:    Boolean(lang["supports_write"]),
      supportsVoice:    Boolean(lang["supports_voice"]),
    };
  });
}

// ─── Usage ───────────────────────────────────────────────────────────────────

/**
 * Parse the response body of `GET /v2/usage`.
 */
export function parseUsage(
  body: Record<string, unknown>,
  requestId?: string,
): UsageSummary {
  return {
    characterCount:    req<number>(body, "character_count", requestId),
    characterLimit:    req<number>(body, "character_limit", requestId),
    sttSeconds:        (body["stt_seconds"] as number | undefined) ?? 0,
    sttLimitSeconds:   (body["stt_limit_seconds"] as number | undefined) ?? 0,
    ttsSeconds:        (body["tts_seconds"] as number | undefined) ?? 0,
    ttsLimitSeconds:   (body["tts_limit_seconds"] as number | undefined) ?? 0,
  };
}

// ─── Glossaries ───────────────────────────────────────────────────────────────

/**
 * Parse a single glossary object from the API.
 */
export function parseGlossaryInfo(
  item: Record<string, unknown>,
  requestId?: string,
): GlossaryInfo {
  return {
    glossaryId:  req<string>(item, "glossary_id", requestId),
    name:        req<string>(item, "name", requestId),
    ready:       Boolean(item["ready"]),
    sourceLang:  req<string>(item, "source_lang", requestId).toUpperCase(),
    targetLang:  req<string>(item, "target_lang", requestId).toUpperCase(),
    creationTime: (item["creation_time"] as string | undefined) ?? "",
    entryCount:  (item["entry_count"] as number | undefined) ?? 0,
  };
}

/**
 * Parse the response of `GET /v2/glossaries`.
 */
export function parseGlossaryList(
  body: Record<string, unknown>,
  requestId?: string,
): GlossaryInfo[] {
  const glossaries = req<unknown[]>(body, "glossaries", requestId);
  if (!Array.isArray(glossaries)) {
    throw new ParseError("glossaries field must be an array", requestId);
  }
  return glossaries.map((g) => parseGlossaryInfo(g as Record<string, unknown>, requestId));
}

/**
 * Parse glossary entries TSV from `GET /v2/glossaries/{id}/entries`.
 */
export function parseGlossaryEntries(
  tsvBody: string,
  _requestId?: string,
): GlossaryEntriesResult {
  const entries: Record<string, string> = {};
  for (const line of tsvBody.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const tab = trimmed.indexOf("\t");
    if (tab === -1) continue;
    entries[trimmed.slice(0, tab)] = trimmed.slice(tab + 1);
  }
  return { entries, count: Object.keys(entries).length };
}

// ─── Document status ──────────────────────────────────────────────────────────

/**
 * Parse `GET /v2/document/{id}` status response.
 */
export function parseDocumentStatus(
  body: Record<string, unknown>,
  requestId?: string,
): DocumentStatus {
  const status = req<string>(body, "status", requestId) as DocumentStatus["status"];
  return {
    documentId:        req<string>(body, "document_id", requestId),
    status,
    secondsRemaining:  (body["seconds_remaining"] as number | undefined) ?? 0,
    billedCharacters:  (body["billed_characters"] as number | undefined) ?? 0,
    errorMessage:      (body["error_message"] as string | undefined) ?? "",
  };
}

// ─── Style rules ─────────────────────────────────────────────────────────────

export function parseStyleRule(
  item: Record<string, unknown>,
  requestId?: string,
): StyleRule {
  return {
    id:         req<string>(item, "id", requestId),
    name:       req<string>(item, "name", requestId),
    sourceLang: (item["source_lang"] as string | undefined) ?? "",
    createdAt:  (item["created_at"] as string | undefined) ?? "",
  };
}

// ─── Translation memory ───────────────────────────────────────────────────────

export function parseTranslationMemoryInfo(
  item: Record<string, unknown>,
  requestId?: string,
): TranslationMemoryInfo {
  return {
    id:         req<string>(item, "id", requestId),
    name:       req<string>(item, "name", requestId),
    sourceLang: req<string>(item, "source_lang", requestId).toUpperCase(),
    targetLang: req<string>(item, "target_lang", requestId).toUpperCase(),
    entryCount: (item["entry_count"] as number | undefined) ?? 0,
    createdAt:  (item["created_at"] as string | undefined) ?? "",
  };
}
