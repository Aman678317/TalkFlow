import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, Skeleton } from "../components/ui";

const DIMENSIONS: [string, string][] = [
  ["characters", "Characters translated"],
  ["translation_requests", "Translation requests"],
  ["audio_seconds", "Audio seconds (realtime voice)"],
  ["document_pages", "Document pages"],
  ["video_minutes", "Video minutes"],
  ["api_requests", "API requests"],
  ["storage_bytes", "Storage bytes"],
  ["gpu_seconds", "GPU seconds"],
  ["tokens", "LLM tokens"],
];

export default function Usage() {
  const { data, isLoading } = useQuery({
    queryKey: ["usage", 30],
    queryFn: () => api<{ totals: Record<string, number>; plan: string; limits: Record<string, number> }>("/api/v1/usage?days=30"),
    refetchInterval: 30_000,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Usage</h1>
          <p className="text-xs text-ink-400">Immutable metering events from the last 30 days. Billing is computed from these numbers.</p>
        </div>
        {data && <Badge tone="info">{data.plan.toUpperCase()} plan</Badge>}
      </div>

      {isLoading && !data ? <Card><Skeleton className="h-40 w-full" /></Card> : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DIMENSIONS.map(([key, label]) => {
            const used = data?.totals?.[key] ?? 0;
            const limit = data?.limits?.[key];
            const pct = limit && isFinite(limit) ? Math.min(100, (used / limit) * 100) : null;
            if (used === 0 && limit === undefined) return null;
            return (
              <div key={key} className="gt-card p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{label}</p>
                <p className="mt-1 text-2xl font-bold text-ink-900">
                  {key === "storage_bytes" ? `${(used / 1048576).toFixed(1)} MB` : Math.round(used).toLocaleString()}
                </p>
                {pct !== null && (
                  <>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-100">
                      <div className={`h-full rounded-full ${pct > 80 ? "bg-red-500" : "bg-signal-500"}`} style={{ width: `${pct}%` }} />
                    </div>
                    <p className="mt-1 text-[11px] text-ink-400">
                      {pct.toFixed(1)}% of included {isFinite(limit!) ? limit!.toLocaleString() : "∞"}
                    </p>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
