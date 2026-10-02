import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Field, Input, Modal, Textarea } from "../components/ui";
import { useToasts } from "../stores/toast";

interface Style {
  id: string; name: string; kind: string; version: number;
  rules: Record<string, unknown>; prompt_fragment: string; is_system: boolean;
}

export default function StyleProfiles() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const [open, setOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Style | null>(null);
  const [form, setForm] = React.useState({ name: "", kind: "custom", prompt_fragment: "" });

  const listQ = useQuery({ queryKey: ["styles"], queryFn: () => api<Style[]>("/api/v1/style-profiles") });

  const save = useMutation({
    mutationFn: () =>
      editing
        ? api(`/api/v1/style-profiles/${editing.id}`, { method: "PUT", body: { ...form, rules: {} } })
        : api("/api/v1/style-profiles", { method: "POST", body: { ...form, rules: {} } }),
    onSuccess: () => {
      setOpen(false); setEditing(null);
      qc.invalidateQueries({ queryKey: ["styles"] });
      push({ kind: "success", title: editing ? "Style updated (version bumped)" : "Style created" });
    },
    onError: (e: any) => push({ kind: "error", title: "Save failed", body: e.message }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/style-profiles/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["styles"] }),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Style profiles</h1>
          <p className="text-xs text-ink-400">Versioned register/terminology guidance applied to translations. System profiles are immutable.</p>
        </div>
        <Button onClick={() => { setEditing(null); setForm({ name: "", kind: "custom", prompt_fragment: "" }); setOpen(true); }}>
          + New profile
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(listQ.data ?? []).map((s) => (
          <Card key={s.id} title={s.name}
                action={s.is_system ? <Badge tone="info">system</Badge> : (
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => {
                      setEditing(s); setForm({ name: s.name, kind: s.kind, prompt_fragment: s.prompt_fragment }); setOpen(true);
                    }}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => remove.mutate(s.id)} aria-label={`Delete ${s.name}`}>✕</Button>
                  </div>
                )}>
            <p className="text-xs leading-relaxed text-ink-500">{s.prompt_fragment || "No guidance text."}</p>
            <p className="mt-2 text-[11px] text-ink-400">{s.kind} · v{s.version}</p>
          </Card>
        ))}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? `Edit ${editing.name}` : "New style profile"} wide>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Kind"><Input value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} placeholder="formal / legal / …" /></Field>
          </div>
          <Field label="Guidance" hint="Applied as style_hint to LLM-routed providers; stored with each translation as style_profile_version">
            <Textarea rows={5} value={form.prompt_fragment} onChange={(e) => setForm({ ...form, prompt_fragment: e.target.value })} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>{editing ? "Save (bump version)" : "Create"}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
