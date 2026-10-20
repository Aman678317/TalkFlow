import { api } from "./api";
import type { TranslateResponse } from "./types";

export class TranslationUnavailableError extends Error {
  constructor(message = "Translation provider is unavailable or not configured. Please retry.") {
    super(message);
    this.name = "TranslationUnavailableError";
  }
}

export interface CanonicalTranslation {
  response: TranslateResponse;
  sourceLanguage: string;
  detectedConfidence: number | null;
}

export function languageCode(value: string | undefined): string {
  return (value || "").toLowerCase().split("-")[0];
}

export function normalizeTranslationResponse(res: any): TranslateResponse {
  const item = Array.isArray(res?.translations) ? res.translations[0] : res;
  return {
    translation_id: item?.translation_id || res?.request_id || "",
    source_language: item?.source_language || "",
    target_language: item?.target_language || "",
    source_text: item?.source_text || "",
    translated_text: item?.translated_text || "",
    model: item?.model || "",
    provider: item?.provider || "",
    latency_ms: Number(item?.latency_ms ?? 0),
    quality_flags: Array.isArray(item?.quality_flags) ? item.quality_flags : [],
    from_translation_memory: Boolean(item?.from_translation_memory || item?.tm_match),
    detected_confidence: Number(item?.detected_confidence ?? 1.0),
    alternatives: Array.isArray(item?.alternatives) ? item.alternatives : [],
    // Honest glossary accounting: keep the backend's "not applied (reason)"
    // note so the UI can surface it (absent = applied or no glossary asked).
    glossary_note: typeof item?.glossary_note === "string" ? item.glossary_note : null,
  };
}

export function isUsableTranslation(
  response: TranslateResponse,
  originalText: string,
  sourceLanguage: string,
  targetLanguage: string,
): boolean {
  const source = languageCode(response.source_language || sourceLanguage);
  const target = languageCode(response.target_language || targetLanguage);
  const differentLanguages = Boolean(source && target && source !== target);
  const output = response.translated_text.trim();
  const metadata = [response.provider, response.model, ...(response.quality_flags || [])]
    .join(" ")
    .toLowerCase();
  const hasSyntheticMarker = /\b(?:dev_echo|dev_provider|untranslated_fallback|source_fallback|echo)\b/.test(metadata)
    || /^\[[a-z]{2,8}\]\s/.test(output);

  if (!output) return false;
  if (differentLanguages && (hasSyntheticMarker || output === originalText.trim())) return false;
  return true;
}

export async function translateCanonical(
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
  body: Record<string, unknown> = {},
): Promise<CanonicalTranslation> {
  const trimmed = text.trim();
  if (!trimmed) throw new TranslationUnavailableError("There is no text to translate.");

  let resolvedSource = languageCode(sourceLanguage);
  let detectedConfidence: number | null = null;
  if (sourceLanguage.toLowerCase() === "auto") {
    const detected = await api<{ language?: string; confidence?: number }>("/api/v1/detect-language", {
      method: "POST",
      body: { text: trimmed },
    });
    resolvedSource = languageCode(detected.language);
    detectedConfidence = typeof detected.confidence === "number" ? detected.confidence : null;
    if (!resolvedSource || resolvedSource === "unknown") {
      throw new TranslationUnavailableError("Unable to detect the source language. Please retry.");
    }
  }

  const raw = await api<TranslateResponse>("/api/v1/translate", {
    method: "POST",
    body: {
      ...body,
      text: trimmed,
      source_language: resolvedSource,
      target_language: languageCode(targetLanguage),
    },
  });
  const response = normalizeTranslationResponse(raw);
  if (!isUsableTranslation(response, trimmed, resolvedSource, targetLanguage)) {
    throw new TranslationUnavailableError();
  }
  return { response, sourceLanguage: resolvedSource, detectedConfidence };
}
