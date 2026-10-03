import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, Trash2, Download } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useLanguages } from "../hooks/useLanguages";
import { Button, Select } from "../components/ui";
import { toast } from "../stores/toasts";

const MAX_MB = 50;
const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.txt,.html,.htm";

interface DocRow {
  id: string; filename: string; status: string; source_language: string; target_language: string;
  detected_language: string; pages: number; segments_total: number; segments_done: number;
  error?: string | null; created_at: string; size_bytes: number; mime_type: string;
}

export default function Documents() {
  const qc = useQueryClient();
  const { data: langs } = useLanguages();
  const [dragOver, setDragOver] = React.useState(false);
  const [target, setTarget] = React.useState("hi");
  const [source, setSource] = React.useState("AUTO");
  const [glossaryId, setGlossaryId] = React.useState("");
  const [styleId, setStyleId] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<"all" | "active" | "completed">("all");
  const inputRef = React.useRef<HTMLInputElement>(null);

  const docsQ = useQuery({ queryKey: ["documents"], queryFn: () => api<DocRow[]>("/api/v1/documents"), refetchInterval: 3000 });
  const glossQ = useQuery({ queryKey: ["glossaries"], queryFn: () => api<any[]>("/api/v1/glossaries") });
  const styleQ = useQuery({ queryKey: ["styles"], queryFn: () => api<any[]>("/api/v1/style-profiles") });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      if (file.size > MAX_MB * 1024 * 1024) throw new Error(`File exceeds ${MAX_MB} MB`);
      const form = new FormData();
      form.append("file", file);
      form.append("target_lang", target);
      form.append("target_language", target);
      form.append("source_lang", source);
      form.append("source_language", source);
      if (glossaryId) form.append("glossary_id", glossaryId);
      if (styleId) form.append("style_profile_id", styleId);
      return api<DocRow>("/api/v1/documents", { method: "POST", form });
    },
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.success("Upload received", `${d.filename} is being processed.`);
    },
    onError: (e: any) => toast.error("Upload failed", e instanceof ApiError ? e.message : String(e.message ?? e)),
  });

  const retry = useMutation({
    mutationFn: (id: string) => api(`/api/v1/documents/${id}/retry`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });

  const STAGE_ORDER = ["uploaded", "queued", "scanning", "parsing", "translating", "reconstructing", "quality_check", "ready"];
  function stageProgress(d: DocRow): number {
    if (d.status === "failed") return 100;
    const idx = Math.max(0, STAGE_ORDER.indexOf(d.status));
    return Math.round((idx / (STAGE_ORDER.length - 1)) * 100);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 lg:p-6">
      {/* Page Header */}
      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">Document translation</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          PDF · DOCX · PPTX · XLSX · HTML · TXT — layout-preserving reconstruction with QA checks.
        </p>
      </div>

      {/* Modern Upload Dropzone */}
      <div
        className={`flex flex-col items-center justify-center gap-2.5 rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
          upload.isPending
            ? "border-slate-300 bg-slate-50 opacity-75 cursor-not-allowed"
            : dragOver
            ? "border-dl-blue bg-blue-50/50 scale-[0.99] cursor-pointer"
            : "border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50/50 shadow-xs cursor-pointer"
        }`}
        onClick={() => { if (!upload.isPending) inputRef.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); if (!upload.isPending) setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false);
          if (upload.isPending) return;
          const f = e.dataTransfer.files?.[0];
          if (f) upload.mutate(f);
        }}
        role="button" tabIndex={0} aria-label="Upload document"
        onKeyDown={(e) => e.key === "Enter" && !upload.isPending && inputRef.current?.click()}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-dl-blue shadow-xs">
          <Upload className="h-6 w-6" />
        </div>
        <p className="text-sm font-semibold text-slate-800">
          Drop a document here, or <span className="text-dl-blue underline">browse your files</span>
        </p>
        <p className="text-xs text-slate-400">
          Supports PDF, Word, PowerPoint, Excel, and Text up to {MAX_MB} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          aria-hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }}
        />
        {upload.isPending && (
          <p className="text-xs font-semibold text-dl-blue animate-pulse">Uploading and scanning…</p>
        )}
      </div>

      {/* Translation Options Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-3">Translation options</h3>
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
              Source language
            </span>
            <Select
              className="w-full rounded-xl text-xs sm:text-sm border-slate-200 h-10"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              aria-label="Source language"
            >
              <option value="AUTO">Auto detect</option>
              {(langs ?? []).filter((l) => l.document_supported).map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </Select>
          </label>
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
              Target language
            </span>
            <Select
              className="w-full rounded-xl text-xs sm:text-sm border-slate-200 h-10"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              aria-label="Target language"
            >
              {(langs ?? []).filter((l) => l.document_supported).map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </Select>
          </label>
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
              Glossary
            </span>
            <Select
              className="w-full rounded-xl text-xs sm:text-sm border-slate-200 h-10"
              value={glossaryId}
              onChange={(e) => setGlossaryId(e.target.value)}
              aria-label="Glossary"
            >
              <option value="">None</option>
              {(glossQ.data ?? []).filter((g) => g.status === "active").map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </Select>
          </label>
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
              Style profile
            </span>
            <Select
              className="w-full rounded-xl text-xs sm:text-sm border-slate-200 h-10"
              value={styleId}
              onChange={(e) => setStyleId(e.target.value)}
              aria-label="Style profile"
            >
              <option value="">Default</option>
              {(styleQ.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </label>
        </div>
      </div>

      {/* Documents Queue List */}
      {(() => {
        const allDocs = docsQ.data ?? [];
        const filteredDocs = allDocs.filter((d) => {
          if (statusFilter === "active") return d.status !== "ready" && d.status !== "failed";
          if (statusFilter === "completed") return d.status === "ready";
          return true;
        });

        return (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Documents queue</h3>
                <p className="text-xs text-slate-500">Track translation pipeline status and download completed documents.</p>
              </div>

              <div className="flex gap-1 rounded-xl bg-slate-100 p-1 text-xs font-medium" role="tablist" aria-label="Filter documents by status">
                {(["all", "active", "completed"] as const).map((tab) => {
                  const count =
                    tab === "all"
                      ? allDocs.length
                      : tab === "active"
                      ? allDocs.filter((d) => d.status !== "ready" && d.status !== "failed").length
                      : allDocs.filter((d) => d.status === "ready").length;
                  return (
                    <button
                      key={tab}
                      type="button"
                      role="tab"
                      aria-selected={statusFilter === tab}
                      onClick={() => setStatusFilter(tab)}
                      className={`rounded-lg px-3 py-1 capitalize transition-colors ${
                        statusFilter === tab
                          ? "bg-white text-slate-900 shadow-xs font-semibold"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      {tab === "all" ? "All" : tab === "active" ? "Active" : "Completed"} ({count})
                    </button>
                  );
                })}
              </div>
            </div>

            {filteredDocs.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400">
                {statusFilter === "active"
                  ? "No active translations currently processing."
                  : statusFilter === "completed"
                  ? "No completed documents ready for download yet."
                  : "No documents uploaded yet. Drop a file above to begin."}
              </div>
            ) : (
              <div className="space-y-3">
                {filteredDocs.map((d) => (
                  <div key={d.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-dl-blue shrink-0">
                          <FileText className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-slate-900">{d.filename}</p>
                          <p className="text-[11px] text-slate-500">
                            {(d.size_bytes / 1024).toFixed(0)} KB · {d.detected_language || d.source_language} → {d.target_language} · {d.pages} pages · {new Date(d.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded-md px-2.5 py-0.5 text-[11px] font-semibold uppercase ${
                            d.status === "ready"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : d.status === "failed"
                              ? "bg-rose-50 text-rose-700 border border-rose-200"
                              : "bg-blue-50 text-dl-blue border border-blue-200"
                          }`}
                        >
                          {d.status}
                        </span>

                        {d.status === "ready" && (
                          <Button
                            size="sm"
                            className="bg-dl-blue hover:bg-dl-blue-hover text-white gap-1 h-8"
                            onClick={async () => {
                              const res = await api<Response>(`/api/v1/documents/${d.id}/download`, { raw: true });
                              const blob = await res.blob();
                              const a = document.createElement("a");
                              a.href = URL.createObjectURL(blob);
                              a.download = `translated_${d.filename}`;
                              a.click();
                              URL.revokeObjectURL(a.href);
                            }}
                          >
                            <Download className="h-3.5 w-3.5" /> Download
                          </Button>
                        )}

                        {(d.status === "failed" || d.status === "review") && (
                          <Button size="sm" variant="secondary" onClick={() => retry.mutate(d.id)} loading={retry.isPending} className="h-8">
                            Retry
                          </Button>
                        )}

                        <button
                          type="button"
                          onClick={() => remove.mutate(d.id)}
                          aria-label={`Delete ${d.filename}`}
                          className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>

                    {d.status !== "ready" && d.status !== "failed" && (
                      <div className="mt-2 space-y-1">
                        <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar"
                             aria-valuenow={stageProgress(d)} aria-valuemin={0} aria-valuemax={100} aria-label="Translation progress">
                          <div className="h-full rounded-full bg-dl-blue transition-all duration-300" style={{ width: `${stageProgress(d)}%` }} />
                        </div>
                        <p className="text-[11px] text-slate-400">
                          {d.status}… {d.segments_total > 0 && `(${d.segments_done}/${d.segments_total} segments)`}
                        </p>
                      </div>
                    )}
                    {d.error && <p className="mt-2 rounded-lg bg-rose-50 px-2.5 py-1 text-xs text-rose-700">{d.error}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
