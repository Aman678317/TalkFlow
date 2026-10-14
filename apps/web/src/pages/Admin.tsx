import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Skeleton } from "../components/ui";
import { useToasts } from "../stores/toast";

export default function Admin() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const [tab, setTab] = React.useState<"health" | "flags" | "audit" | "users" | "security">("health");

  const overviewQ = useQuery({ queryKey: ["admin-overview"], queryFn: () => api<any>("/api/v1/admin/overview"), refetchInterval: 15_000 });
  const modelQ = useQuery({ queryKey: ["admin-model-health"], queryFn: () => api<Record<string, { available: boolean; ewma_latency_ms: number; error_rate: number; requests: number }>>("/api/v1/admin/model-health"), refetchInterval: 30_000 });
  const flagsQ = useQuery({ queryKey: ["admin-flags"], queryFn: () => api<Record<string, boolean>>("/api/v1/flags") });
  const auditQ = useQuery({ queryKey: ["admin-audit"], queryFn: () => api<any[]>("/api/v1/admin/audit-logs?limit=100"), enabled: tab === "audit" || tab === "security" });
  const usersQ = useQuery({ queryKey: ["admin-users"], queryFn: () => api<any[]>("/api/v1/admin/users"), enabled: tab === "users" });

  const setFlag = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api("/api/v1/admin/flags", { method: "PUT", body: { key: name, enabled } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-flags"] }); push({ kind: "success", title: "Feature flag updated" }); },
    onError: (e: any) => push({ kind: "error", title: "Flag update failed", body: e.message }),
  });
  const setUserStatus = useMutation({
    mutationFn: ({ uid, suspend }: { uid: string; suspend: boolean }) =>
      api(`/api/v1/admin/users/${uid}/suspend?suspend=${suspend}`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-users"] }); push({ kind: "success", title: "User status updated" }); },
    onError: (e: any) => push({ kind: "error", title: "Could not change user status", body: e.message }),
  });

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
      <h1 className="text-lg font-bold text-ink-900">Platform admin</h1>

      <div className="flex flex-wrap gap-1.5" role="tablist">
        {(["health", "flags", "audit", "users", "security"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition ${
                    tab === t ? "bg-ink-900 text-white" : "bg-white text-ink-500 border border-ink-200 hover:text-ink-800"}`}>
            {t === "health" ? "components & health" : t}
          </button>
        ))}
      </div>

      {tab === "health" && (<>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {overviewQ.isLoading ? [...Array(6)].map((_, i) => <Skeleton key={i} className="h-16" />) :
            Object.entries(overviewQ.data ?? {})
              .filter(([, v]) => typeof v !== "object")
              .map(([k, v]) => (
              <div key={k} className="gt-card p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{k.replace(/_/g, " ")}</p>
                <p className="mt-0.5 text-xl font-bold text-ink-900">{String(v)}</p>
              </div>
            ))}
        </div>
        <Card title="Model health (live router metrics)">
          {modelQ.isLoading ? <Skeleton className="h-24 w-full" /> : (
            <table className="w-full text-left text-xs">
              <thead><tr className="border-b border-ink-100 text-ink-400">
                <th className="py-1.5">Task / provider</th><th>Status</th><th>EWMA latency</th><th>Error rate</th><th>Requests</th></tr></thead>
              <tbody>
                {Object.entries(modelQ.data ?? {}).map(([key, h]) => (
                  <tr key={key} className="border-b border-ink-50">
                    <td className="py-1.5 font-mono text-ink-800">{key}</td>
                    <td><Badge tone={h.available ? "good" : "bad"}>{h.available ? "available" : "down"}</Badge></td>
                    <td>{h.ewma_latency_ms} ms</td>
                    <td>{(h.error_rate * 100).toFixed(1)}%</td>
                    <td>{h.requests}</td>
                  </tr>
                ))}
                {Object.keys(modelQ.data ?? {}).length === 0 && (
                  <tr><td colSpan={5} className="py-3 text-center text-ink-400">No model traffic recorded yet.</td></tr>
                )}
              </tbody>
            </table>
          )}
          <p className="mt-2 text-[11px] text-ink-400">
            cache backend: <b>{overviewQ.data?.cache_backend ?? "—"}</b>
            {overviewQ.data?.queue_depth && <> · queue depth: <b>{JSON.stringify(overviewQ.data.queue_depth)}</b></>}
          </p>
        </Card>
        <Card title="Metrics">
          <p className="text-xs text-ink-500">
            Prometheus endpoint: <a className="font-mono text-signal-700 hover:underline" href="/metrics" target="_blank" rel="noreferrer">/metrics</a>{" "}
            (http_requests_total, translation_latency_ms p50/p95/p99 per pair, stt_latency_ms, tts_latency_ms,
            realtime_e2e_latency_ms, error rates). Grafana dashboard JSON in <code>infrastructure/</code>.
          </p>
        </Card>
      </>)}

      {tab === "flags" && (
        <Card title="Feature flags">
          <div className="space-y-2">
            {Object.entries(flagsQ.data ?? {}).map(([name, enabled]) => (
              <div key={name} className="flex items-center gap-3 rounded-lg border border-ink-100 p-3">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-xs font-semibold text-ink-800">{name}</p>
                </div>
                <button role="switch" aria-checked={!!enabled} aria-label={`Toggle ${name}`}
                        onClick={() => setFlag.mutate({ name, enabled: !enabled })}
                        className={`relative h-6 w-11 rounded-full transition ${enabled ? "bg-signal-600" : "bg-ink-200"}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${enabled ? "left-[22px]" : "left-0.5"}`} />
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {tab === "audit" && (
        <Card title="Audit log">
          <table className="w-full text-left text-xs">
            <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Time</th><th>Action</th><th>Actor</th><th>Resource</th><th>Outcome</th></tr></thead>
            <tbody>
              {(auditQ.data ?? []).map((a) => (
                <tr key={a.id} className="border-b border-ink-50">
                  <td className="py-1.5 whitespace-nowrap">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="font-mono">{a.action}</td>
                  <td className="max-w-[120px] truncate font-mono text-ink-400">{a.actor_kind}{a.actor_id ? `:${String(a.actor_id).slice(0, 8)}` : ""}</td>
                  <td className="text-ink-500">{a.resource_type}{a.resource_id ? `:${String(a.resource_id).slice(0, 8)}` : ""}</td>
                  <td><Badge tone={a.outcome === "success" ? "good" : "bad"}>{a.outcome}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "users" && (
        <Card title="Users">
          <table className="w-full text-left text-xs">
            <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Email</th><th>Name</th><th>Admin</th><th>Status</th><th>Created</th><th /></tr></thead>
            <tbody>
              {(usersQ.data ?? []).map((u) => (
                <tr key={u.id} className="border-b border-ink-50">
                  <td className="py-1.5">{u.email}</td>
                  <td>{u.name}</td>
                  <td>{u.admin ? <Badge tone="info">admin</Badge> : "—"}</td>
                  <td>{u.status === "suspended" ? <Badge tone="bad">suspended</Badge> : <Badge tone="good">active</Badge>}</td>
                  <td>{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="text-right">
                    {u.status === "suspended"
                      ? <Button size="sm" variant="secondary" onClick={() => setUserStatus.mutate({ uid: u.id, suspend: false })}>Reactivate</Button>
                      : <Button size="sm" variant="ghost" onClick={() => setUserStatus.mutate({ uid: u.id, suspend: true })}>Suspend</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "security" && (
        <Card title="Security events">
          {(() => {
            const events = (auditQ.data ?? []).filter((a) =>
              /^(auth|admin|org\.member|api_key|token)/.test(a.action));
            return events.length === 0 ? <p className="py-4 text-center text-xs text-ink-400">No security events.</p> : (
            <table className="w-full text-left text-xs">
              <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Time</th><th>Action</th><th>Actor</th><th>Details</th></tr></thead>
              <tbody>
                {events.map((s) => (
                  <tr key={s.id} className="border-b border-ink-50">
                    <td className="py-1.5 whitespace-nowrap">{new Date(s.created_at).toLocaleString()}</td>
                    <td className="font-mono">{s.action}</td>
                    <td className="max-w-[120px] truncate font-mono text-ink-400">{s.actor_kind}{s.actor_id ? `:${String(s.actor_id).slice(0, 8)}` : ""}</td>
                    <td className="max-w-[320px] truncate text-ink-500">{JSON.stringify(s.details_json)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            );
          })()}
        </Card>
      )}
    </div>
  );
}
