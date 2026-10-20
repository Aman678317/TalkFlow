import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Skeleton } from "../components/ui";

interface ProviderStatus {
  active_provider: string;
  real_pstn_available: boolean;
  caller_number: string;
  peer_webrtc_available: boolean;
  setup_required: boolean;
  setup_guide: Record<string, Record<string, string>>;
}

interface TelephonyOps {
  provider: ProviderStatus;
  flags: {
    telephony_provider: string;
    call_worker_enabled: boolean;
    asterisk_telephony_enabled: boolean;
    asterisk_inbound_enabled: boolean;
    asterisk_media_enabled: boolean;
  };
  process: {
    call_worker_ticker_running: boolean;
    asterisk_media_runtime_armed: boolean;
  };
  queues: { telephony: number };
}

interface CallRow {
  id: string; call_sid: string; direction: string; status: string; mode: string;
  provider: string; duration_seconds: number; total_cost_cents: number;
  started_at: string | null; ended_at: string | null;
}

/**
 * `/admin/telephony` (P4 §D2): read-only telephony lane visibility for
 * platform admins. The backend draws configured-vs-armed distinctions;
 * the page renders them as badges and never as green checkmarks.
 */
export default function AdminTelephony() {
  const opsQ = useQuery({ queryKey: ["telephony-ops"], queryFn: () => api<TelephonyOps>("/api/v1/admin/telephony-ops"), refetchInterval: 15_000 });
  const callsQ = useQuery({ queryKey: ["telephony-calls"], queryFn: () => api<CallRow[]>("/api/v1/telephony/calls?limit=10"), refetchInterval: 15_000 });

  const ops = opsQ.data;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-lg font-bold text-ink-900">Telephony ops</h1>
        <p className="text-xs text-ink-400">
          Read-only lane visibility. "Configured" means a flag is set; "armed" means
          the component actually started in this process. Local SIP is never shown
          as PSTN.
        </p>
      </div>

      {opsQ.isLoading || !ops ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <Card title="Provider (honesty surface)">
              <div className="space-y-2 text-sm">
                <p className="flex items-center gap-2 text-xs">
                  <span className="text-ink-500">active:</span>
                  <strong className="text-ink-900">{ops.provider.active_provider}</strong>
                  <Badge tone={ops.provider.real_pstn_available ? "bad" : "info"}>
                    {ops.provider.real_pstn_available ? "REAL PSTN" : "local / simulated — NOT PSTN"}
                  </Badge>
                </p>
                <p className="text-xs text-ink-500">caller id presented: <span className="font-mono">{ops.provider.caller_number || "—"}</span></p>
                <p className="text-xs text-ink-500">browser-to-browser calling: {ops.provider.peer_webrtc_available ? "available" : "off"}</p>
                {ops.provider.setup_required && (
                  <div className="rounded-lg border border-ink-100 bg-ink-50/50 p-3" data-testid="setup-guide">
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">setup remaining</p>
                    <ol className="list-inside list-decimal space-y-0.5 text-xs text-ink-600">
                      {Object.values(ops.provider.setup_guide[ops.provider.active_provider] ?? {})
                        .map((step: string, i: number) => <li key={i}>{step}</li>)}
                    </ol>
                  </div>
                )}
              </div>
            </Card>

            <Card title="Lane flags — configured vs armed">
              <table className="w-full text-left text-xs" data-testid="flags-table">
                <thead><tr className="border-b border-ink-100 text-ink-400">
                  <th className="py-1.5 font-medium">component</th>
                  <th className="py-1.5 font-medium">configured</th>
                  <th className="py-1.5 font-medium">armed (this process)</th>
                </tr></thead>
                <tbody>
                  <FlagRow label="auto-dial worker"
                    configured={ops.flags.call_worker_enabled}
                    armed={ops.process.call_worker_ticker_running} />
                  <FlagRow label="asterisk ARI lane"
                    configured={ops.flags.asterisk_telephony_enabled}
                    armed={null} />
                  <FlagRow label="asterisk inbound intake"
                    configured={ops.flags.asterisk_inbound_enabled}
                    armed={null} />
                  <FlagRow label="AI-agent media runtime"
                    configured={ops.flags.asterisk_media_enabled}
                    armed={ops.process.asterisk_media_runtime_armed} />
                </tbody>
              </table>
              <p className="mt-2 text-[11px] text-ink-400">
                telephony queue depth: <strong data-testid="queue-depth">{ops.queues.telephony}</strong>
              </p>
            </Card>
          </div>

          <Card title="Recent call sessions (this org)">
            {(callsQ.data ?? []).length === 0 ? (
              <p className="text-xs text-ink-400">No call sessions yet.</p>
            ) : (
              <table className="w-full text-left text-xs">
                <thead><tr className="border-b border-ink-100 text-ink-400">
                  <th className="py-1.5 font-medium">call_sid</th>
                  <th className="py-1.5 font-medium">mode</th>
                  <th className="py-1.5 font-medium">status</th>
                  <th className="py-1.5 font-medium">dur</th>
                  <th className="py-1.5 font-medium">cost</th>
                </tr></thead>
                <tbody>
                  {(callsQ.data ?? []).map((c) => (
                    <tr key={c.id} className="border-b border-ink-50">
                      <td className="py-1.5 font-mono">{c.call_sid}</td>
                      <td className="py-1.5">{c.mode}</td>
                      <td className="py-1.5">{c.status}</td>
                      <td className="py-1.5">{c.duration_seconds}s</td>
                      <td className="py-1.5">{c.total_cost_cents}¢</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function FlagRow(props: { label: string; configured: boolean; armed: boolean | null }) {
  const { label, configured, armed } = props;
  return (
    <tr className="border-b border-ink-50">
      <td className="py-1.5 text-ink-700">{label}</td>
      <td className="py-1.5">{configured ? <Badge tone="warn">configured</Badge> : <span className="text-ink-400">off</span>}</td>
      <td className="py-1.5">{armed === null ? <span className="text-ink-300">—</span>
        : armed ? <Badge tone="info">running</Badge>
        : <span className="text-ink-400" data-testid="not-armed">not armed</span>}</td>
    </tr>
  );
}
