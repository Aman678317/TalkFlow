/**
 * Selection helpers for the "translate a selection" flow.
 *
 * The reference product translates any text you select (its browser
 * extension). In the app the same gesture works inside the editor, so a
 * selection can be translated on its own without sending the whole draft.
 *
 * These helpers are pure so the gesture can be tested without a DOM.
 */

/** The text currently selected inside a textarea / input element. */
export function selectedTextIn(el: {
  selectionStart: number | null;
  selectionEnd: number | null;
  value: string;
}): string {
  const start = el.selectionStart;
  const end = el.selectionEnd;
  if (start === null || end === null || end <= start) return "";
  return el.value.slice(start, end);
}

/** The text currently selected in the document (outside inputs). */
export function selectedTextInDocument(): string {
  if (typeof window === "undefined") return "";
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return "";
  return selection.toString().trim();
}

/** Selection long enough to be worth translating (a word, a phrase, a line). */
export const MIN_SELECTION_CHARS = 2;
/** Upper bound: translating a whole document through a selection is a different flow. */
export const MAX_SELECTION_CHARS = 2_000;

export function isTranslatableSelection(text: string): boolean {
  const trimmed = (text || "").trim();
  return trimmed.length >= MIN_SELECTION_CHARS && trimmed.length <= MAX_SELECTION_CHARS;
}
