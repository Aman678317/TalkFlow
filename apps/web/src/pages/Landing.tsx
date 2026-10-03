import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  FileText,
  Languages,
  Mic,
  Shield,
  Sparkles,
  Video,
  Volume2,
  Zap,
  Menu,
  X,
  Radio,
  ExternalLink,
} from "lucide-react";
import { Logo } from "../components/Layout";
import { useAuth } from "../stores/auth";

const LANGS = [
  "English", "हिन्दी (Hindi)", "Español (Spanish)", "Deutsch (German)",
  "Français (French)", "日本語 (Japanese)", "中文 (Chinese)", "العربية (Arabic)",
  "मराठी (Marathi)", "বাংলা (Bengali)", "Português", "Italiano",
];

const FAQS = [
  {
    q: "How does GlobalTalk AI achieve sub-second real-time voice translation?",
    a: "GlobalTalk AI streams 16kHz PCM audio directly over WebSockets and WebRTC to low-latency edge models: Silero VAD for instant voice detection, OpenAI Whisper for continuous transcription, neural MT for direct language pairing, and Piper TTS for natural speech synthesis. End-to-end processing completes in under 1,000 milliseconds.",
  },
  {
    q: "Is my conversation or audio data stored or trained on?",
    a: "No. GlobalTalk AI adheres to strict data privacy principles with zero third-party telemetry, ephemeral in-memory audio processing, and tenant isolation. Self-hosted deployments keep all audio and data completely on-premises.",
  },
  {
    q: "What document formats are supported for translation?",
    a: "GlobalTalk AI translates PDF, DOCX (Word), PPTX (PowerPoint), XLSX (Excel), TXT, and HTML files while preserving the original layout, styling, fonts, tables, and images.",
  },
  {
    q: "Can multiple participants in a video meeting speak different languages simultaneously?",
    a: "Yes. In GlobalTalk AI video meetings, each participant selects their spoken language and preferred listening language. WebRTC routes translated audio streams and live translated captions independently to each attendee in real time.",
  },
  {
    q: "How does GlobalTalk AI prevent translation drift across language pairs?",
    a: "GlobalTalk AI enforces the Canonical Source Principle: the original human speaker's segment is the sole semantic source of truth. Rather than daisy-chaining translations (for example, Hindi to English to Japanese), each target language fans out directly from the original source.",
  },
];

export default function Landing() {
  const user = useAuth((s) => s.user);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [demoMode, setDemoMode] = useState<"voice" | "text">("voice");

  return (
    <div className="min-h-full bg-white text-dl-navy selection:bg-dl-blue selection:text-white">
      {/* HEADER NAVBAR */}
      <header className="sticky top-0 z-50 border-b border-dl-border/80 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">
          <Link to="/" className="flex items-center gap-3 group">
            <Logo className="h-8 w-8 text-dl-blue transition-transform group-hover:scale-105" />
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-dl-navy">
                GlobalTalk <span className="text-dl-blue">AI</span>
              </span>
              <span className="hidden sm:inline-block rounded-full border border-dl-border bg-dl-bg-alt px-2.5 py-0.5 text-[11px] font-semibold text-dl-muted">
                Enterprise Suite
              </span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1 text-sm font-medium">
            <Link
              to="/translate"
              className="inline-flex items-center min-h-[40px] px-3.5 rounded-lg text-slate-700 hover:text-dl-navy hover:bg-dl-bg-alt transition-colors"
            >
              Translate
            </Link>
            <Link
              to="/write"
              className="inline-flex items-center min-h-[40px] px-3.5 rounded-lg text-slate-700 hover:text-dl-navy hover:bg-dl-bg-alt transition-colors"
            >
              Write
            </Link>
            <Link
              to="/voice"
              className="inline-flex items-center min-h-[40px] px-3.5 rounded-lg text-slate-700 hover:text-dl-navy hover:bg-dl-bg-alt transition-colors"
            >
              Live Voice
            </Link>
            <Link
              to="/meetings"
              className="inline-flex items-center min-h-[40px] px-3.5 rounded-lg text-slate-700 hover:text-dl-navy hover:bg-dl-bg-alt transition-colors"
            >
              Meetings
            </Link>

            <div className="ml-4 flex items-center gap-2 border-l border-dl-border pl-4">
              {user ? (
                <Link
                  to="/dashboard"
                  className="btn-tactile flex items-center gap-1.5 rounded-xl bg-dl-blue px-4 py-2 font-semibold text-white shadow-sm hover:bg-dl-blue-hover"
                >
                  Go to Dashboard <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="inline-flex items-center min-h-[40px] px-3 py-2 text-slate-700 hover:text-dl-navy transition-colors font-medium"
                  >
                    Sign in
                  </Link>
                  <Link
                    to="/signup"
                    className="btn-tactile rounded-xl bg-dl-blue px-4 py-2 font-semibold text-white shadow-sm hover:bg-dl-blue-hover"
                  >
                    Start Free
                  </Link>
                </>
              )}
            </div>
          </nav>

          {/* Mobile Menu Button */}
          <div className="flex md:hidden items-center gap-2">
            {user ? (
              <Link
                to="/dashboard"
                className="rounded-lg bg-dl-blue px-3 py-1.5 text-xs font-semibold text-white"
              >
                Dashboard
              </Link>
            ) : (
              <Link
                to="/signup"
                className="rounded-lg bg-dl-blue px-3 py-1.5 text-xs font-semibold text-white"
              >
                Start Free
              </Link>
            )}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="inline-flex items-center justify-center p-2 rounded-lg text-slate-700 hover:bg-dl-bg-alt hover:text-dl-navy focus:outline-none focus:ring-2 focus:ring-dl-blue"
              aria-label="Toggle navigation menu"
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-dl-border bg-white px-6 py-4 space-y-2">
            <Link
              to="/translate"
              onClick={() => setMobileMenuOpen(false)}
              className="block rounded-lg px-3 py-2 text-base font-medium text-slate-700 hover:bg-dl-bg-alt hover:text-dl-navy"
            >
              Translate
            </Link>
            <Link
              to="/write"
              onClick={() => setMobileMenuOpen(false)}
              className="block rounded-lg px-3 py-2 text-base font-medium text-slate-700 hover:bg-dl-bg-alt hover:text-dl-navy"
            >
              Write
            </Link>
            <Link
              to="/voice"
              onClick={() => setMobileMenuOpen(false)}
              className="block rounded-lg px-3 py-2 text-base font-medium text-slate-700 hover:bg-dl-bg-alt hover:text-dl-navy"
            >
              Live Voice
            </Link>
            <Link
              to="/meetings"
              onClick={() => setMobileMenuOpen(false)}
              className="block rounded-lg px-3 py-2 text-base font-medium text-slate-700 hover:bg-dl-bg-alt hover:text-dl-navy"
            >
              Meetings
            </Link>
            <div className="border-t border-dl-border pt-3 flex flex-col gap-2">
              {!user && (
                <Link
                  to="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block rounded-lg px-3 py-2 text-center text-sm font-medium text-slate-700 border border-dl-border hover:bg-dl-bg-alt"
                >
                  Sign in
                </Link>
              )}
              <Link
                to={user ? "/dashboard" : "/signup"}
                onClick={() => setMobileMenuOpen(false)}
                className="block rounded-lg bg-dl-blue px-3 py-2 text-center text-sm font-semibold text-white hover:bg-dl-blue-hover"
              >
                {user ? "Go to Dashboard" : "Start Free"}
              </Link>
            </div>
          </div>
        )}
      </header>

      {/* HERO SECTION */}
      <main className="mx-auto max-w-7xl px-6">
        <section className="py-12 lg:py-16 grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            {/* Eyebrow Restraint: Only 1 eyebrow on the entire page */}
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-dl-border bg-dl-bg-alt px-3.5 py-1 text-xs font-semibold text-slate-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              Sub-second voice and text translation pipeline
            </div>

            <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl text-dl-navy leading-[1.1]">
              One conversation.{" "}
              <span className="text-dl-blue">
                Every language.
              </span>
            </h1>

            {/* Strict Subtext Discipline: Exactly 18 words (<= 20 words constraint) */}
            <p className="mt-4 text-base sm:text-lg leading-relaxed text-slate-600 max-w-xl">
              Translate speech, text, documents, and video meetings in real time with sub-second latency and zero data retention.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3.5">
              <Link
                to="/signup"
                className="btn-tactile flex items-center gap-2 rounded-xl bg-dl-blue px-6 py-3.5 text-base font-semibold text-white shadow-sm hover:bg-dl-blue-hover"
              >
                Launch Workspace <ArrowRight className="h-5 w-5" />
              </Link>
              <Link
                to="/translate"
                className="btn-tactile rounded-xl border border-dl-border bg-white px-6 py-3.5 text-base font-semibold text-dl-navy hover:bg-dl-bg-alt shadow-xs"
              >
                Try Translator
              </Link>
            </div>

            <div className="mt-9 border-t border-dl-border/80 pt-5">
              <p className="text-xs font-semibold text-dl-muted mb-2.5">
                Supported Across 100+ Languages
              </p>
              <div className="flex flex-wrap gap-2">
                {LANGS.map((l) => (
                  <span
                    key={l}
                    className="rounded-lg border border-dl-border bg-dl-bg-alt px-2.5 py-1 text-xs text-slate-700 hover:border-dl-blue/40 transition-colors"
                  >
                    {l}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* INTERACTIVE WORKSPACE PREVIEW WIDGET */}
          <div className="rounded-2xl border border-dl-border/90 bg-white p-5 shadow-card hover:shadow-pop transition-shadow duration-300">
            {/* Widget Header & Mode Switcher */}
            <div className="flex items-center justify-between border-b border-dl-border/80 pb-3.5 mb-4">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                  <Radio className="h-3 w-3 text-emerald-600" /> WebRTC Mesh Active
                </span>
                <span className="text-xs text-dl-muted hidden sm:inline">Canonical Source Pipeline</span>
              </div>
              <div className="flex items-center rounded-lg bg-dl-bg-alt p-0.5 border border-dl-border">
                <button
                  type="button"
                  onClick={() => setDemoMode("voice")}
                  className={`btn-tactile rounded-md px-2.5 py-1 text-xs font-semibold transition-all ${
                    demoMode === "voice"
                      ? "bg-white text-dl-navy shadow-xs"
                      : "text-dl-muted hover:text-dl-navy"
                  }`}
                >
                  Speech Flow
                </button>
                <button
                  type="button"
                  onClick={() => setDemoMode("text")}
                  className={`btn-tactile rounded-md px-2.5 py-1 text-xs font-semibold transition-all ${
                    demoMode === "text"
                      ? "bg-white text-dl-navy shadow-xs"
                      : "text-dl-muted hover:text-dl-navy"
                  }`}
                >
                  Dual-Pane
                </button>
              </div>
            </div>

            {demoMode === "voice" ? (
              <div className="space-y-3.5 text-xs">
                {/* Source Speaker with Audio Waveform */}
                <div className="rounded-xl border border-dl-border bg-dl-bg-alt p-3.5">
                  <div className="flex items-center justify-between text-dl-muted mb-2">
                    <span className="flex items-center gap-1.5 font-semibold text-dl-blue">
                      <Mic className="h-4 w-4" /> Live Speaker A (Hindi)
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px] text-emerald-600 font-medium">
                      <span className="flex gap-0.5 items-end h-3.5">
                        <span className="w-1 bg-emerald-500 rounded-full animate-wave-1" />
                        <span className="w-1 bg-emerald-500 rounded-full animate-wave-2" />
                        <span className="w-1 bg-emerald-500 rounded-full animate-wave-3" />
                        <span className="w-1 bg-emerald-500 rounded-full animate-wave-4" />
                      </span>
                      16kHz PCM Stream
                    </span>
                  </div>
                  <p className="text-sm font-medium text-dl-navy">
                    "नमस्ते, हमारी कंपनी नई ग्लोबल टीम मीटिंग शुरू कर रही है।"
                  </p>
                </div>

                {/* Direct fan-out indicator */}
                <div className="flex items-center justify-center gap-2 text-dl-muted py-0.5">
                  <div className="h-px bg-dl-border flex-1" />
                  <span className="text-[11px] font-semibold text-dl-blue flex items-center gap-1 bg-dl-blue-light/60 px-2 py-0.5 rounded-full border border-dl-blue-mid">
                    <Zap className="h-3 w-3 text-amber-500" /> Direct Neural Fan-Out
                  </span>
                  <div className="h-px bg-dl-border flex-1" />
                </div>

                {/* Target Listeners */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="rounded-xl border border-dl-border bg-white p-3.5 shadow-xs hover:border-dl-blue/30 transition-colors">
                    <div className="flex items-center justify-between text-dl-muted mb-1.5">
                      <span className="font-semibold text-slate-800 flex items-center gap-1">
                        <Volume2 className="h-3.5 w-3.5 text-dl-blue" /> Listener B (English)
                      </span>
                      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                        120ms
                      </span>
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed">
                      "Hello, our company is starting the new global team meeting."
                    </p>
                  </div>

                  <div className="rounded-xl border border-dl-border bg-white p-3.5 shadow-xs hover:border-dl-blue/30 transition-colors">
                    <div className="flex items-center justify-between text-dl-muted mb-1.5">
                      <span className="font-semibold text-slate-800 flex items-center gap-1">
                        <Volume2 className="h-3.5 w-3.5 text-dl-blue" /> Listener C (Spanish)
                      </span>
                      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                        145ms
                      </span>
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed">
                      "Hola, nuestra empresa está comenzando la nueva reunión de equipo global."
                    </p>
                  </div>
                </div>

                <div className="rounded-xl border border-dl-border bg-dl-bg-alt p-2.5 text-center text-xs text-slate-600">
                  Every attendee receives native synthetic audio playback in real time without translation daisy-chaining.
                </div>
              </div>
            ) : (
              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-dl-border bg-dl-bg-alt p-3">
                    <span className="text-[11px] font-semibold text-dl-muted block mb-1">Source: English</span>
                    <p className="text-xs text-dl-navy font-medium">
                      Our mission is to empower teams across continents to collaborate seamlessly.
                    </p>
                  </div>
                  <div className="rounded-xl border border-dl-border bg-white p-3 shadow-xs">
                    <span className="text-[11px] font-semibold text-dl-blue block mb-1">Target: German</span>
                    <p className="text-xs text-slate-800 leading-relaxed">
                      Unsere Mission ist es, Teams über Kontinente hinweg zu einer nahtlosen Zusammenarbeit zu befähigen.
                    </p>
                  </div>
                </div>
                <div className="flex items-center justify-between text-dl-muted pt-1">
                  <span>Contextual dictionary · Formality tier: Formal</span>
                  <Link to="/translate" className="text-xs font-semibold text-dl-blue hover:underline">
                    Open Dual-Pane Translator →
                  </Link>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* 5 CORE PILLARS BENTO GRID (Section 4.7 Rhythm & Exact Cell Count) */}
        <section className="border-t border-dl-border/80 py-16 lg:py-20">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <h2 className="text-3xl font-extrabold sm:text-4xl text-dl-navy tracking-tight">
              Five Core Capabilities in One Platform
            </h2>
            <p className="mt-3 text-slate-600 text-sm">
              Engineered with privacy-first self-hosted neural models, sub-second latency, and intuitive workspaces.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {/* Tile 1: Flagship Live Voice Translation (Col-span 2 on desktop) */}
            <Link
              to="/voice"
              className="group relative flex flex-col justify-between rounded-2xl border border-dl-border bg-gradient-to-br from-white to-dl-bg-alt p-7 shadow-xs hover:border-dl-blue/50 hover:shadow-card transition-all lg:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-dl-blue text-white shadow-xs group-hover:scale-105 transition-transform">
                    <Mic className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-dl-border bg-white px-3 py-1 text-xs font-semibold text-dl-blue shadow-xs">
                    Speech-to-Speech
                  </span>
                </div>

                <h3 className="text-xl font-bold text-dl-navy group-hover:text-dl-blue transition-colors">
                  Live Voice Translation Studio
                </h3>

                <p className="mt-2 text-sm leading-relaxed text-slate-600 max-w-xl">
                  Real-time face-to-face speech synthesis with natural audio release, soundwave pulsing visualizer, and bilingual live transcript feeds under 1,000 milliseconds.
                </p>

                <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-dl-border/60">
                  <div className="rounded-lg bg-white p-2.5 border border-dl-border/70 text-xs">
                    <span className="text-slate-500 block text-[11px]">Audio Protocol</span>
                    <strong className="text-dl-navy font-semibold">16kHz PCM Stream</strong>
                  </div>
                  <div className="rounded-lg bg-white p-2.5 border border-dl-border/70 text-xs">
                    <span className="text-slate-500 block text-[11px]">Voice Detection</span>
                    <strong className="text-dl-navy font-semibold">Silero Neural VAD</strong>
                  </div>
                  <div className="rounded-lg bg-white p-2.5 border border-dl-border/70 text-xs">
                    <span className="text-slate-500 block text-[11px]">Speech Output</span>
                    <strong className="text-dl-navy font-semibold">Piper Synthesizer</strong>
                  </div>
                </div>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-dl-blue group-hover:text-dl-blue-hover">
                Open Live Voice Studio <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 2: AI Translation Workspace (1 col) */}
            <Link
              to="/translate"
              className="group relative flex flex-col justify-between rounded-2xl border border-dl-border bg-white p-6 shadow-xs hover:border-dl-blue/40 hover:shadow-card transition-all"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-dl-blue-light text-dl-blue group-hover:bg-dl-blue group-hover:text-white transition-colors">
                    <Languages className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-dl-border bg-dl-bg-alt px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                    Dual-Pane AI
                  </span>
                </div>

                <h3 className="text-lg font-bold text-dl-navy group-hover:text-dl-blue transition-colors">
                  AI Translation Workspace
                </h3>

                <p className="mt-2 text-xs leading-relaxed text-slate-600">
                  Instant translation with contextual dictionary, synonyms lookup, formality control, and native speech listen playback.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-dl-blue group-hover:text-dl-blue-hover">
                Open Workspace <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 3: AI Writing Companion (1 col) */}
            <Link
              to="/write"
              className="group relative flex flex-col justify-between rounded-2xl border border-dl-border bg-white p-6 shadow-xs hover:border-dl-blue/40 hover:shadow-card transition-all"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-dl-blue-light text-dl-blue group-hover:bg-dl-blue group-hover:text-white transition-colors">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-dl-border bg-dl-bg-alt px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                    Writing Companion
                  </span>
                </div>

                <h3 className="text-lg font-bold text-dl-navy group-hover:text-dl-blue transition-colors">
                  AI Writing Companion
                </h3>

                <p className="mt-2 text-xs leading-relaxed text-slate-600">
                  Rewriting and grammar correction across 5 styles (Business, Academic, Casual, Simple, Creative) and 5 tones with side-by-side diff highlighting.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-dl-blue group-hover:text-dl-blue-hover">
                Open Writing Tool <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 4: Multilingual Meetings (1 col) */}
            <Link
              to="/meetings"
              className="group relative flex flex-col justify-between rounded-2xl border border-dl-border bg-white p-6 shadow-xs hover:border-dl-blue/40 hover:shadow-card transition-all"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-dl-blue-light text-dl-blue group-hover:bg-dl-blue group-hover:text-white transition-colors">
                    <Video className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-dl-border bg-dl-bg-alt px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                    WebRTC Video
                  </span>
                </div>

                <h3 className="text-lg font-bold text-dl-navy group-hover:text-dl-blue transition-colors">
                  Video Conferences
                </h3>

                <p className="mt-2 text-xs leading-relaxed text-slate-600">
                  Side-by-side video tiles, crystal-clear audio, camera controls, screen sharing, instant invite links, and live translated captions for every attendee.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-dl-blue group-hover:text-dl-blue-hover">
                Open Meetings <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 5: Document Translation & Enterprise Governance (Col-span 2 on desktop) */}
            <Link
              to="/documents"
              className="group relative flex flex-col justify-between rounded-2xl border border-dl-border bg-gradient-to-br from-white to-dl-bg-alt p-7 shadow-xs hover:border-dl-blue/50 hover:shadow-card transition-all lg:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-xs group-hover:scale-105 transition-transform">
                    <FileText className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                    Layout Preserved
                  </span>
                </div>

                <h3 className="text-xl font-bold text-dl-navy group-hover:text-dl-blue transition-colors">
                  Document Translation & Enterprise Privacy
                </h3>

                <p className="mt-2 text-sm leading-relaxed text-slate-600 max-w-xl">
                  Translate PDFs, DOCX, PPTX, XLSX, and TXT while preserving exact styling, formatting, and tables. Zero telemetry, on-premises deployment, and full GDPR compliance.
                </p>

                <div className="mt-5 flex flex-wrap gap-2 pt-3 border-t border-dl-border/60">
                  {["PDF", "DOCX", "PPTX", "XLSX", "HTML", "TXT"].map((ext) => (
                    <span
                      key={ext}
                      className="rounded-md bg-white border border-dl-border px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-xs"
                    >
                      {ext}
                    </span>
                  ))}
                  <span className="rounded-md bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-xs font-semibold text-emerald-800 flex items-center gap-1">
                    <Shield className="h-3.5 w-3.5" /> 100% On-Premises Safe
                  </span>
                </div>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-dl-blue group-hover:text-dl-blue-hover">
                Translate Documents <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          </div>
        </section>

        {/* FREQUENTLY ASKED QUESTIONS */}
        <section className="border-t border-dl-border/80 py-16 lg:py-20" aria-labelledby="faq-heading">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <h2 id="faq-heading" className="text-3xl font-extrabold sm:text-4xl text-dl-navy tracking-tight">
              Frequently Asked Questions
            </h2>
            <p className="mt-3 text-slate-600 text-sm">
              In-depth details on latency, privacy standards, supported document types, and translation architecture.
            </p>
          </div>

          <div className="max-w-3xl mx-auto space-y-3.5">
            {FAQS.map((faq) => (
              <details
                key={faq.q}
                className="group rounded-xl border border-dl-border bg-white p-5 shadow-xs transition-all open:border-dl-blue/40 open:shadow-card"
              >
                <summary className="flex cursor-pointer items-center justify-between text-base font-semibold text-dl-navy group-hover:text-dl-blue">
                  <span>{faq.q}</span>
                  <ChevronDown className="h-5 w-5 text-dl-muted transition-transform duration-200 group-open:rotate-180 group-open:text-dl-blue flex-shrink-0 ml-4" />
                </summary>
                <p className="mt-3 text-sm leading-relaxed text-slate-600 border-t border-dl-border pt-3">
                  {faq.a}
                </p>
              </details>
            ))}
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-dl-border bg-dl-bg-alt py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 pb-8 border-b border-dl-border">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Logo className="h-6 w-6 text-dl-blue" />
                <span className="font-bold text-dl-navy">GlobalTalk AI</span>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">
                Real-time multilingual voice and text translation platform with sub-second latency and zero data retention.
              </p>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-dl-muted mb-3">Workspaces</h4>
              <ul className="space-y-2 text-xs">
                <li><Link to="/translate" className="text-slate-600 hover:text-dl-navy">Dual-Pane Translator</Link></li>
                <li><Link to="/write" className="text-slate-600 hover:text-dl-navy">Writing Companion</Link></li>
                <li><Link to="/voice" className="text-slate-600 hover:text-dl-navy">Live Voice Translation</Link></li>
                <li><Link to="/meetings" className="text-slate-600 hover:text-dl-navy">Multilingual Meetings</Link></li>
                <li><Link to="/documents" className="text-slate-600 hover:text-dl-navy">Document Translation</Link></li>
              </ul>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-dl-muted mb-3">Developer & API</h4>
              <ul className="space-y-2 text-xs">
                <li><Link to="/docs" className="text-slate-600 hover:text-dl-navy">SDKs & Guides</Link></li>
                <li><Link to="/api/docs" className="text-slate-600 hover:text-dl-navy">REST & WebSocket API</Link></li>
                <li>
                  <a
                    href="https://github.com/Aman678317/Anv-AI"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-slate-600 hover:text-dl-navy"
                  >
                    GitHub Repository <ExternalLink className="h-3 w-3" />
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-dl-muted mb-3">Governance</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Self-hosted on-premises</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Ephemeral audio streams</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> GDPR compliant</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Canonical Source Principle</li>
              </ul>
            </div>
          </div>

          <div className="pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
            <div>
              © {new Date().getFullYear()} GlobalTalk AI. One conversation · every language.
            </div>
            <div>
              Built with modern WebRTC, Whisper, Piper TTS, Argos, and OpenAI models.
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
