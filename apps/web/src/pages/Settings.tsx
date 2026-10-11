import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Field, Input, Select } from "../components/ui";
import { useAuth } from "../stores/auth";
import { useToasts } from "../stores/toast";
import { useLanguages } from "../hooks/useLanguages";

interface SessionRow { id: string; device_info: string; created_at: string; last_seen_at: string | null; revoked_at: string | null; }

export default function SettingsPage() {
  const { user, org } = useAuth();
  const push = useToasts((s) => s.push);
  const { data: langs } = useLanguages();
  const [lang, setLang] = React.useState(user?.default_language ?? "en");
  const [pw, setPw] = React.useState({ token: "", password: "" });
  const [resetStarted, setResetStarted] = React.useState(false);

  const sessionsQ = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionRow[]>("/api/v1/auth/me/sessions") });
  const orgQ = useQuery({ queryKey: ["org"], queryFn: () => api<any>("/api/v1/organizations/current") });

  async function requestReset() {
    if (!user) return;
    try {
      // Backend takes the email as a query param and never reveals whether the account exists.
      await api("/api/v1/auth/password-reset/request?email=" + encodeURIComponent(user.email), { method: "POST" });
      setResetStarted(true);
      push({ kind: "info", title: "Reset link issued", body: "In local dev the token is printed in the backend log — paste it below to finish." });
    } catch (e: any) {
      push({ kind: "error", title: "Could not start reset", body: e.message });
    }
  }
  async function confirmReset(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/api/v1/auth/password-reset/confirm", { method: "POST", body: { token: pw.token, new_password: pw.password } });
      push({ kind: "success", title: "Password updated", body: "All sessions were revoked — sign in again." });
      setPw({ token: "", password: "" });
      setResetStarted(false);
    } catch (e: any) {
      push({ kind: "error", title: "Reset failed", body: e.message });
    }
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
        {resetStarted && (
          <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={confirmReset}>
            <Field label="Reset token">
              <Input required placeholder="paste token from backend log" value={pw.token}
                     onChange={(e) => setPw({ ...pw, token: e.target.value })} />
            </Field>
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
            <thead><tr className="border-b border-ink-100 text-ink-400"><th className="py-1.5">Device</th><th>Started</th><th>Last seen</th><th>State</th></tr></thead>
            <tbody>
              {(sessionsQ.data ?? []).map((s) => (
                <tr key={s.id} className="border-b border-ink-50">
                  <td className="max-w-[240px] truncate py-1.5">{s.device_info || "unknown"}</td>
                  <td>{new Date(s.created_at).toLocaleDateString()}</td>
                  <td>{s.last_seen_at ? new Date(s.last_seen_at).toLocaleString() : "—"}</td>
                  <td>{s.revoked_at ? <Badge tone="bad">revoked</Badge> : <Badge tone="good">active</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
