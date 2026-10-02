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
} from "lucide-react";
import { Logo } from "../components/Layout";
import { useAuth } from "../stores/auth";

const LANGS = [
  "English", "हिन्दी (Hindi)", "Español (Spanish)", "Deutsch (German)",
  "Français (French)", "日本語 (Japanese)", "中文 (Chinese)", "العربية (Arabic)",
  "मराठी (Marathi)", "বাংলা (Bengali)", "Português", "Italiano",
];

const PILLARS = [
  {
    icon: Languages,
    title: "Desi-Grade Translator",
    link: "/translate",
    tag: "Dual-Pane AI",
    desc: "Lightning-fast translation with contextual dictionary, synonyms lookup, formality control, and native speech synthesis listen playback.",
  },
  {
    icon: Sparkles,
    title: "Desi Write AI",
    link: "/write",
    tag: "Writing Companion",
    desc: "AI-driven rewriting and grammar correction across 5 styles (Business, Academic, Casual, Simple, Creative) and 5 tones with side-by-side diff highlighting.",
  },
  {
    icon: Mic,
    title: "Desi Voice Live",
    link: "/voice",
    tag: "Speech-to-Speech",
    desc: "Real-time face-to-face voice translation with smooth audio release, soundwave pulsing visualizer, and bilingual live transcript feeds.",
  },
  {
    icon: Video,
    title: "Google Meet-Style Calls",
    link: "/meetings",
    tag: "WebRTC Video",
    desc: "Side-by-side video tiles, crystal-clear audio, camera controls, screen sharing, instant invite links, and live translated captions for every participant.",
  },
  {
    icon: FileText,
    title: "Document Translation",
    link: "/documents",
    tag: "Layout Preserved",
    desc: "Translate PDFs, DOCX, PPTX, XLSX, and TXT while preserving exact styling, formatting, and tables with automated quality checks.",
  },
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
    a: "GlobalTalk AI enforces the Canonical Source Principle: the original human speaker's segment is the sole semantic source of truth. Rather than daisy-chaining translations (e.g. Hindi to English to Japanese), each target language fans out directly from the original source.",
  },
];

export default function Landing() {
  const user = useAuth((s) => s.user);

  return (
    <div className="min-h-full bg-slate-950 text-white selection:bg-iris-500 selection:text-white">
      {/* HEADER NAVBAR */}
      <header className="sticky top-0 z-50 border-b border-white/[0.08] bg-slate-950/70 backdrop-blur-xl backdrop-saturate-[180%]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Logo className="h-9 w-9 text-iris-500" />
            <div>
              <span className="text-xl font-bold tracking-tight">
                GlobalTalk <span className="text-iris-400">AI</span>
              </span>
              <span className="hidden sm:inline-block ml-2 rounded-full border border-iris-500/30 bg-iris-500/10 px-2 py-0.5 text-[10px] font-semibold text-iris-300">
                Enterprise Suite
              </span>
            </div>
          </div>

          <nav className="flex items-center gap-1 text-sm font-medium">
            <Link to="/translate" className="hidden md:inline-flex items-center min-h-[44px] px-3 rounded-lg text-slate-300 hover:text-white hover:bg-white/[0.04] transition-colors">
              Translate
            </Link>
            <Link to="/write" className="hidden md:inline-flex items-center min-h-[44px] px-3 rounded-lg text-slate-300 hover:text-white hover:bg-white/[0.04] transition-colors">
              Write
            </Link>
            <Link to="/voice" className="hidden md:inline-flex items-center min-h-[44px] px-3 rounded-lg text-slate-300 hover:text-white hover:bg-white/[0.04] transition-colors">
              Live Voice
            </Link>
            <Link to="/meetings" className="hidden md:inline-flex items-center min-h-[44px] px-3 rounded-lg text-slate-300 hover:text-white hover:bg-white/[0.04] transition-colors">
              Meetings
            </Link>

            {user ? (
              <Link
                to="/dashboard"
                className="flex items-center gap-1.5 rounded-xl bg-iris-600 px-5 py-2 font-semibold text-white shadow-md hover:bg-iris-500 active:scale-[0.98] active:brightness-95 transition-all duration-100 ease-out"
              >
                Go to Dashboard <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link to="/login" className="inline-flex items-center min-h-[44px] px-3 py-2 text-slate-300 hover:text-white transition-colors">
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className="rounded-xl bg-iris-600 px-5 py-2 font-semibold text-white shadow-md hover:bg-iris-500 active:scale-[0.98] active:brightness-95 transition-all duration-100 ease-out"
                >
                  Start Free
                </Link>
              </div>
            )}
          </nav>
        </div>
      </header>

      {/* HERO SECTION */}
      <main className="mx-auto max-w-7xl px-6">
        <section className="py-16 lg:py-24 grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-iris-500/30 bg-iris-950/60 px-4 py-1.5 text-xs font-semibold text-iris-300 shadow-inner">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-pulse motion-reduce:animate-none rounded-full bg-iris-400/50" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-iris-500" />
              </span>
              The Complete Full-Stack AI Translation & Voice Platform
            </div>

            <h1 className="text-4xl font-extrabold tracking-[-0.03em] sm:text-6xl sm:tracking-[-0.035em] sm:leading-[1.05]">
              One conversation.{" "}
              <span className="bg-gradient-to-r from-iris-400 via-sky-300 to-lagoon-400 bg-clip-text text-transparent">
                Every language.
              </span>
            </h1>

            <p className="mt-6 text-lg leading-relaxed text-slate-300 max-w-xl">
              Break language barriers with Desi-grade text & document translation, Desi Write AI style
              enhancements, Desi Voice face-to-face speech synthesis, and Google Meet-style WebRTC video
              conferences with live multilingual audio.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                to="/signup"
                className="flex items-center gap-2 rounded-xl bg-iris-600 px-6 py-3.5 text-base font-semibold text-white shadow-lg hover:bg-iris-500 hover:shadow-iris-500/25 active:scale-[0.98] active:brightness-95 transition-all duration-100 ease-out"
              >
                Launch Workspace <ArrowRight className="h-5 w-5" />
              </Link>
              <Link
                to="/translate"
                className="rounded-xl border border-slate-700 bg-slate-900/60 px-6 py-3.5 text-base font-semibold text-slate-200 hover:border-slate-500 hover:text-white active:scale-[0.98] active:bg-slate-800 transition-all duration-100 ease-out"
              >
                Try Translator
              </Link>
            </div>

            <div className="mt-10 border-t border-slate-800/80 pt-6">
              <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-3">
                Supported Across 100+ Languages
              </p>
              <div className="flex flex-wrap gap-2">
                {LANGS.map((l) => (
                  <span
                    key={l}
                    className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-1 text-xs text-slate-300"
                  >
                    {l}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* INTERACTIVE WORKSPACE PREVIEW CARD */}
          <div className="rounded-[28px] border border-white/10 bg-gradient-to-b from-slate-900/90 to-slate-950 p-6 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-4 mb-4">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-rose-500/80" />
                <span className="h-3 w-3 rounded-full bg-amber-500/80" />
                <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
                <span className="ml-2 text-xs font-mono text-slate-400">GlobalTalk AI Live Flow</span>
              </div>
              <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" /> E2E Active
              </span>
            </div>

            <div className="space-y-4 font-sans text-xs">
              <div className="rounded-xl border border-white/[0.06] bg-slate-900/60 p-4">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="flex items-center gap-1.5 font-semibold text-iris-400">
                    <Mic className="h-4 w-4" /> Live Speaker A (Hindi)
                  </span>
                  <span>Audio captured via WebRTC</span>
                </div>
                <p className="text-sm font-medium text-slate-100">
                  "नमस्ते, हमारी कंपनी नई ग्लोबल टीम मीटिंग शुरू कर रही है।"
                </p>
              </div>

              <div className="flex justify-center text-slate-500">
                <Zap className="h-4 w-4 text-amber-400 opacity-90" />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-white/[0.06] bg-slate-900/60 p-4">
                  <div className="flex items-center justify-between text-slate-400 mb-2">
                    <span className="font-semibold text-sky-400 flex items-center gap-1">
                      <Volume2 className="h-3.5 w-3.5" /> Listener B (English)
                    </span>
                    <span className="text-[10px] text-emerald-400">120ms</span>
                  </div>
                  <p className="text-xs font-medium text-slate-200">
                    "Hello, our company is starting the new global team meeting."
                  </p>
                </div>

                <div className="rounded-xl border border-white/[0.06] bg-slate-900/60 p-4">
                  <div className="flex items-center justify-between text-slate-400 mb-2">
                    <span className="font-semibold text-lagoon-400 flex items-center gap-1">
                      <Volume2 className="h-3.5 w-3.5" /> Listener C (Spanish)
                    </span>
                    <span className="text-[10px] text-emerald-400">145ms</span>
                  </div>
                  <p className="text-xs font-medium text-slate-200">
                    "Hola, nuestra empresa está comenzando la nueva reunión de equipo global."
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-iris-500/20 bg-iris-950/30 p-3 text-center text-slate-300">
                Every listener experiences native audio voice playback in real time. Zero distortion.
              </div>
            </div>
          </div>
        </section>

        {/* 5 CORE PILLARS GRID */}
        <section className="border-t border-white/[0.08] py-20">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="text-xs font-bold uppercase tracking-widest text-iris-400">
              Complete AI Ecosystem
            </h2>
            <h3 className="mt-2 text-3xl font-extrabold sm:text-4xl text-white">
              Five Industry-Leading Capabilities in One App
            </h3>
            <p className="mt-3 text-slate-400 text-sm">
              Engineered with privacy-first self-hosted AI models, sub-second latency, and intuitive
              interfaces.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {PILLARS.map((p) => {
              const Icon = p.icon;
              return (
                <Link
                  key={p.title}
                  to={p.link}
                  className="group relative flex flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/40 p-6 transition-colors duration-150 hover:border-white/20 hover:bg-slate-900/70 active:scale-[0.99]"
                >
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-iris-500/10 text-iris-400 group-hover:bg-iris-500 group-hover:text-white transition-colors">
                        <Icon className="h-6 w-6" />
                      </div>
                      <span className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-0.5 text-[11px] font-semibold text-slate-300">
                        {p.tag}
                      </span>
                    </div>

                    <h4 className="text-lg font-bold text-white group-hover:text-iris-300 transition-colors">
                      {p.title}
                    </h4>
                    <p className="mt-2 text-xs leading-relaxed text-slate-400">
                      {p.desc}
                    </p>
                  </div>

                  <div className="mt-6 flex items-center text-xs font-semibold text-iris-400 group-hover:text-iris-300">
                    Open {p.title} <ArrowRight className="h-3.5 w-3.5 ml-1 transition-transform group-hover:translate-x-1" />
                  </div>
                </Link>
              );
            })}

            {/* ENTERPRISE SECURITY CARD */}
            <div className="flex flex-col justify-between rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/50 to-slate-950 p-6">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-lagoon-500/10 text-lagoon-400">
                    <Shield className="h-6 w-6" />
                  </div>
                  <span className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-0.5 text-[11px] font-semibold text-slate-300">
                    Enterprise Ready
                  </span>
                </div>
                <h4 className="text-lg font-bold text-white">Full Privacy & Governance</h4>
                <p className="mt-2 text-xs leading-relaxed text-slate-400">
                  Custom glossaries, translation memory with 100% fuzzy matching, company style guides,
                  tenant isolation, and zero third-party telemetry.
                </p>
              </div>

              <div className="mt-6 flex items-center gap-2 text-xs text-emerald-400 font-medium">
                <CheckCircle2 className="h-4 w-4" /> Self-hosted & GDPR compliant
              </div>
            </div>
          </div>
        </section>

        {/* FREQUENTLY ASKED QUESTIONS (GEO & CITABILITY) */}
        <section className="border-t border-white/[0.08] py-20" aria-labelledby="faq-heading">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <h2 id="faq-heading" className="text-xs font-bold uppercase tracking-widest text-iris-400">
              Frequently Asked Questions
            </h2>
            <h3 className="mt-2 text-3xl font-extrabold sm:text-4xl text-white">
              Everything You Need to Know
            </h3>
            <p className="mt-3 text-slate-400 text-sm">
              In-depth details on latency, privacy standards, supported document types, and translation architecture.
            </p>
          </div>

          <div className="max-w-3xl mx-auto space-y-4">
            {FAQS.map((faq) => (
              <details
                key={faq.q}
                className="group rounded-2xl border border-slate-800 bg-slate-900/40 p-6 transition-all duration-150 open:border-iris-500/30 open:bg-slate-900/80"
              >
                <summary className="flex cursor-pointer items-center justify-between text-base font-semibold text-white group-hover:text-iris-300">
                  <span>{faq.q}</span>
                  <ChevronDown className="h-5 w-5 text-slate-400 transition-transform duration-200 group-open:rotate-180 group-open:text-iris-400 flex-shrink-0 ml-4" />
                </summary>
                <p className="mt-4 text-sm leading-relaxed text-slate-300 border-t border-white/[0.06] pt-4">
                  {faq.a}
                </p>
              </details>
            ))}
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-white/[0.08] bg-slate-950 py-10">
        <div className="mx-auto max-w-7xl px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <Logo className="h-5 w-5 text-iris-500" />
            <span className="font-semibold text-slate-300">GlobalTalk AI</span>
            <span>· One conversation, every language.</span>
          </div>
          <div>
            Built with modern WebRTC, Whisper, Piper TTS, Argos, and OpenAI models.
          </div>
        </div>
      </footer>
    </div>
  );
}
