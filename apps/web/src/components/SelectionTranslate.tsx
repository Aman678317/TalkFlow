/**
 * "Translate a selection" popover.
 *
 * The reference product translates whatever text you select (its browser
 * extension). Inside the app the same gesture works on the source editor:
 * select a phrase and translate just that phrase, without sending the whole
 * draft.
 *
 * The popover is anchored to the editor's top-right corner (the editor is a
 * textarea, so there is no DOM range to position against reliably).
 */
import React from "react";
import { Languages, Loader2, X } from "lucide-react";
import { api, friendlyMessage } from "../lib/api";
import { isTranslatableSelection, selectedTextIn } from "../lib/selection";

export function SelectionTranslate({
  editorRef,
  sourceLanguage,
  targetLanguage,
  onApply,
}: {
  editorRef: React.RefObject<HTMLTextAreaElement | null>;
  sourceLanguage: string;
  targetLanguage: string;
  /** Called with the translation so the caller can use it (e.g. copy). */
  onApply?: (translation: string) => void;
}) {
  const [text, setText] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const popoverRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    function onUp(e: Event) {
      // A click inside the popover must NOT clear the selection: the browser
      // collapses the textarea selection on mousedown, and the document mouseup
      // would otherwise unmount the popover before the button's click ran.
      const target = e.target as Node | null;
      if (target && popoverRef.current?.contains(target)) return;
      const el = editorRef.current;
      if (!el) return;
      const sel = selectedTextIn(el);
      if (!isTranslatableSelection(sel)) {
        setText(null);
        return;
      }
      setText(sel);
      setResult(null);
      setError(null);
    }
    document.addEventListener("mouseup", onUp);
    document.addEventListener("keyup", onUp);
    return () => {
      document.removeEventListener("mouseup", onUp);
      document.removeEventListener("keyup", onUp);
    };
  }, [editorRef]);

  async function translateSelection() {
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ translations?: { translated_text?: string }[]; translated_text?: string }>(
        "/api/v1/translate",
        {
          method: "POST",
          body: {
            text,
            source_language: sourceLanguage === "AUTO" ? "AUTO" : sourceLanguage,
            target_language: targetLanguage,
          },
        },
      );
      const translated = r?.translations?.[0]?.translated_text ?? r?.translated_text ?? "";
      setResult(translated);
      onApply?.(translated);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!text) return null;

  return (
    <div
      ref={popoverRef}
      className="absolute right-3 top-2 z-30 w-72 rounded-xl border border-slate-200 bg-white p-3 shadow-lg animate-scale-in"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <p className="line-clamp-2 text-[11px] text-slate-500" title={text}>
          “{text}”
        </p>
        <button
          type="button"
          onClick={() => { setText(null); setResult(null); }}
          aria-label="Close selection translation"
          className="text-slate-400 hover:text-slate-600"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {result ? (
        <div className="space-y-2">
          <p className="text-sm text-slate-800 animate-result-reveal">{result}</p>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => { void navigator.clipboard.writeText(result); }}
              className="rounded-lg border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:bg-slate-50"
            >
              Copy
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => void translateSelection()}
          disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-iris-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-iris-700 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Languages className="h-3.5 w-3.5" />}
          {busy ? "Translating…" : "Translate selection"}
        </button>
      )}

      {error && <p className="mt-2 text-[11px] text-rose-600">{error}</p>}
    </div>
  );
}
