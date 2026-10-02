import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, Button, Card, EmptyState, Select } from "../components/ui";
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
  const inputRef = React.useRef<HTMLInputElement>(null);

  const docsQ = useQuery({ queryKey: ["documents"], queryFn: () => api<DocRow[]>("/api/v1/documents"), refetchInterval: 3000 });
  const glossQ = useQuery({ queryKey: ["glossaries"], queryFn: () => api<any[]>("/api/v1/glossaries") });
  const styleQ = useQuery({ queryKey: ["styles"], queryFn: () => api<any[]>("/api/v1/style-profiles") });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      if (file.size > MAX_MB * 1024 * 1024) throw new Error(`File exceeds ${MAX_MB} MB`);
      const form = new FormData();
      form.append("file", file);
      form.append("source_language", source);
      form.append("target_language", target);
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
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-lg font-bold text-ink-900">Document translation</h1>
        <p className="text-xs text-ink-400">PDF · DOCX · PPTX · XLSX · HTML · TXT — layout-preserving reconstruction with QA checks.</p>
      </div>

      {/* dropzone */}
      <div
        className={`gt-card flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed p-8 text-center transition ${
          dragOver ? "border-signal-500 bg-signal-50" : "border-ink-200"}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) upload.mutate(f);
        }}
        role="button" tabIndex={0} aria-label="Upload document"
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}>
        <span className="text-2xl" aria-hidden>▤</span>
        <p className="text-sm font-medium text-ink-700">Drop a document here, or click to browse</p>
        <p className="text-xs text-ink-400">Max {MAX_MB} MB · validated by content, not extension</p>
        <input ref={inputRef} type="file" accept={ACCEPT} className="hidden" aria-hidden
               onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
        {upload.isPending && <p className="text-xs text-signal-700">Uploading & scanning…</p>}
      </div>

      {/* options */}
      <Card title="Translation options">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="gt-label">Source language</span>
            <Select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source language">
              <option value="AUTO">Auto detect</option>
              {(langs ?? []).filter((l) => l.document_supported).map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </Select>
          </label>
          <label className="block">
            <span className="gt-label">Target language</span>
            <Select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Target language">
              {(langs ?? []).filter((l) => l.document_supported).map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </Select>
          </label>
          <label className="block">
            <span className="gt-label">Glossary</span>
            <Select value={glossaryId} onChange={(e) => setGlossaryId(e.target.value)} aria-label="Glossary">
              <option value="">None</option>
              {(glossQ.data ?? []).filter((g) => g.status === "active").map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </Select>
          </label>
          <label className="block">
            <span className="gt-label">Style profile</span>
            <Select value={styleId} onChange={(e) => setStyleId(e.target.value)} aria-label="Style profile">
              <option value="">Default</option>
              {(styleQ.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </label>
        </div>
      </Card>

      {/* list */}
      {(docsQ.data ?? []).length === 0 ? (
        <Card><EmptyState title="No documents yet" body="Uploaded documents and their pipeline status will appear here." icon="▤" /></Card>
      ) : (
        <div className="space-y-2">
          {(docsQ.data ?? []).map((d) => (
            <div key={d.id} className="gt-card p-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink-900">{d.filename}</p>
                  <p className="text-[11px] text-ink-400">
                    {(d.size_bytes / 1024).toFixed(0)} KB · {d.detected_language || d.source_language} → {d.target_language}
                    {" · "}{d.pages} pages · {new Date(d.created_at).toLocaleString()}
                  </p>
                </div>
                <Badge tone={d.status === "ready" ? "good" : d.status === "failed" ? "bad" : d.status === "review" ? "warn" : "info"}>
                  {d.status}
                </Badge>
                {d.status === "ready" && (
                  <Button size="sm" onClick={async () => {
                    const res = await api<Response>(`/api/v1/documents/${d.id}/download`, { raw: true });
                    const blob = await res.blob();
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = `translated_${d.filename}`;
                    a.click();
                    URL.revokeObjectURL(a.href);
                  }}>
                    Download
                  </Button>
                )}
                {(d.status === "failed" || d.status === "review") && (
                  <Button size="sm" variant="secondary" onClick={() => retry.mutate(d.id)} loading={retry.isPending}>Retry</Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(d.id)} aria-label={`Delete ${d.filename}`}>Delete</Button>
              </div>
              {d.status !== "ready" && d.status !== "failed" && (
                <div className="mt-3">
                  <div className="h-1.5 overflow-hidden rounded-full bg-ink-100" role="progressbar"
                       aria-valuenow={stageProgress(d)} aria-valuemin={0} aria-valuemax={100} aria-label="Translation progress">
                    <div className="h-full rounded-full bg-signal-500 transition-all" style={{ width: `${stageProgress(d)}%` }} />
                  </div>
                  <p className="mt-1 text-[11px] text-ink-400">
                    {d.status}… {d.segments_total > 0 && `(${d.segments_done}/${d.segments_total} segments)`}
                  </p>
                </div>
              )}
              {d.error && <p className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700">{d.error}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
