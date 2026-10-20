import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  isUsableTranslation,
  normalizeTranslationResponse,
  translateCanonical,
  TranslationUnavailableError,
} from "./translation";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ api: apiMock }));

describe("canonical translation client", () => {
  beforeEach(() => apiMock.mockReset());

  it("normalizes the backend's response envelope", () => {
    const response = normalizeTranslationResponse({
      request_id: "request-1",
      translations: [{
        translation_id: "translation-1",
        source_language: "en",
        target_language: "de",
        source_text: "Hello",
        translated_text: "Hallo",
        model: "provider-model",
        provider: "configured-provider",
        latency_ms: 12,
        quality_flags: [],
        alternatives: ["Guten Tag"],
        glossary_note: "glossary not applied: language pair mismatch (en→hi vs en→de)",
      }],
    });

    expect(response.translation_id).toBe("translation-1");
    expect(response.translated_text).toBe("Hallo");
    expect(response.alternatives).toEqual(["Guten Tag"]);
    // The backend's honest glossary accounting survives normalization…
    expect(response.glossary_note).toBe(
      "glossary not applied: language pair mismatch (en→hi vs en→de)",
    );
    expect(
      normalizeTranslationResponse({ translations: [{ translation_id: "x" }] })
        .glossary_note,
    ).toBeNull();
  });

  it("uses backend language detection before translating AUTO input", async () => {
    apiMock
      .mockResolvedValueOnce({ language: "hi", confidence: 0.62 })
      .mockResolvedValueOnce({
        translations: [{
          translation_id: "translation-2",
          source_language: "hi",
          target_language: "en",
          source_text: "नमस्ते",
          translated_text: "Hello",
          model: "real-model",
          provider: "configured-provider",
          latency_ms: 20,
          quality_flags: [],
        }],
      });

    const result = await translateCanonical("नमस्ते", "AUTO", "en");

    expect(result.sourceLanguage).toBe("hi");
    expect(result.detectedConfidence).toBe(0.62);
    expect(result.response.translated_text).toBe("Hello");
    expect(apiMock.mock.calls[1][0]).toBe("/api/v1/translate");
    expect(apiMock.mock.calls[1][1].body.source_language).toBe("hi");
    expect(apiMock.mock.calls[1][1].body.target_language).toBe("en");
  });

  it.each([
    ["empty output", { translated_text: "" }],
    ["dev echo", { translated_text: "[de] Hello", provider: "dev_echo" }],
    ["untranslated fallback", { translated_text: "Hello", quality_flags: ["untranslated_fallback"] }],
  ])("rejects %s rather than presenting it as a translation", (_label, response) => {
    const candidate = response as {
      translated_text?: string;
      model?: string;
      provider?: string;
      quality_flags?: string[];
    };
    expect(isUsableTranslation({
      ...response,
      translation_id: "x",
      source_language: "en",
      target_language: "de",
      source_text: "Hello",
      translated_text: candidate.translated_text ?? "",
      model: candidate.model ?? "",
      provider: candidate.provider ?? "",
      latency_ms: 0,
      quality_flags: candidate.quality_flags ?? [],
      from_translation_memory: false,
      detected_confidence: 1,
    }, "Hello", "en", "de")).toBe(false);
  });

  it("raises a recoverable error when the backend only echoes the source", async () => {
    apiMock.mockResolvedValue({
      translations: [{
        source_language: "en",
        target_language: "de",
        source_text: "Hello",
        translated_text: "Hello",
        provider: "configured-provider",
        model: "configured-model",
        quality_flags: [],
      }],
    });

    await expect(translateCanonical("Hello", "en", "de")).rejects.toBeInstanceOf(TranslationUnavailableError);
  });
});
