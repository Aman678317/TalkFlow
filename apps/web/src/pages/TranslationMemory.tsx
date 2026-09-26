import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, Button, Card, EmptyState, Field, Input, Modal, Select, Textarea } from "../components/ui";

interface TmEntry {
  id: string; source_text: string; target_text: string; source_language: string;
  target_language: string; domain: string; approved: boolean; confidence: number;
  usage_count: number; version: number; created_at: string;
}

export default function TranslationMemory() {
  const qc = useQueryClient();
  const { data: langs } = useLanguages();
  const [addOpen, setAddOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [form, setForm] = React.useState({
    source_text: "", target_text: "", source_language: "en", target_language: "hi",
    domain: "general", approved: true,
  });

  const listQ = useQuery({
    queryKey: ["tm", q],
    queryFn: () => api<TmEntry[]>(`/api/v1/translation-memories?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  });

  const add = useMutation({
    mutationFn: () => api("/api/v1/translation-memories", { method: "POST", body: form }),
    onSuccess: () => { setAddOpen(false); qc.invalidateQueries({ queryKey: ["tm"] }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/translation-memories/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tm"] }),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Translation memory</h1>
          <p className="text-xs text-ink-400">
            Exact + fuzzy (embedding cosine) reuse before model generation. Approved entries win; every hit is metered as provider=tm.
          </p>
        </div>
        <div className="flex gap-2">
          <Input placeholder="Search source text…" aria-label="Search translation memory" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" />
          <Button onClick={() => setAddOpen(true)}>+ Add entry</Button>
        </div>
      </div>

      {(listQ.data ?? []).length === 0 ? (
        <Card><EmptyState title="Memory is empty" icon="⛁"
          body="Successful translations are added automatically; you can also curate approved pairs here." /></Card>
      ) : (
        <div className="space-y-2">
          {(listQ.data ?? []).map((t) => (
            <div key={t.id} className="gt-card p-4">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                <Badge>{t.source_language} → {t.target_language}</Badge>
                {t.approved ? <Badge tone="good">approved</Badge> : <Badge tone="warn">unreviewed</Badge>}
                <span>v{t.version}</span>
                <span title="times reused">used {t.usage_count}×</span>
                <span>confidence {(t.confidence * 100).toFixed(0)}%</span>
                <span>{t.domain}</span>
                <div className="flex-1" />
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(t.id)} aria-label="Delete entry">Delete</Button>
              </div>
              <p className="text-sm text-ink-500">{t.source_text}</p>
              <p className="mt-0.5 text-sm font-medium text-ink-900">{t.target_text}</p>
            </div>
          ))}
        </div>
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add memory entry" wide>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Source text"><Textarea rows={3} required value={form.source_text} onChange={(e) => setForm({ ...form, source_text: e.target.value })} /></Field>
            <Field label="Target text"><Textarea rows={3} required value={form.target_text} onChange={(e) => setForm({ ...form, target_text: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Source lang">
              <Select value={form.source_language} onChange={(e) => setForm({ ...form, source_language: e.target.value })}>
                {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </Select>
            </Field>
            <Field label="Target lang">
              <Select value={form.target_language} onChange={(e) => setForm({ ...form, target_language: e.target.value })}>
                {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </Select>
            </Field>
            <Field label="Domain"><Input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-ink-600">
            <input type="checkbox" checked={form.approved} onChange={(e) => setForm({ ...form, approved: e.target.checked })} />
            Approved (human-verified — wins over fuzzy matches)
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button type="submit" loading={add.isPending}>Save entry</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
