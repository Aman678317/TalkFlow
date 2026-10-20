/**
 * Language-picker logic (reference parity, 2026-10-21).
 *
 * The language bar offered the common languages as pills and everything else
 * through a native `<select>` — a list that cannot be searched and that
 * grows to a hundred entries. The reference product uses a searchable
 * combobox with native names.
 *
 * The matching and keyboard rules live here as pure functions so they can be
 * tested without a DOM.
 */
export interface PickerLanguage {
  code: string;
  name: string;
  native_name?: string | null;
}

/** Match a language against a search query: name, native name or code. */
export function matchesLanguage(lang: PickerLanguage, query: string): boolean {
  const q = (query || "").trim().toLowerCase();
  if (!q) return true;
  return (
    (lang.code || "").toLowerCase().includes(q) ||
    (lang.name || "").toLowerCase().includes(q) ||
    (lang.native_name || "").toLowerCase().includes(q)
  );
}

/** Filter a language list, keeping the original order. */
export function filterLanguages(langs: PickerLanguage[], query: string): PickerLanguage[] {
  return (langs || []).filter((l) => matchesLanguage(l, query));
}

/** Move the highlighted option; the list wraps at both ends. */
export function nextActiveIndex(current: number, count: number, delta: number): number {
  if (count <= 0) return -1;
  const next = current + delta;
  if (next < 0) return count - 1;
  if (next >= count) return 0;
  return next;
}

/** The label shown for a language: "Hindi (हिन्दी)". */
export function languageOptionLabel(lang: PickerLanguage): string {
  return lang.native_name && lang.native_name !== lang.name
    ? `${lang.name} (${lang.native_name})`
    : lang.name || lang.code;
}
