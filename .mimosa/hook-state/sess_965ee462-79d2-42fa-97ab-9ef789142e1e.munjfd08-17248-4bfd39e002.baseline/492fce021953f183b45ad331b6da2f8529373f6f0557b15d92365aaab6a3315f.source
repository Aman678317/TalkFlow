import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, Button, Card, EmptyState, Field, Input, Modal, Select, Textarea } from "../components/ui";
import { useToasts } from "../stores/toast";

interface Glossary {
  id: string; name: string; source_language: string; target_language: string;
  version: number; status: string; domain: string; term_count: number; created_at: string; description?: string;
}
interface Term {
  id: string; source_term: string; target_term: string; part_of_speech: string;
  do_not_translate: boolean; spoken_variants: string[];
}

export default function Glossaries() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const { data: langs } = useLanguages();
  const [selected, setSelected] = React.useState<string | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [termOpen, setTermOpen] = React.useState(false);
  const [importOpen, setImportOpen] = React.useState(false);
  const [form, setForm] = React.useState({ name: "", source_language: "en", target_language: "hi", domain: "general", description: "" });
  const [term, setTerm] = React.useState({ source_term: "", target_term: "", part_of_speech: "", do_not_translate: false, spoken_variants: "" });
  const [csvText, setCsvText] = React.useState("");

  const listQ = useQuery({ queryKey: ["glossaries"], queryFn: () => api<Glossary[]>("/api/v1/glossaries") });
  const detailQ = useQuery({
    queryKey: ["glossary", selected],
    queryFn: () => api<Glossary & { terms: Term[] }>(`/api/v1/glossaries/${selected}`),
    enabled: !!selected,
  });

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["glossaries"] }); qc.invalidateQueries({ queryKey: ["glossary"] }); };

  const create = useMutation({
    mutationFn: () => api("/api/v1/glossaries", { method: "POST", body: form }),
    onSuccess: (g: any) => { setCreateOpen(false); setSelected(g.id); invalidate(); },
    onError: (e: any) => push({ kind: "error", title: "Create failed", body: e.message }),
  });
  const addTerm = useMutation({
    mutationFn: () => api(`/api/v1/glossaries/${selected}/terms`, {
      method: "POST",
      body: { ...term, spoken_variants: term.spoken_variants.split(",").map((s) => s.trim()).filter(Boolean) },
    }),
    onSuccess: () => { setTermOpen(false); setTerm({ source_term: "", target_term: "", part_of_speech: "", do_not_translate: false, spoken_variants: "" }); invalidate(); },
  });
  const removeTerm = useMutation({
    mutationFn: (tid: string) => api(`/api/v1/glossaries/${selected}/terms/${tid}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
  const activate = useMutation({
    mutationFn: () => api(`/api/v1/glossaries/${selected}/activate`, { method: "POST" }),
    onSuccess: () => { invalidate(); push({ kind: "success", title: "Glossary activated", body: "It now applies to text, documents, chat and realtime translation." }); },
    onError: (e: any) => push({ kind: "error", title: "Cannot activate", body: e.message }),
  });
  const archive = useMutation({
    mutationFn: () => api(`/api/v1/glossaries/${selected}/archive`, { method: "POST" }),
    onSuccess: invalidate,
  });
  const importCsv = useMutation({
    mutationFn: () => api(`/api/v1/glossaries/${selected}/import?csv_text=${encodeURIComponent(csvText)}`, { method: "POST" }),
    onSuccess: (r: any) => { setImportOpen(false); invalidate(); push({ kind: "success", title: `Imported ${r.imported} terms` }); },
  });

  const g = detailQ.data;

  return (
    <div className="mx-auto max-w-6xl p-4 lg:p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Glossaries</h1>
          <p className="text-xs text-ink-400">Terminology enforcement across text, documents, chat and realtime voice (with spoken-variant normalization).</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>+ New glossary</Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-2">
          {(listQ.data ?? []).map((gl) => (
            <button key={gl.id} onClick={() => setSelected(gl.id)}
                    className={`gt-card w-full p-3.5 text-left transition hover:border-signal-300 ${selected === gl.id ? "border-signal-500 ring-2 ring-signal-500/20" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold text-ink-900">{gl.name}</p>
                <Badge tone={gl.status === "active" ? "good" : gl.status === "archived" ? "neutral" : "warn"}>{gl.status}</Badge>
              </div>
              <p className="mt-0.5 text-[11px] text-ink-400">
                {gl.source_language} → {gl.target_language} · v{gl.version} · {gl.term_count} terms · {gl.domain}
              </p>
            </button>
          ))}
          {(listQ.data ?? []).length === 0 && (
            <Card><EmptyState title="No glossaries" body="Create one to enforce your terminology everywhere." icon="❡" /></Card>
          )}
        </div>

        {g ? (
          <Card title={<span>{g.name} <span className="font-normal text-ink-400">v{g.version}</span></span>}
                action={
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => setImportOpen(true)}>Import CSV</Button>
                    <Button size="sm" variant="secondary" onClick={() => window.open(`/api/v1/glossaries/${g.id}/export`)}>Export</Button>
                    {g.status === "draft" && <Button size="sm" onClick={() => activate.mutate()}>Activate</Button>}
                    {g.status === "active" && <Button size="sm" variant="ghost" onClick={() => archive.mutate()}>Archive</Button>}
                    <Button size="sm" onClick={() => setTermOpen(true)}>+ Term</Button>
                  </div>
                }>
            {g.description && <p className="mb-3 text-xs text-ink-500">{g.description}</p>}
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-[11px] uppercase tracking-wider text-ink-400">
                  <th className="py-2 pr-2">Source ({g.source_language})</th>
                  <th className="py-2 pr-2">Target ({g.target_language})</th>
                  <th className="py-2 pr-2">Spoken variants</th>
                  <th className="py-2" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {g.terms.map((t) => (
                  <tr key={t.id} className="border-b border-ink-50">
                    <td className="py-2 pr-2">
                      {t.source_term}
                      {t.do_not_translate && <Badge tone="warn" title="Kept as-is in translations"> DNT</Badge>}
                    </td>
                    <td className="py-2 pr-2 font-medium">{t.target_term}</td>
                    <td className="py-2 pr-2 text-xs text-ink-400">{t.spoken_variants?.join(", ")}</td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => removeTerm.mutate(t.id)} aria-label={`Delete ${t.source_term}`}>✕</Button>
                    </td>
                  </tr>
                ))}
                {g.terms.length === 0 && (
                  <tr><td colSpan={4}><EmptyState title="No terms yet" body="Add terms individually or import a CSV." icon="❡" /></td></tr>
                )}
              </tbody>
            </table>
          </Card>
        ) : (
          <Card><EmptyState title="Select a glossary" body="Pick a glossary on the left to view and manage its terms." icon="←" /></Card>
        )}
      </div>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New glossary">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Source language">
              <Select value={form.source_language} onChange={(e) => setForm({ ...form, source_language: e.target.value })}>
                {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </Select>
            </Field>
            <Field label="Target language">
              <Select value={form.target_language} onChange={(e) => setForm({ ...form, target_language: e.target.value })}>
                {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Domain"><Input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} /></Field>
          <Field label="Description"><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button type="submit" loading={create.isPending}>Create</Button>
          </div>
        </form>
      </Modal>

      <Modal open={termOpen} onClose={() => setTermOpen(false)} title="Add term">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); addTerm.mutate(); }}>
          <Field label="Source term"><Input required value={term.source_term} onChange={(e) => setTerm({ ...term, source_term: e.target.value })} /></Field>
          <Field label="Target term"><Input required value={term.target_term} onChange={(e) => setTerm({ ...term, target_term: e.target.value })} /></Field>
          <Field label="Spoken variants" hint="Comma-separated pronunciations/ASR variants normalized before matching">
            <Input value={term.spoken_variants} onChange={(e) => setTerm({ ...term, spoken_variants: e.target.value })} placeholder="cloud console, cloud konsol" />
          </Field>
          <label className="flex items-center gap-2 text-sm text-ink-600">
            <input type="checkbox" checked={term.do_not_translate}
                   onChange={(e) => setTerm({ ...term, do_not_translate: e.target.checked })} />
            Do not translate (keep source term)
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setTermOpen(false)}>Cancel</Button>
            <Button type="submit" loading={addTerm.isPending}>Add term</Button>
          </div>
        </form>
      </Modal>

      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Import CSV">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); importCsv.mutate(); }}>
          <Field label="CSV content" hint="source_term,target_term[,pos[,do_not_translate]]">
            <Textarea rows={8} value={csvText} onChange={(e) => setCsvText(e.target.value)}
                      placeholder={"cloud console,क्लाउड कंसोल\nAPI key,API कुंजी"} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setImportOpen(false)}>Cancel</Button>
            <Button type="submit" loading={importCsv.isPending}>Import</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
