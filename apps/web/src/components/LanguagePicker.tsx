/**
 * Searchable language picker (reference parity, 2026-10-21).
 *
 * Replaces the native `<select>` that listed every supported language: a
 * native select cannot be searched, cannot show native names next to English
 * names in a scannable way, and grows to a hundred entries.
 *
 * Behaviour: a trigger that opens a popover with a search field, the
 * filtered list, keyboard navigation (↑/↓ move, Enter selects, Escape
 * closes) and click-outside to dismiss. The filtering and keyboard rules
 * live in `lib/languagePicker` and are unit-tested.
 */
import React from "react";
import { Check, Search } from "lucide-react";
import {
  filterLanguages,
  languageOptionLabel,
  nextActiveIndex,
  type PickerLanguage,
} from "../lib/languagePicker";

export function LanguagePicker({
  languages,
  value,
  onSelect,
  ariaLabel,
  triggerLabel,
  className,
}: {
  languages: PickerLanguage[];
  value: string;
  onSelect: (code: string) => void;
  ariaLabel: string;
  /** Text shown on the trigger when nothing specific is selected. */
  triggerLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);
  const boxRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listRef = React.useRef<HTMLUListElement>(null);

  const filtered = React.useMemo(
    () => filterLanguages(languages, query),
    [languages, query],
  );

  React.useEffect(() => {
    if (!open) return;
    setActive(0);
    // Focus the search field once the popover is mounted.
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open, filtered]);

  function choose(code: string) {
    onSelect(code);
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => nextActiveIndex(i, filtered.length, 1));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => nextActiveIndex(i, filtered.length, -1));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const picked = filtered[active];
      if (picked) choose(picked.code);
    }
  }

  const current = languages.find((l) => l.code === value);

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "Enter") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={
          className ??
          "flex h-8 items-center gap-1.5 rounded-lg border border-dl-border bg-white px-3 text-xs font-medium text-dl-muted hover:border-dl-blue/40 focus:outline-none focus:ring-2 focus:ring-dl-blue/20"
        }
      >
        {current ? languageOptionLabel(current) : triggerLabel ?? "Select language"}
        <span aria-hidden className="text-[10px]">▾</span>
      </button>

      {open && (
        <div
          className="absolute left-0 z-50 mt-1 w-72 overflow-hidden rounded-xl border border-dl-border bg-white shadow-lg"
          onKeyDown={onKeyDown}
        >
          <div className="flex items-center gap-2 border-b border-dl-border px-3 py-2">
            <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            <input
              ref={inputRef}
              type="text"
              role="searchbox"
              aria-label={`Search ${ariaLabel}`}
              placeholder="Search languages…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              className="w-full bg-transparent text-xs outline-none placeholder:text-slate-400"
            />
          </div>
          <ul ref={listRef} role="listbox" aria-label={ariaLabel} className="max-h-64 overflow-auto py-1">
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-xs text-slate-400">No language matches that search.</li>
            )}
            {filtered.map((l, i) => (
              <li key={l.code} data-index={i} role="option" aria-selected={l.code === value}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(l.code)}
                  className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs ${
                    i === active ? "bg-dl-blue-light/60 text-dl-blue" : "text-slate-700 hover:bg-dl-blue-light/30"
                  }`}
                >
                  <span className="truncate">{languageOptionLabel(l)}</span>
                  {l.code === value && <Check className="h-3.5 w-3.5 shrink-0" />}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
