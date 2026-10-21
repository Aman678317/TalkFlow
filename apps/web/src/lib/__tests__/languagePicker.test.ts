/**
 * The language bar listed every supported language in a native <select> —
 * unsearchable and unreadable at a hundred entries. The reference product
 * uses a searchable combobox; these rules are the pure part of it.
 */
import { describe, expect, it } from "vitest";
import {
  filterLanguages,
  languageOptionLabel,
  matchesLanguage,
  nextActiveIndex,
  type PickerLanguage,
} from "../languagePicker";

const LANGS: PickerLanguage[] = [
  { code: "en", name: "English", native_name: "English" },
  { code: "hi", name: "Hindi", native_name: "हिन्दी" },
  { code: "de", name: "German", native_name: "Deutsch" },
  { code: "ja", name: "Japanese", native_name: "日本語" },
];

describe("matchesLanguage", () => {
  it("matches on the English name", () => {
    expect(matchesLanguage(LANGS[1], "hindi")).toBe(true);
  });

  it("matches on the native name", () => {
    expect(matchesLanguage(LANGS[1], "हिन्दी")).toBe(true);
    expect(matchesLanguage(LANGS[2], "deutsch")).toBe(true);
  });

  it("matches on the code", () => {
    expect(matchesLanguage(LANGS[3], "ja")).toBe(true);
  });

  it("ignores case and surrounding spaces", () => {
    expect(matchesLanguage(LANGS[0], "  ENGLISH ")).toBe(true);
  });

  it("matches everything for an empty query", () => {
    expect(matchesLanguage(LANGS[0], "")).toBe(true);
    expect(matchesLanguage(LANGS[0], "   ")).toBe(true);
  });

  it("does not match an unrelated query", () => {
    expect(matchesLanguage(LANGS[0], "klingon")).toBe(false);
  });
});

describe("filterLanguages", () => {
  it("keeps the original order", () => {
    // "e" matches English, German and Japanese (Ja-pan-ese) — not Hindi.
    expect(filterLanguages(LANGS, "e").map((l) => l.code)).toEqual(["en", "de", "ja"]);
  });

  it("finds one language by a distinctive query", () => {
    expect(filterLanguages(LANGS, "japan").map((l) => l.code)).toEqual(["ja"]);
  });

  it("returns everything for an empty query", () => {
    expect(filterLanguages(LANGS, "")).toHaveLength(LANGS.length);
  });

  it("returns nothing when nothing matches", () => {
    expect(filterLanguages(LANGS, "zzzz")).toEqual([]);
  });
});

describe("nextActiveIndex", () => {
  it("moves down and wraps at the end", () => {
    expect(nextActiveIndex(0, 3, 1)).toBe(1);
    expect(nextActiveIndex(2, 3, 1)).toBe(0);
  });

  it("moves up and wraps at the start", () => {
    expect(nextActiveIndex(2, 3, -1)).toBe(1);
    expect(nextActiveIndex(0, 3, -1)).toBe(2);
  });

  it("has no active option in an empty list", () => {
    expect(nextActiveIndex(0, 0, 1)).toBe(-1);
  });
});

describe("languageOptionLabel", () => {
  it("shows the native name next to the English name", () => {
    expect(languageOptionLabel(LANGS[1])).toBe("Hindi (हिन्दी)");
  });

  it("does not repeat an identical native name", () => {
    expect(languageOptionLabel(LANGS[0])).toBe("English");
  });

  it("falls back to the code when there is no name", () => {
    expect(languageOptionLabel({ code: "xx", name: "" })).toBe("xx");
  });
});
