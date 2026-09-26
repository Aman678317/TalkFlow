import React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Meeting } from "../lib/types";
import { Badge, Button, Card, EmptyState, Field, Input, Modal } from "../components/ui";
import { toast } from "../stores/toasts";

export default function Meetings() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [open, setOpen] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [joinUrl, setJoinUrl] = React.useState("");

  const meetingsQ = useQuery({ queryKey: ["meetings"], queryFn: () => api<Meeting[]>("/api/v1/meetings"), refetchInterval: 10_000 });

  const create = useMutation({
    mutationFn: () => api<Meeting>("/api/v1/meetings", { method: "POST", body: { title } }),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ["meetings"] });
      setOpen(false);
      setTitle("");
      nav(`/meeting/${m.id}`);
    },
    onError: (e: any) => toast.error("Could not create meeting", e.message),
  });

  const endMeeting = useMutation({
    mutationFn: (id: string) => api(`/api/v1/meetings/${id}/end`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["meetings"] }); toast.success("Meeting ended"); },
  });

  React.useEffect(() => {
    const end = params.get("end");
    if (end) { endMeeting.mutate(end); nav("/meetings", { replace: true }); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  async function copyInvite(m: Meeting) {
    const url = `${location.origin}/meeting/${m.id}?join=${m.join_token}`;
    await navigator.clipboard.writeText(url);
    setJoinUrl(url);
    toast.success("Invite link copied", "Guests can join with this link.");
  }

  return (
    <div className="mx-auto max-w-5xl p-4 lg:p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Meetings</h1>
          <p className="text-xs text-ink-400">One shared conversation — every participant hears their own language.</p>
        </div>
        <Button onClick={() => setOpen(true)}>+ New meeting</Button>
      </div>

      {(meetingsQ.data ?? []).length === 0 && !meetingsQ.isLoading ? (
        <Card><EmptyState title="No meetings yet" icon="◉"
          body="Create a meeting, open it in multiple browser tabs, pick 'I speak' and 'I want to hear', and start talking."
          action={<Button onClick={() => setOpen(true)}>Create your first meeting</Button>} /></Card>
      ) : (
        <div className="space-y-2">
          {(meetingsQ.data ?? []).map((m) => (
            <div key={m.id} className="gt-card flex flex-wrap items-center gap-3 p-4">
              <Link to={`/meeting/${m.id}`} className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink-900 hover:text-signal-700">{m.title}</p>
                <p className="text-[11px] text-ink-400">
                  {new Date(m.created_at).toLocaleString()} · room {m.room_name} · {m.transport}
                </p>
              </Link>
              <Badge tone={m.status === "live" ? "good" : m.status === "ended" ? "neutral" : "info"}>{m.status}</Badge>
              {m.has_summary && <Badge tone="info">AI summary ✓</Badge>}
              <Button size="sm" variant="secondary" onClick={() => copyInvite(m)}>Copy invite</Button>
              <Link to={`/meeting/${m.id}`}><Button size="sm">{m.status === "ended" ? "View" : "Join"}</Button></Link>
              {m.status !== "ended" && (
                <Button size="sm" variant="ghost" onClick={() => endMeeting.mutate(m.id)}>End</Button>
              )}
            </div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New meeting">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Meeting title">
            <Input autoFocus required value={title} onChange={(e) => setTitle(e.target.value)}
                   placeholder="Weekly sync — EN/HI/JA" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={create.isPending}>Create & join</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!joinUrl} onClose={() => setJoinUrl("")} title="Invite link">
        <p className="text-sm text-ink-600">Share this link — guests join with the embedded token (no account needed):</p>
        <code className="mt-2 block break-all rounded bg-ink-50 p-2 text-xs">{joinUrl}</code>
      </Modal>
    </div>
  );
}
