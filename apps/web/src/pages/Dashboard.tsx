import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Languages, Mic, Video, FileText, Activity, Clock, Globe } from "lucide-react";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui";
import { Stagger, StaggerItem } from "../components/Motion";
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
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
      {/* Welcome Banner & Quick Action Buttons */}
      <div className="flex flex-col gap-6 border-b border-border pb-8">
        <div className="min-w-0">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-600">Workspace overview</p>
          <h1 className="break-words text-3xl font-semibold tracking-title text-ink-950 sm:text-4xl">Welcome back, {userName} <span aria-hidden="true">👋</span></h1>
          <p className="mt-3 text-sm leading-relaxed text-ink-600">
            {org?.name || "GlobalTalk"} · {planName} plan · {realtimeLangs} realtime-ready languages
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/translate" className="btn-tactile inline-flex min-h-11 items-center justify-center gap-2 rounded-xl2 bg-accent-600 px-4 py-2 text-sm font-semibold text-white shadow-xs hover:bg-accent-700">
            Translate text <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </Link>
          <Link to="/write" className="btn-tactile inline-flex min-h-11 items-center justify-center rounded-xl2 border border-border bg-surface-panel px-4 py-2 text-sm font-medium text-ink-700 hover:bg-surface-subtle">
            Write companion
          </Link>
          <Link to="/voice" className="btn-tactile inline-flex min-h-11 items-center justify-center rounded-xl2 border border-border bg-surface-panel px-4 py-2 text-sm font-medium text-ink-700 hover:bg-surface-subtle">
            Live Voice
          </Link>
          <Link to="/meetings" className="btn-tactile inline-flex min-h-11 items-center justify-center rounded-xl2 border border-border bg-surface-panel px-4 py-2 text-sm font-medium text-ink-700 hover:bg-surface-subtle">
            Start a meeting
          </Link>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <Stagger className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <StaggerItem key={s.label} className="min-w-0 rounded-2xl border border-border bg-surface-panel p-4 shadow-xs sm:p-5">
              <div className="mb-5 flex items-start justify-between gap-2">
                <p className="text-xs font-medium leading-relaxed text-ink-600">{s.label}</p>
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-surface-canvas text-ink-600">
                  <Icon className="h-3.5 w-3.5" />
                </div>
              </div>
              {usageQ.isLoading ? (
                <Skeleton className="h-8 w-24 rounded-lg" />
              ) : (
                <p className="break-words font-display text-2xl font-semibold tabular-nums tracking-title text-ink-950 sm:text-3xl">{s.value}</p>
              )}
            </StaggerItem>
          );
        })}
      </Stagger>

      {/* Workspace Activity Cards */}
      <Stagger className="grid gap-5 lg:grid-cols-2">
        {/* Recent Translations Card */}
        <StaggerItem className="min-w-0 rounded-2xl border border-border bg-surface-panel p-5 shadow-xs sm:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 pb-4">
            <h2 className="flex items-center gap-2 text-base font-semibold text-ink-950">
              <Languages className="h-4 w-4 text-accent-600" /> Recent translations
            </h2>
            <Link to="/history" className="flex items-center gap-1 text-xs font-semibold text-accent-600 hover:text-accent-700 hover:underline">
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
            <p className="rounded-xl2 border border-dashed border-border bg-surface-canvas px-5 py-10 text-center text-sm leading-relaxed text-ink-600">No translations yet. Try the Translate workspace.</p>
          ) : (
            <ul className="divide-y divide-ink-100">
              {historyItems.map((h: any) => (
                <li key={h.id} className="py-3.5 text-sm">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-600">
                    <span className="rounded bg-surface-subtle px-2 py-0.5 font-semibold text-ink-700">
                      {h.source_lang || h.source_language || "?"} → {h.target_lang || h.target_language || "?"}
                    </span>
                    <span className="font-mono">{Math.round(h.latency_ms ?? 0)} ms</span>
                  </div>
                  <p className="truncate font-normal text-ink-600">{h.source_text}</p>
                  <p className="truncate font-semibold text-ink-950">{h.target_text || h.translated_text}</p>
                </li>
              ))}
            </ul>
          )}
        </StaggerItem>

        {/* Recent Meetings Card */}
        <StaggerItem className="min-w-0 rounded-2xl border border-border bg-surface-panel p-5 shadow-xs sm:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 pb-4">
            <h2 className="flex items-center gap-2 text-base font-semibold text-ink-950">
              <Video className="h-4 w-4 text-accent-600" /> Recent meetings
            </h2>
            <Link to="/meetings" className="flex items-center gap-1 text-xs font-semibold text-accent-600 hover:text-accent-700 hover:underline">
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
            <p className="rounded-xl2 border border-dashed border-border bg-surface-canvas px-5 py-10 text-center text-sm text-ink-600">No meetings yet.</p>
          ) : (
            <ul className="divide-y divide-ink-100">
              {meetingItems.map((m: any) => (
                <li key={m.id} className="flex items-center justify-between gap-3 py-3.5 text-sm">
                  <Link to={`/meeting/${m.id}`} className="group min-w-0 flex-1 rounded-md">
                    <p className="truncate font-medium text-ink-950 group-hover:text-accent-700">{m.title}</p>
                    <p className="mt-1 flex items-center gap-1 text-xs text-ink-600">
                      <Clock className="h-3 w-3" /> {m.created_at ? new Date(m.created_at).toLocaleString() : ""}
                    </p>
                  </Link>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                      m.status === "live"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-surface-subtle text-ink-600"
                    }`}
                  >
                    {m.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </StaggerItem>

        {/* Documents Summary Card */}
        <StaggerItem className="min-w-0 rounded-2xl border border-border bg-surface-panel p-5 shadow-xs sm:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 pb-4">
            <h2 className="flex items-center gap-2 text-base font-semibold text-ink-950">
              <FileText className="h-4 w-4 text-accent-600" /> Documents
            </h2>
            <Link to="/documents" className="flex items-center gap-1 text-xs font-semibold text-accent-600 hover:text-accent-700 hover:underline">
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
            <p className="rounded-xl2 border border-dashed border-border bg-surface-canvas px-5 py-10 text-center text-sm text-ink-600">No documents translated yet.</p>
          ) : (
            <ul className="divide-y divide-ink-100">
              {docItems.slice(0, 5).map((d: any) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-3.5 text-sm">
                  <span className="min-w-0 truncate font-medium text-ink-800">{d.filename}</span>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
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
        </StaggerItem>

        {/* Supported Languages Card */}
        <StaggerItem className="min-w-0 rounded-2xl border border-border bg-surface-panel p-5 shadow-xs sm:p-6">
          <div className="mb-4 flex items-center justify-between border-b border-ink-100 pb-4">
            <h2 className="flex items-center gap-2 text-base font-semibold text-ink-950">
              <Globe className="h-4 w-4 text-accent-600" /> Language capabilities
            </h2>
          </div>
          <div className="flex max-h-44 flex-wrap gap-2 overflow-y-auto rounded-lg p-1" role="region" aria-label="Language capabilities" tabIndex={0}>
            {(langs ?? []).map((l) => (
              <span
                key={l.code}
                title={`${l.name}: STT ${l.stt_status}, MT ${l.mt_status}, TTS ${l.tts_status}`}
                className={`rounded-md border px-2 py-1 text-xs font-medium ${
                  l.translation_supported
                    ? "border-accent-200 bg-accent-50 text-ink-800"
                    : "border-border bg-surface-canvas text-ink-600"
                }`}
              >
                {l.native_name || l.name}
                {l.speech_output_supported && " 🔊"}
              </span>
            ))}
          </div>
          <p className="mt-4 border-t border-ink-100 pt-4 text-xs leading-relaxed text-ink-600">
            Capabilities are validated per deployment. A language is only shown as supported when models are installed and healthy. 🔊 = translated voice available.
          </p>
        </StaggerItem>
      </Stagger>
    </div>
  );
}
