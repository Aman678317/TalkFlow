import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Trash2, Copy, Check, ArrowRight, X, Clock, Zap, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useLanguages, languageLabel } from "../hooks/useLanguages";
import { Badge, Button, Card, EmptyState, Input, Select, Skeleton } from "../components/ui";

function formatHistoryDate(isoStr?: string): string {
  if (!isoStr) return "";
  const date = new Date(isoStr);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function HistoryPage() {
  const { data: langs } = useLanguages();
  const [q, setQ] = React.useState("");
  const [src, setSrc] = React.useState("");
  const [tgt, setTgt] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 400);
    return () => clearTimeout(t);
  }, [q]);

  const historyQ = useQuery({
    queryKey: ["history", debounced, src, tgt],
    queryFn: async () => {
      const p = new URLSearchParams({ limit: "100" });
      if (debounced) p.set("q", debounced);
      if (src) p.set("source_language", src);
      if (tgt) p.set("target_language", tgt);
      const res = await api<any>(`/api/v1/history?${p}`);
      return Array.isArray(res) ? res : (res?.items ?? []);
    },
  });

  const del = async (id: string) => {
    await api(`/api/v1/history/${id}`, { method: "DELETE" });
    historyQ.refetch();
  };

  const copyToClipboard = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const clearFilters = () => {
    setQ("");
    setSrc("");
    setTgt("");
  };

  const hasActiveFilters = Boolean(q || src || tgt);
  const items: any[] = Array.isArray(historyQ.data)
    ? historyQ.data
    : (historyQ.data?.items ?? []);

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 lg:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Translation history</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Search and review translation records across your organization.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 shadow-xs">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            {items.length} {items.length === 1 ? "record" : "records"}
          </span>
        </div>
      </div>

      {/* Unified Filter Bar */}
      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-xs space-y-2.5">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
          <div className="relative flex-1">
            <Input
              className="w-full rounded-xl pl-9 pr-8 text-xs sm:text-sm border-slate-200 focus:border-dl-blue h-10"
              placeholder="Search source or translation…"
              aria-label="Search history"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400 pointer-events-none" aria-hidden="true" />
            {q && (
              <button
                type="button"
                onClick={() => setQ("")}
                className="absolute right-2.5 top-2.5 p-1 rounded-md text-slate-400 hover:text-slate-600"
                aria-label="Clear search input"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="w-full sm:w-44">
            <Select
              aria-label="Filter source language"
              className="w-full rounded-xl text-xs sm:text-sm border-slate-200 focus:border-dl-blue h-10"
              value={src}
              onChange={(e) => setSrc(e.target.value)}
            >
              <option value="">Any source</option>
              {(langs ?? []).map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="w-full sm:w-44">
            <Select
              aria-label="Filter target language"
              className="w-full rounded-xl text-xs sm:text-sm border-slate-200 focus:border-dl-blue h-10"
              value={tgt}
              onChange={(e) => setTgt(e.target.value)}
            >
              <option value="">Any target</option>
              {(langs ?? []).map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </Select>
          </div>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center justify-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors h-10"
            >
              <X className="h-3.5 w-3.5" /> Reset
            </button>
          )}
        </div>
      </div>

      {/* History Items Feed */}
      {historyQ.isLoading ? (
        <Card>
          <div className="space-y-3 p-4">
            {[1, 2, 3, 4].map((key) => (
              <Skeleton key={key} className="h-20 w-full rounded-xl" />
            ))}
          </div>
        </Card>
      ) : items.length === 0 ? (
        <Card className="border border-slate-200 bg-white p-8 text-center">
          <EmptyState
            title={hasActiveFilters ? "No matching records found" : "No translation history yet"}
            body={
              hasActiveFilters
                ? "Try clearing your search query or language filters to see more results."
                : "Translations you perform will be archived here with language pairs, latency, and quality telemetry."
            }
            icon="⧗"
          />
          {hasActiveFilters && (
            <div className="mt-4">
              <Button size="sm" variant="secondary" onClick={clearFilters}>
                Clear filters
              </Button>
            </div>
          )}
        </Card>
      ) : (
        <div className="space-y-3.5">
          {items.map((h: any) => {
            const sourceLabel = languageLabel(langs, h.source_lang || h.source_language);
            const targetLabel = languageLabel(langs, h.target_lang || h.target_language);
            const targetText = h.target_text || h.translated_text || "";
            const isCopied = copiedId === h.id;

            return (
              <div
                key={h.id}
                className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-xs hover:border-slate-300 hover:shadow-card transition-all space-y-3.5"
              >
                {/* Header Metadata Bar */}
                <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-100 pb-3 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Language Pair Pill */}
                    <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-800 border border-slate-200/70">
                      <span>{sourceLabel}</span>
                      <ArrowRight className="h-3 w-3 text-slate-400" />
                      <span className="text-dl-blue">{targetLabel}</span>
                    </span>

                    {/* Modality Tag */}
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600 uppercase tracking-wider">
                      {h.kind || h.product || "text"}
                    </span>

                    {/* TM Badge if applicable */}
                    {(h.from_tm || h.tm_match) && (
                      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                        <Sparkles className="h-3 w-3 text-emerald-600" /> Translation Memory
                      </span>
                    )}

                    {/* Latency Tag */}
                    <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-mono text-slate-600">
                      <Zap className="h-3 w-3 text-amber-500" /> {Math.round(h.latency_ms ?? 0)} ms
                    </span>

                    {/* Timestamp */}
                    <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 font-medium">
                      <Clock className="h-3 w-3 text-slate-400" /> {formatHistoryDate(h.created_at)}
                    </span>

                    {/* Quality Flags */}
                    {(h.quality_flags ?? []).map((f: string) => (
                      <Badge
                        key={f}
                        tone={f.includes("untranslated") ? "bad" : "neutral"}
                        className="text-[11px] font-medium"
                      >
                        {f.replace(/_/g, " ")}
                      </Badge>
                    ))}
                  </div>

                  {/* Actions: Copy & Delete */}
                  <div className="flex items-center gap-1">
                    {targetText && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard(h.id, targetText)}
                        aria-label="Copy translation"
                        title="Copy translation"
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors"
                      >
                        {isCopied ? (
                          <>
                            <Check className="h-3.5 w-3.5 text-emerald-600" />
                            <span className="text-emerald-700">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="h-3.5 w-3.5 text-slate-400" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => del(h.id)}
                      aria-label="Delete history record"
                      title="Delete record"
                      className="inline-flex items-center gap-1 rounded-lg p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Structured Comparative Content */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  {/* Source Block */}
                  <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3 space-y-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                      Source · {sourceLabel}
                    </span>
                    <p className="text-sm text-slate-700 leading-relaxed break-words font-normal">
                      {h.source_text || "—"}
                    </p>
                  </div>

                  {/* Target Block */}
                  <div className="rounded-xl border border-blue-100 bg-blue-50/20 p-3 space-y-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-dl-blue block">
                      Translation · {targetLabel}
                    </span>
                    <p className="text-sm text-dl-navy leading-relaxed break-words font-semibold">
                      {targetText || "—"}
                    </p>
                  </div>
                </div>

                {/* Engine / Model Details Footer */}
                {(h.provider || h.model) && (
                  <div className="flex items-center justify-between pt-1 text-[11px] text-slate-400 font-mono">
                    <span>Engine: {h.provider || "default"} / {h.model || "standard"}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
