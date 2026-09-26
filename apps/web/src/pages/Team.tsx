import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Field, Input, Modal, Select } from "../components/ui";
import { useToasts } from "../stores/toast";
import { useAuth } from "../stores/auth";

interface Member { user_id: string; email: string; full_name: string; role: string; joined_at: string; }
const ROLES = ["owner", "admin", "manager", "member", "viewer"];
const ROLE_DESC: Record<string, string> = {
  owner: "Full control incl. billing & security",
  admin: "Manage everything except plan changes",
  manager: "Manage members, glossaries, integrations",
  member: "Create meetings, translate, upload documents",
  viewer: "Read-only: view transcripts, translate",
};

export default function Team() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const { org } = useAuth();
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState({ email: "", role: "member" });

  const membersQ = useQuery({ queryKey: ["members"], queryFn: () => api<Member[]>("/api/v1/members") });
  const orgQ = useQuery({ queryKey: ["org"], queryFn: () => api<any>("/api/v1/org") });

  const add = useMutation({
    mutationFn: () => api("/api/v1/members", { method: "POST", body: form }),
    onSuccess: () => { setOpen(false); qc.invalidateQueries({ queryKey: ["members"] }); push({ kind: "success", title: "Member added" }); },
    onError: (e: any) => push({ kind: "error", title: "Could not add member", body: e.message }),
  });
  const changeRole = useMutation({
    mutationFn: ({ email, role }: { email: string; role: string }) =>
      api("/api/v1/members", { method: "POST", body: { email, role } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members"] }),
    onError: (e: any) => push({ kind: "error", title: "Role change failed", body: e.message }),
  });
  const removeMember = useMutation({
    mutationFn: (uid: string) => api(`/api/v1/members/${uid}`, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["members"] }); push({ kind: "success", title: "Member removed" }); },
    onError: (e: any) => push({ kind: "error", title: "Cannot remove", body: e.message }),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">{orgQ.data?.name ?? org?.name} · Team</h1>
          <p className="text-xs text-ink-400">Role-based access control. Tenant isolation is enforced on every API boundary.</p>
        </div>
        <Button onClick={() => setOpen(true)}>+ Add member</Button>
      </div>

      <Card title={`Members (${membersQ.data?.length ?? 0})`}>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-ink-100 text-[11px] uppercase tracking-wider text-ink-400">
              <th className="py-2">Person</th><th>Role</th><th title={ROLE_DESC["member"]}>Permissions</th><th>Joined</th><th />
            </tr>
          </thead>
          <tbody>
            {(membersQ.data ?? []).map((m) => (
              <tr key={m.user_id} className="border-b border-ink-50">
                <td className="py-2.5">
                  <p className="font-medium text-ink-900">{m.full_name || m.email}</p>
                  <p className="text-[11px] text-ink-400">{m.email}</p>
                </td>
                <td>
                  <Select aria-label={`Role for ${m.email}`} className="!w-32 !py-1 text-xs" value={m.role}
                          onChange={(e) => changeRole.mutate({ email: m.email, role: e.target.value })}>
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </Select>
                </td>
                <td className="max-w-[220px] text-[11px] text-ink-400">{ROLE_DESC[m.role]}</td>
                <td className="text-xs text-ink-400">{new Date(m.joined_at).toLocaleDateString()}</td>
                <td className="text-right">
                  {m.role !== "owner" && (
                    <Button size="sm" variant="ghost" onClick={() => removeMember.mutate(m.user_id)}
                            aria-label={`Remove ${m.email}`}>Remove</Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Roles & permissions">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {ROLES.map((r) => (
            <div key={r} className="rounded-lg border border-ink-100 p-3">
              <Badge tone={r === "owner" ? "good" : "neutral"}>{r}</Badge>
              <p className="mt-1.5 text-[11px] leading-relaxed text-ink-500">{ROLE_DESC[r]}</p>
            </div>
          ))}
        </div>
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="Add member">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Email" hint="The person must have a GlobalTalk account (invite emails are queued in production)">
            <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field label="Role">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.filter((r) => r !== "owner").map((r) => <option key={r} value={r}>{r} — {ROLE_DESC[r]}</option>)}
            </Select>
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={add.isPending}>Add member</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
