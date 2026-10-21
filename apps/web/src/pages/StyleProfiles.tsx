import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Field, Input, Modal, Select } from "../components/ui";
import { useToasts } from "../stores/toast";

/**
 * Style profiles.
 *
 * The page used to read `rules` / `prompt_fragment` / `is_system` — none of
 * which exist. The API serves `config_json` (a dict of tone / formality /
 * domain / flags), and a profile is *system* when it is global
 * (`org_id === null`), which is what makes it read-only server-side. The
 * previous shape meant the guidance was never shown, the typed guidance was
 * silently dropped on save, and system profiles offered Edit/Delete buttons
 * the API then rejected (2026-10-21 same-class sweep).
 */
interface Style {
  id: string;
  name: string;
  kind: string;
  version: number;
  config_json: Record<string, unknown>;
  status: string;
  org_id: string | null;
}

const TONES = ["professional", "friendly", "precise", "diplomatic", "persuasive", "clear", "neutral"];
const FORMALITIES = ["default", "formal", "informal", "neutral"];

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

function describeConfig(config: Record<string, unknown>): string[] {
  const parts: string[] = [];
  const tone = asString(config.tone, "");
  if (tone) parts.push(`tone: ${tone}`);
  const formality = asString(config.formality, "");
  if (formality) parts.push(`formality: ${formality}`);
  const domain = asString(config.domain, "");
  if (domain && domain !== "general") parts.push(`domain: ${domain}`);
  for (const [key, value] of Object.entries(config)) {
    if (["tone", "formality", "domain", "punctuation"].includes(key)) continue;
    if (value === true) parts.push(key);
    else if (value !== false && value !== null && value !== "") parts.push(`${key}: ${String(value)}`);
  }
  return parts;
}

export default function StyleProfiles() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const [open, setOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Style | null>(null);
  const [form, setForm] = React.useState({ name: "", kind: "custom", tone: "professional", formality: "default", domain: "general" });

  const listQ = useQuery({ queryKey: ["styles"], queryFn: () => api<Style[]>("/api/v1/style-profiles") });

  const save = useMutation({
    mutationFn: () => {
      // The API field is `config` — the old body sent `rules`/`prompt_fragment`,
      // which pydantic dropped, so every profile was stored with config={}.
      const config: Record<string, unknown> = {
        ...(editing?.config_json ?? {}),
        tone: form.tone,
        formality: form.formality,
        domain: form.domain,
      };
      const body = { name: form.name, kind: form.kind, config };
      return editing
        ? api(`/api/v1/style-profiles/${editing.id}`, { method: "PUT", body })
        : api("/api/v1/style-profiles", { method: "POST", body });
    },
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
    onError: (e: any) => push({ kind: "error", title: "Delete failed", body: e.message }),
  });

  function openEdit(s: Style) {
    setEditing(s);
    setForm({
      name: s.name,
      kind: s.kind,
      tone: asString(s.config_json?.tone, "professional"),
      formality: asString(s.config_json?.formality, "default"),
      domain: asString(s.config_json?.domain, "general"),
    });
    setOpen(true);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Style profiles</h1>
          <p className="text-xs text-ink-400">Versioned register/terminology guidance applied to translations. System profiles are immutable.</p>
        </div>
        <Button onClick={() => { setEditing(null); setForm({ name: "", kind: "custom", tone: "professional", formality: "default", domain: "general" }); setOpen(true); }}>
          + New profile
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(listQ.data ?? []).map((s) => {
          const isSystem = s.org_id === null;
          const summary = describeConfig(s.config_json ?? {});
          return (
            <Card key={s.id} title={s.name}
                  action={isSystem ? <Badge tone="info">system</Badge> : (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(s)}>Edit</Button>
                      <Button size="sm" variant="ghost" onClick={() => remove.mutate(s.id)} aria-label={`Delete ${s.name}`}>✕</Button>
                    </div>
                  )}>
              <p className="text-xs leading-relaxed text-ink-500">
                {summary.length ? summary.join(" · ") : "No guidance set."}
              </p>
              <p className="mt-2 text-[11px] text-ink-400">{s.kind} · v{s.version}{s.status ? ` · ${s.status}` : ""}</p>
            </Card>
          );
        })}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? `Edit ${editing.name}` : "New style profile"} wide>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Kind">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="custom">custom</option>
                <option value="formal">formal</option>
                <option value="casual">casual</option>
                <option value="technical">technical</option>
                <option value="legal">legal</option>
                <option value="finance">finance</option>
                <option value="support">support</option>
                <option value="education">education</option>
                <option value="sales">sales</option>
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Tone">
              <Select value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })}>
                {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Formality">
              <Select value={form.formality} onChange={(e) => setForm({ ...form, formality: e.target.value })}>
                {FORMALITIES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Domain">
              <Input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} />
            </Field>
          </div>
          {editing && (
            <p className="text-[11px] text-ink-400">
              Saving keeps the profile&apos;s other settings
              {Object.keys(editing.config_json ?? {}).length
                ? ` (${Object.keys(editing.config_json).filter((k) => !["tone", "formality", "domain"].includes(k)).join(", ") || "none"})`
                : ""}.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>Save profile</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
