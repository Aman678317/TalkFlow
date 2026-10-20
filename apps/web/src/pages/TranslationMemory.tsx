import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, Button, Card, EmptyState, Field, Input, Modal, Select, Textarea } from "../components/ui";

interface TmEntry {
  id: string;
  source_text: string;
  target_text: string;
  source_language: string;
  target_language: string;
  domain: string;
  approved: boolean;
  confidence: number;
  usage_count: number;
  version: number;
  created_at: string;
  tm_id: string;
  tm_name: string;
}

interface TmMemory {
  id: string;
  name: string;
  source_lang: string;
  target_lang: string;
  domain: string;
  entry_count: number;
}

const emptyEntry = {
  source_text: "",
  target_text: "",
  source_language: "en",
  target_language: "hi",
  domain: "general",
  approved: true,
};

export default function TranslationMemory() {
  const qc = useQueryClient();
  const { data: langs } = useLanguages();
  const [addOpen, setAddOpen] = React.useState(false);
  const [memoryOpen, setMemoryOpen] = React.useState(false);
  const [editId, setEditId] = React.useState<string | null>(null);
  const [q, setQ] = React.useState("");
  const [form, setForm] = React.useState(emptyEntry);
  const [edit, setEdit] = React.useState({ target_text: "", approved: true });
  const [memory, setMemory] = React.useState({ name: "", source_lang: "en", target_lang: "hi", domain: "general" });

  // The entries endpoint returns the pairs themselves (the page used to read
  // the memory list, which rendered empty languages and "confidence NaN%").
  const listQ = useQuery({
    queryKey: ["tm-entries", q],
    queryFn: () => api<TmEntry[]>(`/api/v1/translation-memories/entries?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  });
  const memoriesQ = useQuery({
    queryKey: ["tm-memories"],
    queryFn: () => api<TmMemory[]>("/api/v1/translation-memories"),
  });
  const memories = memoriesQ.data ?? [];
  const editing = (listQ.data ?? []).find((e) => e.id === editId) ?? null;

  const add = useMutation({
    mutationFn: () =>
      api("/api/v1/translation-memories/entries", {
        method: "POST",
        body: {
          tm_id: memories[0]?.id ?? null,
          source_text: form.source_text,
          target_text: form.target_text,
          approved: form.approved,
          domain: form.domain,
        },
      }),
    onSuccess: () => {
      setAddOpen(false);
      setForm(emptyEntry);
      qc.invalidateQueries({ queryKey: ["tm-entries"] });
      qc.invalidateQueries({ queryKey: ["tm-memories"] });
    },
  });
  const update = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/translation-memories/entries/${id}`, { method: "PUT", body: edit }),
    onSuccess: () => {
      setEditId(null);
      qc.invalidateQueries({ queryKey: ["tm-entries"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/translation-memories/entries/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tm-entries"] }),
  });
  const createMemory = useMutation({
    mutationFn: () => api("/api/v1/translation-memories", { method: "POST", body: memory }),
    onSuccess: () => {
      setMemoryOpen(false);
      setMemory({ name: "", source_lang: "en", target_lang: "hi", domain: "general" });
      qc.invalidateQueries({ queryKey: ["tm-memories"] });
    },
  });

  function openEdit(entry: TmEntry) {
    setEdit({ target_text: entry.target_text, approved: entry.approved });
    setEditId(entry.id);
  }

  function exportCsv() {
    window.open("/api/v1/translation-memories/entries/export", "_blank");
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Translation memory</h1>
          <p className="text-xs text-ink-400">
            Exact + fuzzy (embedding cosine) reuse before model generation. Approved entries win; every hit is metered as provider=tm.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Input placeholder="Search source text…" aria-label="Search translation memory" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" />
          <Button variant="secondary" onClick={() => setMemoryOpen(true)}>+ Memory</Button>
          <Button variant="secondary" onClick={exportCsv}>Export CSV</Button>
          <Button onClick={() => setAddOpen(true)} disabled={memories.length === 0}>+ Add entry</Button>
        </div>
      </div>

      {(listQ.data ?? []).length === 0 ? (
        <Card><EmptyState title={q ? "No pair matches that search" : "Memory is empty"} icon="⛁"
          body={q
            ? "Try a different search term."
            : memories.length === 0
            ? "Create a translation memory first, then add the pairs you want to reuse."
            : "Successful translations are added automatically; you can also curate approved pairs here."} /></Card>
      ) : (
        <div className="space-y-2 stagger">
          {(listQ.data ?? []).map((t) => (
            <div key={t.id} className="gt-card p-4 motion-interactive">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                <Badge>{t.source_language} → {t.target_language}</Badge>
                {t.approved ? <Badge tone="good">approved</Badge> : <Badge tone="warn">unreviewed</Badge>}
                <span title="Memory this pair belongs to">{t.tm_name}</span>
                <span>v{t.version}</span>
                <span title="times reused">used {t.usage_count}×</span>
                <span>confidence {(t.confidence * 100).toFixed(0)}%</span>
                <span>{t.domain}</span>
                <div className="flex-1" />
                <Button size="sm" variant="ghost" onClick={() => openEdit(t)} aria-label={`Edit ${t.source_text}`}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(t.id)} aria-label={`Delete ${t.source_text}`}>Delete</Button>
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
          <Field label="Memory">
            <Select value={memories[0]?.id ?? ""} disabled>
              {memories.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.source_lang} → {m.target_lang})</option>)}
            </Select>
          </Field>
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

      <Modal open={memoryOpen} onClose={() => setMemoryOpen(false)} title="New translation memory">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); createMemory.mutate(); }}>
          <Field label="Name"><Input required value={memory.name} onChange={(e) => setMemory({ ...memory, name: e.target.value })} placeholder="Customer support (en→hi)" /></Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Source lang">
              <Select value={memory.source_lang} onChange={(e) => setMemory({ ...memory, source_lang: e.target.value })}>
                {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </Select>
            </Field>
            <Field label="Target lang">
              <Select value={memory.target_lang} onChange={(e) => setMemory({ ...memory, target_lang: e.target.value })}>
                {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </Select>
            </Field>
            <Field label="Domain"><Input value={memory.domain} onChange={(e) => setMemory({ ...memory, domain: e.target.value })} /></Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setMemoryOpen(false)}>Cancel</Button>
            <Button type="submit" loading={createMemory.isPending}>Create memory</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!editing} onClose={() => setEditId(null)} title="Edit memory entry" wide>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (editing) update.mutate(editing.id); }}>
          {editing && (
            <>
              <p className="text-xs text-ink-400">
                <span className="font-medium text-ink-600">{editing.source_text}</span>
                {" → "}
                <span className="font-medium text-ink-600">{editing.source_language} → {editing.target_language}</span>
                {" · "}
                {editing.tm_name} · v{editing.version}
              </p>
              <Field label="Target text">
                <Textarea rows={3} required value={edit.target_text} onChange={(e) => setEdit({ ...edit, target_text: e.target.value })} />
              </Field>
              <label className="flex items-center gap-2 text-sm text-ink-600">
                <input type="checkbox" checked={edit.approved} onChange={(e) => setEdit({ ...edit, approved: e.target.checked })} />
                Approved (human-verified — wins over fuzzy matches)
              </label>
            </>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setEditId(null)}>Cancel</Button>
            <Button type="submit" loading={update.isPending}>Save changes</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
