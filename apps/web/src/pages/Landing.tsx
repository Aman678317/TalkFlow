import { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronDown,
  FileText,
  GitBranch,
  Languages,
  Mic,
  RefreshCw,
  Shield,
  Sparkles,
  Video,
  Volume2,
  Workflow,
  Zap,
  Menu,
  X,
  Radio,
  ExternalLink,
} from "lucide-react";
import { Logo } from "../components/Layout";
import { Reveal } from "../components/Motion";
import { staggerContainerVariants, staggerItemVariants, springSoft } from "../lib/motion";
import { useAuth } from "../stores/auth";
import { api } from "../lib/api";

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
  const reducedMotion = useReducedMotion();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [contactForm, setContactForm] = useState({ name: "", email: "", subject: "General Inquiry", message: "" });
  const [contactStatus, setContactStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [contactError, setContactError] = useState("");

  const handleSubmitContact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contactForm.name || !contactForm.email || !contactForm.message) {
      setContactError("Please fill out all required fields.");
      return;
    }
    setContactStatus("submitting");
    setContactError("");
    try {
      await api("/api/v1/feedback/inquiry", {
        method: "POST",
        body: contactForm,
      });
      setContactStatus("success");
      setContactForm({ name: "", email: "", subject: "General Inquiry", message: "" });
    } catch (err: any) {
      setContactStatus("error");
      setContactError(err.message || "Failed to deliver inquiry. Please reach out to support@globaltalk.ai directly.");
    }
  };

  const [demoMode, setDemoMode] = useState<"voice" | "text">("voice");

  return (
    <div className="min-h-full bg-white text-neutral-950 selection:bg-[#007AFF]/20 selection:text-neutral-950">
      {/* HEADER NAVBAR — frosted Liquid Glass material (Apple HIG) */}
      <header className="material-bar sticky top-0 z-50 backdrop-blur-2xl bg-white/80 border-b border-black/[0.06]">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
          <Link to="/" className="group flex shrink-0 items-center gap-2.5">
            <Logo className="h-7 w-7 sm:h-8 sm:w-8" />
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold tracking-[-0.02em] text-neutral-950 sm:text-lg">
                GlobalTalk <span className="text-[#007AFF]">AI</span>
              </span>
              <span className="hidden rounded-full border border-black/[0.06] bg-black/[0.03] px-2.5 py-0.5 text-[11px] font-medium text-neutral-600 2xl:inline-block">
                Enterprise Suite
              </span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav aria-label="Main navigation" className="hidden items-center gap-1 text-sm font-medium xl:flex">
            <Link
              to="/translate"
              className="inline-flex min-h-[44px] items-center rounded-full px-4 text-neutral-700 transition-colors hover:bg-black/[0.04] hover:text-neutral-950"
            >
              Translate
            </Link>
            <Link
              to="/write"
              className="inline-flex min-h-[44px] items-center rounded-full px-4 text-neutral-700 transition-colors hover:bg-black/[0.04] hover:text-neutral-950"
            >
              Write
            </Link>
            <Link
              to="/voice"
              className="inline-flex min-h-[44px] items-center rounded-full px-4 text-neutral-700 transition-colors hover:bg-black/[0.04] hover:text-neutral-950"
            >
              Live Voice
            </Link>
            <Link
              to="/meetings"
              className="inline-flex min-h-[44px] items-center rounded-full px-4 text-neutral-700 transition-colors hover:bg-black/[0.04] hover:text-neutral-950"
            >
              Meetings
            </Link>
            <Link
              to="/agents"
              className="inline-flex min-h-[44px] items-center rounded-full px-4 font-semibold text-[#5856D6] transition-colors hover:bg-[#5856D6]/10"
            >
              <Bot className="mr-1.5 h-4 w-4 text-[#5856D6]" />
              Agent Studio
            </Link>
            <button
              type="button"
              onClick={() => setContactOpen(true)}
              className="inline-flex min-h-[44px] items-center rounded-full px-4 text-neutral-700 transition-colors hover:bg-black/[0.04] hover:text-neutral-950 font-medium"
            >
              Contact
            </button>

            <div className="ml-3 flex items-center gap-2 border-l border-black/[0.06] pl-4">
              {user ? (
                <Link
                  to="/dashboard"
                  className="apple-btn-primary"
                >
                  Go to Dashboard <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="inline-flex min-h-[44px] items-center rounded-full px-4 font-medium text-neutral-700 transition-colors hover:text-neutral-950 hover:bg-black/[0.04]"
                  >
                    Sign in
                  </Link>
                  <Link
                    to="/translate"
                    className="apple-btn-primary"
                  >
                    Start Free
                  </Link>
                </>
              )}
            </div>
          </nav>

          {/* Mobile Menu Button */}
          <div className="flex items-center gap-1.5 xl:hidden">
            {user ? (
              <Link
                to="/dashboard"
                className="apple-btn-primary min-h-[38px] px-3.5 text-xs"
              >
                Dashboard
              </Link>
            ) : (
              <Link
                to="/translate"
                className="apple-btn-primary min-h-[38px] px-3.5 text-xs"
              >
                Start Free
              </Link>
            )}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full text-neutral-700 hover:bg-black/[0.05] hover:text-neutral-950 focus-visible:ring-2 focus-visible:ring-[#007AFF]"
              aria-label="Toggle navigation menu"
              aria-expanded={mobileMenuOpen}
              aria-controls="landing-navigation"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        <AnimatePresence initial={false}>
          {mobileMenuOpen && (
            <motion.div
              id="landing-navigation"
              initial={reducedMotion ? false : { opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reducedMotion ? undefined : { opacity: 0, y: -4 }}
              transition={{ duration: reducedMotion ? 0 : 0.16 }}
              className="absolute inset-x-0 top-full max-h-[calc(100dvh-5rem)] overflow-y-auto border-b border-t border-black/[0.06] bg-white shadow-xl xl:hidden"
            >
              <div className="px-6 py-4 space-y-2">
                <Link
                  to="/translate"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block rounded-2xl px-4 py-3 text-base font-medium text-neutral-800 hover:bg-black/[0.04]"
                >
                  Translate
                </Link>
                <Link
                  to="/write"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block rounded-2xl px-4 py-3 text-base font-medium text-neutral-800 hover:bg-black/[0.04]"
                >
                  Write
                </Link>
                <Link
                  to="/voice"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block rounded-2xl px-4 py-3 text-base font-medium text-neutral-800 hover:bg-black/[0.04]"
                >
                  Live Voice
                </Link>
                <Link
                  to="/meetings"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block rounded-2xl px-4 py-3 text-base font-medium text-neutral-800 hover:bg-black/[0.04]"
                >
                  Meetings
                </Link>
                <Link
                  to="/agents"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center gap-2 rounded-2xl px-4 py-3 text-base font-semibold text-[#5856D6] hover:bg-[#5856D6]/10"
                >
                  <Bot className="h-4 w-4 text-[#5856D6]" />
                  Agent Studio
                </Link>
                <div className="flex flex-col gap-2.5 border-t border-black/[0.06] pt-4">
                  {!user && (
                    <Link
                      to="/login"
                      onClick={() => setMobileMenuOpen(false)}
                      className="apple-btn-tinted w-full"
                    >
                      Sign in
                    </Link>
                  )}
                  <Link
                    to={user ? "/dashboard" : "/translate"}
                    onClick={() => setMobileMenuOpen(false)}
                    className="apple-btn-primary w-full"
                  >
                    {user ? "Go to Dashboard" : "Start Free"}
                  </Link>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {/* HERO SECTION */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6">
        <section className="grid gap-12 py-14 lg:grid-cols-2 lg:items-center lg:gap-12 lg:py-24">
          <motion.div variants={staggerContainerVariants} initial={reducedMotion ? false : "hidden"} animate="visible" className="min-w-0">
            {/* Hero Eyebrows */}
            <motion.div variants={staggerItemVariants} className="mb-4 flex flex-wrap items-center gap-2.5">
              <div className="apple-pill-badge">
                <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#007AFF]" />
                Sub-second voice and text translation pipeline
              </div>
              <Link
                to="/agents"
                className="inline-flex items-center gap-1.5 rounded-full border border-[#5856D6]/20 bg-[#5856D6]/[0.06] px-3 py-1 text-xs font-semibold text-[#5856D6] hover:bg-[#5856D6]/[0.12] transition-colors"
              >
                <Bot className="h-3.5 w-3.5 shrink-0 text-[#5856D6]" />
                <span>New: Multi-Agent Studio (LangGraph + CrewAI)</span>
                <ArrowRight className="h-3 w-3 ml-0.5" />
              </Link>
            </motion.div>

            <motion.h1 variants={staggerItemVariants} className="max-w-3xl text-4xl font-semibold leading-[1.06] tracking-[-0.035em] text-neutral-950 sm:text-6xl lg:text-5xl xl:text-6xl">
              One conversation.{" "}
              <span className="block text-[#007AFF]">
                Every language.
              </span>
            </motion.h1>

            {/* Strict Subtext Discipline: Exactly 18 words (<= 20 words constraint) */}
            <motion.p variants={staggerItemVariants} className="mt-5 max-w-xl text-base leading-relaxed text-neutral-600 sm:text-lg">
              Translate speech, text, documents, and video meetings in real time with sub-second latency and zero data retention.
            </motion.p>

            <motion.div variants={staggerItemVariants} className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                to="/dashboard"
                className="apple-btn-primary min-h-[48px] px-6 text-[15px]"
              >
                Launch Workspace <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                to="/agents"
                className="apple-btn-tinted min-h-[48px] px-5 text-[15px]"
              >
                <Bot className="h-4 w-4 text-[#5856D6]" />
                Multi-Agent Studio
              </Link>
              <Link
                to="/translate"
                className="inline-flex min-h-[48px] items-center rounded-full px-4 text-sm font-medium text-neutral-600 hover:text-neutral-950 hover:underline"
              >
                Try Translator
              </Link>
            </motion.div>

            <motion.div variants={staggerItemVariants} className="mt-10 border-t border-black/[0.06] pt-5">
              <p className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Supported Across 100+ Languages
              </p>
              <div className="flex flex-wrap gap-2">
                {LANGS.map((l) => (
                  <span
                    key={l}
                    className="rounded-full border border-black/[0.04] bg-black/[0.03] px-3 py-1 text-xs font-medium text-neutral-700"
                  >
                    {l}
                  </span>
                ))}
              </div>
            </motion.div>
          </motion.div>

          {/* INTERACTIVE WORKSPACE PREVIEW WIDGET */}
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 12, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={reducedMotion ? { duration: 0 } : { ...springSoft, delay: 0.12 }}
            className="min-w-0 apple-widget p-5 sm:p-7 shadow-[0_8px_32px_-4px_rgba(0,0,0,0.06)]"
          >
            {/* Widget Header & Mode Switcher */}
            <div className="mb-5 flex flex-wrap items-center justify-between gap-4 border-b border-black/[0.06] pb-5">
              <div className="flex flex-col items-start gap-1.5">
                <span className="flex items-center gap-1.5 rounded-full border border-[#34C759]/25 bg-[#34C759]/10 px-2.5 py-0.5 text-xs font-semibold text-[#248A3D]">
                  <Radio className="h-3 w-3 text-[#34C759]" /> WebRTC Mesh Active
                </span>
                <span className="text-xs text-neutral-500">Canonical Source Pipeline</span>
              </div>
              <div className="inline-flex rounded-full bg-black/[0.05] p-1">
                <button
                  type="button"
                  onClick={() => setDemoMode("voice")}
                  aria-pressed={demoMode === "voice"}
                  className={`min-h-[32px] rounded-full px-3.5 py-1 text-xs font-semibold transition-all ${
                    demoMode === "voice"
                      ? "bg-white text-neutral-950 shadow-xs"
                      : "text-neutral-500 hover:text-neutral-950"
                  }`}
                >
                  Speech Flow
                </button>
                <button
                  type="button"
                  onClick={() => setDemoMode("text")}
                  aria-pressed={demoMode === "text"}
                  className={`min-h-[32px] rounded-full px-3.5 py-1 text-xs font-semibold transition-all ${
                    demoMode === "text"
                      ? "bg-white text-neutral-950 shadow-xs"
                      : "text-neutral-500 hover:text-neutral-950"
                  }`}
                >
                  Dual-Pane
                </button>
              </div>
            </div>

            {demoMode === "voice" ? (
              <div className="space-y-3.5 text-xs">
                {/* Source Speaker with Audio Waveform */}
                <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-4">
                  <div className="mb-2.5 flex flex-wrap items-center justify-between gap-3 text-neutral-600">
                    <span className="flex items-center gap-1.5 font-semibold text-[#007AFF]">
                      <Mic className="h-4 w-4" /> Live Speaker A (Hindi)
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px] font-medium text-neutral-600">
                      <span aria-hidden="true" className="flex h-3.5 items-end gap-0.5">
                        <span className="h-3.5 w-1 rounded-full bg-[#007AFF] animate-wave-1" />
                        <span className="h-3.5 w-1 rounded-full bg-[#007AFF] animate-wave-2" />
                        <span className="h-3.5 w-1 rounded-full bg-[#007AFF] animate-wave-3" />
                        <span className="h-3.5 w-1 rounded-full bg-[#007AFF] animate-wave-4" />
                      </span>
                      16kHz PCM Stream
                    </span>
                  </div>
                  <p className="text-sm font-medium text-neutral-950">
                    "नमस्ते, हमारी कंपनी नई ग्लोबल टीम मीटिंग शुरू कर रही है।"
                  </p>
                </div>

                {/* Direct fan-out indicator */}
                <div className="flex items-center justify-center gap-2 py-0.5 text-neutral-400">
                  <div className="h-px flex-1 bg-black/[0.06]" />
                  <span className="flex items-center gap-1 rounded-full border border-black/[0.06] bg-black/[0.03] px-2.5 py-0.5 text-[11px] font-semibold text-neutral-700">
                    <Zap className="h-3 w-3 text-[#FF9500]" /> Direct Neural Fan-Out
                  </span>
                  <div className="h-px flex-1 bg-black/[0.06]" />
                </div>

                {/* Target Listeners */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-black/[0.06] bg-white p-3.5 shadow-xs transition-shadow hover:shadow-sm">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-neutral-600">
                      <span className="flex items-center gap-1 font-semibold text-neutral-800">
                        <Volume2 className="h-3.5 w-3.5 text-[#007AFF]" /> Listener B (English)
                      </span>
                      <span className="rounded-full bg-[#007AFF]/10 px-2 py-0.5 text-[10px] font-semibold text-[#007AFF]">
                        120ms
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-neutral-700">
                      "Hello, our company is starting the new global team meeting."
                    </p>
                  </div>

                  <div className="rounded-2xl border border-black/[0.06] bg-white p-3.5 shadow-xs transition-shadow hover:shadow-sm">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-neutral-600">
                      <span className="flex items-center gap-1 font-semibold text-neutral-800">
                        <Volume2 className="h-3.5 w-3.5 text-[#007AFF]" /> Listener C (Spanish)
                      </span>
                      <span className="rounded-full bg-[#007AFF]/10 px-2 py-0.5 text-[10px] font-semibold text-[#007AFF]">
                        145ms
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-neutral-700">
                      "Hola, nuestra empresa está comenzando la nueva reunión de equipo global."
                    </p>
                  </div>
                </div>

                <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-3 text-center text-xs text-neutral-600">
                  Every attendee receives native synthetic audio playback in real time without translation daisy-chaining.
                </div>
              </div>
            ) : (
              <div className="space-y-3.5 text-xs">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-black/[0.06] bg-neutral-50/80 p-3.5">
                    <span className="mb-1 block text-[11px] font-semibold text-neutral-500">Source: English</span>
                    <p className="text-xs font-medium text-neutral-950">
                      Our mission is to empower teams across continents to collaborate seamlessly.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-black/[0.06] bg-white p-3.5 shadow-xs">
                    <span className="mb-1 block text-[11px] font-semibold text-[#007AFF]">Target: German</span>
                    <p className="text-xs leading-relaxed text-neutral-800">
                      Unsere Mission ist es, Teams über Kontinente hinweg zu einer nahtlosen Zusammenarbeit zu befähigen.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-neutral-600">
                  <span>Contextual dictionary · Formality tier: Formal</span>
                  <Link to="/translate" className="text-xs font-semibold text-[#007AFF] hover:underline">
                    Open Dual-Pane Translator →
                  </Link>
                </div>
              </div>
            )}
          </motion.div>
        </section>

        {/* 5 CORE PILLARS BENTO GRID (Apple Bento Style) */}
        <section className="border-t border-black/[0.06] py-16 lg:py-24">
          <Reveal className="mb-10 max-w-2xl">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">01 / Your workspaces</p>
            <h2 className="text-3xl font-semibold tracking-[-0.025em] text-neutral-950 sm:text-4xl">
              Five Core Capabilities in One Platform
            </h2>
            <p className="mt-3 text-sm text-neutral-600">
              Engineered with privacy-first self-hosted neural models, sub-second latency, and intuitive workspaces.
            </p>
          </Reveal>

          <Reveal className="grid gap-5 md:grid-cols-2 lg:grid-cols-6">
            {/* Tile 1: Flagship Live Voice Translation (Apple Canonical Dark Finish) */}
            <Link
              to="/voice"
              className="group relative flex min-w-0 flex-col justify-between rounded-3xl border border-neutral-800 bg-neutral-950 p-7 text-white shadow-xl transition-all hover:border-neutral-700 lg:col-span-3 lg:p-8"
            >
              <div>
                <div className="flex items-center justify-between mb-5">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-white">
                    <Mic className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-white/20 bg-white/5 px-3 py-1 text-xs font-medium text-neutral-300">
                    Speech-to-Speech
                  </span>
                </div>

                <h3 className="text-2xl font-semibold text-white">
                  Live Voice Translation Studio
                </h3>

                <p className="mt-3 max-w-xl text-sm leading-relaxed text-neutral-300">
                  Real-time face-to-face speech synthesis with natural audio release, soundwave pulsing visualizer, and bilingual live transcript feeds under 1,000 milliseconds.
                </p>

                <div className="mt-6 grid grid-cols-1 gap-3 border-t border-white/10 pt-5 sm:grid-cols-3">
                  <div className="text-xs">
                    <span className="mb-1 block text-[11px] text-neutral-400">Audio Protocol</span>
                    <strong className="font-medium text-white">16kHz PCM Stream</strong>
                  </div>
                  <div className="text-xs">
                    <span className="mb-1 block text-[11px] text-neutral-400">Voice Detection</span>
                    <strong className="font-medium text-white">Silero Neural VAD</strong>
                  </div>
                  <div className="text-xs">
                    <span className="mb-1 block text-[11px] text-neutral-400">Speech Output</span>
                    <strong className="font-medium text-white">Piper Synthesizer</strong>
                  </div>
                </div>
              </div>

              <div className="mt-8 flex items-center text-sm font-medium text-[#007AFF] group-hover:text-[#409CFF] transition-colors">
                Open Live Voice Studio <ArrowRight className="h-4 w-4 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 2: AI Translation Workspace (White Apple Card) */}
            <Link
              to="/translate"
              className="group relative flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-7 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] transition-all hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.08)] lg:col-span-3 lg:p-8"
            >
              <div>
                <div className="flex items-center justify-between mb-5">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#007AFF]/10 text-[#007AFF] transition-colors group-hover:bg-[#007AFF] group-hover:text-white">
                    <Languages className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-black/[0.06] bg-black/[0.03] px-3 py-1 text-xs font-semibold text-neutral-700">
                    Dual-Pane AI
                  </span>
                </div>

                <h3 className="text-2xl font-semibold text-neutral-950 group-hover:text-[#007AFF] transition-colors">
                  AI Translation Workspace
                </h3>

                <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-600">
                  Instant translation with contextual dictionary, synonyms lookup, formality control, and native speech listen playback.
                </p>
              </div>

              <div className="mt-8 flex items-center text-sm font-medium text-[#007AFF]">
                Open Workspace <ArrowRight className="h-4 w-4 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 3: AI Writing Companion */}
            <Link
              to="/write"
              className="group relative flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-6 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] transition-all hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.08)] lg:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#5856D6]/10 text-[#5856D6] transition-colors group-hover:bg-[#5856D6] group-hover:text-white">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-black/[0.06] bg-black/[0.03] px-2.5 py-0.5 text-[11px] font-semibold text-neutral-700">
                    Writing Companion
                  </span>
                </div>

                <h3 className="text-lg font-semibold text-neutral-950 transition-colors group-hover:text-[#5856D6]">
                  AI Writing Companion
                </h3>

                <p className="mt-3 text-sm leading-relaxed text-neutral-600">
                  Rewriting and grammar correction across 5 styles (Business, Academic, Casual, Simple, Creative) and 5 tones with side-by-side diff highlighting.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-[#5856D6]">
                Open Writing Tool <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 4: Multilingual Meetings */}
            <Link
              to="/meetings"
              className="group relative flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-6 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] transition-all hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.08)] lg:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#34C759]/10 text-[#34C759] transition-colors group-hover:bg-[#34C759] group-hover:text-white">
                    <Video className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-black/[0.06] bg-black/[0.03] px-2.5 py-0.5 text-[11px] font-semibold text-neutral-700">
                    WebRTC Video
                  </span>
                </div>

                <h3 className="text-lg font-semibold text-neutral-950 transition-colors group-hover:text-[#34C759]">
                  Video Conferences
                </h3>

                <p className="mt-3 text-sm leading-relaxed text-neutral-600">
                  Side-by-side video tiles, crystal-clear audio, camera controls, screen sharing, instant invite links, and live translated captions for every attendee.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-[#34C759]">
                Open Meetings <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 5: Document Translation & Enterprise Governance */}
            <Link
              to="/documents"
              className="group relative flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-6 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] transition-all hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.08)] md:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#FF9500]/10 text-[#FF9500]">
                    <FileText className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-[#FF9500]/25 bg-[#FF9500]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#A05D00]">
                    Layout Preserved
                  </span>
                </div>

                <h3 className="text-lg font-semibold text-neutral-950 transition-colors group-hover:text-[#FF9500]">
                  Document Translation & Privacy
                </h3>

                <p className="mt-2.5 text-sm leading-relaxed text-neutral-600">
                  Translate PDFs, DOCX, PPTX, XLSX, and TXT while preserving exact styling, formatting, and tables. Zero telemetry and full GDPR compliance.
                </p>

                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-black/[0.06] pt-3">
                  {["PDF", "DOCX", "PPTX", "XLSX", "HTML", "TXT"].map((ext) => (
                    <span
                      key={ext}
                      className="rounded-full border border-black/[0.06] bg-black/[0.03] px-2.5 py-0.5 text-[11px] font-semibold text-neutral-700"
                    >
                      {ext}
                    </span>
                  ))}
                  <span className="flex items-center gap-1 rounded-full border border-[#34C759]/25 bg-[#34C759]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#248A3D]">
                    <Shield className="h-3 w-3" /> 100% On-Premises
                  </span>
                </div>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-[#FF9500]">
                Translate Documents <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          </Reveal>
        </section>

        {/* MULTI-AGENT SYSTEMS STUDIO SHOWCASE */}
        <section className="border-t border-black/[0.06] py-16 lg:py-24" aria-labelledby="multi-agent-heading">
          <Reveal className="mb-10 max-w-3xl">
            <div className="mb-2.5 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#5856D6]">
              <Bot className="h-3.5 w-3.5" />
              Autonomous Agent Orchestration
            </div>
            <h2 id="multi-agent-heading" className="text-3xl font-semibold tracking-[-0.025em] text-neutral-950 sm:text-4xl">
              Production Multi-Agent Systems in Action
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-neutral-600">
              Explore 3 production agent architectures powered by LangGraph state machines and CrewAI role-playing personas. Interactive, live, and inspectable in real time.
            </p>
          </Reveal>

          <Reveal className="mb-8 grid gap-5 lg:grid-cols-3">
            {/* Card 1: Customer Support Triage Graph */}
            <div className="group flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-7 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)]">
              <div>
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#007AFF]/10 text-[#007AFF] transition-colors group-hover:bg-[#007AFF] group-hover:text-white">
                    <GitBranch className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-[#007AFF]/25 bg-[#007AFF]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#007AFF]">
                    LangGraph State Machine
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-neutral-950 transition-colors group-hover:text-[#007AFF]">
                  Customer Support Triage Graph
                </h3>
                <p className="mt-2.5 text-sm leading-relaxed text-neutral-600">
                  Classifies customer tickets, extracts priority, routes to specialist subgraphs (Billing, Technical, General), and detects escalation triggers.
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-black/[0.06] pt-3">
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Conditional Edges</span>
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Human Escalation</span>
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Typed Dict State</span>
                </div>
              </div>
              <Link
                to="/agents"
                className="mt-6 inline-flex items-center text-xs font-semibold text-[#007AFF] hover:underline"
              >
                Try Triage Graph <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>

            {/* Card 2: Autonomous Content Pipeline */}
            <div className="group flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-7 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)]">
              <div>
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#5856D6]/10 text-[#5856D6] transition-colors group-hover:bg-[#5856D6] group-hover:text-white">
                    <RefreshCw className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-[#5856D6]/25 bg-[#5856D6]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#5856D6]">
                    Self-Correcting Loop
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-neutral-950 transition-colors group-hover:text-[#5856D6]">
                  Autonomous Content Pipeline
                </h3>
                <p className="mt-2.5 text-sm leading-relaxed text-neutral-600">
                  Researches, drafts, and audits content in an automated feedback loop. Iterates up to 3 cycles until quality score reaches 0.80+.
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-black/[0.06] pt-3">
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">LangGraph + CrewAI</span>
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Quality Rubric</span>
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Infinite-Loop Guards</span>
                </div>
              </div>
              <Link
                to="/agents"
                className="mt-6 inline-flex items-center text-xs font-semibold text-[#5856D6] hover:underline"
              >
                Launch Pipeline <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>

            {/* Card 3: Research Assistant Crew */}
            <div className="group flex min-w-0 flex-col justify-between rounded-3xl border border-black/[0.06] bg-white p-7 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)]">
              <div>
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#30B0C7]/10 text-[#30B0C7] transition-colors group-hover:bg-[#30B0C7] group-hover:text-white">
                    <Workflow className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-[#30B0C7]/25 bg-[#30B0C7]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#0B8599]">
                    CrewAI 4-Agent Crew
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-neutral-950 transition-colors group-hover:text-[#30B0C7]">
                  Research Assistant Crew
                </h3>
                <p className="mt-2.5 text-sm leading-relaxed text-neutral-600">
                  Hub & Spoke architecture with 4 specialized roles: Information Gatherer, Synthesizer, Report Writer, and Fact-Checker.
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-black/[0.06] pt-3">
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Role & Goal Prompts</span>
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Executive Briefings</span>
                  <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[10px] font-medium text-neutral-600">Fact Verification</span>
                </div>
              </div>
              <Link
                to="/agents"
                className="mt-6 inline-flex items-center text-xs font-semibold text-[#30B0C7] hover:underline"
              >
                Deploy Crew <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </Reveal>

          <Reveal className="flex flex-col items-start justify-between gap-5 rounded-3xl border border-[#007AFF]/20 bg-[#007AFF]/[0.05] p-6 lg:flex-row lg:items-center lg:p-8">
            <div>
              <h4 className="text-base font-semibold text-neutral-950">
                Interactive Multi-Agent Studio with Real-time Visualizer
              </h4>
              <p className="mt-1 text-xs text-neutral-600">
                Test prompts, trace state transitions, examine agent personas, and run live multi-agent pipelines with zero setup.
              </p>
            </div>
            <Link
              to="/agents"
              className="apple-btn-blue shrink-0"
            >
              Open Agent Studio <ArrowRight className="h-4 w-4" />
            </Link>
          </Reveal>
        </section>

        {/* FREQUENTLY ASKED QUESTIONS — iOS Grouped Disclosure List */}
        <section className="border-t border-black/[0.06] py-16 lg:py-24" aria-labelledby="faq-heading">
          <Reveal className="mx-auto mb-12 max-w-2xl text-center">
            <h2 id="faq-heading" className="text-3xl font-semibold tracking-[-0.025em] text-neutral-950 sm:text-4xl">
              Frequently Asked Questions
            </h2>
            <p className="mt-3 text-sm text-neutral-600">
              In-depth details on latency, privacy standards, supported document types, and translation architecture.
            </p>
          </Reveal>

          <Reveal className="mx-auto max-w-3xl overflow-hidden rounded-3xl border border-black/[0.06] bg-white divide-y divide-black/[0.06] shadow-sm">
            {FAQS.map((faq) => (
              <details
                key={faq.q}
                className="group p-5 sm:p-6 transition-colors hover:bg-black/[0.015]"
              >
                <summary className="flex cursor-pointer items-center justify-between text-base font-medium text-neutral-950 list-none">
                  <span>{faq.q}</span>
                  <ChevronDown aria-hidden="true" className="ml-4 h-5 w-5 flex-shrink-0 text-neutral-400 transition-transform duration-200 group-open:rotate-180 group-open:text-[#007AFF] motion-reduce:transition-none" />
                </summary>
                <p className="mt-3 pt-3 text-sm leading-relaxed text-neutral-600 border-t border-black/[0.04]">
                  {faq.a}
                </p>
              </details>
            ))}
          </Reveal>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-black/[0.06] bg-neutral-50/80 py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 gap-8 border-b border-black/[0.06] pb-8 md:grid-cols-4">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Logo className="h-6 w-6 text-[#007AFF]" />
                <span className="font-semibold text-neutral-950">GlobalTalk AI</span>
              </div>
              <p className="text-xs leading-relaxed text-neutral-500">
                Real-time multilingual voice and text translation platform with sub-second latency and zero data retention.
              </p>
            </div>

            <div>
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-neutral-500">Workspaces</h4>
              <ul className="space-y-2 text-xs">
                <li><Link to="/translate" className="text-neutral-600 hover:text-neutral-950">Dual-Pane Translator</Link></li>
                <li><Link to="/write" className="text-neutral-600 hover:text-neutral-950">Writing Companion</Link></li>
                <li><Link to="/voice" className="text-neutral-600 hover:text-neutral-950">Live Voice Translation</Link></li>
                <li><Link to="/meetings" className="text-neutral-600 hover:text-neutral-950">Multilingual Meetings</Link></li>
                <li><Link to="/documents" className="text-neutral-600 hover:text-neutral-950">Document Translation</Link></li>
                <li><Link to="/agents" className="font-semibold text-[#5856D6] hover:underline">Multi-Agent Studio</Link></li>
              </ul>
            </div>

            <div>
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-neutral-500">Developer & API</h4>
              <ul className="space-y-2 text-xs">
                <li><Link to="/docs" className="text-neutral-600 hover:text-neutral-950">SDKs & Guides</Link></li>
                <li><Link to="/api/docs" className="text-neutral-600 hover:text-neutral-950">REST & WebSocket API</Link></li>
                <li>
                  <button
                    type="button"
                    onClick={() => setContactOpen(true)}
                    className="text-neutral-600 hover:text-neutral-950"
                  >
                    Contact & Enquiries
                  </button>
                </li>
                <li>
                  <a
                    href="https://github.com/Aman678317/TalkFlow"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-neutral-600 hover:text-neutral-950"
                  >
                    GitHub Repository <ExternalLink className="h-3 w-3" />
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-neutral-500">Governance</h4>
              <ul className="space-y-2 text-xs text-neutral-600">
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-[#34C759]" /> Self-hosted on-premises</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-[#34C759]" /> Ephemeral audio streams</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-[#34C759]" /> GDPR compliant</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-[#34C759]" /> Canonical Source Principle</li>
              </ul>
            </div>
          </div>

          <div className="flex flex-col items-center justify-between gap-4 pt-6 text-xs text-neutral-500 sm:flex-row">
            <div>
              © {new Date().getFullYear()} GlobalTalk AI. One conversation · every language.
            </div>
            <div>
              Built with modern WebRTC, Whisper, Piper TTS, Argos, and OpenAI models.
            </div>
          </div>
        </div>
      </footer>
    
      {/* Contact & Enquiry Modal */}
      {contactOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-black/[0.08]">
            <div className="flex items-center justify-between border-b border-black/[0.06] pb-4">
              <div>
                <h3 className="text-lg font-bold text-neutral-900">Contact Us & Enquiry</h3>
                <p className="text-xs text-neutral-500 mt-0.5">Reach our team directly. We respond within 2-4 hours.</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setContactOpen(false);
                  setContactStatus("idle");
                  setContactError("");
                }}
                className="rounded-full p-1.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="my-4 rounded-xl bg-blue-50/60 p-3 text-xs text-blue-900 border border-blue-100/80">
              <span className="font-semibold">Direct Email:</span> support@globaltalk.ai · <span className="font-semibold">Hours:</span> Mon–Fri, 9:00 AM – 7:00 PM UTC
            </div>

            {contactStatus === "success" ? (
              <div className="py-6 text-center space-y-3">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <h4 className="font-bold text-neutral-900">Enquiry Delivered!</h4>
                <p className="text-xs text-neutral-600 max-w-sm mx-auto">
                  Thank you for contacting us. Your message has reached our team and an engineer will review your request shortly.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setContactOpen(false);
                    setContactStatus("idle");
                  }}
                  className="apple-btn-primary mt-2 min-h-[38px] px-6 text-xs"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmitContact} className="space-y-3 text-left">
                {contactError && (
                  <div className="rounded-lg bg-red-50 p-2.5 text-xs text-red-700 border border-red-200">
                    {contactError}
                  </div>
                )}
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">Your Name *</label>
                  <input
                    type="text"
                    required
                    value={contactForm.name}
                    onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })}
                    placeholder="Jane Doe"
                    className="w-full rounded-lg border border-black/[0.12] px-3 py-2 text-xs text-neutral-900 placeholder:text-neutral-400 focus:border-[#007AFF] focus:outline-none focus:ring-1 focus:ring-[#007AFF]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">Work Email *</label>
                  <input
                    type="email"
                    required
                    value={contactForm.email}
                    onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })}
                    placeholder="jane@company.com"
                    className="w-full rounded-lg border border-black/[0.12] px-3 py-2 text-xs text-neutral-900 placeholder:text-neutral-400 focus:border-[#007AFF] focus:outline-none focus:ring-1 focus:ring-[#007AFF]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">Subject</label>
                  <select
                    value={contactForm.subject}
                    onChange={(e) => setContactForm({ ...contactForm, subject: e.target.value })}
                    className="w-full rounded-lg border border-black/[0.12] px-3 py-2 text-xs text-neutral-900 focus:border-[#007AFF] focus:outline-none focus:ring-1 focus:ring-[#007AFF]"
                  >
                    <option value="General Inquiry">General Inquiry</option>
                    <option value="Enterprise & Sales">Enterprise & Sales</option>
                    <option value="Technical Support">Technical Support</option>
                    <option value="Security & Compliance">Security & Compliance</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">Message *</label>
                  <textarea
                    required
                    rows={4}
                    value={contactForm.message}
                    onChange={(e) => setContactForm({ ...contactForm, message: e.target.value })}
                    placeholder="How can we help your team?"
                    className="w-full rounded-lg border border-black/[0.12] px-3 py-2 text-xs text-neutral-900 placeholder:text-neutral-400 focus:border-[#007AFF] focus:outline-none focus:ring-1 focus:ring-[#007AFF]"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setContactOpen(false)}
                    className="rounded-lg px-4 py-2 text-xs font-medium text-neutral-600 hover:bg-neutral-100 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={contactStatus === "submitting"}
                    className="apple-btn-primary min-h-[38px] px-5 text-xs"
                  >
                    {contactStatus === "submitting" ? "Sending..." : "Send Enquiry"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
