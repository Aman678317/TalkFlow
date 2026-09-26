import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, EmptyState, Field, Input, Modal } from "../components/ui";
import { useToasts } from "../stores/toast";

interface ApiKey {
  id: string; name: string; prefix: string; scopes: string[];
  created_at: string; last_used_at?: string | null; revoked: boolean;
}
const ALL_SCOPES = ["translate", "detect", "documents", "glossaries", "meetings", "usage", "admin"];

export default function ApiKeys() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [scopes, setScopes] = React.useState<string[]>(["translate", "detect"]);
  const [created, setCreated] = React.useState<{ key: string; name: string } | null>(null);

  const listQ = useQuery({ queryKey: ["api-keys"], queryFn: () => api<ApiKey[]>("/api/v1/api-keys") });

  const create = useMutation({
    mutationFn: () => api<ApiKey & { key: string }>("/api/v1/api-keys", { method: "POST", body: { name, scopes } }),
    onSuccess: (r) => {
      setOpen(false); setName("");
      setCreated({ key: r.key, name: r.name });
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e: any) => push({ kind: "error", title: "Could not create key", body: e.message }),
  });
  const rotate = useMutation({
    mutationFn: (id: string) => api<ApiKey & { key: string }>(`/api/v1/api-keys/${id}/rotate`, { method: "POST" }),
    onSuccess: (r) => { setCreated({ key: r.key, name: r.name }); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/api/v1/api-keys/${id}/revoke`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["api-keys"] }); push({ kind: "success", title: "API key revoked" }); },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Developer API keys</h1>
          <p className="text-xs text-ink-400">
            Keys authenticate via <code className="rounded bg-ink-100 px-1">X-API-Key</code> or Bearer.
            Only the hash is stored — the full key is shown exactly once. Never ship keys in browser code.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>+ New key</Button>
      </div>

      {(listQ.data ?? []).length === 0 ? (
        <Card><EmptyState title="No API keys" icon="⚿" body="Create a scoped key to call /api/v1/translate, /documents, /voice/session and more." /></Card>
      ) : (
        <div className="space-y-2">
          {(listQ.data ?? []).map((k) => (
            <div key={k.id} className="gt-card flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink-900">
                  {k.name} {k.revoked && <Badge tone="bad">revoked</Badge>}
                </p>
                <p className="font-mono text-[11px] text-ink-400">{k.prefix}…  · created {new Date(k.created_at).toLocaleDateString()}
                  {k.last_used_at ? ` · last used ${new Date(k.last_used_at).toLocaleString()}` : " · never used"}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {k.scopes.map((s) => <Badge key={s} tone="info">{s}</Badge>)}
                </div>
              </div>
              {!k.revoked && <>
                <Button size="sm" variant="secondary" onClick={() => rotate.mutate(k.id)}>Rotate</Button>
                <Button size="sm" variant="danger" onClick={() => revoke.mutate(k.id)}>Revoke</Button>
              </>}
            </div>
          ))}
        </div>
      )}

      <Card title="Quick start">
        <pre className="overflow-x-auto rounded-lg bg-ink-950 p-4 font-mono text-[11px] leading-relaxed text-signal-300">{`curl -X POST "$ORIGIN/api/v1/translate" \\
  -H "X-API-Key: gtk_..." -H "content-type: application/json" \\
  -d '{"text":"Good morning","target_language":"hi"}'`}</pre>
        <p className="mt-2 text-xs text-ink-400">
          Full OpenAPI schema at <a className="text-signal-700 hover:underline" href="/docs" target="_blank" rel="noreferrer">/docs</a> ·
          realtime protocol documented in docs/REALTIME.md · SDK-ready flat JSON contracts.
        </p>
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="New API key">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="production-backend" /></Field>
          <fieldset>
            <legend className="gt-label">Scopes</legend>
            <div className="grid grid-cols-2 gap-1.5">
              {ALL_SCOPES.map((s) => (
                <label key={s} className="flex items-center gap-2 text-sm text-ink-600">
                  <input type="checkbox" checked={scopes.includes(s)}
                         onChange={(e) => setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))} />
                  {s}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={create.isPending}>Create key</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!created} onClose={() => setCreated(null)} title="Copy your key now">
        <p className="text-sm text-ink-600">
          This is the only time <b>{created?.name}</b> will be shown. Store it securely (secret manager / CI secrets).
        </p>
        <code className="mt-3 block break-all rounded-lg bg-ink-950 p-3 font-mono text-xs text-signal-300">{created?.key}</code>
        <div className="mt-3 flex justify-end">
          <Button size="sm" onClick={async () => { await navigator.clipboard.writeText(created?.key ?? ""); push({ kind: "success", title: "Copied" }); }}>
            Copy to clipboard
          </Button>
        </div>
      </Modal>
    </div>
  );
}
