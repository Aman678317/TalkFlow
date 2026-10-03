import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Languages, Mic, Video, FileText, Activity, Clock, Globe } from "lucide-react";
import { api } from "../lib/api";
import { Button, Skeleton } from "../components/ui";
import { useAuth } from "../stores/auth";
import { useLanguages } from "../hooks/useLanguages";

const SKELETON_ITEMS = [1, 2, 3];

export default function Dashboard() {
  const { user, org } = useAuth();
  const { data: langs } = useLanguages();
  const historyQ = useQuery({
    queryKey: ["history", "dash"],
    queryFn: async () => {
      const res = await api<any>("/api/v1/history?limit=5");
      return Array.isArray(res) ? res : (res?.items ?? []);
    },
  });
  const meetingsQ = useQuery({
    queryKey: ["meetings", "dash"],
    queryFn: async () => {
      const res = await api<any>("/api/v1/meetings?limit=5");
      return Array.isArray(res) ? res : (res?.items ?? []);
    },
  });
  const docsQ = useQuery({
    queryKey: ["documents", "dash"],
    queryFn: async () => {
      const res = await api<any>("/api/v1/documents");
      return Array.isArray(res) ? res : (res?.items ?? []);
    },
  });
  const usageQ = useQuery({ queryKey: ["usage", "dash"], queryFn: () => api<any>("/api/v1/usage?days=30") });

  const historyItems: any[] = Array.isArray(historyQ.data)
    ? historyQ.data
    : (historyQ.data?.items ?? []);
  const meetingItems: any[] = Array.isArray(meetingsQ.data)
    ? meetingsQ.data
    : (meetingsQ.data?.items ?? []);
  const docItems: any[] = Array.isArray(docsQ.data)
    ? docsQ.data
    : (docsQ.data?.items ?? []);

  const stats = [
    { label: "Translations (30d)", value: Math.round(usageQ.data?.totals?.translation_requests ?? 0), icon: Activity },
    { label: "Characters", value: Math.round(usageQ.data?.totals?.characters ?? 0).toLocaleString(), icon: Languages },
    { label: "Audio seconds", value: Math.round(usageQ.data?.totals?.audio_seconds ?? 0), icon: Mic },
    { label: "Document pages", value: Math.round(usageQ.data?.totals?.document_pages ?? 0), icon: FileText },
  ];
  const realtimeLangs = (langs ?? []).filter((l) => l.realtime_supported).length;
  const userName = (user?.full_name || user?.name || user?.email || "there").split(" ")[0];
  const planName = (org?.plan || usageQ.data?.plan || "pro").toUpperCase();

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 lg:p-6">
      {/* Welcome Banner & Quick Action Buttons */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200/80 pb-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Welcome back, {userName} 👋</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {org?.name || "GlobalTalk"} · {planName} plan · {realtimeLangs} realtime-ready languages
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/translate">
            <Button size="sm" className="bg-dl-blue hover:bg-dl-blue-hover text-white">
              Translate text
            </Button>
          </Link>
          <Link to="/write">
            <Button size="sm" variant="secondary" className="border-slate-200">
              Write companion
            </Button>
          </Link>
          <Link to="/voice">
            <Button size="sm" variant="secondary" className="border-slate-200">
              Live Voice
            </Button>
          </Link>
          <Link to="/meetings">
            <Button size="sm" variant="secondary" className="border-slate-200">
              Start a meeting
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{s.label}</p>
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50 text-slate-500">
                  <Icon className="h-3.5 w-3.5" />
                </div>
              </div>
              {usageQ.isLoading ? (
                <Skeleton className="h-8 w-24 rounded-lg" />
              ) : (
                <p className="text-2xl font-bold text-slate-900 font-mono tracking-tight">{s.value}</p>
              )}
            </div>
          );
        })}
      </div>

      {/* Workspace Activity Cards */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Recent Translations Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <Languages className="h-4 w-4 text-dl-blue" /> Recent translations
            </h3>
            <Link to="/history" className="text-xs font-semibold text-dl-blue hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          {historyQ.isLoading ? (
            <div className="space-y-2">
              {SKELETON_ITEMS.map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-xl" />
              ))}
            </div>
          ) : historyItems.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-400">No translations yet. Try the Translate workspace.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {historyItems.map((h: any) => (
                <li key={h.id} className="py-2.5 text-xs">
                  <div className="flex items-center justify-between gap-2 text-[11px] text-slate-400 mb-1">
                    <span className="font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                      {h.source_lang || h.source_language || "?"} → {h.target_lang || h.target_language || "?"}
                    </span>
                    <span className="font-mono">{Math.round(h.latency_ms ?? 0)} ms</span>
                  </div>
                  <p className="truncate text-slate-600 font-normal">{h.source_text}</p>
                  <p className="truncate font-semibold text-dl-navy">{h.target_text || h.translated_text}</p>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recent Meetings Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <Video className="h-4 w-4 text-dl-blue" /> Recent meetings
            </h3>
            <Link to="/meetings" className="text-xs font-semibold text-dl-blue hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          {meetingsQ.isLoading ? (
            <div className="space-y-2">
              {SKELETON_ITEMS.map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-xl" />
              ))}
            </div>
          ) : meetingItems.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-400">No meetings yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {meetingItems.map((m: any) => (
                <li key={m.id} className="flex items-center justify-between gap-2 py-2.5 text-xs">
                  <Link to={`/meeting/${m.id}`} className="min-w-0 flex-1 hover:text-dl-blue">
                    <p className="truncate font-semibold text-slate-900">{m.title}</p>
                    <p className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                      <Clock className="h-3 w-3" /> {m.created_at ? new Date(m.created_at).toLocaleString() : ""}
                    </p>
                  </Link>
                  <span
                    className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase ${
                      m.status === "live"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {m.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Documents Summary Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-dl-blue" /> Documents
            </h3>
            <Link to="/documents" className="text-xs font-semibold text-dl-blue hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          {docsQ.isLoading ? (
            <div className="space-y-2">
              {SKELETON_ITEMS.map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-xl" />
              ))}
            </div>
          ) : docItems.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-400">No documents translated yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {docItems.slice(0, 5).map((d: any) => (
                <li key={d.id} className="flex items-center justify-between gap-2 py-2.5 text-xs">
                  <span className="min-w-0 truncate text-slate-800 font-medium">{d.filename}</span>
                  <span
                    className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase ${
                      d.status === "ready"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : d.status === "failed"
                        ? "bg-rose-50 text-rose-700 border border-rose-200"
                        : "bg-amber-50 text-amber-700 border border-amber-200"
                    }`}
                  >
                    {d.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Supported Languages Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <Globe className="h-4 w-4 text-dl-blue" /> Language capabilities
            </h3>
          </div>
          <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
            {(langs ?? []).map((l) => (
              <span
                key={l.code}
                title={`${l.name}: STT ${l.stt_status}, MT ${l.mt_status}, TTS ${l.tts_status}`}
                className={`rounded-md border px-2 py-1 text-xs font-medium ${
                  l.translation_supported
                    ? "border-blue-200 bg-blue-50/60 text-slate-800"
                    : "border-slate-200 bg-slate-50 text-slate-400"
                }`}
              >
                {l.native_name || l.name}
                {l.speech_output_supported && " 🔊"}
              </span>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
            Capabilities are validated per deployment. A language is only shown as supported when models are installed and healthy. 🔊 = translated voice available.
          </p>
        </div>
      </div>
    </div>
  );
}
