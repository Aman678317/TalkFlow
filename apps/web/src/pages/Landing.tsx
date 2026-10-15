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
  const [demoMode, setDemoMode] = useState<"voice" | "text">("voice");

  return (
    <div className="min-h-full bg-surface-panel text-ink-950 selection:bg-accent-200 selection:text-ink-950">
      {/* HEADER NAVBAR — frosted material, content scrolls under */}
      <header className="material-bar sticky top-0 z-50">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <Link to="/" className="group flex shrink-0 items-center gap-2.5">
            <Logo className="h-7 w-7 sm:h-8 sm:w-8" />
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold tracking-tight text-ink-950 sm:text-lg">
                GlobalTalk <span className="text-accent-600">AI</span>
              </span>
              <span className="hidden rounded-full border border-border bg-surface-canvas px-2.5 py-0.5 text-[11px] font-medium text-ink-600 2xl:inline-block">
                Enterprise Suite
              </span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav aria-label="Main navigation" className="hidden items-center gap-1 text-sm font-medium xl:flex">
            <Link
              to="/translate"
              className="inline-flex min-h-[40px] items-center rounded-lg px-3.5 text-ink-700 transition-colors hover:bg-surface-subtle hover:text-ink-950"
            >
              Translate
            </Link>
            <Link
              to="/write"
              className="inline-flex min-h-[40px] items-center rounded-lg px-3.5 text-ink-700 transition-colors hover:bg-surface-subtle hover:text-ink-950"
            >
              Write
            </Link>
            <Link
              to="/voice"
              className="inline-flex min-h-[40px] items-center rounded-lg px-3.5 text-ink-700 transition-colors hover:bg-surface-subtle hover:text-ink-950"
            >
              Live Voice
            </Link>
            <Link
              to="/meetings"
              className="inline-flex min-h-[40px] items-center rounded-lg px-3.5 text-ink-700 transition-colors hover:bg-surface-subtle hover:text-ink-950"
            >
              Meetings
            </Link>
            <Link
              to="/agents"
              className="inline-flex min-h-[40px] items-center rounded-lg px-3.5 font-semibold text-accent-700 transition-colors hover:bg-accent-50 hover:text-accent-900"
            >
              <Bot className="mr-1.5 h-4 w-4 text-accent-600" />
              Agent Studio
            </Link>

            <div className="ml-4 flex items-center gap-2 border-l border-border pl-4">
              {user ? (
                <Link
                  to="/dashboard"
                  className="btn-tactile flex items-center gap-1.5 rounded-xl2 bg-accent-600 px-4 py-2 font-semibold text-white shadow-accent hover:bg-accent-700"
                >
                  Go to Dashboard <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="inline-flex min-h-[40px] items-center px-3 py-2 font-medium text-ink-700 transition-colors hover:text-ink-950"
                  >
                    Sign in
                  </Link>
                  <Link
                    to="/translate"
                    className="btn-tactile rounded-xl2 bg-accent-600 px-4 py-2 font-semibold text-white shadow-accent hover:bg-accent-700"
                  >
                    Start Free
                  </Link>
                </>
              )}
            </div>
          </nav>

          {/* Mobile Menu Button */}
          <div className="flex items-center gap-1 xl:hidden">
            {user ? (
              <Link
                to="/dashboard"
                className="inline-flex min-h-10 items-center rounded-lg bg-accent-600 px-2.5 text-xs font-semibold text-white shadow-xs"
              >
                Dashboard
              </Link>
            ) : (
              <Link
                to="/translate"
                className="inline-flex min-h-10 items-center rounded-lg bg-accent-600 px-2.5 text-xs font-semibold text-white shadow-xs"
              >
                Start Free
              </Link>
            )}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-700 hover:bg-surface-subtle hover:text-ink-950 focus-visible:ring-2 focus-visible:ring-focus"
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
              className="absolute inset-x-0 top-full max-h-[calc(100dvh-5rem)] overflow-y-auto border-b border-t border-border bg-surface-panel shadow-card xl:hidden"
            >
              <div className="px-6 py-4 space-y-2">
            <Link
              to="/translate"
              onClick={() => setMobileMenuOpen(false)}
               className="block rounded-lg px-3 py-2 text-base font-medium text-ink-700 hover:bg-surface-subtle hover:text-ink-950"
            >
              Translate
            </Link>
            <Link
              to="/write"
              onClick={() => setMobileMenuOpen(false)}
               className="block rounded-lg px-3 py-2 text-base font-medium text-ink-700 hover:bg-surface-subtle hover:text-ink-950"
            >
              Write
            </Link>
            <Link
              to="/voice"
              onClick={() => setMobileMenuOpen(false)}
               className="block rounded-lg px-3 py-2 text-base font-medium text-ink-700 hover:bg-surface-subtle hover:text-ink-950"
            >
              Live Voice
            </Link>
            <Link
              to="/meetings"
              onClick={() => setMobileMenuOpen(false)}
               className="block rounded-lg px-3 py-2 text-base font-medium text-ink-700 hover:bg-surface-subtle hover:text-ink-950"
            >
              Meetings
            </Link>
            <Link
              to="/agents"
              onClick={() => setMobileMenuOpen(false)}
               className="flex items-center gap-2 rounded-lg px-3 py-2 text-base font-semibold text-accent-700 hover:bg-accent-50"
            >
               <Bot className="h-4 w-4 text-accent-600" />
              Agent Studio
            </Link>
             <div className="flex flex-col gap-2 border-t border-border pt-3">
              {!user && (
                <Link
                  to="/login"
                  onClick={() => setMobileMenuOpen(false)}
                   className="block rounded-lg border border-border px-3 py-2 text-center text-sm font-medium text-ink-700 hover:bg-surface-subtle"
                >
                  Sign in
                </Link>
              )}
              <Link
                to={user ? "/dashboard" : "/translate"}
                onClick={() => setMobileMenuOpen(false)}
                 className="block rounded-lg bg-accent-600 px-3 py-2 text-center text-sm font-semibold text-white hover:bg-accent-700"
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
              <div className="inline-flex items-center gap-2 text-xs font-medium text-ink-600">
                <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent-600" />
                Sub-second voice and text translation pipeline
              </div>
              <Link
                to="/agents"
                className="inline-flex items-center gap-1.5 rounded-lg py-1 text-xs font-medium text-accent-700 hover:text-accent-900"
              >
                <Bot className="h-3.5 w-3.5 shrink-0 text-accent-600" />
                <span>New: Multi-Agent Studio (LangGraph + CrewAI)</span>
                <ArrowRight className="h-3 w-3 ml-0.5" />
              </Link>
            </motion.div>

            <motion.h1 variants={staggerItemVariants} className="max-w-3xl text-4xl font-semibold leading-[1.06] tracking-display text-ink-950 sm:text-6xl lg:text-5xl xl:text-6xl">
              One conversation.{" "}
              <span className="block text-accent-600">
                Every language.
              </span>
            </motion.h1>

            {/* Strict Subtext Discipline: Exactly 18 words (<= 20 words constraint) */}
            <motion.p variants={staggerItemVariants} className="mt-5 max-w-xl text-base leading-relaxed text-ink-600 sm:text-lg">
              Translate speech, text, documents, and video meetings in real time with sub-second latency and zero data retention.
            </motion.p>

            <motion.div variants={staggerItemVariants} className="mt-7 flex flex-wrap items-center gap-3">
              <Link
                to="/dashboard"
                className="btn-tactile flex min-h-12 items-center justify-center gap-2 rounded-xl2 bg-accent-600 px-5 py-3 text-sm font-semibold text-white shadow-xs hover:bg-accent-700"
              >
                Launch Workspace <ArrowRight className="h-5 w-5" />
              </Link>
              <Link
                to="/agents"
                className="btn-tactile flex min-h-12 items-center justify-center gap-2 rounded-xl2 border border-border bg-surface-panel px-5 py-3 text-sm font-semibold text-ink-800 shadow-xs hover:bg-surface-canvas"
              >
                <Bot className="h-5 w-5 text-accent-600" />
                Multi-Agent Studio
              </Link>
              <Link
                to="/translate"
                className="inline-flex min-h-10 items-center rounded-lg px-1 text-sm font-medium text-ink-600 underline-offset-4 hover:text-ink-950 hover:underline"
              >
                Try Translator
              </Link>
            </motion.div>

            <motion.div variants={staggerItemVariants} className="mt-10 border-t border-border pt-5">
              <p className="mb-2.5 text-xs font-semibold text-ink-500">
                Supported Across 100+ Languages
              </p>
              <div className="flex flex-wrap gap-2">
                {LANGS.map((l) => (
                  <span
                    key={l}
                    className="rounded-md bg-surface-canvas px-2.5 py-1 text-xs text-ink-600"
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
            className="min-w-0 rounded-2xl border border-border bg-surface-canvas p-4 shadow-card sm:p-6"
          >
            {/* Widget Header & Mode Switcher */}
            <div className="mb-5 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5">
              <div className="flex flex-col items-start gap-2">
                   <span className="flex items-center gap-1.5 rounded-md border border-accent-200 bg-accent-50 px-2 py-0.5 text-xs font-semibold text-accent-700">
                     <Radio className="h-3 w-3 text-accent-600" /> WebRTC Mesh Active
                   </span>
                 <span className="text-xs text-ink-600">Canonical Source Pipeline</span>
               </div>
               <div className="flex items-center rounded-lg border border-border bg-surface-subtle p-0.5">
                <button
                  type="button"
                  onClick={() => setDemoMode("voice")}
                  aria-pressed={demoMode === "voice"}
                  className={`min-h-9 rounded-md px-2.5 py-1 text-xs font-semibold ${
                    demoMode === "voice"
                       ? "bg-surface-panel text-ink-950 shadow-xs"
                       : "text-ink-500 hover:text-ink-950"
                  }`}
                >
                  Speech Flow
                </button>
                <button
                  type="button"
                  onClick={() => setDemoMode("text")}
                  aria-pressed={demoMode === "text"}
                  className={`min-h-9 rounded-md px-2.5 py-1 text-xs font-semibold ${
                    demoMode === "text"
                       ? "bg-surface-panel text-ink-950 shadow-xs"
                       : "text-ink-500 hover:text-ink-950"
                  }`}
                >
                  Dual-Pane
                </button>
              </div>
            </div>

            {demoMode === "voice" ? (
              <div className="space-y-3.5 text-xs">
                {/* Source Speaker with Audio Waveform */}
                 <div className="rounded-xl2 border border-border bg-surface-canvas p-3.5">
                   <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-ink-600">
                     <span className="flex items-center gap-1.5 font-semibold text-accent-600">
                      <Mic className="h-4 w-4" /> Live Speaker A (Hindi)
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px] font-medium text-accent-700">
                      <span aria-hidden="true" className="flex h-3.5 items-end gap-0.5">
                        <span className="h-3.5 w-1 rounded-full bg-accent-500 animate-wave-1" />
                        <span className="h-3.5 w-1 rounded-full bg-accent-500 animate-wave-2" />
                        <span className="h-3.5 w-1 rounded-full bg-accent-500 animate-wave-3" />
                        <span className="h-3.5 w-1 rounded-full bg-accent-500 animate-wave-4" />
                      </span>
                      16kHz PCM Stream
                    </span>
                  </div>
                   <p className="text-sm font-medium text-ink-950">
                    "नमस्ते, हमारी कंपनी नई ग्लोबल टीम मीटिंग शुरू कर रही है।"
                  </p>
                </div>

                {/* Direct fan-out indicator */}
                 <div className="flex items-center justify-center gap-2 py-0.5 text-ink-500">
                   <div className="h-px flex-1 bg-border" />
                   <span className="flex items-center gap-1 rounded-full border border-accent-200 bg-accent-50 px-2 py-0.5 text-[11px] font-semibold text-accent-700">
                     <Zap className="h-3 w-3 text-accent-500" /> Direct Neural Fan-Out
                   </span>
                   <div className="h-px flex-1 bg-border" />
                </div>

                {/* Target Listeners */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                   <div className="rounded-xl2 border border-border bg-surface-panel p-3.5 shadow-xs transition-colors hover:border-accent-300">
                     <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-ink-600">
                       <span className="flex items-center gap-1 font-semibold text-ink-800">
                         <Volume2 className="h-3.5 w-3.5 text-accent-600" /> Listener B (English)
                      </span>
                      <span className="rounded bg-accent-50 px-1.5 py-0.5 text-[10px] font-semibold text-accent-700">
                        120ms
                      </span>
                    </div>
                   <p className="text-xs leading-relaxed text-ink-700">
                      "Hello, our company is starting the new global team meeting."
                    </p>
                  </div>

                   <div className="rounded-xl2 border border-border bg-surface-panel p-3.5 shadow-xs transition-colors hover:border-accent-300">
                     <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-ink-600">
                       <span className="flex items-center gap-1 font-semibold text-ink-800">
                         <Volume2 className="h-3.5 w-3.5 text-accent-600" /> Listener C (Spanish)
                      </span>
                      <span className="rounded bg-accent-50 px-1.5 py-0.5 text-[10px] font-semibold text-accent-700">
                        145ms
                      </span>
                    </div>
                   <p className="text-xs leading-relaxed text-ink-700">
                      "Hola, nuestra empresa está comenzando la nueva reunión de equipo global."
                    </p>
                  </div>
                </div>

                 <div className="rounded-xl border border-border bg-surface-canvas p-2.5 text-center text-xs text-ink-600">
                  Every attendee receives native synthetic audio playback in real time without translation daisy-chaining.
                </div>
              </div>
            ) : (
              <div className="space-y-3 text-xs">
                <div className="grid gap-3 sm:grid-cols-2">
                   <div className="rounded-xl border border-border bg-surface-canvas p-3">
                     <span className="mb-1 block text-[11px] font-semibold text-ink-500">Source: English</span>
                     <p className="text-xs font-medium text-ink-950">
                      Our mission is to empower teams across continents to collaborate seamlessly.
                    </p>
                  </div>
                   <div className="rounded-xl border border-border bg-surface-panel p-3 shadow-xs">
                     <span className="mb-1 block text-[11px] font-semibold text-accent-600">Target: German</span>
                     <p className="text-xs leading-relaxed text-ink-800">
                      Unsere Mission ist es, Teams über Kontinente hinweg zu einer nahtlosen Zusammenarbeit zu befähigen.
                    </p>
                  </div>
                </div>
                 <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-ink-600">
                  <span>Contextual dictionary · Formality tier: Formal</span>
                   <Link to="/translate" className="text-xs font-semibold text-accent-600 hover:text-accent-700 hover:underline">
                    Open Dual-Pane Translator →
                  </Link>
                </div>
              </div>
            )}
          </motion.div>
        </section>

        {/* 5 CORE PILLARS BENTO GRID (Section 4.7 Rhythm & Exact Cell Count) */}
        <section className="border-t border-border py-16 lg:py-24">
          <Reveal className="mb-10 max-w-2xl">
            <p className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-accent-700">01 / Your workspaces</p>
            <h2 className="text-3xl font-semibold tracking-title text-ink-950 sm:text-4xl">
              Five Core Capabilities in One Platform
            </h2>
            <p className="mt-3 text-sm text-ink-600">
              Engineered with privacy-first self-hosted neural models, sub-second latency, and intuitive workspaces.
            </p>
          </Reveal>

          <Reveal className="grid gap-4 md:grid-cols-2 lg:grid-cols-6">
            {/* Tile 1: Flagship Live Voice Translation (Col-span 2 on desktop) */}
            <Link
              to="/voice"
              className="group relative flex min-w-0 flex-col justify-between rounded-2xl border border-ink-800 bg-surface-inverse p-6 shadow-card hover:border-accent-500 lg:col-span-3 lg:p-8"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl2 bg-white/10 text-accent-300">
                    <Mic className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-border-inverse px-3 py-1 text-xs font-medium text-ink-200">
                    Speech-to-Speech
                  </span>
                </div>

                <h3 className="text-2xl font-semibold text-white">
                  Live Voice Translation Studio
                </h3>

                <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink-300">
                  Real-time face-to-face speech synthesis with natural audio release, soundwave pulsing visualizer, and bilingual live transcript feeds under 1,000 milliseconds.
                </p>

                <div className="mt-6 grid grid-cols-1 gap-3 border-t border-border-inverse pt-5 sm:grid-cols-3">
                  <div className="text-xs">
                    <span className="mb-1 block text-[11px] text-ink-300">Audio Protocol</span>
                    <strong className="font-medium text-ink-100">16kHz PCM Stream</strong>
                  </div>
                  <div className="text-xs">
                    <span className="mb-1 block text-[11px] text-ink-300">Voice Detection</span>
                    <strong className="font-medium text-ink-100">Silero Neural VAD</strong>
                  </div>
                  <div className="text-xs">
                    <span className="mb-1 block text-[11px] text-ink-300">Speech Output</span>
                    <strong className="font-medium text-ink-100">Piper Synthesizer</strong>
                  </div>
                </div>
              </div>

              <div className="mt-8 flex items-center text-sm font-medium text-accent-300 group-hover:text-accent-200">
                Open Live Voice Studio <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 2: AI Translation Workspace (1 col) */}
            <Link
              to="/translate"
              className="group relative flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-canvas p-6 hover:border-accent-300 lg:col-span-3 lg:p-8"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600 transition-colors group-hover:bg-accent-600 group-hover:text-white">
                    <Languages className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-0.5 text-[11px] font-semibold text-ink-600">
                    Dual-Pane AI
                  </span>
                </div>

                <h3 className="text-2xl font-semibold text-ink-950 group-hover:text-accent-700">
                  AI Translation Workspace
                </h3>

                <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-600">
                  Instant translation with contextual dictionary, synonyms lookup, formality control, and native speech listen playback.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-accent-600 group-hover:text-accent-700">
                Open Workspace <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 3: AI Writing Companion (1 col) */}
            <Link
              to="/write"
              className="group relative flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-panel p-6 hover:border-accent-300 lg:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600 transition-colors group-hover:bg-accent-600 group-hover:text-white">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-0.5 text-[11px] font-semibold text-ink-600">
                    Writing Companion
                  </span>
                </div>

                <h3 className="text-lg font-bold text-ink-950 transition-colors group-hover:text-accent-700">
                  AI Writing Companion
                </h3>

                <p className="mt-3 text-sm leading-relaxed text-ink-600">
                  Rewriting and grammar correction across 5 styles (Business, Academic, Casual, Simple, Creative) and 5 tones with side-by-side diff highlighting.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-accent-600 group-hover:text-accent-700">
                Open Writing Tool <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 4: Multilingual Meetings (1 col) */}
            <Link
              to="/meetings"
              className="group relative flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-panel p-6 hover:border-accent-300 lg:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600 transition-colors group-hover:bg-accent-600 group-hover:text-white">
                    <Video className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-0.5 text-[11px] font-semibold text-ink-600">
                    WebRTC Video
                  </span>
                </div>

                <h3 className="text-lg font-bold text-ink-950 transition-colors group-hover:text-accent-700">
                  Video Conferences
                </h3>

                <p className="mt-3 text-sm leading-relaxed text-ink-600">
                  Side-by-side video tiles, crystal-clear audio, camera controls, screen sharing, instant invite links, and live translated captions for every attendee.
                </p>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-accent-600 group-hover:text-accent-700">
                Open Meetings <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>

            {/* Tile 5: Document Translation & Enterprise Governance (Col-span 2 on desktop) */}
            <Link
              to="/documents"
              className="group relative flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-panel p-6 hover:border-accent-300 md:col-span-2"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600">
                    <FileText className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-accent-200 bg-accent-50 px-3 py-1 text-xs font-semibold text-accent-700">
                    Layout Preserved
                  </span>
                </div>

                <h3 className="text-xl font-bold text-ink-950 transition-colors group-hover:text-accent-700">
                  Document Translation & Enterprise Privacy
                </h3>

                <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-600">
                  Translate PDFs, DOCX, PPTX, XLSX, and TXT while preserving exact styling, formatting, and tables. Zero telemetry, on-premises deployment, and full GDPR compliance.
                </p>

                <div className="mt-5 flex flex-wrap gap-2 border-t border-border/80 pt-3">
                  {["PDF", "DOCX", "PPTX", "XLSX", "HTML", "TXT"].map((ext) => (
                    <span
                      key={ext}
                      className="rounded-md border border-border bg-surface-panel px-2.5 py-1 text-xs font-semibold text-ink-700 shadow-xs"
                    >
                      {ext}
                    </span>
                  ))}
                   <span className="flex items-center gap-1 rounded-md border border-accent-200 bg-accent-50 px-2.5 py-1 text-xs font-semibold text-accent-700">
                     <Shield className="h-3.5 w-3.5" /> 100% On-Premises Safe
                  </span>
                </div>
              </div>

              <div className="mt-6 flex items-center text-xs font-semibold text-accent-600 group-hover:text-accent-700">
                Translate Documents <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          </Reveal>
        </section>

        {/* MULTI-AGENT SYSTEMS STUDIO SHOWCASE */}
        <section className="border-t border-border py-16 lg:py-24" aria-labelledby="multi-agent-heading">
          <Reveal className="mb-10 max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.12em] text-accent-700">
              <Bot className="h-3.5 w-3.5 text-accent-600" />
              Autonomous Agent Orchestration
            </div>
            <h2 id="multi-agent-heading" className="text-3xl font-semibold tracking-title text-ink-950 sm:text-4xl">
              Production Multi-Agent Systems in Action
            </h2>
            <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-600">
              Explore 3 production agent architectures powered by LangGraph state machines and CrewAI role-playing personas. Interactive, live, and inspectable in real time.
            </p>
          </Reveal>

          <Reveal className="mb-6 grid gap-4 lg:grid-cols-3">
            {/* Card 1: Customer Support Triage Graph */}
            <div className="group flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-panel p-6">
              <div>
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600 transition-colors group-hover:bg-accent-600 group-hover:text-white">
                    <GitBranch className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-accent-200 bg-accent-50 px-2.5 py-0.5 text-[11px] font-semibold text-accent-700">
                    LangGraph State Machine
                  </span>
                </div>
                <h3 className="text-lg font-bold text-ink-950 transition-colors group-hover:text-accent-700">
                  Customer Support Triage Graph
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-ink-600">
                  Classifies customer tickets, extracts priority, routes to specialist subgraphs (Billing, Technical, General), and detects escalation triggers.
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-border/80 pt-3">
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Conditional Edges</span>
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Human Escalation</span>
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Typed Dict State</span>
                </div>
              </div>
              <Link
                to="/agents"
                className="mt-6 inline-flex items-center text-xs font-semibold text-accent-600 hover:text-accent-700"
              >
                Try Triage Graph <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>

            {/* Card 2: Autonomous Content Pipeline */}
            <div className="group flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-panel p-6">
              <div>
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600 transition-colors group-hover:bg-accent-600 group-hover:text-white">
                    <RefreshCw className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-accent-200 bg-accent-50 px-2.5 py-0.5 text-[11px] font-semibold text-accent-700">
                    Self-Correcting Loop
                  </span>
                </div>
                <h3 className="text-lg font-bold text-ink-950 transition-colors group-hover:text-accent-700">
                  Autonomous Content Pipeline
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-ink-600">
                  Researches, drafts, and audits content in an automated feedback loop. Iterates up to 3 cycles until quality score reaches 0.80+.
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-border/80 pt-3">
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">LangGraph + CrewAI</span>
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Quality Rubric</span>
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Infinite-Loop Guards</span>
                </div>
              </div>
              <Link
                to="/agents"
                className="mt-6 inline-flex items-center text-xs font-semibold text-accent-600 hover:text-accent-700"
              >
                Launch Pipeline <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>

            {/* Card 3: Research Assistant Crew */}
            <div className="group flex min-w-0 flex-col justify-between rounded-2xl border border-border bg-surface-panel p-6">
              <div>
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl2 bg-accent-50 text-accent-600 transition-colors group-hover:bg-accent-600 group-hover:text-white">
                    <Workflow className="h-5 w-5" />
                  </div>
                  <span className="rounded-full border border-accent-200 bg-accent-50 px-2.5 py-0.5 text-[11px] font-semibold text-accent-700">
                    CrewAI 4-Agent Crew
                  </span>
                </div>
                <h3 className="text-lg font-bold text-ink-950 transition-colors group-hover:text-accent-700">
                  Research Assistant Crew
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-ink-600">
                  Hub & Spoke architecture with 4 specialized roles: Information Gatherer, Synthesizer, Report Writer, and Fact-Checker.
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5 border-t border-border/80 pt-3">
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Role & Goal Prompts</span>
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Executive Briefings</span>
                  <span className="rounded bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-ink-600">Fact Verification</span>
                </div>
              </div>
              <Link
                to="/agents"
                className="mt-6 inline-flex items-center text-xs font-semibold text-accent-600 hover:text-accent-700"
              >
                Deploy Crew <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </Reveal>

          <Reveal className="flex flex-col items-start justify-between gap-5 rounded-2xl border border-accent-200 bg-accent-50 p-6 lg:flex-row lg:items-center lg:p-8">
            <div>
              <h4 className="text-base font-bold text-ink-950">
                Interactive Multi-Agent Studio with Real-time Visualizer
              </h4>
              <p className="mt-1 text-xs text-ink-600">
                Test prompts, trace state transitions, examine agent personas, and run live multi-agent pipelines with zero setup.
              </p>
            </div>
            <Link
              to="/agents"
              className="btn-tactile flex shrink-0 items-center gap-2 rounded-xl2 bg-accent-600 px-5 py-2.5 text-sm font-semibold text-white shadow-accent hover:bg-accent-700"
            >
              Open Agent Studio <ArrowRight className="h-4 w-4" />
            </Link>
          </Reveal>
        </section>

        {/* FREQUENTLY ASKED QUESTIONS */}
        <section className="border-t border-border py-16 lg:py-24" aria-labelledby="faq-heading">
          <Reveal className="mx-auto mb-12 max-w-2xl text-center">
            <h2 id="faq-heading" className="text-3xl font-bold tracking-title text-ink-950 sm:text-4xl">
              Frequently Asked Questions
            </h2>
            <p className="mt-3 text-sm text-ink-600">
              In-depth details on latency, privacy standards, supported document types, and translation architecture.
            </p>
          </Reveal>

          <Reveal className="mx-auto max-w-3xl space-y-3.5">
            {FAQS.map((faq) => (
              <details
                key={faq.q}
                className="group rounded-xl2 border border-border bg-surface-panel p-5 open:border-accent-300 open:bg-accent-50/40 sm:p-6"
              >
                <summary className="flex cursor-pointer items-center justify-between text-base font-semibold text-ink-950 group-hover:text-accent-700">
                  <span>{faq.q}</span>
                  <ChevronDown aria-hidden="true" className="ml-4 h-5 w-5 flex-shrink-0 text-ink-500 transition-transform duration-200 group-open:rotate-180 group-open:text-accent-600 motion-reduce:transition-none" />
                </summary>
                <p className="mt-3 border-t border-border pt-3 text-sm leading-relaxed text-ink-600">
                  {faq.a}
                </p>
              </details>
            ))}
          </Reveal>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-border bg-surface-canvas py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 gap-8 border-b border-border pb-8 md:grid-cols-4">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Logo className="h-6 w-6 text-accent-600" />
                <span className="font-bold text-ink-950">GlobalTalk AI</span>
              </div>
              <p className="text-xs leading-relaxed text-ink-600">
                Real-time multilingual voice and text translation platform with sub-second latency and zero data retention.
              </p>
            </div>

            <div>
               <h4 className="mb-3 text-xs font-semibold text-ink-500">Workspaces</h4>
              <ul className="space-y-2 text-xs">
                 <li><Link to="/translate" className="text-ink-600 hover:text-ink-950">Dual-Pane Translator</Link></li>
                 <li><Link to="/write" className="text-ink-600 hover:text-ink-950">Writing Companion</Link></li>
                 <li><Link to="/voice" className="text-ink-600 hover:text-ink-950">Live Voice Translation</Link></li>
                 <li><Link to="/meetings" className="text-ink-600 hover:text-ink-950">Multilingual Meetings</Link></li>
                 <li><Link to="/documents" className="text-ink-600 hover:text-ink-950">Document Translation</Link></li>
                 <li><Link to="/agents" className="font-semibold text-accent-600 hover:text-accent-800">Multi-Agent Studio</Link></li>
              </ul>
            </div>

            <div>
               <h4 className="mb-3 text-xs font-semibold text-ink-500">Developer & API</h4>
              <ul className="space-y-2 text-xs">
                 <li><Link to="/docs" className="text-ink-600 hover:text-ink-950">SDKs & Guides</Link></li>
                 <li><Link to="/api/docs" className="text-ink-600 hover:text-ink-950">REST & WebSocket API</Link></li>
                <li>
                  <a
                    href="https://github.com/Aman678317/TalkFlow"
                    target="_blank"
                    rel="noopener noreferrer"
                     className="inline-flex items-center gap-1 text-ink-600 hover:text-ink-950"
                  >
                    GitHub Repository <ExternalLink className="h-3 w-3" />
                  </a>
                </li>
              </ul>
            </div>

            <div>
               <h4 className="mb-3 text-xs font-semibold text-ink-500">Governance</h4>
               <ul className="space-y-2 text-xs text-ink-600">
                 <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-accent-600" /> Self-hosted on-premises</li>
                 <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-accent-600" /> Ephemeral audio streams</li>
                 <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-accent-600" /> GDPR compliant</li>
                 <li className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-accent-600" /> Canonical Source Principle</li>
              </ul>
            </div>
          </div>

           <div className="flex flex-col items-center justify-between gap-4 pt-6 text-xs text-ink-500 sm:flex-row">
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
