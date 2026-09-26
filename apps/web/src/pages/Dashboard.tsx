import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Skeleton } from "../components/ui";
import { useAuth } from "../stores/auth";
import { useLanguages } from "../hooks/useLanguages";

export default function Dashboard() {
  const { user, org } = useAuth();
  const { data: langs } = useLanguages();
  const historyQ = useQuery({ queryKey: ["history", "dash"], queryFn: () => api<any[]>("/api/v1/history?limit=5") });
  const meetingsQ = useQuery({ queryKey: ["meetings", "dash"], queryFn: () => api<any[]>("/api/v1/meetings?limit=5") });
  const docsQ = useQuery({ queryKey: ["documents", "dash"], queryFn: () => api<any[]>("/api/v1/documents") });
  const usageQ = useQuery({ queryKey: ["usage", "dash"], queryFn: () => api<any>("/api/v1/usage?days=30") });

  const stats = [
    { label: "Translations (30d)", value: Math.round(usageQ.data?.totals?.translation_requests ?? 0) },
    { label: "Characters", value: Math.round(usageQ.data?.totals?.characters ?? 0).toLocaleString() },
    { label: "Audio seconds", value: Math.round(usageQ.data?.totals?.audio_seconds ?? 0) },
    { label: "Document pages", value: Math.round(usageQ.data?.totals?.document_pages ?? 0) },
  ];
  const realtimeLangs = (langs ?? []).filter((l) => l.realtime_supported).length;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink-900">Welcome back, {user?.full_name?.split(" ")[0] || "there"} 👋</h1>
          <p className="text-xs text-ink-400">{org?.name} · {usageQ.data?.plan?.toUpperCase()} plan · {realtimeLangs} realtime-ready languages</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/translate"><Button size="sm">Translate text</Button></Link>
          <Link to="/write"><Button size="sm" variant="secondary">DeepL Write</Button></Link>
          <Link to="/voice"><Button size="sm" variant="secondary">Live Voice</Button></Link>
          <Link to="/meetings"><Button size="sm" variant="secondary">Start a meeting</Button></Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="gt-card p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{s.label}</p>
            {usageQ.isLoading ? <Skeleton className="mt-2 h-7 w-20" /> :
              <p className="mt-1 text-2xl font-bold text-ink-900">{s.value}</p>}
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Recent translations" action={<Link to="/history" className="text-xs font-medium text-signal-700 hover:underline">View all</Link>}>
          {historyQ.isLoading ? <div className="space-y-2">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div> :
           (historyQ.data ?? []).length === 0 ? <p className="py-6 text-center text-xs text-ink-400">No translations yet — try the Translate page.</p> :
            <ul className="divide-y divide-ink-100">
              {(historyQ.data ?? []).map((h) => (
                <li key={h.id} className="py-2 text-sm">
                  <div className="flex items-center gap-2 text-[11px] text-ink-400">
                    <Badge>{h.source_language} → {h.target_language}</Badge>
                    <span>{Math.round(h.latency_ms)} ms</span>
                    {h.from_tm && <Badge tone="good">TM</Badge>}
                  </div>
                  <p className="mt-0.5 truncate text-ink-700">{h.source_text}</p>
                  <p className="truncate font-medium text-ink-900">{h.translated_text}</p>
                </li>
              ))}
            </ul>}
        </Card>

        <Card title="Recent meetings" action={<Link to="/meetings" className="text-xs font-medium text-signal-700 hover:underline">View all</Link>}>
          {(meetingsQ.data ?? []).length === 0 ? <p className="py-6 text-center text-xs text-ink-400">No meetings yet.</p> :
            <ul className="divide-y divide-ink-100">
              {(meetingsQ.data ?? []).map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 py-2.5 text-sm">
                  <Link to={`/meeting/${m.id}`} className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink-900 hover:text-signal-700">{m.title}</p>
                    <p className="text-[11px] text-ink-400">{new Date(m.created_at).toLocaleString()}</p>
                  </Link>
                  <Badge tone={m.status === "live" ? "good" : m.status === "ended" ? "neutral" : "info"}>{m.status}</Badge>
                </li>
              ))}
            </ul>}
        </Card>

        <Card title="Documents" action={<Link to="/documents" className="text-xs font-medium text-signal-700 hover:underline">View all</Link>}>
          {(docsQ.data ?? []).length === 0 ? <p className="py-6 text-center text-xs text-ink-400">No documents translated yet.</p> :
            <ul className="divide-y divide-ink-100">
              {(docsQ.data ?? []).slice(0, 5).map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2 py-2.5 text-sm">
                  <span className="min-w-0 truncate text-ink-800">{d.filename}</span>
                  <Badge tone={d.status === "ready" ? "good" : d.status === "failed" ? "bad" : "warn"}>{d.status}</Badge>
                </li>
              ))}
            </ul>}
        </Card>

        <Card title="Language capabilities">
          <div className="flex flex-wrap gap-1.5">
            {(langs ?? []).map((l) => (
              <span key={l.code} title={`${l.name}: STT ${l.stt_status}, MT ${l.mt_status}, TTS ${l.tts_status}`}
                className={`gt-chip border ${l.translation_supported ? "border-signal-200 bg-signal-50 text-signal-800" : "border-ink-200 bg-ink-50 text-ink-400"}`}>
                {l.native_name || l.name}
                {l.speech_output_supported && " 🔊"}
              </span>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
            Capabilities are validated per deployment — a language is only shown as supported when the actual
            models for it are installed and healthy. 🔊 = translated voice available.
          </p>
        </Card>
      </div>
    </div>
  );
}
