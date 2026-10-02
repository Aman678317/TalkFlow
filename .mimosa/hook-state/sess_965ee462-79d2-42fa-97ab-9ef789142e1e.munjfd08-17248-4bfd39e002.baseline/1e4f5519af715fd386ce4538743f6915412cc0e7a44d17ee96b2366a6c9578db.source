import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Field, Input, Select } from "../components/ui";
import { useAuth } from "../stores/auth";
import { useToasts } from "../stores/toast";
import { useLanguages } from "../hooks/useLanguages";

interface SessionRow { id: string; user_agent: string; ip_address: string; created_at: string; last_seen_at: string; revoked: boolean; }

export default function SettingsPage() {
  const { user, org } = useAuth();
  const push = useToasts((s) => s.push);
  const { data: langs } = useLanguages();
  const [lang, setLang] = React.useState(user?.default_language ?? "en");
  const [pw, setPw] = React.useState({ token: "", password: "" });

  const sessionsQ = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionRow[]>("/api/v1/auth/sessions") });
  const orgQ = useQuery({ queryKey: ["org"], queryFn: () => api<any>("/api/v1/org") });

  async function requestReset() {
    if (!user) return;
    const r = await api<any>("/api/v1/auth/password-reset", { method: "POST", body: { email: user.email } });
    if (r.dev_token) {
      setPw({ token: r.dev_token, password: "" });
      push({ kind: "info", title: "Reset token generated (dev mode)", body: "In production this is emailed, never shown." });
    } else {
      push({ kind: "success", title: "If the account exists, a reset link has been sent" });
    }
  }
  async function confirmReset(e: React.FormEvent) {
    e.preventDefault();
    await api("/api/v1/auth/password-reset/confirm", { method: "POST", body: { token: pw.token, new_password: pw.password } });
    push({ kind: "success", title: "Password updated", body: "All sessions were revoked — sign in again." });
    setPw({ token: "", password: "" });
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4 lg:p-6">
      <h1 className="text-lg font-bold text-ink-900">Settings</h1>

      <Card title="Profile">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Email"><Input value={user?.email ?? ""} disabled /></Field>
          <Field label="Full name"><Input value={user?.full_name ?? ""} disabled /></Field>
          <Field label="Default language">
            <Select value={lang} onChange={(e) => setLang(e.target.value)}>
              {(langs ?? []).map((l) => <option key={l.code} value={l.code}>{l.name} ({l.native_name})</option>)}
            </Select>
          </Field>
          <div className="flex items-end gap-2">
            <Badge tone={user?.email_verified ? "good" : "warn"}>
              email {user?.email_verified ? "verified" : "unverified"}
            </Badge>
            {user?.is_platform_admin && <Badge tone="info">platform admin</Badge>}
          </div>
        </div>
      </Card>

      <Card title="Organization">
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-[11px] uppercase tracking-wider text-ink-400">Name</dt><dd>{orgQ.data?.name ?? org?.name}</dd></div>
          <div><dt className="text-[11px] uppercase tracking-wider text-ink-400">Slug</dt><dd className="font-mono text-xs">{orgQ.data?.slug}</dd></div>
          <div><dt className="text-[11px] uppercase tracking-wider text-ink-400">Plan</dt><dd>{orgQ.data?.plan}</dd></div>
          <div><dt className="text-[11px] uppercase tracking-wider text-ink-400">Retention</dt>
            <dd className="text-xs text-ink-500">{JSON.stringify(orgQ.data?.retention_policy ?? "defaults")}</dd></div>
        </dl>
      </Card>

      <Card title="Password">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" size="sm" onClick={requestReset}>Start password reset</Button>
          <span className="text-xs text-ink-400">Resets revoke every active session.</span>
        </div>
        {pw.token && (
          <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={confirmReset}>
            <Field label="New password">
              <Input type="password" required minLength={8} value={pw.password}
                     onChange={(e) => setPw({ ...pw, password: e.target.value })} />
            </Field>
            <Button type="submit" size="sm">Confirm reset</Button>
          </form>
        )}
      </Card>

      <Card title="Active sessions (device tracking)">
        {(sessionsQ.data ?? []).length === 0 ? <p className="text-xs text-ink-400">No sessions recorded.</p> : (
          <table className="w-full text-left text-xs">
            <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Device</th><th>IP</th><th>Last seen</th><th>State</th></tr></thead>
            <tbody>
              {(sessionsQ.data ?? []).map((s) => (
                <tr key={s.id} className="border-b border-ink-50">
                  <td className="max-w-[240px] truncate py-1.5">{s.user_agent || "unknown"}</td>
                  <td className="font-mono">{s.ip_address || "—"}</td>
                  <td>{new Date(s.last_seen_at).toLocaleString()}</td>
                  <td>{s.revoked ? <Badge tone="bad">revoked</Badge> : <Badge tone="good">active</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
