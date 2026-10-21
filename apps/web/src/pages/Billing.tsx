import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card } from "../components/ui";

interface BillingEvent {
  id: string; kind: string; amount_cents: number; currency: string;
  period: string; lines_json: { description?: string; amount_cents?: number }[];
  created_at: string;
}

interface InvoicePreview {
  period: string; plan: string; currency: string; total_cents: number;
  lines: { description: string; amount_cents: number }[];
  usage: Record<string, number>;
}

interface PlanCatalog {
  plans: {
    code: string; label: string; base_cents: number; currency: string;
    price_note: string;
    per_unit_cents: Record<string, number>;
    included: Record<string, number>;
  }[];
  metered_dimensions: string[];
  unpriced_dimensions: string[];
}

const DIMENSION_LABELS: Record<string, string> = {
  characters: "characters",
  translation_requests: "translation requests",
  api_requests: "API requests",
  document_pages: "document pages",
  audio_seconds: "voice minutes",
  telephony_minutes: "call minutes",
};

function includedBlurb(included: Record<string, number>): string {
  const parts = Object.entries(included).map(([key, value]) => {
    const amount = key === "audio_seconds" ? Math.round(value / 60) : value;
    const unit = key === "audio_seconds" ? "voice minutes" : DIMENSION_LABELS[key] ?? key;
    return `${amount.toLocaleString()} ${unit}`;
  });
  return parts.length ? parts.join(" · ") : "Unlimited metering";
}

export default function Billing() {
  const eventsQ = useQuery({ queryKey: ["billing-events"], queryFn: () => api<BillingEvent[]>("/api/v1/billing/events") });
  const invoices = (eventsQ.data ?? []).filter((e) => e.kind === "invoice_created");
  const previewQ = useQuery({ queryKey: ["billing-preview"], queryFn: () => api<InvoicePreview>("/api/v1/billing/preview-invoice") });
  const usageQ = useQuery({ queryKey: ["usage", 30], queryFn: () => api<any>("/api/v1/usage?days=30") });
  // The plan table comes from the server. The page used to hard-code the
  // prices and quotas, and they contradicted the server (issue #109 class 4)
  // — a hard-coded price is a promise the server does not make.
  const plansQ = useQuery({ queryKey: ["billing-plans"], queryFn: () => api<PlanCatalog>("/api/v1/billing/plans") });
  const currentPlan = usageQ.data?.plan ?? "free";
  const plans = plansQ.data?.plans ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-lg font-bold text-ink-900">Billing</h1>
        <p className="text-xs text-ink-400">Usage-first pricing: plan base + metered overage, computed from immutable usage events (never estimated).</p>
      </div>

      {plansQ.isError ? (
        <Card title="Plans">
          <p className="text-xs text-ink-500">
            The plan table could not be loaded. No prices are shown rather than
            showing numbers this server did not publish.
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((p) => (
            <div key={p.code} className={`gt-card flex flex-col p-5 ${currentPlan === p.code ? "border-signal-500 ring-2 ring-signal-500/20" : ""}`}>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-ink-900">{p.label}</h2>
                {currentPlan === p.code && <Badge tone="good">current</Badge>}
              </div>
              <p className="mt-2 text-2xl font-extrabold text-ink-900">
                {p.price_note || `$${(p.base_cents / 100).toFixed(0)}`}
                {!p.price_note && <span className="text-xs font-medium text-ink-400">/mo</span>}
              </p>
              <p className="mt-2 flex-1 text-[11px] leading-relaxed text-ink-400">
                {includedBlurb(p.included)}
              </p>
              <Button size="sm" variant={currentPlan === p.code ? "secondary" : "primary"} className="mt-3" disabled
                      title="Plan changes go through the billing provider integration (Stripe adapter) in production deployments">
                {currentPlan === p.code ? "Active" : "Contact sales"}
              </Button>
            </div>
          ))}
        </div>
      )}

      {previewQ.data && (
        <Card title={`Current period estimate — ${previewQ.data.period} (from real metering)`}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-[11px] uppercase tracking-wider text-ink-400">Plan</p>
              <p className="text-xl font-bold capitalize text-ink-900">{previewQ.data.plan}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-ink-400">Estimated total</p>
              <p className="text-xl font-extrabold text-signal-700">
                ${(previewQ.data.total_cents / 100).toFixed(2)} {previewQ.data.currency}
              </p>
            </div>
          </div>
          {previewQ.data.lines.length > 0 && (
            <table className="mt-4 w-full text-left text-xs">
              <thead><tr className="border-b border-ink-100 text-ink-400">
                <th className="py-1.5">Line item</th><th className="text-right">Amount</th></tr></thead>
              <tbody>
                {previewQ.data.lines.map((l, i) => (
                  <tr key={i} className="border-b border-ink-50">
                    <td className="py-1.5 font-medium text-ink-700">{l.description}</td>
                    <td className="text-right">${(l.amount_cents / 100).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      <Card title="Invoices">
        {invoices.length === 0 ? (
          <p className="py-4 text-center text-xs text-ink-400">No invoices yet — invoices are generated at period close from metered usage.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-ink-100 text-[11px] uppercase tracking-wider text-ink-400">
              <th className="py-2">Date</th><th>Period</th><th>Amount</th></tr></thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-b border-ink-50">
                  <td className="py-2">{new Date(inv.created_at).toLocaleDateString()}</td>
                  <td className="text-xs text-ink-400">{inv.period}</td>
                  <td className="font-medium">${(inv.amount_cents / 100).toFixed(2)} {inv.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
