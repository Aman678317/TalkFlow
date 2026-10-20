/**
 * The reference product (deepl.com) is keyboard-driven: Ctrl/Cmd+Enter
 * submits, Ctrl/Cmd+Shift+K swaps the language pair, Ctrl/Cmd+Shift+C copies
 * the result and Escape clears the editor. This app had those gestures only
 * on one page (Translate) and none at all on Write, so the rules live in one
 * shared, tested module.
 */
import { describe, expect, it } from "vitest";
import { matchShortcut, type ShortcutEventLike } from "../shortcuts";

function ev(partial: Partial<ShortcutEventLike> = {}): ShortcutEventLike {
  return {
    key: "",
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    ...partial,
  };
}

describe("matchShortcut", () => {
  it("maps Ctrl/Cmd+Enter to submit", () => {
    expect(matchShortcut(ev({ key: "Enter", ctrlKey: true }))).toBe("submit");
    expect(matchShortcut(ev({ key: "Enter", metaKey: true }))).toBe("submit");
  });

  it("maps Ctrl/Cmd+Shift+K to swap", () => {
    expect(matchShortcut(ev({ key: "K", ctrlKey: true, shiftKey: true }))).toBe("swap");
    expect(matchShortcut(ev({ key: "k", metaKey: true, shiftKey: true }))).toBe("swap");
  });

  it("maps Ctrl/Cmd+Shift+C to copy", () => {
    expect(matchShortcut(ev({ key: "C", metaKey: true, shiftKey: true }))).toBe("copy");
  });

  it("maps Escape to clear", () => {
    expect(matchShortcut(ev({ key: "Escape" }))).toBe("clear");
  });

  it("ignores plain typing and unrelated combinations", () => {
    expect(matchShortcut(ev({ key: "a" }))).toBeNull();
    expect(matchShortcut(ev({ key: "Enter" }))).toBeNull();
    expect(matchShortcut(ev({ key: "k", ctrlKey: true }))).toBeNull();
    expect(matchShortcut(ev({ key: "Enter", ctrlKey: true, shiftKey: true }))).toBeNull();
    expect(matchShortcut(ev({ key: "k", ctrlKey: true, shiftKey: true, altKey: true }))).toBeNull();
  });

  it("does not treat a modified Escape as a clear", () => {
    expect(matchShortcut(ev({ key: "Escape", ctrlKey: true }))).toBeNull();
    expect(matchShortcut(ev({ key: "Escape", shiftKey: true }))).toBeNull();
  });
});
