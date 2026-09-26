import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card } from "../components/ui";

interface Invoice {
  id: string; amount_cents: number; currency: string; status: string;
  period_start?: string; period_end?: string; breakdown: Record<string, any>; created_at: string;
}

const PLANS = [
  { id: "free", name: "Free", price: "$0", blurb: "500K characters · 10 voice minutes · 50 document pages · 3 seats" },
  { id: "pro", name: "Pro", price: "$29", blurb: "5M characters · 100 voice minutes · 500 pages · 15 seats · glossaries + TM" },
  { id: "business", name: "Business", price: "$129", blurb: "50M characters · 1000 voice minutes · 5K pages · 100 seats · webhooks + SSO-ready" },
  { id: "enterprise", name: "Enterprise", price: "Custom", blurb: "Unlimited metering · private deployments · GPU pools · audit + retention controls" },
];

export default function Billing() {
  const invoicesQ = useQuery({ queryKey: ["invoices"], queryFn: () => api<Invoice[]>("/api/v1/billing/invoices") });
  const previewQ = useQuery({ queryKey: ["billing-preview"], queryFn: () => api<any>("/api/v1/billing/checkout-preview", { method: "POST" }) });
  const usageQ = useQuery({ queryKey: ["usage", 30], queryFn: () => api<any>("/api/v1/usage?days=30") });
  const currentPlan = usageQ.data?.plan ?? "free";

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-lg font-bold text-ink-900">Billing</h1>
        <p className="text-xs text-ink-400">Usage-first pricing: plan base + metered overage, computed from immutable usage events (never estimated).</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {PLANS.map((p) => (
          <div key={p.id} className={`gt-card flex flex-col p-5 ${currentPlan === p.id ? "border-signal-500 ring-2 ring-signal-500/20" : ""}`}>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-ink-900">{p.name}</h2>
              {currentPlan === p.id && <Badge tone="good">current</Badge>}
            </div>
            <p className="mt-2 text-2xl font-extrabold text-ink-900">{p.price}<span className="text-xs font-medium text-ink-400">/mo</span></p>
            <p className="mt-2 flex-1 text-[11px] leading-relaxed text-ink-400">{p.blurb}</p>
            <Button size="sm" variant={currentPlan === p.id ? "secondary" : "primary"} className="mt-3" disabled
                    title="Plan changes go through the billing provider integration (Stripe adapter) in production deployments">
              {currentPlan === p.id ? "Active" : "Contact sales"}
            </Button>
          </div>
        ))}
      </div>

      {previewQ.data && (
        <Card title="Current period estimate (from real metering)">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-[11px] uppercase tracking-wider text-ink-400">Base</p>
              <p className="text-xl font-bold">${(previewQ.data.base_cents / 100).toFixed(2)}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-ink-400">Overage</p>
              <p className="text-xl font-bold">${(previewQ.data.overage_cents / 100).toFixed(2)}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-ink-400">Estimated total</p>
              <p className="text-xl font-extrabold text-signal-700">${(previewQ.data.total_cents / 100).toFixed(2)}</p>
            </div>
          </div>
          {Object.keys(previewQ.data.breakdown ?? {}).length > 0 && (
            <table className="mt-4 w-full text-left text-xs">
              <thead><tr className="border-b border-ink-100 text-ink-400">
                <th className="py-1.5">Dimension</th><th>Used</th><th>Included</th><th>Overage</th><th>Cost</th></tr></thead>
              <tbody>
                {Object.entries<any>(previewQ.data.breakdown).map(([dim, b]) => (
                  <tr key={dim} className="border-b border-ink-50">
                    <td className="py-1.5 font-medium text-ink-700">{dim}</td>
                    <td>{Math.round(b.used).toLocaleString()}</td>
                    <td>{isFinite(b.included) ? Math.round(b.included).toLocaleString() : "∞"}</td>
                    <td>{Math.round(b.overage).toLocaleString()}</td>
                    <td>${(b.overage_cents / 100).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      <Card title="Invoices">
        {(invoicesQ.data ?? []).length === 0 ? (
          <p className="py-4 text-center text-xs text-ink-400">No invoices yet — invoices are generated at period close from metered usage.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-ink-100 text-[11px] uppercase tracking-wider text-ink-400">
              <th className="py-2">Date</th><th>Period</th><th>Amount</th><th>Status</th></tr></thead>
            <tbody>
              {(invoicesQ.data ?? []).map((inv) => (
                <tr key={inv.id} className="border-b border-ink-50">
                  <td className="py-2">{new Date(inv.created_at).toLocaleDateString()}</td>
                  <td className="text-xs text-ink-400">{inv.period_start ? new Date(inv.period_start).toLocaleDateString() : "—"} → {inv.period_end ? new Date(inv.period_end).toLocaleDateString() : "—"}</td>
                  <td className="font-medium">${(inv.amount_cents / 100).toFixed(2)} {inv.currency}</td>
                  <td><Badge tone={inv.status === "paid" ? "good" : "warn"}>{inv.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
