import React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Calendar,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Globe,
  Keyboard,
  Link2,
  Phone,
  Radio,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Sparkles,
  Users,
  Video,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import type { Meeting } from "../lib/types";
import { Badge, Button, Card, Field, Input, Modal } from "../components/ui";
import { toast } from "../stores/toasts";

export default function Meetings() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();

  // Dialog & Form State
  const [open, setOpen] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [joinUrl, setJoinUrl] = React.useState("");
  const [copiedId, setCopiedId] = React.useState<string | null>(null);

  // Direct Code / Link Join Bar State
  const [joinInput, setJoinInput] = React.useState("");

  // Filter & Search State
  const [statusFilter, setStatusFilter] = React.useState<"all" | "live" | "scheduled" | "ended">("all");
  const [searchQuery, setSearchQuery] = React.useState("");

  // Showcase Carousel State
  const [activeSlide, setActiveSlide] = React.useState(0);

  const meetingsQ = useQuery({
    queryKey: ["meetings"],
    queryFn: () => api<Meeting[]>("/api/v1/meetings"),
    refetchInterval: 10_000,
  });

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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["meetings"] });
      toast.success("Meeting ended");
    },
  });

  React.useEffect(() => {
    const end = params.get("end");
    if (end) {
      endMeeting.mutate(end);
      nav("/meetings", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // Handle direct "Enter a code or link" join
  function handleJoinWithCode(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const trimmed = joinInput.trim();
    if (!trimmed) return;

    if (trimmed.includes("/meeting/")) {
      try {
        const url = new URL(trimmed.startsWith("http") ? trimmed : `http://${trimmed}`);
        nav(`${url.pathname}${url.search}`);
        return;
      } catch {
        const match = trimmed.match(/\/meeting\/([a-zA-Z0-9_-]+)(\?join=[a-zA-Z0-9_-]+)?/);
        if (match) {
          nav(match[0]);
          return;
        }
      }
    }

    nav(`/meeting/${trimmed}`);
  }

  async function copyInvite(m: Meeting) {
    const url = `${location.origin}/meeting/${m.id}?join=${m.join_token}`;
    await navigator.clipboard.writeText(url);
    setJoinUrl(url);
    setCopiedId(m.id);
    setTimeout(() => setCopiedId(null), 2500);
    toast.success("Invite link copied", "Guests can join with this link.");
  }

  const allMeetings = meetingsQ.data ?? [];

  // Filtered list
  const filteredMeetings = allMeetings.filter((m) => {
    // Status filter
    if (statusFilter !== "all" && m.status !== statusFilter) return false;
    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = m.title?.toLowerCase().includes(q);
      const matchRoom = m.room_name?.toLowerCase().includes(q);
      const matchId = m.id.toLowerCase().includes(q);
      if (!matchTitle && !matchRoom && !matchId) return false;
    }
    return true;
  });

  const liveCount = allMeetings.filter((m) => m.status === "live").length;
  const scheduledCount = allMeetings.filter((m) => m.status === "scheduled").length;
  const endedCount = allMeetings.filter((m) => m.status === "ended").length;

  const slides = [
    {
      badge: "Zero-Install WebRTC",
      icon: Link2,
      iconColor: "text-dl-blue",
      bgColor: "bg-blue-50 border-blue-100",
      title: "Get a link you can share",
      description:
        "Click New meeting to get a secure link you can send to colleagues or clients. Anyone can join instantly in their web browser with no account needed.",
    },
    {
      badge: "Real-Time Neural AI",
      icon: Globe,
      iconColor: "text-emerald-600",
      bgColor: "bg-emerald-50 border-emerald-100",
      title: "Speak in any language",
      description:
        "Every participant speaks their own language and hears live real-time audio and subtitles in theirs with under 350ms streaming latency.",
    },
    {
      badge: "Enterprise Security",
      icon: ShieldCheck,
      iconColor: "text-indigo-600",
      bgColor: "bg-indigo-50 border-indigo-100",
      title: "Your meetings are private & safe",
      description:
        "No one can join a room unless admitted by token or host. Media streams are end-to-end encrypted with self-hosted AI models and zero data retention.",
    },
  ];

  return (
    <div className="mx-auto max-w-6xl p-4 lg:p-8">
      {/* =========================================================================
          SECTION 1: GOOGLE MEET PARADIGM HERO (Two-Column Layout)
         ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center mb-10 pt-2">
        {/* Left Column: Greeting, Value Prop, Action Controls */}
        <div className="lg:col-span-7 space-y-6">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-dl-blue-light border border-dl-blue-mid text-xs font-semibold text-dl-blue">
              <Sparkles className="h-3.5 w-3.5 text-dl-blue" />
              <span>GlobalTalk Real-Time Translation</span>
            </div>

            <h1 className="text-3xl sm:text-4xl lg:text-[40px] font-bold tracking-tight text-slate-900 leading-tight">
              Multilingual video meetings for everyone
            </h1>

            <p className="text-base sm:text-lg text-slate-600 leading-relaxed max-w-xl">
              Connect, collaborate, and speak across borders. One shared conversation where every participant hears their own language in real time.
            </p>
          </div>

          {/* Action Row: Google Meet Signature Layout */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-1">
            <Button
              size="lg"
              className="h-12 px-6 rounded-xl bg-dl-blue hover:bg-dl-blue-hover text-white font-medium shadow-sm flex items-center justify-center gap-2.5 shrink-0 transition-all active:scale-[0.99]"
              onClick={() => setOpen(true)}
            >
              <Video className="h-5 w-5" />
              <span>New meeting</span>
            </Button>

            <form onSubmit={handleJoinWithCode} className="flex items-center gap-2 flex-1">
              <div className="relative flex-1">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                  <Keyboard className="h-4 w-4" />
                </div>
                <input
                  type="text"
                  value={joinInput}
                  onChange={(e) => setJoinInput(e.target.value)}
                  placeholder="Enter a code or link"
                  className="w-full h-12 pl-10 pr-4 rounded-xl border border-slate-300 bg-white text-sm text-slate-900 placeholder:text-slate-400 focus:border-dl-blue focus:outline-none focus:ring-2 focus:ring-dl-blue/20 transition-all shadow-2xs"
                />
              </div>
              <Button
                type="submit"
                variant="ghost"
                disabled={!joinInput.trim()}
                className="h-12 px-5 rounded-xl font-medium text-dl-blue hover:bg-dl-blue-light disabled:text-slate-300 disabled:hover:bg-transparent shrink-0"
              >
                Join
              </Button>
            </form>
          </div>

          {/* Trust & Spec Chips */}
          <div className="flex flex-wrap items-center gap-y-2 gap-x-5 pt-1 text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <Shield className="h-3.5 w-3.5 text-slate-400" />
              End-to-end encrypted
            </span>
            <span className="flex items-center gap-1.5">
              <Radio className="h-3.5 w-3.5 text-emerald-500" />
              Streaming latency &lt; 350ms
            </span>
            <span className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5 text-slate-400" />
              No login required for guests
            </span>
          </div>
        </div>

        {/* Right Column: Google Meet Feature Spotlight Carousel */}
        <div className="lg:col-span-5">
          <div className="bg-white rounded-2.5xl border border-slate-200 p-6 sm:p-7 shadow-card relative flex flex-col justify-between min-h-[310px]">
            {/* Slide Header */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700">
                  {slides[activeSlide].badge}
                </span>
                <span className="text-xs font-medium text-slate-400 tabular-nums">
                  {activeSlide + 1} / {slides.length}
                </span>
              </div>

              {/* Graphic container */}
              <div className="flex items-center justify-center my-4">
                <div
                  className={`w-20 h-20 rounded-2xl ${slides[activeSlide].bgColor} border flex items-center justify-center transition-all duration-300 shadow-2xs`}
                >
                  {React.createElement(slides[activeSlide].icon, {
                    className: `h-10 w-10 ${slides[activeSlide].iconColor}`,
                  })}
                </div>
              </div>

              {/* Text content */}
              <div className="text-center space-y-1.5 mt-2">
                <h3 className="text-base font-bold text-slate-900">{slides[activeSlide].title}</h3>
                <p className="text-xs text-slate-600 leading-relaxed max-w-sm mx-auto">
                  {slides[activeSlide].description}
                </p>
              </div>
            </div>

            {/* Carousel navigation controls */}
            <div className="flex items-center justify-between pt-5 mt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setActiveSlide((prev) => (prev === 0 ? slides.length - 1 : prev - 1))}
                className="h-8 w-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                aria-label="Previous slide"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>

              <div className="flex items-center gap-1.5">
                {slides.map((_, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setActiveSlide(idx)}
                    className={`h-2 rounded-full transition-all ${
                      idx === activeSlide ? "w-6 bg-dl-blue" : "w-2 bg-slate-200 hover:bg-slate-300"
                    }`}
                    aria-label={`Slide ${idx + 1}`}
                  />
                ))}
              </div>

              <button
                type="button"
                onClick={() => setActiveSlide((prev) => (prev === slides.length - 1 ? 0 : prev + 1))}
                className="h-8 w-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                aria-label="Next slide"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-slate-200 my-8" />

      {/* =========================================================================
          SECTION 2: MEETINGS MANAGEMENT HUB (Filter Pills, Search, Feed)
         ========================================================================= */}
      <div className="space-y-4">
        {/* Header row: Title + Date Strip + Search */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900">Meetings Hub</h2>
              <span className="text-xs text-slate-400">·</span>
              <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
                <Calendar className="h-3.5 w-3.5 text-dl-blue" />
                <span>
                  {new Date().toLocaleDateString(undefined, {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}
                </span>
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Manage ongoing conversations, access past AI transcripts, or invite new participants.
            </p>
          </div>

          {/* Search & Refresh */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-3 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search rooms or titles..."
                className="h-9 w-48 sm:w-60 pl-8 pr-7 rounded-lg border border-slate-200 bg-white text-xs text-slate-900 placeholder:text-slate-400 focus:border-dl-blue focus:outline-none focus:ring-1 focus:ring-dl-blue"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => qc.invalidateQueries({ queryKey: ["meetings"] })}
              title="Refresh meetings"
              className="h-9 w-9 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 flex items-center justify-center text-slate-500 hover:text-slate-800 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${meetingsQ.isFetching ? "animate-spin text-dl-blue" : ""}`} />
            </button>
          </div>
        </div>

        {/* Tab Filters */}
        <div className="flex items-center gap-2 border-b border-slate-200 pb-2 overflow-x-auto">
          <button
            type="button"
            onClick={() => setStatusFilter("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              statusFilter === "all"
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            All Meetings ({allMeetings.length})
          </button>

          <button
            type="button"
            onClick={() => setStatusFilter("live")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 transition-all ${
              statusFilter === "live"
                ? "bg-emerald-600 text-white"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            {liveCount > 0 && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            )}
            Live Now ({liveCount})
          </button>

          <button
            type="button"
            onClick={() => setStatusFilter("scheduled")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              statusFilter === "scheduled"
                ? "bg-dl-blue text-white"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            Scheduled ({scheduledCount})
          </button>

          <button
            type="button"
            onClick={() => setStatusFilter("ended")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              statusFilter === "ended"
                ? "bg-slate-700 text-white"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            Past / Concluded ({endedCount})
          </button>
        </div>

        {/* Meeting List or Empty State */}
        {filteredMeetings.length === 0 && !meetingsQ.isLoading ? (
          <Card className="p-8 text-center bg-white rounded-2xl border border-slate-200">
            <div className="w-14 h-14 rounded-full bg-blue-50 border border-blue-100 flex items-center justify-center mx-auto mb-3 text-dl-blue">
              <Video className="h-6 w-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-900">
              {searchQuery
                ? "No matching meetings found"
                : statusFilter === "live"
                ? "No live meetings in progress"
                : "No meetings scheduled"}
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              {searchQuery
                ? `No meetings match "${searchQuery}". Try searching by room ID or clearing the query.`
                : "Start an instant multilingual meeting to share a link, or join a room created by your team."}
            </p>
            <div className="mt-4 flex items-center justify-center gap-2">
              {searchQuery ? (
                <Button size="sm" variant="secondary" onClick={() => setSearchQuery("")}>
                  Clear Search
                </Button>
              ) : (
                <Button size="sm" onClick={() => setOpen(true)}>
                  Create New Meeting
                </Button>
              )}
            </div>
          </Card>
        ) : (
          <div className="space-y-3">
            {filteredMeetings.map((m) => {
              const isLive = m.status === "live";
              const isEnded = m.status === "ended";
              const isPhoneCall = m.title.toLowerCase().includes("phone call") || m.room_name.startsWith("phone-call");

              return (
                <div
                  key={m.id}
                  className={`bg-white rounded-xl border transition-all p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-2xs hover:shadow-card ${
                    isLive ? "border-emerald-300 ring-1 ring-emerald-500/10" : "border-slate-200 hover:border-slate-300"
                  }`}
                >
                  {/* Left Side: Room details */}
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <Link
                        to={`/meeting/${m.id}`}
                        className="text-sm font-semibold text-slate-900 hover:text-dl-blue transition-colors truncate"
                      >
                        {m.title || "Untitled Meeting"}
                      </Link>

                      {/* Status Badge */}
                      <Badge tone={isLive ? "good" : isEnded ? "neutral" : "info"}>
                        {isLive ? (
                          <span className="flex items-center gap-1">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            Live Now
                          </span>
                        ) : (
                          m.status
                        )}
                      </Badge>

                      {m.has_summary && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-dl-blue border border-blue-200">
                          <Sparkles className="h-3 w-3" /> AI Summary ✓
                        </span>
                      )}

                      {isPhoneCall && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                          <Phone className="h-3 w-3" /> Voice Session
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-slate-500 flex-wrap">
                      <span>{new Date(m.created_at).toLocaleString()}</span>
                      <span>·</span>
                      <span className="font-mono bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded text-[10px] text-slate-600">
                        room: {m.room_name}
                      </span>
                      {m.transport && (
                        <>
                          <span>·</span>
                          <span className="uppercase text-[10px] font-medium text-slate-400">{m.transport}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Right Side: Action Buttons */}
                  <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                    <Button
                      size="sm"
                      variant="secondary"
                      className="rounded-lg h-8 px-3 text-xs gap-1.5"
                      onClick={() => copyInvite(m)}
                    >
                      {copiedId === m.id ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                          <span className="text-emerald-600">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5 text-slate-500" />
                          <span>Copy invite</span>
                        </>
                      )}
                    </Button>

                    <Link to={`/meeting/${m.id}`}>
                      <Button
                        size="sm"
                        className={`rounded-lg h-8 px-3.5 text-xs font-medium gap-1.5 ${
                          isEnded ? "bg-slate-700 hover:bg-slate-800" : "bg-dl-blue hover:bg-dl-blue-hover text-white"
                        }`}
                      >
                        {isEnded ? "View Summary" : "Join"}
                        <ExternalLink className="h-3 w-3" />
                      </Button>
                    </Link>

                    {!isEnded && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="rounded-lg h-8 px-2.5 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                        onClick={() => endMeeting.mutate(m.id)}
                      >
                        End
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* =========================================================================
          MODAL 1: NEW MEETING CREATION (Strictly preserving form field name)
         ========================================================================= */}
      <Modal open={open} onClose={() => setOpen(false)} title="New meeting">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Meeting title">
            <Input
              autoFocus
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Weekly sync — EN/HI/JA"
            />
          </Field>

          {/* Quick preset chips for rapid creation */}
          <div className="space-y-1.5">
            <p className="text-[11px] font-medium text-slate-500">Quick suggestions:</p>
            <div className="flex flex-wrap gap-1.5">
              {[
                "Instant Multilingual Sync",
                "Product & Engineering Standup",
                "Client Briefing (EN ↔ ES)",
                "Global Townhall",
              ].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setTitle(preset)}
                  className="px-2.5 py-1 rounded-md bg-slate-100 hover:bg-slate-200 text-[11px] text-slate-700 transition-colors"
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} className="bg-dl-blue hover:bg-dl-blue-hover text-white">
              Create & join
            </Button>
          </div>
        </form>
      </Modal>

      {/* =========================================================================
          MODAL 2: INVITE LINK SHARING (Strictly preserving copy & token display)
         ========================================================================= */}
      <Modal open={!!joinUrl} onClose={() => setJoinUrl("")} title="Invite link">
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            Share this link — guests join with the embedded token (no account needed):
          </p>

          <code className="block break-all rounded-lg bg-slate-50 border border-slate-200 p-2.5 text-xs font-mono text-slate-800">
            {joinUrl}
          </code>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                await navigator.clipboard.writeText(joinUrl);
                toast.success("Copied to clipboard!");
              }}
              className="gap-1.5"
            >
              <Copy className="h-3.5 w-3.5" />
              Copy link
            </Button>
            <Button type="button" onClick={() => setJoinUrl("")}>
              Done
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
