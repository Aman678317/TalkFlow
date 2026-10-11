/**
 * Writing / rephrasing option enums and validation.
 * Mirrors the values accepted by the TalkFlow /api/v1/write endpoint.
 */

export const STYLES = ["business", "academic", "casual", "simple", "creative"];
export const TONES = ["professional", "friendly", "confident", "diplomatic", "direct"];
export const FORMALITY = ["default", "formal", "informal"];

export function normalizeStyle(value) {
  const v = String(value ?? "business").toLowerCase();
  return STYLES.includes(v) ? v : "business";
}

export function normalizeTone(value) {
  const v = String(value ?? "professional").toLowerCase();
  return TONES.includes(v) ? v : "professional";
}

export function normalizeFormality(value) {
  const v = String(value ?? "default").toLowerCase();
  return FORMALITY.includes(v) ? v : "default";
}
