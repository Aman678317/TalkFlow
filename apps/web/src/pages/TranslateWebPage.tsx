/**
 * Translate a public web page (reference parity, 2026-10-21).
 *
 * The server fetches the page with strict guards and returns its **readable
 * text**; the page here shows the source, the translation and the honest
 * caveats — this is a text translation of a page, not a mirrored page: images,
 * layout and scripts are not reproduced.
 */
import React from "react";
import { Globe, Link2, Loader2, ShieldCheck } from "lucide-react";
import { api, friendlyMessage } from "../lib/api";
import { useLanguages } from "../hooks/useLanguages";
import { normalizePageUrl, pageUrlProblem } from "../lib/pageUrl";
import type { PageTranslateResponse } from "../lib/types";
import { Button } from "../components/ui";
import { toast } from "../stores/toasts";

export default function TranslateWebPage() {
  const { data: langs } = useLanguages();
  const [url, setUrl] = React.useState("");
  const [target, setTarget] = React.useState("hi");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<PageTranslateResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function run() {
    const problem = pageUrlProblem(url);
    if (problem) {
      setError(problem);
      return;
    }
    const prepared = normalizePageUrl(url);
    if (!prepared) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await api<PageTranslateResponse>("/api/v1/translate/page", {
        method: "POST",
        body: { url: prepared, target_language: target },
      });
      setResult(r);
    } catch (e) {
      const message = friendlyMessage(e);
      setError(message);
      toast.error("Page translation unavailable", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 lg:p-8">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-900">
          <Globe className="h-5 w-5 text-dl-blue" />
          Translate a web page
        </h1>
        <p className="text-xs text-slate-500">
          Paste a link to a public page. Its readable text is fetched securely and translated —
          images, layout and scripts are not reproduced.
        </p>
      </header>

      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Link2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="url"
              inputMode="url"
              aria-label="Page URL"
              placeholder="https://example.com/article"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !busy) void run();
              }}
              className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-dl-blue focus:ring-2 focus:ring-dl-blue/20"
            />
          </div>
          <select
            aria-label="Target language"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm"
          >
            {(langs ?? []).map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
          </select>
          <Button onClick={() => void run()} disabled={busy} className="h-10 gap-2">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
            {busy ? "Fetching…" : "Translate page"}
          </Button>
        </div>

        {error && (
          <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {error}
          </p>
        )}

        <p className="flex items-start gap-2 text-[11px] text-slate-400">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
          Only public web addresses are fetched. Private, loopback and link-local addresses
          (including cloud metadata endpoints) are refused, redirects are re-checked, and the
          response size and type are capped.
        </p>
      </div>

      {result && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="font-semibold text-slate-800">{result.title || result.final_url}</span>
            <a
              href={result.final_url}
              target="_blank"
              rel="noreferrer noopener"
              className="text-dl-blue underline"
            >
              {result.final_url}
            </a>
            <span>
              {result.source_language} → {result.target_language}
            </span>
            <span>
              {Math.round(result.latency_ms)} ms · {result.provider}
            </span>
            {result.truncated && (
              <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                Page text was truncated
              </span>
            )}
          </div>

          {result.glossary_note && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              {result.glossary_note}
            </p>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Source text
              </h2>
              <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-700">
                {result.source_text}
              </pre>
            </section>
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Translation
              </h2>
              <pre className="animate-result-reveal max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800">
                {result.translated_text}
              </pre>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
