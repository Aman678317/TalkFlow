/**
 * 2026-10-20 localhost audit: the Write panel showed "(N% word diff)" computed
 * from a WORD-COUNT delta, so a draft with five applied spelling/grammar
 * corrections reported "0% word diff" next to "5 improvements applied".
 * The metric must reflect the words that actually changed.
 */
import { describe, expect, it } from "vitest";
import { wordDiffPercent } from "../writeDiff";

describe("wordDiffPercent", () => {
  it("reports the changed words of a spelling/grammar rewrite", () => {
    const original =
      "We recieved the componay budget report and it was to expensive. The team will acceppt the new adress tommorow.";
    const improved =
      "We received the company budget report and it was too expensive. The team will accept the new address tomorrow.";
    const pct = wordDiffPercent(original, improved);
    // 19 words, 6 changed -> ~32%
    expect(pct).toBeGreaterThan(20);
    expect(pct).toBeLessThan(45);
  });

  it("is 0% for identical texts", () => {
    expect(wordDiffPercent("The quick brown fox", "The quick brown fox")).toBe(0);
  });

  it("is 100% when every word changed", () => {
    expect(wordDiffPercent("one two three", "four five six")).toBe(100);
  });

  it("counts an insertion as a change", () => {
    // 4 original words, one inserted -> 1/4 = 25%
    expect(wordDiffPercent("a b c d", "a b x c d")).toBe(25);
  });

  it("counts a deletion as a change", () => {
    // 5 original words, 1 removed -> 1/5 = 20% (the original is the base)
    expect(wordDiffPercent("a b x c d", "a b c d")).toBe(20);
  });

  it("handles empty input without dividing by zero", () => {
    expect(wordDiffPercent("", "")).toBe(0);
    expect(wordDiffPercent("", "hello")).toBe(100);
    expect(wordDiffPercent("hello", "")).toBe(100);
  });

  it("ignores whitespace differences", () => {
    expect(wordDiffPercent("a  b\nc", "a b c")).toBe(0);
  });
});
