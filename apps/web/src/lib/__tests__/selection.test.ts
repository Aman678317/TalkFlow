/**
 * "Translate a selection" — the reference product translates whatever text
 * you select (its browser extension); in the app the same gesture works
 * inside the editor, so a selection can be translated on its own.
 */
import { describe, expect, it } from "vitest";
import {
  isTranslatableSelection,
  MAX_SELECTION_CHARS,
  MIN_SELECTION_CHARS,
  selectedTextIn,
} from "../selection";

function field(value: string, selectionStart: number | null, selectionEnd: number | null) {
  return { value, selectionStart, selectionEnd };
}

describe("selectedTextIn", () => {
  it("returns the selected slice of the field", () => {
    expect(selectedTextIn(field("translate this bit", 10, 14))).toBe("this");
  });

  it("returns nothing when the caret is collapsed", () => {
    expect(selectedTextIn(field("translate this bit", 5, 5))).toBe("");
  });

  it("returns nothing when there is no selection information", () => {
    expect(selectedTextIn(field("text", null, null))).toBe("");
  });

  it("returns nothing when the selection is inverted", () => {
    expect(selectedTextIn(field("text", 3, 1))).toBe("");
  });
});

describe("isTranslatableSelection", () => {
  it("accepts a word or a phrase", () => {
    expect(isTranslatableSelection("cloud")).toBe(true);
    expect(isTranslatableSelection("  cloud console  ")).toBe(true);
  });

  it("rejects a single character or an empty selection", () => {
    expect(isTranslatableSelection("a")).toBe(false);
    expect(isTranslatableSelection("")).toBe(false);
    expect(isTranslatableSelection("   ")).toBe(false);
    expect(MIN_SELECTION_CHARS).toBe(2);
  });

  it("rejects a selection that is really a whole document", () => {
    expect(isTranslatableSelection("x".repeat(MAX_SELECTION_CHARS + 1))).toBe(false);
    expect(isTranslatableSelection("x".repeat(MAX_SELECTION_CHARS))).toBe(true);
  });
});
