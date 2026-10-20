/**
 * Shared keyboard shortcuts (DeepL-style).
 *
 * The Translate page grew its own key handler and the Write page had none,
 * so the same gestures behaved differently per page. The matching rules live
 * here as pure functions so every page (and the tests) agree on them.
 *
 *   Ctrl/Cmd + Enter   submit the current action (translate / improve)
 *   Ctrl/Cmd + Shift + K   swap source and target
 *   Ctrl/Cmd + Shift + C   copy the result
 *   Escape              clear the editor (only when the editor has focus)
 *
 * The reference product also ships these, which is why they are the parity
 * baseline for this app (2026-10-21 reference benchmark).
 */
import { useEffect, useRef } from "react";

export type ShortcutName = "submit" | "swap" | "copy" | "clear";

export interface ShortcutEventLike {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

/** Map a key event to a shortcut name, or null when it is not a shortcut. */
export function matchShortcut(e: ShortcutEventLike): ShortcutName | null {
  const mod = e.metaKey || e.ctrlKey;
  const key = (e.key || "").toLowerCase();

  if (mod && !e.shiftKey && !e.altKey && key === "enter") return "submit";
  if (mod && e.shiftKey && !e.altKey && key === "k") return "swap";
  if (mod && e.shiftKey && !e.altKey && key === "c") return "copy";
  if (!mod && !e.shiftKey && !e.altKey && key === "escape") return "clear";
  return null;
}

export interface ShortcutHandlers {
  submit?: () => void;
  swap?: () => void;
  copy?: () => void;
  clear?: () => void;
}

export interface ShortcutOptions {
  /**
   * Only clear while an element with this aria-label holds the focus —
   * Escape must not wipe the page while a menu or a dialog is open.
   */
  clearTargetLabel?: string;
  enabled?: boolean;
}

/**
 * Bind the shared shortcuts to the window. Handlers are read through a ref so
 * the listener is registered once and never re-bound on every render.
 */
export function useShortcuts(handlers: ShortcutHandlers, options: ShortcutOptions = {}) {
  const { clearTargetLabel, enabled = true } = options;
  const ref = useRef(handlers);
  // Keep the ref pointed at the latest handlers so the listener (registered
  // once) always calls the current closures.
  ref.current = handlers;

  useEffect(() => {
    if (!enabled) return;
    function onKey(e: KeyboardEvent) {
      const name = matchShortcut(e);
      if (!name) return;
      if (name === "clear") {
        const el = document.activeElement as HTMLElement | null;
        if (clearTargetLabel && el?.getAttribute("aria-label") !== clearTargetLabel) return;
      }
      const fn = ref.current[name];
      if (!fn) return;
      e.preventDefault();
      fn();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, clearTargetLabel]);
}
