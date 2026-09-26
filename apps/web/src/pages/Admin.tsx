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
  const compsQ = useQuery({ queryKey: ["admin-components"], queryFn: () => api<any>("/internal/components"), refetchInterval: 30_000 });
  const audioQ = useQuery({ queryKey: ["admin-audio"], queryFn: () => api<any>("/internal/audio-health"), refetchInterval: 15_000 });
  const flagsQ = useQuery({ queryKey: ["admin-flags"], queryFn: () => api<Record<string, any>>("/api/v1/admin/feature-flags") });
  const auditQ = useQuery({ queryKey: ["admin-audit"], queryFn: () => api<any[]>("/api/v1/admin/audit-logs?limit=100"), enabled: tab === "audit" });
  const usersQ = useQuery({ queryKey: ["admin-users"], queryFn: () => api<any[]>("/api/v1/admin/users"), enabled: tab === "users" });
  const secQ = useQuery({ queryKey: ["admin-security"], queryFn: () => api<any[]>("/api/v1/admin/security-events"), enabled: tab === "security" });

  const setFlag = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api(`/api/v1/admin/feature-flags/${name}?enabled=${enabled}`, { method: "PUT" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-flags"] }); push({ kind: "success", title: "Feature flag updated" }); },
  });
  const deactivate = useMutation({
    mutationFn: (uid: string) => api(`/api/v1/admin/users/${uid}/deactivate`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const statusTone = (s: string) => s === "READY" ? "good" : s === "FAILED" ? "bad" : s === "DEGRADED" ? "warn" : "neutral";

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
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {overviewQ.isLoading ? [...Array(7)].map((_, i) => <Skeleton key={i} className="h-16" />) :
            Object.entries(overviewQ.data ?? {}).map(([k, v]) => (
              <div key={k} className="gt-card p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{k.replace(/_/g, " ")}</p>
                <p className="mt-0.5 text-xl font-bold text-ink-900">{String(v)}</p>
              </div>
            ))}
        </div>
        <Card title="Open-source component health (/internal/components)">
          <table className="w-full text-left text-xs">
            <thead><tr className="border-b border-ink-100 text-ink-400">
              <th className="py-1.5">Component</th><th>Task</th><th>Status</th><th>Health / model</th><th>License review</th><th>GPU</th></tr></thead>
            <tbody>
              {(compsQ.data?.components ?? []).map((c: any) => (
                <tr key={c.component + c.task} className="border-b border-ink-50">
                  <td className="py-1.5 font-semibold text-ink-800">{c.component}</td>
                  <td>{c.task}</td>
                  <td><Badge tone={statusTone(c.status) as any}>{c.status}</Badge></td>
                  <td className="max-w-[280px] truncate text-ink-500" title={c.health}>
                    {c.loaded_model ? c.version || c.provider : c.health}
                  </td>
                  <td className="text-ink-400">{c.license_review_status}</td>
                  <td>{c.gpu_required ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-ink-400">
            cache backend: <b>{compsQ.data?.cache_backend}</b> · storage: <b>{compsQ.data?.storage_backend}</b>
          </p>
        </Card>
        <Card title="Audio engine health (/internal/audio-health)">
          {audioQ.data ? (
            <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(audioQ.data).map(([k, v]) => (
                <div key={k} className="rounded-lg border border-ink-100 p-2">
                  <p className="text-[10px] uppercase tracking-wider text-ink-400">{k.replace(/_/g, " ")}</p>
                  <p className="mt-0.5 font-medium text-ink-800">{typeof v === "object" ? JSON.stringify(v) : String(v)}</p>
                </div>
              ))}
            </div>
          ) : <Skeleton className="h-20 w-full" />}
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
            {Object.entries(flagsQ.data ?? {}).map(([name, f]: [string, any]) => (
              <div key={name} className="flex items-center gap-3 rounded-lg border border-ink-100 p-3">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-xs font-semibold text-ink-800">{name}</p>
                  <p className="text-[11px] text-ink-400">{f.description}</p>
                </div>
                <button role="switch" aria-checked={!!f.enabled} aria-label={`Toggle ${name}`}
                        onClick={() => setFlag.mutate({ name, enabled: !f.enabled })}
                        className={`relative h-6 w-11 rounded-full transition ${f.enabled ? "bg-signal-600" : "bg-ink-200"}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${f.enabled ? "left-[22px]" : "left-0.5"}`} />
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {tab === "audit" && (
        <Card title="Audit log">
          <table className="w-full text-left text-xs">
            <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Time</th><th>Action</th><th>Org</th><th>Actor</th><th>Resource</th><th>IP</th></tr></thead>
            <tbody>
              {(auditQ.data ?? []).map((a) => (
                <tr key={a.id} className="border-b border-ink-50">
                  <td className="py-1.5 whitespace-nowrap">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="font-mono">{a.action}</td>
                  <td className="max-w-[90px] truncate font-mono text-ink-400">{a.org_id?.slice(0, 8)}</td>
                  <td className="max-w-[90px] truncate font-mono text-ink-400">{a.actor_user_id?.slice(0, 8) ?? "api-key"}</td>
                  <td className="text-ink-500">{a.resource_type}{a.resource_id ? `:${a.resource_id.slice(0, 8)}` : ""}</td>
                  <td className="font-mono text-ink-400">{a.ip_address}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "users" && (
        <Card title="Users">
          <table className="w-full text-left text-xs">
            <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Email</th><th>Name</th><th>Admin</th><th>Verified</th><th>Last login</th><th /></tr></thead>
            <tbody>
              {(usersQ.data ?? []).map((u) => (
                <tr key={u.id} className="border-b border-ink-50">
                  <td className="py-1.5">{u.email}</td>
                  <td>{u.full_name}</td>
                  <td>{u.is_platform_admin ? <Badge tone="info">admin</Badge> : "—"}</td>
                  <td>{u.email_verified ? "✓" : "—"}</td>
                  <td>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}</td>
                  <td className="text-right">
                    {u.is_active
                      ? <Button size="sm" variant="ghost" onClick={() => deactivate.mutate(u.id)}>Deactivate</Button>
                      : <Badge tone="bad">deactivated</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "security" && (
        <Card title="Security events">
          {(secQ.data ?? []).length === 0 ? <p className="py-4 text-center text-xs text-ink-400">No security events.</p> : (
            <table className="w-full text-left text-xs">
              <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Time</th><th>Action</th><th>IP</th><th>Details</th></tr></thead>
              <tbody>
                {(secQ.data ?? []).map((s, i) => (
                  <tr key={i} className="border-b border-ink-50">
                    <td className="py-1.5 whitespace-nowrap">{new Date(s.created_at).toLocaleString()}</td>
                    <td className="font-mono">{s.action}</td>
                    <td className="font-mono">{s.ip_address}</td>
                    <td className="max-w-[320px] truncate text-ink-500">{JSON.stringify(s.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  );
}
