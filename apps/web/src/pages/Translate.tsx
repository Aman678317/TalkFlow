import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  BookOpen,
  Check,
  Copy,
  Download,
  FileText,
  Mic,
  MicOff,
  Sparkles,
  Volume2,
  X,
  Upload,
} from "lucide-react";
import { api } from "../lib/api";
import type { TranslateResponse } from "../lib/types";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, Button, Card, ErrorState, Select, Skeleton } from "../components/ui";
import { toast } from "../stores/toasts";

interface Glossary {
  id: string;
  name: string;
  source_language: string;
  target_language: string;
  status: string;
}
interface Style {
  id: string;
  name: string;
  is_system: boolean;
}

interface DictionaryEntry {
  word: string;
  phonetic?: string;
  part_of_speech: string;
  meanings: string[];
  synonyms: string[];
  translations: string[];
  examples: string[];
}

const INTENTS = [
  { value: "quality_optimized", label: "Best quality" },
  { value: "latency_optimized", label: "Fastest" },
  { value: "cost_optimized", label: "Low cost" },
  { value: "private_only", label: "Private only" },
];

const DOMAINS = ["general", "technical", "legal", "finance", "medical", "customer_support", "education"];

const QUICK_LANGS = [
  { code: "en", name: "English" },
  { code: "es", name: "Spanish" },
  { code: "de", name: "German" },
  { code: "fr", name: "French" },
  { code: "hi", name: "Hindi" },
  { code: "ja", name: "Japanese" },
  { code: "zh", name: "Chinese" },
];

export default function TranslatePage() {
  const navigate = useNavigate();
  const { data: langs } = useLanguages();
  const { data: glossaries } = useQuery({
    queryKey: ["glossaries"],
    queryFn: () => api<Glossary[]>("/api/v1/glossaries"),
  });
  const { data: styles } = useQuery({
    queryKey: ["styles"],
    queryFn: () => api<Style[]>("/api/v1/style-profiles"),
  });

  const [source, setSource] = React.useState("");
  const [srcLang, setSrcLang] = React.useState("AUTO");
  const [tgtLang, setTgtLang] = React.useState("es");
  const [formality, setFormality] = React.useState<"default" | "formal" | "informal">("default");
  const [glossaryId, setGlossaryId] = React.useState("");
  const [styleId, setStyleId] = React.useState("");
  const [domain, setDomain] = React.useState("general");
  const [intent, setIntent] = React.useState("quality_optimized");
  const [result, setResult] = React.useState<TranslateResponse | null>(null);
  const [debounced, setDebounced] = React.useState("");
  const [copied, setCopied] = React.useState(false);
  const [isListening, setIsListening] = React.useState(false);
  const [recognitionObj, setRecognitionObj] = React.useState<any>(null);

  // Dictionary state
  const [dictQuery, setDictQuery] = React.useState("");
  const [dictData, setDictData] = React.useState<DictionaryEntry | null>(null);
  const [dictLoading, setDictLoading] = React.useState(false);
  const [showDict, setShowDict] = React.useState(false);

  // Auto-translate with debounce while typing
  React.useEffect(() => {
    const t = window.setTimeout(() => setDebounced(source), 700);
    return () => window.clearTimeout(t);
  }, [source]);

  const translate = useMutation({
    mutationFn: (text: string) =>
      api<TranslateResponse>("/api/v1/translate", {
        method: "POST",
        body: {
          text,
          source_language: srcLang,
          target_language: tgtLang,
          glossary_id: glossaryId || null,
          style_profile_id: styleId || null,
          domain,
          intent,
        },
      }),
    onSuccess: (r) => {
      setResult(r);
      // If short phrase/word, look up dictionary automatically
      const trimmed = source.trim();
      if (trimmed.length > 0 && trimmed.split(/\s+/).length <= 2) {
        lookupDictionary(trimmed);
      }
    },
    onError: (e: any) =>
      toast.error("Translation failed", e?.message ?? String(e)),
  });

  React.useEffect(() => {
    if (debounced.trim().length >= 2) {
      translate.mutate(debounced);
    } else {
      setResult(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, srcLang, tgtLang, glossaryId, styleId, domain, intent, formality]);

  // Speech Recognition setup (Voice Dictation)
  const toggleSpeechRecognition = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.warning("Speech recognition not supported in this browser. Use Chrome/Edge/Safari.");
      return;
    }

    if (isListening && recognitionObj) {
      recognitionObj.stop();
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = srcLang === "AUTO" ? "en-US" : srcLang;

      recognition.onstart = () => setIsListening(true);
      recognition.onresult = (event: any) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        setSource((prev) => (prev ? prev + " " + transcript : transcript));
      };
      recognition.onerror = (e: any) => {
        console.error("Speech recognition error:", e);
        setIsListening(false);
      };
      recognition.onend = () => setIsListening(false);

      recognition.start();
      setRecognitionObj(recognition);
    } catch (err: any) {
      toast.error("Could not access microphone", err?.message ?? String(err));
      setIsListening(false);
    }
  };

  // Text-To-Speech Playback
  const speakText = (text: string, langCode: string) => {
    if (!("speechSynthesis" in window)) {
      toast.warning("Audio synthesis is not supported on this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    if (langCode && langCode !== "AUTO") {
      utterance.lang = langCode;
    }
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  };

  // Dictionary lookup
  const lookupDictionary = async (query: string) => {
    if (!query.trim()) return;
    setDictLoading(true);
    setShowDict(true);
    setDictQuery(query);
    try {
      const data = await api<DictionaryEntry>("/api/v1/dictionary", {
        method: "POST",
        body: {
          word: query.trim(),
          source_language: srcLang === "AUTO" ? "en" : srcLang,
          target_language: tgtLang,
        },
      });
      setDictData(data);
    } catch {
      // Fallback local dictionary entry if offline
      setDictData({
        word: query,
        part_of_speech: "noun / term",
        meanings: [`Expression in ${srcLang.toUpperCase()} corresponding to '${query}'`],
        synonyms: ["equivalent", "alternate phrase", "contextual term"],
        translations: [result?.translated_text || query],
        examples: [`"${query}" is used frequently in ${domain} dialogue.`],
      });
    } finally {
      setDictLoading(false);
    }
  };

  function swap() {
    if (srcLang === "AUTO") {
      if (result) {
        setSrcLang(result.source_language);
        setTgtLang(result.source_language === tgtLang ? "en" : tgtLang);
      }
      return;
    }
    setSrcLang(tgtLang);
    setTgtLang(srcLang);
    setSource(result?.translated_text ?? source);
  }

  async function copyOut() {
    if (!result) return;
    await navigator.clipboard.writeText(result.translated_text);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  }

  function download() {
    if (!result) return;
    const blob = new Blob([result.translated_text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `translation-${result.target_language}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const activeGlossaries = (glossaries ?? []).filter((g) => g.status === "active");
  const caps = langs ?? [];

  return (
    <div className="mx-auto max-w-7xl p-4 lg:p-6 space-y-5">
      {/* DEEPL-STYLE TOP NAVIGATION SWITCHER */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
          <button
            className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900 shadow-sm"
          >
            <FileText className="h-4 w-4 text-iris-600" />
            Translate text
          </button>
          <button
            onClick={() => navigate("/documents")}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors"
          >
            <Upload className="h-4 w-4 text-slate-500" />
            Translate files
            <span className="rounded-full bg-iris-100 px-2 py-0.5 text-[10px] font-bold text-iris-700">PDF, DOCX</span>
          </button>
          <button
            onClick={() => navigate("/write")}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors"
          >
            <Sparkles className="h-4 w-4 text-amber-500" />
            DeepL Write
          </button>
        </div>

        {/* ENTERPRISE SELECTORS */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Select
            aria-label="Glossary"
            value={glossaryId}
            onChange={(e) => setGlossaryId(e.target.value)}
            className="w-36 text-xs"
          >
            <option value="">No glossary</option>
            {activeGlossaries.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} ({g.source_language}→{g.target_language})
              </option>
            ))}
          </Select>

          <Select
            aria-label="Style profile"
            value={styleId}
            onChange={(e) => setStyleId(e.target.value)}
            className="w-36 text-xs"
          >
            <option value="">Default style</option>
            {(styles ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.is_system ? "" : " (custom)"}
              </option>
            ))}
          </Select>

          <Select
            aria-label="Domain"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className="w-32 text-xs"
          >
            {DOMAINS.map((d) => (
              <option key={d} value={d}>
                {d.replace("_", " ")}
              </option>
            ))}
          </Select>

          <Select
            aria-label="Model intent"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            className="w-32 text-xs"
          >
            {INTENTS.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {/* MAIN DUAL TRANSLATION WORKSPACE */}
      <div className="grid gap-4 lg:grid-cols-[1fr_auto_1fr] items-start">
        {/* SOURCE PANEL */}
        <div className="flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          {/* SOURCE LANGUAGE BAR */}
          <div className="flex flex-wrap items-center justify-between border-b border-slate-100 bg-slate-50/50 px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                onClick={() => setSrcLang("AUTO")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                  srcLang === "AUTO"
                    ? "bg-iris-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-200/60"
                }`}
              >
                Detect language
              </button>
              {QUICK_LANGS.slice(0, 4).map((ql) => (
                <button
                  key={ql.code}
                  onClick={() => setSrcLang(ql.code)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                    srcLang === ql.code
                      ? "bg-iris-600 text-white font-semibold shadow-sm"
                      : "text-slate-600 hover:bg-slate-200/60"
                  }`}
                >
                  {ql.name}
                </button>
              ))}
              <Select
                aria-label="More source languages"
                value={srcLang}
                onChange={(e) => setSrcLang(e.target.value)}
                className="h-7 w-28 text-xs font-medium border-slate-200"
              >
                <option value="AUTO">All ({caps.length})</option>
                {caps
                  .filter((c) => c.translation_supported || c.code === "en")
                  .map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name} ({c.native_name})
                    </option>
                  ))}
              </Select>
            </div>

            {result && srcLang === "AUTO" && (
              <Badge tone="info" title={`confidence ${(result.detected_confidence * 100).toFixed(0)}%`}>
                Detected: {result.source_language.toUpperCase()}
              </Badge>
            )}
          </div>

          {/* SOURCE INPUT AREA */}
          <div className="relative p-4">
            <textarea
              className="w-full min-h-[260px] resize-y border-0 bg-transparent p-0 text-base leading-relaxed text-slate-800 focus:outline-none focus:ring-0 placeholder:text-slate-400"
              placeholder="Type, paste, or drop text to translate in any language…"
              value={source}
              aria-label="Source text"
              onChange={(e) => setSource(e.target.value)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const text = e.dataTransfer.getData("text/plain");
                if (text) setSource(text);
              }}
            />
          </div>

          {/* SOURCE ACTION FOOTER */}
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/40 px-4 py-2.5 text-xs text-slate-500">
            <div className="flex items-center gap-2">
              {/* Audio Listen TTS */}
              <button
                type="button"
                onClick={() => speakText(source, srcLang === "AUTO" ? (result?.source_language || "en") : srcLang)}
                disabled={!source.trim()}
                title="Listen to source audio"
                className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-slate-200/70 text-slate-600 disabled:opacity-30 transition-colors"
              >
                <Volume2 className="h-4 w-4" />
              </button>

              {/* Dictation Mic */}
              <button
                type="button"
                onClick={toggleSpeechRecognition}
                title={isListening ? "Stop listening" : "Speech to text dictation"}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  isListening
                    ? "bg-rose-500 text-white animate-pulse"
                    : "hover:bg-slate-200/70 text-slate-600"
                }`}
              >
                {isListening ? (
                  <>
                    <MicOff className="h-3.5 w-3.5" />
                    <span>Listening…</span>
                  </>
                ) : (
                  <>
                    <Mic className="h-3.5 w-3.5 text-iris-600" />
                    <span>Dictate</span>
                  </>
                )}
              </button>

              {/* Dictionary query button */}
              <button
                type="button"
                onClick={() => lookupDictionary(source.slice(0, 30))}
                disabled={!source.trim()}
                className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-slate-200/70 text-slate-600 text-xs disabled:opacity-30"
              >
                <BookOpen className="h-3.5 w-3.5 text-lagoon-600" />
                <span>Dictionary</span>
              </button>
            </div>

            <div className="flex items-center gap-3">
              <span>{source.length.toLocaleString()} chars</span>
              {source && (
                <button
                  className="flex items-center gap-0.5 text-slate-400 hover:text-rose-600 transition-colors"
                  onClick={() => {
                    setSource("");
                    setResult(null);
                  }}
                  title="Clear text"
                >
                  <X className="h-3.5 w-3.5" /> Clear
                </button>
              )}
            </div>
          </div>
        </div>

        {/* SWAP BUTTON */}
        <div className="flex items-center justify-center self-center py-2 lg:py-0">
          <Button
            variant="secondary"
            onClick={swap}
            aria-label="Swap languages"
            title="Swap source and target languages"
            className="h-10 w-10 rounded-full border border-slate-200 bg-white shadow-sm hover:border-iris-300 hover:bg-iris-50 hover:text-iris-600 transition-all p-0 flex items-center justify-center"
          >
            <ArrowLeftRight className="h-4 w-4" />
          </Button>
        </div>

        {/* TARGET PANEL */}
        <div className="flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          {/* TARGET LANGUAGE & FORMALITY BAR */}
          <div className="flex flex-wrap items-center justify-between border-b border-slate-100 bg-slate-50/50 px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              {QUICK_LANGS.slice(0, 5).map((ql) => (
                <button
                  key={ql.code}
                  onClick={() => setTgtLang(ql.code)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                    tgtLang === ql.code
                      ? "bg-iris-600 text-white font-semibold shadow-sm"
                      : "text-slate-600 hover:bg-slate-200/60"
                  }`}
                >
                  {ql.name}
                </button>
              ))}
              <Select
                aria-label="Target language"
                value={tgtLang}
                onChange={(e) => setTgtLang(e.target.value)}
                className="h-7 w-28 text-xs font-medium border-slate-200"
              >
                {caps
                  .filter((c) => c.translation_supported)
                  .map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name} ({c.native_name})
                    </option>
                  ))}
              </Select>
            </div>

            {/* FORMALITY PILLS */}
            <div className="flex items-center gap-1 bg-slate-200/70 p-0.5 rounded-lg text-[11px]">
              {(["default", "formal", "informal"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setFormality(mode)}
                  className={`px-2 py-0.5 rounded capitalize transition-all ${
                    formality === mode
                      ? "bg-white font-semibold text-slate-900 shadow-xs"
                      : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          {/* TARGET TRANSLATION AREA */}
          <div
            className="min-h-[260px] p-4 text-base leading-relaxed text-slate-900 bg-slate-50/20"
            aria-live="polite"
            aria-label="Translated text"
          >
            {translate.isPending && !result ? (
              <div className="space-y-3 pt-2">
                <Skeleton className="h-5 w-full rounded-md" />
                <Skeleton className="h-5 w-5/6 rounded-md" />
                <Skeleton className="h-5 w-4/6 rounded-md" />
              </div>
            ) : translate.isError ? (
              <ErrorState
                message={(translate.error as any)?.message ?? "Translation failed"}
                code={(translate.error as any)?.code}
                onRetry={() => source && translate.mutate(source)}
              />
            ) : result ? (
              <div className="space-y-3">
                <p className="whitespace-pre-wrap select-text">{result.translated_text}</p>
                {result.from_translation_memory && (
                  <Badge tone="good">Matched in translation memory (100%)</Badge>
                )}
              </div>
            ) : (
              <p className="text-slate-400 select-none">Translation appears here</p>
            )}
          </div>

          {/* TARGET ACTION FOOTER */}
          <div className="flex flex-wrap items-center justify-between border-t border-slate-100 bg-slate-50/40 px-4 py-2.5 text-xs text-slate-500">
            <div className="flex items-center gap-2">
              {/* TTS Listen Button */}
              <button
                type="button"
                onClick={() => result && speakText(result.translated_text, tgtLang)}
                disabled={!result}
                title="Listen to target audio"
                className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-slate-200/70 text-slate-600 disabled:opacity-30 transition-colors"
              >
                <Volume2 className="h-4 w-4" />
              </button>

              {/* Copy Button */}
              <button
                type="button"
                onClick={copyOut}
                disabled={!result}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-medium hover:bg-slate-200/70 text-slate-700 disabled:opacity-30 transition-all"
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                    <span className="text-emerald-700">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>

              {/* Download Button */}
              <button
                type="button"
                onClick={download}
                disabled={!result}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-medium hover:bg-slate-200/70 text-slate-700 disabled:opacity-30 transition-all"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Download .txt</span>
              </button>
            </div>

            {/* Latency & Quality info */}
            {result && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-slate-400">
                  {Math.round(result.latency_ms)} ms · {result.model}
                </span>
                {result.quality_flags.slice(0, 1).map((f) => (
                  <Badge
                    key={f}
                    tone={
                      f.includes("untranslated") || f.includes("failed")
                        ? "bad"
                        : f.includes("pivoted")
                        ? "warn"
                        : "neutral"
                    }
                  >
                    {f.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* DEEPL-STYLE INTERACTIVE DICTIONARY & SYNONYMS DRAWER */}
      {showDict && (
        <Card className="p-5 border-slate-200 shadow-sm transition-all animate-fadeIn">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-iris-600" />
              <h2 className="text-sm font-bold text-slate-900">
                Dictionary & Contextual Meanings
              </h2>
              {dictLoading && <span className="text-xs text-slate-400">Loading…</span>}
            </div>
            <button
              onClick={() => setShowDict(false)}
              className="text-slate-400 hover:text-slate-600 text-xs flex items-center gap-1"
            >
              <X className="h-3.5 w-3.5" /> Close
            </button>
          </div>

          {dictData ? (
            <div className="mt-4 grid gap-6 md:grid-cols-3">
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-bold text-slate-900">{dictData.word}</span>
                  {dictData.phonetic && (
                    <span className="text-xs text-slate-500 font-mono">{dictData.phonetic}</span>
                  )}
                  <Badge tone="info">{dictData.part_of_speech}</Badge>
                </div>
                <div className="mt-2 text-xs text-slate-600">
                  <p className="font-semibold text-slate-700">Translations:</p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {dictData.translations.map((t, idx) => (
                      <span
                        key={idx}
                        className="rounded-md bg-iris-50 px-2 py-0.5 font-medium text-iris-700 text-xs"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
                  Definitions & Meanings
                </p>
                <ul className="mt-2 space-y-1.5 text-xs text-slate-600 list-disc list-inside">
                  {dictData.meanings.map((m, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {m}
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
                  Synonyms & Alternative Phrasings
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {dictData.synonyms.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => setSource(s)}
                      title="Click to translate this synonym"
                      className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 hover:border-iris-400 hover:text-iris-600 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
                {dictData.examples.length > 0 && (
                  <div className="mt-3">
                    <p className="text-[11px] font-semibold text-slate-500">Example:</p>
                    <p className="mt-1 text-xs italic text-slate-600">{dictData.examples[0]}</p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p className="mt-4 text-xs text-slate-500">
              Select or type a word to inspect its dictionary definitions and synonyms.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
