import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Trash2 } from "lucide-react";
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

  const items: any[] = Array.isArray(historyQ.data)
    ? historyQ.data
    : (historyQ.data?.items ?? []);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900">Translation history</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Search and review translation records across your organization.
        </p>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="relative flex-1">
          <Input
            className="w-full rounded-xl pl-9"
            placeholder="Search source or translation…"
            aria-label="Search history"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400 pointer-events-none" aria-hidden="true" />
        </div>
        <div className="w-full sm:w-44">
          <Select
            aria-label="Filter source language"
            className="w-full rounded-xl"
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
            className="w-full rounded-xl"
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
      </div>

      {historyQ.isLoading ? (
        <Card>
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            title="Nothing here yet"
            body="Translations you run will be stored here with model, latency and quality metadata."
            icon="⧗"
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((h: any) => (
            <div
              key={h.id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-all duration-150 space-y-3"
            >
              {/* Card Header & Metadata */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5 text-xs text-slate-500">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral" className="text-xs font-medium">
                    {languageLabel(langs, h.source_lang || h.source_language)} → {languageLabel(langs, h.target_lang || h.target_language)}
                  </Badge>
                  <Badge tone="neutral" className="text-xs font-medium">
                    {h.kind || h.product || "text"}
                  </Badge>
                  {(h.from_tm || h.tm_match) && (
                    <Badge tone="good" className="text-xs font-medium">
                      translation memory
                    </Badge>
                  )}
                  <span>{h.provider} · {h.model}</span>
                  <span>{Math.round(h.latency_ms ?? 0)} ms</span>
                  <span>{formatHistoryDate(h.created_at)}</span>
                  {(h.quality_flags ?? []).map((f: string) => (
                    <Badge
                      key={f}
                      tone={f.includes("untranslated") ? "bad" : "neutral"}
                      className="text-xs font-medium"
                    >
                      {f.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>

                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => del(h.id)}
                  aria-label="Delete history item"
                  className="h-8 gap-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 hover:text-rose-700 active:bg-rose-100 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Delete</span>
                </Button>
              </div>

              {/* Translation Content */}
              <div className="space-y-1">
                <p className="text-sm text-slate-600 leading-relaxed">{h.source_text}</p>
                <p className="text-sm font-semibold text-slate-900 leading-relaxed">
                  {h.target_text || h.translated_text}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
