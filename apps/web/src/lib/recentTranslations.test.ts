import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  RECENTS_LIMIT,
  relativeTime,
  saveRecents,
  loadRecents,
  withRecent,
  type RecentTranslation,
} from "./recentTranslations";

const entry = (over: Partial<RecentTranslation> = {}): RecentTranslation => ({
  sourceText: "Good morning",
  translatedText: "Guten Morgen",
  srcLang: "en",
  tgtLang: "de",
  ts: 1_000,
  ...over,
});

describe("recentTranslations.withRecent", () => {
  it("prepends the newest entry", () => {
    const prev = [entry({ sourceText: "older", ts: 1 })];
    const next = withRecent(prev, entry({ sourceText: "newer", ts: 2 }));
    expect(next[0].sourceText).toBe("newer");
    expect(next).toHaveLength(2);
  });

  it("dedupes by language pair + source text (case-insensitive) and refreshes position", () => {
    const prev = [entry({ ts: 1 }), entry({ sourceText: "other", ts: 2 })];
    const next = withRecent(prev, entry({ sourceText: "GOOD MORNING", ts: 99 }));
    expect(next).toHaveLength(2);
    expect(next[0].ts).toBe(99); // moved to front, not duplicated
    expect(next.some((r) => r.ts === 1)).toBe(false);
  });

  it("keeps the same source text when the target language differs", () => {
    const prev = [entry({ tgtLang: "de" })];
    const next = withRecent(prev, entry({ tgtLang: "fr" }));
    expect(next).toHaveLength(2);
  });

  it("caps the list at RECENTS_LIMIT", () => {
    const prev = Array.from({ length: RECENTS_LIMIT }, (_, i) => entry({ sourceText: `s${i}`, ts: i }));
    const next = withRecent(prev, entry({ sourceText: "fresh", ts: 999 }));
    expect(next).toHaveLength(RECENTS_LIMIT);
    expect(next[0].sourceText).toBe("fresh");
  });
});

describe("recentTranslations persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips through localStorage", () => {
    const items = [entry({ ts: 5 }), entry({ ts: 6 })];
    saveRecents(items);
    expect(loadRecents()).toEqual(items);
  });

  it("returns an empty list when nothing is stored", () => {
    expect(loadRecents()).toEqual([]);
  });

  it("ignores malformed stored payloads instead of throwing", () => {
    localStorage.setItem("globaltalk.recentTranslations.v1", "{not json");
    expect(loadRecents()).toEqual([]);
  });

  it("drops entries missing required fields", () => {
    localStorage.setItem(
      "globaltalk.recentTranslations.v1",
      JSON.stringify([{ sourceText: "x" }, entry()]),
    );
    expect(loadRecents()).toHaveLength(1);
  });

  it("swallows storage write failures (best-effort)", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => saveRecents([entry()])).not.toThrow();
    spy.mockRestore();
  });
});

describe("recentTranslations.relativeTime", () => {
  const now = 1_700_000_000_000;
  it("formats seconds, minutes, hours and days", () => {
    expect(relativeTime(now - 30_000, now)).toBe("just now");
    expect(relativeTime(now - 5 * 60_000, now)).toBe("5m ago");
    expect(relativeTime(now - 3 * 3_600_000, now)).toBe("3h ago");
    expect(relativeTime(now - 2 * 86_400_000, now)).toBe("2d ago");
  });
});
