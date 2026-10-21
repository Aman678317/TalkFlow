import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Languages, Mic, Video, FileText, Activity, Clock, Globe, ChevronRight } from "lucide-react";
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
    { label: "Translations (30d)", value: Math.round(usageQ.data?.totals?.translation_requests ?? 0), icon: Activity, tint: "bg-[#007AFF]/10 text-[#007AFF]" },
    { label: "Characters", value: Math.round(usageQ.data?.totals?.characters ?? 0).toLocaleString(), icon: Languages, tint: "bg-[#5856D6]/10 text-[#5856D6]" },
    { label: "Audio seconds", value: Math.round(usageQ.data?.totals?.audio_seconds ?? 0), icon: Mic, tint: "bg-[#FF9500]/10 text-[#FF9500]" },
    { label: "Document pages", value: Math.round(usageQ.data?.totals?.document_pages ?? 0), icon: FileText, tint: "bg-[#30B0C7]/10 text-[#30B0C7]" },
  ];
  const realtimeLangs = (langs ?? []).filter((l) => l.realtime_supported).length;
  const userName = (user?.full_name || user?.name || user?.email || "there").split(" ")[0];
  const planName = (org?.plan || usageQ.data?.plan || "pro").toUpperCase();

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
      {/* Welcome Banner & Quick Action Buttons */}
      <div className="flex flex-col gap-6 border-b border-black/[0.06] pb-8">
        <div className="min-w-0">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-500">Workspace overview</p>
          <h1 className="break-words text-3xl font-semibold tracking-[-0.025em] text-neutral-950 sm:text-4xl">
            Welcome back, {userName} <span aria-hidden="true">👋</span>
          </h1>
          <p className="mt-2.5 text-sm leading-relaxed text-neutral-600 flex flex-wrap items-center gap-2">
            <span>{org?.name || "GlobalTalk"}</span>
            <span aria-hidden="true" className="text-neutral-300">·</span>
            <span className="apple-pill-badge">{planName}</span>
            <span aria-hidden="true" className="text-neutral-300">·</span>
            <span>{realtimeLangs} realtime-ready languages</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Link to="/translate" className="apple-btn-blue">
            Translate text <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </Link>
          <Link to="/write" className="apple-btn-tinted">
            Write companion
          </Link>
          <Link to="/voice" className="apple-btn-tinted">
            Live Voice
          </Link>
          <Link to="/meetings" className="apple-btn-tinted">
            Start a meeting
          </Link>
        </div>
      </div>

      {/* KPI Stats Grid - Apple Health / Widget Aesthetic */}
      <Stagger className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <StaggerItem key={s.label} className="apple-widget">
              <div className="mb-4 flex items-start justify-between gap-2">
                <p className="text-xs font-medium leading-relaxed text-neutral-600">{s.label}</p>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${s.tint}`}>
                  <Icon className="h-4 w-4" />
                </div>
              </div>
              {usageQ.isLoading ? (
                <Skeleton className="h-8 w-24 rounded-lg" />
              ) : (
                <p className="break-words text-2xl font-semibold tabular-nums tracking-[-0.025em] text-neutral-950 sm:text-3xl">
                  {s.value}
                </p>
              )}
            </StaggerItem>
          );
        })}
      </Stagger>

      {/* Workspace Activity Cards - Inset Grouped Lists */}
      <Stagger className="grid gap-6 lg:grid-cols-2">
        {/* Recent Translations Card */}
        <StaggerItem className="apple-grouped-card">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-black/[0.06] pb-4">
            <h2 className="flex items-center gap-2.5 text-base font-semibold text-neutral-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#007AFF]/10 text-[#007AFF]">
                <Languages className="h-4 w-4" />
              </span>
              Recent translations
            </h2>
            <Link to="/history" className="flex items-center gap-1 text-xs font-semibold text-[#007AFF] hover:underline">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </div>

          {historyQ.isLoading ? (
            <div className="space-y-2.5">
              {SKELETON_ITEMS.map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-2xl" />
              ))}
            </div>
          ) : historyItems.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-black/[0.08] bg-black/[0.02] px-5 py-10 text-center text-sm leading-relaxed text-neutral-500">
              No translations yet. Try the Translate workspace.
            </p>
          ) : (
            <ul className="divide-y divide-black/[0.06]">
              {historyItems.map((h: any) => (
                <li key={h.id} className="py-3 text-sm transition-colors hover:bg-black/[0.015] rounded-xl px-2">
                  <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
                    <span className="rounded-full bg-black/[0.05] px-2.5 py-0.5 font-medium text-neutral-700">
                      {h.source_lang || h.source_language || "?"} → {h.target_lang || h.target_language || "?"}
                    </span>
                    <span className="font-mono text-[11px] text-neutral-400">{Math.round(h.latency_ms ?? 0)} ms</span>
                  </div>
                  <p className="truncate font-normal text-neutral-600">{h.source_text}</p>
                  <p className="truncate font-medium text-neutral-950">{h.target_text || h.translated_text}</p>
                </li>
              ))}
            </ul>
          )}
        </StaggerItem>

        {/* Recent Meetings Card */}
        <StaggerItem className="apple-grouped-card">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-black/[0.06] pb-4">
            <h2 className="flex items-center gap-2.5 text-base font-semibold text-neutral-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#5856D6]/10 text-[#5856D6]">
                <Video className="h-4 w-4" />
              </span>
              Recent meetings
            </h2>
            <Link to="/meetings" className="flex items-center gap-1 text-xs font-semibold text-[#007AFF] hover:underline">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </div>

          {meetingsQ.isLoading ? (
            <div className="space-y-2.5">
              {SKELETON_ITEMS.map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-2xl" />
              ))}
            </div>
          ) : meetingItems.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-black/[0.08] bg-black/[0.02] px-5 py-10 text-center text-sm text-neutral-500">
              No meetings yet.
            </p>
          ) : (
            <ul className="divide-y divide-black/[0.06]">
              {meetingItems.map((m: any) => (
                <li key={m.id} className="flex items-center justify-between gap-3 py-3 text-sm transition-colors hover:bg-black/[0.015] rounded-xl px-2">
                  <Link to={`/meeting/${m.id}`} className="group min-w-0 flex-1">
                    <p className="truncate font-medium text-neutral-950 group-hover:text-[#007AFF] transition-colors">{m.title}</p>
                    <p className="mt-1 flex items-center gap-1 text-xs text-neutral-500">
                      <Clock className="h-3 w-3 text-neutral-400" /> {m.created_at ? new Date(m.created_at).toLocaleString() : ""}
                    </p>
                  </Link>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                      m.status === "live"
                        ? "bg-[#34C759]/15 text-[#248A3D] border border-[#34C759]/30"
                        : "bg-black/[0.05] text-neutral-600"
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
        <StaggerItem className="apple-grouped-card">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-black/[0.06] pb-4">
            <h2 className="flex items-center gap-2.5 text-base font-semibold text-neutral-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#30B0C7]/10 text-[#30B0C7]">
                <FileText className="h-4 w-4" />
              </span>
              Documents
            </h2>
            <Link to="/documents" className="flex items-center gap-1 text-xs font-semibold text-[#007AFF] hover:underline">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </div>

          {docsQ.isLoading ? (
            <div className="space-y-2.5">
              {SKELETON_ITEMS.map((key) => (
                <Skeleton key={key} className="h-12 w-full rounded-2xl" />
              ))}
            </div>
          ) : docItems.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-black/[0.08] bg-black/[0.02] px-5 py-10 text-center text-sm text-neutral-500">
              No documents translated yet.
            </p>
          ) : (
            <ul className="divide-y divide-black/[0.06]">
              {docItems.slice(0, 5).map((d: any) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-3 text-sm transition-colors hover:bg-black/[0.015] rounded-xl px-2">
                  <span className="min-w-0 truncate font-medium text-neutral-800">{d.filename}</span>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                      d.status === "ready"
                        ? "bg-[#34C759]/15 text-[#248A3D] border border-[#34C759]/30"
                        : d.status === "failed"
                        ? "bg-[#FF3B30]/15 text-[#D70015] border border-[#FF3B30]/30"
                        : "bg-[#FF9500]/15 text-[#A05D00] border border-[#FF9500]/30"
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
        <StaggerItem className="apple-grouped-card">
          <div className="mb-4 flex items-center justify-between border-b border-black/[0.06] pb-4">
            <h2 className="flex items-center gap-2.5 text-base font-semibold text-neutral-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#FF9500]/10 text-[#FF9500]">
                <Globe className="h-4 w-4" />
              </span>
              Language capabilities
            </h2>
          </div>
          <div className="flex max-h-44 flex-wrap gap-2 overflow-y-auto rounded-2xl p-1" role="region" aria-label="Language capabilities" tabIndex={0}>
            {(langs ?? []).map((l) => (
              <span
                key={l.code}
                title={`${l.name}: STT ${l.speech_input_status}, MT ${l.translation_status}, TTS ${l.speech_output_status}`}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  l.translation_supported
                    ? "border-black/[0.06] bg-black/[0.03] text-neutral-800 hover:bg-black/[0.06]"
                    : "border-black/[0.04] bg-neutral-50 text-neutral-400"
                }`}
              >
                {l.native_name || l.name}
                {l.speech_output_supported && " 🔊"}
              </span>
            ))}
          </div>
          <p className="mt-4 border-t border-black/[0.06] pt-4 text-xs leading-relaxed text-neutral-500">
            Capabilities are validated per deployment. A language is only shown as supported when models are installed and healthy. 🔊 = translated voice available.
          </p>
        </StaggerItem>
      </Stagger>
    </div>
  );
}
