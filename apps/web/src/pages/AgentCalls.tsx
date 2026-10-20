import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, EmptyState } from "../components/ui";
import { useToasts } from "../stores/toast";
import {
  CallTranscript, EscalationTicket, fingerprintHint, formatAge, reasonLabel,
  stateBadgeTone, turnHeadline,
} from "../lib/agentConsole";

const RESOLUTIONS = [
  { code: "handled_by_human", label: "Handled by human" },
  { code: "called_back_by_agent", label: "Called back later" },
  { code: "no_contact_possible", label: "Could not reach them" },
];

/**
 * Live-agent escalation console (P4 §D1): C1 tickets in, claim→resolve out,
 * C2 transcript on demand. The board is honest by construction — only the
 * media runtime (escalation armed) enqueues tickets; this page invents none.
 */
export default function AgentCalls() {
  const qc = useQueryClient();
  const push = useToasts((s) => s.push);
  const [openTicket, setOpenTicket] = React.useState<string | null>(null);
  const [resolution, setResolution] = React.useState(RESOLUTIONS[0].code);

  const boardQ = useQuery({
    queryKey: ["escalations"],
    queryFn: () => api<EscalationTicket[]>("/api/v1/telephony/escalations"),
    refetchInterval: 5000,
  });

  const claim = useMutation({
    mutationFn: (ticketId: string) =>
      api<EscalationTicket>(`/api/v1/telephony/escalations/${ticketId}/claim`, { method: "POST", body: {} }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["escalations"] }); push({ kind: "success", title: "Ticket claimed" }); },
    onError: (e: any) => push({ kind: "error", title: "Could not claim", body: e.message }),
  });

  const resolve = useMutation({
    mutationFn: (ticketId: string) =>
      api<EscalationTicket>(`/api/v1/telephony/escalations/${ticketId}/resolve`,
        { method: "POST", body: { resolution } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["escalations"] }); push({ kind: "success", title: "Ticket resolved" }); },
    onError: (e: any) => push({ kind: "error", title: "Could not resolve", body: e.message }),
  });

  const tickets = boardQ.data ?? [];
  const sections: Array<{ label: string; tickets: EscalationTicket[] }> = [
    { label: "Pending", tickets: tickets.filter((t) => t.state === "pending") },
    { label: "Claimed by agents", tickets: tickets.filter((t) => t.state === "claimed") },
    { label: "Resolved", tickets: tickets.filter((t) => t.state === "resolved") },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-lg font-bold text-ink-900">Agent calls</h1>
        <p className="text-xs text-ink-400">
          Live-agent escalation board. Claims are audited on the call ledger; a ticket is
          claimed exactly once and can only be resolved after a claim.
        </p>
      </div>

      {boardQ.data?.length === 0 && (
        <Card>
          <EmptyState title="Nothing waiting" icon="☎"
            body="No escalations yet — the AI agent handled every call (or no call has escalated in this organization)." />
        </Card>
      )}

      {sections.map((section) => section.tickets.length > 0 && (
        <section key={section.label} className="space-y-2"
          data-testid={`board-${section.label.toLowerCase().replace(/\W+/g, "-")}`}>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-400">{section.label}</h2>
          {section.tickets.map((t) => (
            <TicketCard
              key={t.ticket_id}
              ticket={t}
              expanded={openTicket === t.ticket_id}
              onToggle={() => setOpenTicket(openTicket === t.ticket_id ? null : t.ticket_id)}
              onClaim={() => claim.mutate(t.ticket_id)}
              onResolve={() => resolve.mutate(t.ticket_id)}
              resolution={resolution}
              onResolutionChange={setResolution}
              claiming={claim.isPending}
              resolving={resolve.isPending}
            />
          ))}
        </section>
      ))}
    </div>
  );
}

function TicketCard(props: {
  ticket: EscalationTicket;
  expanded: boolean;
  onToggle: () => void;
  onClaim: () => void;
  onResolve: () => void;
  resolution: string;
  onResolutionChange: (code: string) => void;
  claiming: boolean;
  resolving: boolean;
}) {
  const { ticket, expanded, onToggle, onClaim, onResolve, resolution, onResolutionChange, claiming, resolving } = props;
  const transcript = useTranscript(ticket.call_sid, expanded);

  return (
    <div className="gt-card p-4" data-ticket-id={ticket.ticket_id}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink-900">
            {reasonLabel(ticket.reason)}{" "}
            <Badge tone={stateBadgeTone(ticket.state)}>{ticket.state}</Badge>
          </p>
          <p className="text-xs text-ink-400">
            <span className="font-mono">{ticket.call_sid}</span>
            {" · "}{ticket.turns} turn{ticket.turns === 1 ? "" : "s"}
            {" · "}waiting {formatAge(ticket.age_seconds)}
            {ticket.claimed_by ? <>{" · claimed by "}<strong>{ticket.claimed_by}</strong></> : null}
            {ticket.resolution ? <>{" · "}{ticket.resolution}</> : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={onToggle}>{expanded ? "Hide call" : "View call"}</Button>
          {ticket.state === "pending" && (
            <Button onClick={onClaim} disabled={claiming}>Claim</Button>
          )}
          {ticket.state === "claimed" && (
            <>
              <select
                aria-label="Resolution"
                className="h-9 rounded-lg border border-ink-200 bg-white px-2 text-xs text-ink-700 focus:outline-none"
                value={resolution}
                onChange={(e) => onResolutionChange(e.target.value)}
              >
                {RESOLUTIONS.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
              </select>
              <Button onClick={onResolve} disabled={resolving}>Resolve</Button>
            </>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-ink-100 pt-3">
          {transcript.isPending && <p className="text-xs text-ink-400">Loading call…</p>}
          {transcript.data && (
            <>
              <p className="text-xs text-ink-400">
                {transcript.data.call.mode} · {transcript.data.call.status} · provider {transcript.data.call.provider}
                {transcript.data.outcome ? <> · outcome <strong>{transcript.data.outcome.terminal}</strong></> : null}
                {transcript.data.meta?.events_total != null ? <> · {transcript.data.meta.events_total} ledger events</> : null}
              </p>
              <ol className="space-y-2">
                {transcript.data.turns.map((turn) => (
                  <li key={`${turn.turn}-${turn.at ?? ""}`} data-testid="transcript-turn">
                    <p className="text-xs font-semibold text-ink-800">{turnHeadline(turn)}</p>
                    {turn.agent_lines.map((line, i) => (
                      <p key={i} data-testid="agent-line" className="text-xs text-ink-700">
                        <span className="text-ink-400">agent · {line.tts === "absent" ? "unrendered" : "spoken"}:</span>{" "}{line.text}
                      </p>
                    ))}
                    {turn.caller.text_sha256 && (
                      <p className="text-xs text-ink-500" data-testid="caller-fingerprint">
                        <span className="text-ink-400">caller (fingerprint only):</span>{" "}
                        {fingerprintHint(turn.caller.text_sha256)} · {turn.caller.text_len} chars
                        {turn.caller.confidence != null ? ` · confidence ${turn.caller.confidence}` : ""}
                      </p>
                    )}
                    {turn.citations.length > 0 && (
                      <p className="text-[11px] text-ink-400" data-testid="citation-line">
                        {turn.citations.map((c, i) => (
                          <span key={i}>
                            {c.from}→{c.to}{c.output_sha256 ? ` (${c.output_sha256.slice(0, 10)}…)` : ""}{i < turn.citations.length - 1 ? " · " : ""}
                          </span>
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function useTranscript(callSid: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["call-transcript", callSid],
    enabled: Boolean(enabled && callSid),
    queryFn: () => api<CallTranscript>(`/api/v1/telephony/calls/${callSid}/transcript`),
  });
}
