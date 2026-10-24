import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  ArrowLeftRight,
  BookOpen,
  Check,
  Clock,
  Copy,
  Download,
  FileText,
  Globe,
  Mic,
  Radio,
  Sparkles,
  Trash2,
  Volume2,
  X,
  Upload,
  Columns2,
  Rows2,
  Zap,
  Info,
  BookmarkPlus,
  BookmarkCheck,
} from "lucide-react";
import { TranslationBenchmarkModal } from "../components/TranslationBenchmarkModal";
import { api, friendlyMessage } from "../lib/api";
import type { NormalizedTranslation } from "../lib/types";
import {
  isUsableTranslation,
  normalizeTranslationResponse,
  translateCanonical,
} from "../lib/translation";
import { streamLiveTranslation } from "../lib/liveTranslation";
import { useShortcuts } from "../lib/shortcuts";
import { LanguagePicker } from "../components/LanguagePicker";
import { SelectionTranslate } from "../components/SelectionTranslate";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, ErrorState } from "../components/ui";
import { toast } from "../stores/toasts";
import {
  RECENTS_LIMIT,
  loadRecents,
  relativeTime,
  saveRecents,
  withRecent,
  type RecentTranslation,
} from "../lib/recentTranslations";

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
  { value: "cost_optimized",    label: "Low cost" },
  { value: "private_only",      label: "Private only" },
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

/* ─── Small helpers ───────────────────────────────────────────────── */

function TabSwitcher({ active, onChange, tabs }: {
  active: string;
  onChange: (v: string) => void;
  tabs: { value: string; label: string; icon?: React.ReactNode; badge?: React.ReactNode }[];
}) {
  const groupId = React.useId();
  return (
    <div className="flex items-center gap-0.5" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={active === t.value}
          onClick={() => onChange(t.value)}
          className={`
            relative inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium
            transition-colors duration-150 active:scale-[0.98]
            ${active === t.value
              ? "text-dl-navy"
              : "text-dl-muted hover:bg-white/60 hover:text-dl-navy"}
          `}
        >
          {active === t.value && (
            <motion.span
              layoutId={`tabswitcher-${groupId}`}
              transition={{ type: "spring", bounce: 0, duration: 0.3 }}
              className="absolute inset-0 rounded-lg border border-dl-border bg-white shadow-xs"
            />
          )}
          <span className="relative z-10 inline-flex items-center gap-1.5">
            {t.icon}
            {t.label}
            {t.badge}
          </span>
        </button>
      ))}
    </div>
  );
}

function LangBar({
  selected,
  onSelect,
  showAuto = false,
  langs,
  detected,
  detectedConfidence,
  right,
}: {
  selected: string;
  onSelect: (code: string) => void;
  showAuto?: boolean;
  langs: { code: string; name: string; native_name?: string }[];
  detected?: string;
  detectedConfidence?: number | null;
  right?: React.ReactNode;
}) {
  // If selected language is not in default QUICK_LANGS (and not AUTO), dynamically include it in the tab bar
  const selectedLangObj = React.useMemo(() => {
    if (selected === "AUTO") return null;
    return langs.find((l) => l.code === selected);
  }, [selected, langs]);

  const quickItems = React.useMemo(() => {
    const list = [...QUICK_LANGS.slice(0, showAuto ? 3 : 4)];
    if (selectedLangObj && !list.some((q) => q.code === selectedLangObj.code)) {
      list.push({
        code: selectedLangObj.code,
        name: selectedLangObj.native_name && selectedLangObj.native_name !== selectedLangObj.name
          ? `${selectedLangObj.name} (${selectedLangObj.native_name})`
          : selectedLangObj.name,
      });
    }
    return list;
  }, [selectedLangObj, showAuto]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-dl-border bg-[#FAFBFC] px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-0.5">
        {showAuto && (
          <button
            type="button"
            onClick={() => onSelect("AUTO")}
            className={selected === "AUTO" ? "lang-pill-active" : "lang-pill"}
          >
            Detect language
          </button>
        )}
        {quickItems.map((ql) => (
          <button
            key={ql.code}
            type="button"
            onClick={() => onSelect(ql.code)}
            className={selected === ql.code ? "lang-pill-active" : "lang-pill"}
          >
            {ql.name}
          </button>
        ))}
        <LanguagePicker
          languages={langs.filter((c: any) => c.translation_supported || c.code === "en")}
          value={selected}
          onSelect={onSelect}
          ariaLabel={showAuto ? "More source languages" : "More target languages"}
          triggerLabel="More ▾"
        />
        {detected && (
          <>
            <Badge tone="info" title="Auto-detected language">
              Detected: {detected.toUpperCase()}
            </Badge>
            {detectedConfidence !== null && detectedConfidence !== undefined && detectedConfidence < 0.75 && (
              <Badge tone="warn" title="The backend detected this language with low confidence">
                Low confidence ({Math.round(detectedConfidence * 100)}%)
              </Badge>
            )}
          </>
        )}
      </div>
      {right}
    </div>
  );
}

/*
const SCRIPT_RANGES: [RegExp, string][] = [
  [/[\u0900-\u097F]/, "hi"],
  [/[\u0980-\u09FF]/, "bn"],
  [/[\u0B80-\u0BFF]/, "ta"],
  [/[\u0C00-\u0C7F]/, "te"],
  [/[\u3040-\u30FF]/, "ja"],
  [/[\u4E00-\u9FFF]/, "zh"],
  [/[\uAC00-\uD7AF]/, "ko"],
  [/[\u0400-\u04FF]/, "ru"],
  [/[\u0600-\u06FF]/, "ar"],
];

const FUNCTION_WORDS: Record<string, string[]> = {
  en: [
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not",
    "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from",
    "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would",
    "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
    "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
    "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
    "even", "new", "want", "because", "any", "these", "give", "day", "most", "us", "is",
    "am", "are", "was", "were", "name", "hello", "welcome", "please", "thanks", "thank"
  ],
  es: [
    "el", "la", "de", "que", "y", "en", "un", "ser", "se", "no", "haber", "por", "con",
    "su", "para", "como", "estar", "tener", "le", "lo", "todo", "pero", "mas", "hacer",
    "o", "poder", "decir", "este", "ir", "otro", "ese", "si", "me", "ya", "ver",
    "porque", "dar", "cuando", "muy", "sin", "vez", "mucho", "saber", "sobre", "mi",
    "nombre", "es", "hola", "gracias", "buenos", "dias"
  ],
  de: [
    "der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich", "des", "auf",
    "für", "ist", "im", "dem", "nicht", "ein", "eine", "als", "auch", "es", "an",
    "werden", "aus", "er", "hat", "dass", "sie", "nach", "wird", "bei", "einer", "um",
    "am", "sind", "noch", "wie", "einem", "über", "einen", "so", "zum", "war", "haben",
    "nur", "oder", "aber", "vor", "zur", "bis", "mein", "meine", "name", "heisse",
    "hallo", "guten", "morgen", "danke"
  ],
  fr: [
    "de", "la", "le", "et", "les", "des", "en", "un", "du", "une", "que", "est", "pour",
    "qui", "dans", "a", "par", "plus", "pas", "au", "sur", "ne", "ce", "avec", "se",
    "sont", "ou", "comme", "mais", "nous", "sa", "vous", "tout", "faire", "son", "il",
    "elle", "je", "mon", "ma", "mes", "nom", "appelle", "bonjour", "merci", "salut"
  ],
  it: [
    "di", "e", "il", "la", "che", "in", "un", "per", "una", "non", "del", "dei", "a",
    "al", "si", "da", "della", "con", "ha", "ed", "delle", "sono", "gli", "nel", "le",
    "mio", "mia", "nome", "chiamo", "ciao", "grazie"
  ],
  pt: [
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com", "não", "uma",
    "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi", "ao",
    "ele", "das", "tem", "à", "seu", "sua", "ou", "quando", "muito", "meu", "minha",
    "nome", "ola", "obrigado"
  ]
};

*/
/*
async function fetchNeuralTranslation(
  text: string,
  srcLang: string,
  tgtLang: string,
  formality: string = "default"
): Promise<NormalizedTranslation> {
  const t0 = performance.now();
  const src = (srcLang || "en").toLowerCase().split("-")[0];
  const tgt = (tgtLang || "de").toLowerCase().split("-")[0];

  // Pre-translation typo normalization for high-accuracy translation
  const cleanQueryText = text
    .replace(/\b(?:beteen|betten|bettewn|betwen|betweeen|betwene|betwn|bettn|betwaseen|betwassseen)\b/gi, "between")
    .replace(/\b(?:nme|nae|nam)\b/gi, "name")
    .replace(/\b(?:rea|aer)\b/gi, "are")
    .replace(/\b(?:mondey|mondy)\b/gi, "Monday")
    .replace(/\b(?:tueday|tuseday)\b/gi, "Tuesday")
    .replace(/\b(?:wensday|wednsday)\b/gi, "Wednesday")
    .replace(/\b(?:thrusday|thurday|thursdy)\b/gi, "Thursday")
    .replace(/\b(?:fridy|fryday)\b/gi, "Friday")
    .replace(/\b(?:satday|saterday)\b/gi, "Saturday")
    .replace(/\b(?:sundy|sunnday)\b/gi, "Sunday")
    .replace(/\baman\b/g, "Aman")
    .replace(/\b(?:speling|speeling|spellinge|spelin)\b/gi, "spelling")
    .replace(/\b(?:transaltion|transaltions|traslation|traslations|translaton)\b/gi, "translation")
    .replace(/\b(?:translater|translaters)\b/gi, "translator")
    .replace(/\b(?:impove|inprove)\b/gi, "improve")
    .replace(/\b(?:impovement|inprovement)\b/gi, "improvement")
    .replace(/\byou\s+(day|name|time|work|email|account|profile|friend|language|job|task)\b/gi, "your $1")
    .replace(/\bin\s+during\b/gi, "during")
    .replace(/\bgive\s+correct\s+ans\b/gi, "give the correct answer");

  const introMatch = cleanQueryText.match(/^(?:my name is|i am|i'm)\s+(.+)$/i);
  let primary = "";
  let alts: string[] = [];

  if (introMatch) {
    const name = introMatch[1].trim();
    if (tgt === "de") {
      primary = `Mein Name ist ${name}`;
      alts = [`Ich heiße ${name}`];
    } else if (tgt === "es") {
      primary = `Mi nombre es ${name}`;
      alts = [`Me llamo ${name}`];
    } else if (tgt === "fr") {
      primary = `Je m'appelle ${name}`;
      alts = [`Mon nom est ${name}`];
    } else if (tgt === "it") {
      primary = `Mi chiamo ${name}`;
      alts = [`Il mio nome è ${name}`];
    } else if (tgt === "pt") {
      primary = `Meu nome é ${name}`;
    } else if (tgt === "hi") {
      primary = `मेरा नाम ${name} है`;
    }
  }

  let modelName = "neural-mymemory-v1";

  // 1. Try MyMemory API
  if (!primary) {
    try {
      const url = ""; // legacy browser provider removed
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const raw = data?.responseData?.translatedText;
        if (raw && !raw.startsWith("MYMEMORY WARNING")) {
          primary = raw;
          modelName = "neural-mymemory-v1";
          if (Array.isArray(data?.matches)) {
            const seen = new Set([primary.toLowerCase()]);
            for (const m of data.matches) {
              const cand = (m.translation || "").trim();
              if (cand && !seen.has(cand.toLowerCase()) && !cand.toLowerCase().startsWith("mymemory")) {
                seen.add(cand.toLowerCase());
                alts.push(cand);
                if (alts.length >= 3) break;
              }
            }
          }
        }
      }
    } catch (e) {
      console.warn("MyMemory fetch error:", e);
    }
  }

  // 2. Try Google Web MT if MyMemory is rate-limited or failed
  if (!primary) {
    try {
      const gUrl = ""; // legacy browser provider removed
      const gRes = await fetch(gUrl);
      if (gRes.ok) {
        const gData = await gRes.json();
        if (Array.isArray(gData) && Array.isArray(gData[0])) {
          const joined = gData[0].map((chunk: any) => chunk[0]).filter(Boolean).join("").trim();
          if (joined) {
            primary = joined;
            modelName = "google-nmt-web";
          }
        }
      }
    } catch (e) {
      console.warn("Google Web MT fetch error:", e);
    }
  }

  // 3. Try Client Phrase Dictionary for common phrases
  if (!primary) {
    const norm = cleanQueryText.toLowerCase().trim().replace(/[?!.,]+$/, "");
    const COMMON_CLIENT_TRANSLATIONS: Record<string, Record<string, string>> = {
      "hello": { es: "Hola", de: "Hallo", fr: "Bonjour", hi: "नमस्ते", it: "Ciao", pt: "Olá" },
      "hello world": { es: "Hola Mundo", de: "Hallo Welt", fr: "Bonjour le monde", hi: "नमस्ते दुनिया", it: "Ciao mondo", pt: "Olá mundo" },
      "hello, how are you today": { es: "Hola, ¿cómo estás hoy?", de: "Hallo, wie geht es Ihnen heute?", fr: "Bonjour, comment allez-vous aujourd'hui ?", hi: "नमस्ते, आज आप कैसे हैं?", it: "Ciao, come stai oggi?", pt: "Olá, como você está hoje?" },
      "how are you": { es: "¿Cómo estás?", de: "Wie geht es Ihnen?", fr: "Comment allez-vous ?", hi: "आप कैसे हैं?", it: "Come stai?", pt: "Como você está?" },
      "how are you today": { es: "¿Cómo estás hoy?", de: "Wie geht es Ihnen heute?", fr: "Comment allez-vous aujourd'hui ?", hi: "आज आप कैसे हैं?", it: "Come stai oggi?", pt: "Como você está hoje?" },
      "good morning": { es: "Buenos días", de: "Guten Morgen", fr: "Bonjour", hi: "शुभ प्रभात", it: "Buongiorno", pt: "Bom dia" },
      "thank you": { es: "Gracias", de: "Danke", fr: "Merci", hi: "धन्यवाद", it: "Grazie", pt: "Obrigado" },
      "thank you very much": { es: "Muchas gracias", de: "Vielen Dank", fr: "Merci beaucoup", hi: "बहुत बहुत धन्यवाद", it: "Grazie mille", pt: "Muito obrigado" },
      "welcome": { es: "Bienvenido", de: "Willkommen", fr: "Bienvenue", hi: "स्वागत है", it: "Benvenuto", pt: "Bem-vindo" },
      "नमस्ते": { en: "Hello", es: "Hola", de: "Hallo", fr: "Bonjour" },
      "नमस्ते दुनिया": { en: "Hello world", es: "Hola Mundo", de: "Hallo Welt", fr: "Bonjour le monde" },
      "आप कैसे हैं": { en: "How are you?", es: "¿Cómo estás?", de: "Wie geht es Ihnen?", fr: "Comment allez-vous ?" },
      "शुभ प्रभात": { en: "Good morning", es: "Buenos días", de: "Guten Morgen", fr: "Bonjour" },
      "धन्यवाद": { en: "Thank you", es: "Gracias", de: "Danke", fr: "Merci" },
    };
    if (COMMON_CLIENT_TRANSLATIONS[norm]?.[tgt]) {
      primary = COMMON_CLIENT_TRANSLATIONS[norm][tgt];
      modelName = "linguistic-dictionary-v1";
    }
  }

  if (primary && text.length > 0 && text[0] === text[0].toUpperCase()) {
    primary = primary.charAt(0).toUpperCase() + primary.slice(1);
  }

  if (tgt === "de") {
    if (formality === "formal") {
      primary = primary.replace(/\bdu\b/gi, "Sie").replace(/\bdir\b/gi, "Ihnen").replace(/\bdein\b/gi, "Ihr");
    } else if (formality === "informal") {
      primary = primary.replace(/\bSie\b/g, "du").replace(/\bIhnen\b/g, "dir").replace(/\bIhr\b/g, "dein");
    }
  } else if (tgt === "es") {
    if (formality === "formal") {
      primary = primary.replace(/\btú\b/gi, "usted").replace(/\bte\b/gi, "le");
    } else if (formality === "informal") {
      primary = primary.replace(/\busted\b/gi, "tú").replace(/\ble\b/gi, "te");
    }
  }

  const isUntranslated = !primary || (primary.trim() === text.trim() && src !== tgt);

  return {
    translation_id: isUntranslated ? "fallback-" + Date.now() : "neural-" + Date.now(),
    source_language: src,
    target_language: tgt,
    source_text: text,
    translated_text: primary || text,
    model: isUntranslated ? "untranslated-fallback" : modelName,
    provider: isUntranslated ? "source_fallback" : "neural_online",
    latency_ms: Math.round(performance.now() - t0),
    quality_flags: isUntranslated ? ["untranslated_fallback"] : ["neural_mt", "high_quality"],
    from_translation_memory: false,
    detected_confidence: isUntranslated ? 0.0 : 0.98,
    alternatives: alts,
  };
}

*/
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
  const sourceRef = React.useRef<HTMLTextAreaElement | null>(null);
  const [srcLang, setSrcLang] = React.useState("AUTO");
  const [tgtLang, setTgtLang] = React.useState("de");
  const [detectedLanguage, setDetectedLanguage] = React.useState("");
  const [detectedConfidence, setDetectedConfidence] = React.useState<number | null>(null);

  const handleSelectSrcLang = (code: string) => {
    if (code !== "AUTO" && code === tgtLang) {
      const prevSrc = srcLang !== "AUTO" && srcLang !== code ? srcLang : "en";
      const fallbackTarget = prevSrc === code ? (code === "en" ? "es" : "en") : prevSrc;
      setTgtLang(fallbackTarget);
    }
    setSrcLang(code);
  };

  const handleSelectTgtLang = (code: string) => {
    if (srcLang !== "AUTO" && code === srcLang) {
      const nextSrc = tgtLang !== code ? tgtLang : (code === "en" ? "es" : "en");
      setSrcLang(nextSrc);
    } else if (srcLang === "AUTO" && detectedLanguage && code.toLowerCase() === detectedLanguage.toLowerCase()) {
      const altTarget = code === "en" ? "es" : "en";
      setSrcLang(code);
      code = altTarget;
    }
    setTgtLang(code);
  };
  const [formality, setFormality] = React.useState<"default" | "formal" | "informal">("default");
  const [glossaryId, setGlossaryId] = React.useState("");
  const [styleId, setStyleId] = React.useState("");
  const [domain, setDomain] = React.useState("general");
  const [intent, setIntent] = React.useState("quality_optimized");
  const [result, setResult] = React.useState<NormalizedTranslation | null>(null);
  const [debounced, setDebounced] = React.useState("");
  const [copied, setCopied] = React.useState(false);
  const [isSpeaking, setIsSpeaking] = React.useState(false);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  // Layout mode (DeepL side-by-side or upper/lower stacked)
  const [layoutMode, setLayoutMode] = React.useState<"side-by-side" | "stacked">(() => {
    try {
      return (localStorage.getItem("talkflow_translate_layout") as "side-by-side" | "stacked") || "side-by-side";
    } catch {
      return "side-by-side";
    }
  });
  const [showBenchmark, setShowBenchmark] = React.useState(false);

  // Notes & Annotations Save Modal State
  const [showNoteModal, setShowNoteModal] = React.useState(false);
  const [noteTitle, setNoteTitle] = React.useState("");
  const [noteContent, setNoteContent] = React.useState("");
  const [noteTagInput, setNoteTagInput] = React.useState("");
  const [noteTags, setNoteTags] = React.useState<string[]>(["vocabulary"]);
  const [savingNote, setSavingNote] = React.useState(false);

  // Restore prefilled text/languages when directed from /notes
  React.useEffect(() => {
    const pSrc = sessionStorage.getItem("talkflow_prefill_source");
    const pSrcL = sessionStorage.getItem("talkflow_prefill_src_lang");
    const pTgtL = sessionStorage.getItem("talkflow_prefill_tgt_lang");
    if (pSrc) {
      setSource(pSrc);
      if (pSrcL) setSrcLang(pSrcL);
      if (pTgtL) setTgtLang(pTgtL);
      sessionStorage.removeItem("talkflow_prefill_source");
      sessionStorage.removeItem("talkflow_prefill_src_lang");
      sessionStorage.removeItem("talkflow_prefill_tgt_lang");
    }
  }, []);

  const openSaveNoteModal = () => {
    if (!result) return;
    setNoteTitle(source.slice(0, 40));
    setNoteContent("");
    setNoteTags(["vocabulary"]);
    setShowNoteModal(true);
  };

  const handleSaveNote = async () => {
    if (!result) return;
    setSavingNote(true);
    try {
      await api("/api/v1/notes", {
        method: "POST",
        body: {
          title: noteTitle.trim() || source.slice(0, 40),
          source_text: source.trim(),
          translated_text: result.translated_text.trim(),
          source_lang: result.source_language || (srcLang === "AUTO" ? (detectedLanguage || "en") : srcLang),
          target_lang: result.target_language || tgtLang,
          note: noteContent.trim(),
          tags: noteTags,
          is_favorite: true,
        },
      });
      toast.success("Note & translation saved to library!");
      setShowNoteModal(false);
    } catch (err) {
      toast.error("Failed to save note", friendlyMessage(err));
    } finally {
      setSavingNote(false);
    }
  };

  const updateLayout = (mode: "side-by-side" | "stacked") => {
    setLayoutMode(mode);
    try {
      localStorage.setItem("talkflow_translate_layout", mode);
    } catch {}
  };

  // Live translation (SSE): a provisional draft appears as soon as the stable
  // prefix is translated, then the final pass revises it. The previous result
  // stays on screen until a newer one arrives, so typing never flickers.
  const [live, setLive] = React.useState(true);
  const [draft, setDraft] = React.useState<NormalizedTranslation | null>(null);
  const [livePhase, setLivePhase] = React.useState<"idle" | "waiting" | "streaming">("idle");
  const [liveError, setLiveError] = React.useState<{ message: string; code?: string } | null>(null);
  const [liveStats, setLiveStats] = React.useState<{ ttfd_ms: number | null; total_ms: number } | null>(null);
  const liveAbort = React.useRef<AbortController | null>(null);
  const liveSeq = React.useRef(0);
  const liveLastKey = React.useRef("");

  // Recent translations (persisted client-side)
  const [recents, setRecents] = React.useState<RecentTranslation[]>(() => loadRecents());

  // Dictionary
  const [dictData, setDictData] = React.useState<DictionaryEntry | null>(null);
  const [dictLoading, setDictLoading] = React.useState(false);
  const [showDict, setShowDict] = React.useState(false);

  // Debounce (legacy path only — live mode streams on its own timer below)
  React.useEffect(() => {
    const t = window.setTimeout(() => setDebounced(source), 700);
    return () => window.clearTimeout(t);
  }, [source]);

  React.useEffect(() => {
    if (srcLang !== "AUTO") {
      setDetectedLanguage("");
      setDetectedConfidence(null);
    }
  }, [srcLang]);

  const translate = useMutation({
    mutationFn: async (text: string) => {
      const { response, sourceLanguage, detectedConfidence: confidence } = await translateCanonical(
        text,
        srcLang,
        tgtLang,
        {
          glossary_id: glossaryId || null,
          style_profile_id: styleId || null,
          domain,
          intent,
          formality,
        },
      );
      if (srcLang.toLowerCase() === "auto") {
        setDetectedLanguage(sourceLanguage);
        setDetectedConfidence(confidence);
      }
      return response;
    },
    // Keep the previous translation visible while a new one is in flight
    // (DeepL-style stale-while-revalidate); clearing it here caused flicker.
    onSuccess: (normalized: NormalizedTranslation) => {
      setResult(normalized);
      const trimmed = source.trim();
      if (trimmed.length > 0 && trimmed.split(/\s+/).length <= 2) {
        lookupDictionary(trimmed);
      }
    },
    onError: (e: unknown) => {
      const msg = friendlyMessage(e).toLowerCase();
      if (msg.includes("equals the target") || msg.includes("must differ")) {
        const trimmed = source.trim();
        setResult({
          translation_id: "identity",
          from_translation_memory: false,
          source_language: srcLang === "AUTO" ? (detectedLanguage || tgtLang) : srcLang,
          target_language: tgtLang,
          source_text: trimmed,
          translated_text: trimmed,
          model: "identity/same_language",
          provider: "identity",
          latency_ms: 0,
          quality_flags: ["source_equals_target"],
          detected_confidence: 1.0,
          alternatives: [],
          glossary_note: null,
        });
        return;
      }
      toast.error("Translation unavailable", friendlyMessage(e));
    },
  });

  React.useEffect(() => {
    if (live) return;
    if (debounced.trim().length >= 2) {
      translate.mutate(debounced);
    } else {
      setResult(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, srcLang, tgtLang, glossaryId, styleId, domain, intent, formality, live]);

  /** Start a live (SSE) translation; supersedes any in-flight request. */
  async function runLiveSource(text: string) {
    const controller = new AbortController();
    liveAbort.current?.abort();
    liveAbort.current = controller;
    const seq = ++liveSeq.current;
    const current = () => seq === liveSeq.current && !controller.signal.aborted;
    const trimmed = text.trim();
    if (!trimmed) return;

    setLivePhase("streaming");
    setLiveError(null);

    try {
      await streamLiveTranslation(
        {
          text: trimmed,
          source_language: srcLang.toLowerCase() === "auto" ? "AUTO" : srcLang,
          target_language: tgtLang,
          glossary_id: glossaryId || null,
          style_profile_id: styleId || null,
          domain,
          intent,
          formality,
        },
        {
          onMeta: (meta) => {
            if (!current()) return;
            if (srcLang.toLowerCase() === "auto" && meta.phase === "ready") {
              setDetectedLanguage(meta.source_language);
              setDetectedConfidence(meta.detected_confidence);
              if (meta.source_language && meta.source_language.toLowerCase() === tgtLang.toLowerCase()) {
                const alt = tgtLang.toLowerCase() === "en" ? "es" : "en";
                setTgtLang(alt);
              }
            }
          },
          onDraft: (d) => {
            if (!current()) return;
            const normalized = normalizeTranslationResponse({
              request_id: d.request_id,
              translations: [{
                translation_id: d.request_id,
                source_language: d.source_language,
                target_language: d.target_language,
                source_text: trimmed,
                translated_text: d.text,
                model: d.model,
                provider: d.provider,
                latency_ms: d.latency_ms,
                quality_flags: d.quality_flags,
              }],
            });
            if (isUsableTranslation(normalized, trimmed, srcLang, tgtLang)) {
              setDraft(normalized);
            }
          },
          onDone: (done) => {
            if (!current()) return;
            const normalized = normalizeTranslationResponse({
              request_id: done.request_id,
              translations: done.translations,
              detected_confidence: done.detected_confidence ?? undefined,
            });
            setDraft(null);
            setLiveError(null);
            setLiveStats({ ttfd_ms: done.ttfd_ms, total_ms: done.total_ms });
            setLivePhase("idle");
            setResult(normalized);
            if (srcLang.toLowerCase() === "auto" && normalized.source_language) {
              setDetectedLanguage(normalized.source_language);
            }
            if (trimmed.split(/\s+/).length <= 2) lookupDictionary(trimmed);
          },
          onError: (err) => {
            if (!current()) return;
            setDraft(null);
            setLivePhase("idle");
            const msg = (err.message || "").toLowerCase();
            if (msg.includes("equals the target") || msg.includes("must differ") || err.code === "unsupported_language") {
              setLiveError(null);
              setResult({
                translation_id: "identity",
          from_translation_memory: false,
                source_language: srcLang === "AUTO" ? (detectedLanguage || tgtLang) : srcLang,
                target_language: tgtLang,
                source_text: trimmed,
                translated_text: trimmed,
                model: "identity/same_language",
                provider: "identity",
                latency_ms: 0,
                quality_flags: ["source_equals_target"],
                detected_confidence: 1.0,
                alternatives: [],
                glossary_note: null,
              });
              return;
            }
            setLiveError({ message: err.message || "Translation failed.", code: err.code });
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted || seq !== liveSeq.current) return;
      liveLastKey.current = "";
      setDraft(null);
      setLivePhase("idle");
      const msg = friendlyMessage(err).toLowerCase();
      if (msg.includes("equals the target") || msg.includes("must differ") || (err as any)?.code === "unsupported_language") {
        setLiveError(null);
        setResult({
          translation_id: "identity",
          from_translation_memory: false,
          source_language: srcLang === "AUTO" ? (detectedLanguage || tgtLang) : srcLang,
          target_language: tgtLang,
          source_text: trimmed,
          translated_text: trimmed,
          model: "identity/same_language",
          provider: "identity",
          latency_ms: 0,
          quality_flags: ["source_equals_target"],
          detected_confidence: 1.0,
          alternatives: [],
          glossary_note: null,
        });
        return;
      }
      setLiveError({ message: friendlyMessage(err), code: (err as any)?.code });
    }
  }

  // Live mode: every edit supersedes the in-flight stream, then the settled
  // text is translated after a short pause (not a 700 ms submit-style wait).
  React.useEffect(() => {
    const stop = () => {
      liveAbort.current?.abort();
      liveAbort.current = null;
      liveSeq.current += 1;
    };

    if (!live) {
      liveLastKey.current = "";
      stop();
      return;
    }

    const text = source.trim();
    if (text.length < 2) {
      liveLastKey.current = "";
      stop();
      setDraft(null);
      setLiveError(null);
      setLiveStats(null);
      setLivePhase("idle");
      setResult(null);
      return;
    }

    // A duplicated change event (same text, same pair) must not abort and
    // restart a stream that is already in flight for it.
    const key = `${srcLang}|${tgtLang}|${glossaryId}|${styleId}|${domain}|${intent}|${formality}|${text}`;
    if (key === liveLastKey.current) return;
    liveLastKey.current = key;

    stop();
    setLiveError(null);
    setLivePhase("waiting");
    const timer = window.setTimeout(() => { void runLiveSource(text); }, 180);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, srcLang, tgtLang, glossaryId, styleId, domain, intent, formality, live]);

  React.useEffect(() => () => { liveAbort.current?.abort(); }, []);

  // Audio output is always provider-backed. The browser never synthesizes or
  // substitutes speech when the server-side TTS provider is unavailable.
  const speakText = async (text: string, langCode: string) => {
    if (!text.trim()) return;
    if (isSpeaking && audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
      setIsSpeaking(false);
      return;
    }

    try {
      const response = await api<{ audio_base64?: string; format?: string }>("/api/v1/voice/tts", {
        method: "POST",
        body: { text: text.trim(), language: langCode === "AUTO" ? "en" : langCode },
        timeoutMs: 9000,
      });
      if (!response.audio_base64) throw new Error("Translated audio is unavailable.");

      const mime = response.format === "wav" ? "audio/wav" : "audio/mpeg";
      const audio = new Audio(`data:${mime};base64,${response.audio_base64}`);
      audioRef.current = audio;
      audio.onended = () => {
        audioRef.current = null;
        setIsSpeaking(false);
      };
      audio.onerror = () => {
        audioRef.current = null;
        setIsSpeaking(false);
      };
      setIsSpeaking(true);
      await audio.play();
    } catch (err) {
      setIsSpeaking(false);
      toast.error("Audio unavailable", friendlyMessage(err));
    }
  };

  const lookupDictionary = async (query: string) => {
    if (!query.trim()) return;
    setDictLoading(true);
    setShowDict(true);
    try {
      const data = await api<DictionaryEntry>("/api/v1/dictionary", {
        method: "POST",
        body: {
          word: query.trim(),
          // The dictionary endpoint takes `source_lang`/`target_lang`; the
          // `source_language`/`target_language` names were dropped by
          // pydantic, so every lookup silently ran en->en.
          source_lang: srcLang === "AUTO" ? (detectedLanguage || result?.source_language || "") : srcLang,
          target_lang: tgtLang,
        },
      });
      setDictData(data);
    } catch {
      setDictData(null);
    } finally {
      setDictLoading(false);
    }
  };

  function swap() {
    const curSrc = srcLang === "AUTO" ? (detectedLanguage || (result ? result.source_language : "en")) : srcLang;
    const curTgt = tgtLang;
    setSrcLang(curTgt);
    setTgtLang(curSrc === curTgt ? (curTgt === "en" ? "es" : "en") : curSrc);
    if (result?.translated_text) {
      setSource(result.translated_text);
    }
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
    const url = URL.createObjectURL(blob);
    a.href = url;
    a.download = `translation-${result.target_language}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 200);
  }

  function commitRecent(res: NormalizedTranslation) {
    const srcText = (res.source_text || "").trim();
    const outText = (res.translated_text || "").trim();
    if (!srcText || !outText) return;
    if (res.quality_flags?.includes("untranslated_fallback")) return;
    setRecents((prev) =>
      withRecent(
        prev,
        {
          sourceText: srcText,
          translatedText: outText,
          srcLang: res.source_language,
          tgtLang: res.target_language,
          ts: Date.now(),
        },
        RECENTS_LIMIT,
      ),
    );
  }

  function restoreRecent(r: RecentTranslation) {
    setSrcLang(r.srcLang);
    setTgtLang(r.tgtLang);
    setSource(r.sourceText);
  }

  function removeRecent(r: RecentTranslation) {
    setRecents((prev) => prev.filter((x) => !(x.ts === r.ts && x.sourceText === r.sourceText)));
  }

  function clearRecents() {
    setRecents([]);
  }

  function clearAll() {
    setSource("");
    setResult(null);
    setDraft(null);
    setLiveError(null);
    setLiveStats(null);
    setLivePhase("idle");
  }

  // Persist recents whenever they change (keeps state updaters pure).
  React.useEffect(() => {
    saveRecents(recents);
  }, [recents]);

  // Commit a translation to recents once the text has settled (avoids per-keystroke spam).
  React.useEffect(() => {
    if (!result) return;
    const snapshot = result;
    const t = window.setTimeout(() => commitRecent(snapshot), 2000);
    return () => window.clearTimeout(t);
  }, [result]);

  // DeepL-style keyboard shortcuts (shared matcher, 2026-10-21): swap
  // languages, copy translation, clear, and submit with Ctrl/Cmd+Enter.
  useShortcuts(
    {
      submit: () => {
        if (!source.trim()) return;
        if (live) void runLiveSource(source);
        else translate.mutate(source);
      },
      swap: () => { swap(); },
      copy: () => { copyOut(); },
      clear: () => { clearAll(); },
    },
    { clearTargetLabel: "Source text" },
  );

  const activeGlossaries = (glossaries ?? []).filter((g) => g.status === "active");
  const caps = langs ?? [];

  // Without a `rtl` context the browser lays an Arabic line out left-to-right:
  // the pane showed "الطقس حار…" flush-left with its full stop on the wrong
  // side (seen 2026-10-24). `dir` alone re-aligns the whole line.
  const isRtl = (code?: string) => !!caps.find((c: any) => c.code === code)?.rtl;
  const sourceRtl = isRtl(srcLang === "AUTO"
    ? (detectedLanguage || (result ? result.source_language : undefined))
    : srcLang);
  const targetRtl = isRtl(tgtLang);

  const working = live ? livePhase !== "idle" : translate.isPending;
  const isSameLangError = (err: { message?: string; code?: string } | null) => {
    if (!err) return false;
    const msg = (err.message || "").toLowerCase();
    return msg.includes("equals the target") || msg.includes("must differ") || (err.code === "unsupported_language" && (msg.includes("language") || msg.includes("target")));
  };

  const displayError = live
    ? liveError
    : translate.isError
      ? { message: friendlyMessage(translate.error), code: (translate.error as any)?.code as string | undefined }
      : null;
  const retryTranslation = () => {
    if (!source.trim()) return;
    if (live) void runLiveSource(source);
    else translate.mutate(source);
  };

  return (
    <div className="flex flex-col min-h-full lg:h-full bg-[#F8F9FA]">

      {/* ── Top mode switcher bar (Desi style) ─────────────────── */}
      <div className="bg-white border-b border-dl-border px-6 py-2.5 flex flex-wrap items-center justify-between gap-3">
        <TabSwitcher
          active="text"
          onChange={(v) => {
            if (v === "file") navigate("/documents");
            if (v === "write") navigate("/write");
            if (v === "page") navigate("/translate/page");
            if (v === "notes") navigate("/notes");
          }}
          tabs={[
            { value: "text",  label: "Translate text",  icon: <FileText  className="h-4 w-4" /> },
            { value: "file",  label: "Translate files", icon: <Upload    className="h-4 w-4" />,
              badge: <span className="ml-1 rounded-full bg-dl-blue-light px-2 py-0.5 text-[10px] font-bold text-dl-blue">PDF · DOCX</span> },
            { value: "page",  label: "Web page",       icon: <Globe     className="h-4 w-4 text-emerald-600" /> },
            { value: "write", label: "AI Write",        icon: <Sparkles  className="h-4 w-4 text-amber-500" /> },
            { value: "notes", label: "Notes & Search",  icon: <BookmarkCheck className="h-4 w-4 text-blue-600" /> },
          ]}
        />

        {/* Enterprise options & DeepL layout/benchmark tools */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Layout orientation toggle */}
          <div className="flex items-center gap-0.5 rounded-lg border border-dl-border bg-white p-0.5 shadow-2xs">
            <button
              type="button"
              onClick={() => updateLayout("side-by-side")}
              title="Side-by-side layout (Left: Source / Right: Target)"
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                layoutMode === "side-by-side"
                  ? "bg-dl-blue text-white shadow-xs font-semibold"
                  : "text-dl-muted hover:text-dl-navy hover:bg-slate-50"
              }`}
            >
              <Columns2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Side-by-Side</span>
            </button>
            <button
              type="button"
              onClick={() => updateLayout("stacked")}
              title="Stacked layout (Upper: Source / Lower: Target like DeepL)"
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                layoutMode === "stacked"
                  ? "bg-dl-blue text-white shadow-xs font-semibold"
                  : "text-dl-muted hover:text-dl-navy hover:bg-slate-50"
              }`}
            >
              <Rows2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Upper / Lower</span>
            </button>
          </div>

          {/* Benchmark trigger */}
          <button
            type="button"
            onClick={() => setShowBenchmark(true)}
            title="Run DeepL-grade Live Speed Benchmark"
            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-100 transition-colors shadow-2xs"
          >
            <Zap className="h-3.5 w-3.5 text-amber-600 fill-amber-500" />
            <span>Speed Benchmark</span>
          </button>
          <select
            aria-label="Glossary"
            value={glossaryId}
            onChange={(e) => setGlossaryId(e.target.value)}
            className="h-8 rounded-lg border border-dl-border bg-white pl-3 pr-8 text-xs font-medium text-dl-muted focus:outline-none focus:ring-2 focus:ring-dl-blue/20"
          >
            <option value="">No glossary</option>
            {activeGlossaries.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} ({g.source_language}→{g.target_language})
              </option>
            ))}
          </select>

          <select
            aria-label="Style profile"
            value={styleId}
            onChange={(e) => setStyleId(e.target.value)}
            className="h-8 rounded-lg border border-dl-border bg-white pl-3 pr-8 text-xs font-medium text-dl-muted focus:outline-none focus:ring-2 focus:ring-dl-blue/20"
          >
            <option value="">Default style</option>
            {(styles ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}{s.is_system ? "" : " (custom)"}
              </option>
            ))}
          </select>

          <select
            aria-label="Domain"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className="h-8 rounded-lg border border-dl-border bg-white pl-3 pr-8 text-xs font-medium text-dl-muted focus:outline-none focus:ring-2 focus:ring-dl-blue/20"
          >
            {DOMAINS.map((d) => (
              <option key={d} value={d}>{d.replace("_", " ")}</option>
            ))}
          </select>

          <select
            aria-label="Model intent"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            className="h-8 rounded-lg border border-dl-border bg-white pl-3 pr-8 text-xs font-medium text-dl-muted focus:outline-none focus:ring-2 focus:ring-dl-blue/20"
          >
            {INTENTS.map((i) => (
              <option key={i.value} value={i.value}>{i.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Dual panel workspace (Side-by-side or Stacked Upper/Lower) ───────── */}
      {layoutMode === "side-by-side" ? (
        <div className="flex flex-1 min-h-0 flex-col lg:flex-row">
          {/* SOURCE PANEL */}
          <div className="flex flex-1 flex-col bg-white min-h-0">
{/* Language bar */}
          <LangBar
            selected={srcLang}
            onSelect={handleSelectSrcLang}
            showAuto
            langs={caps}
            detected={
              srcLang === "AUTO" ? (detectedLanguage || (result ? result.source_language : undefined)) : undefined
            }
            detectedConfidence={srcLang === "AUTO" ? detectedConfidence : null}
          />

          {/* Textarea */}
          <div className="relative flex-1 p-5">
            <textarea
              ref={sourceRef}
              dir={sourceRtl ? "rtl" : "ltr"}
              className="w-full h-full min-h-[200px] resize-none border-0 bg-transparent p-0 text-[15px] leading-relaxed text-dl-navy focus:outline-none focus:ring-0 placeholder:text-dl-faint"
              placeholder="Type or paste text…"
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

            {/* Translate just the selected phrase (reference parity, 2026-10-21). */}
            <SelectionTranslate
              editorRef={sourceRef}
              sourceLanguage={srcLang}
              targetLanguage={tgtLang}
            />

            {/* Clear button */}
            {source && (
              <button
                onClick={() => { setSource(""); setResult(null); }}
                className="absolute right-4 top-4 flex h-7 w-7 items-center justify-center rounded-full bg-dl-bg-alt text-dl-muted hover:bg-dl-border hover:text-dl-navy transition-colors"
                title="Clear text"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Footer toolbar */}
          <div className="flex items-center justify-between border-t border-dl-border px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => void speakText(source, srcLang === "AUTO" ? (result?.source_language || "en") : srcLang)}
                disabled={!source.trim()}
                title={isSpeaking ? "Stop audio" : "Listen with server audio"}
                className={`icon-btn ${isSpeaking ? "text-dl-blue" : ""}`}
              >
                <Volume2 className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={() => navigate("/voice?tab=live")}
                title="Open server-backed voice mode"
                className="tool-btn"
              >
                <Mic className="h-4 w-4" /><span>Voice mode</span>
              </button>

              <button
                type="button"
                onClick={() => lookupDictionary(source.slice(0, 30))}
                disabled={!source.trim()}
                className="tool-btn"
              >
                <BookOpen className="h-4 w-4 text-dl-blue" />
                <span>Dictionary</span>
              </button>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => {
                  const next = !live;
                  setLive(next);
                  if (!next) {
                    liveAbort.current?.abort();
                    setDraft(null);
                    setLiveError(null);
                    setLivePhase("idle");
                  }
                }}
                aria-pressed={live}
                title={live
                  ? "Live translation is on — results update while you type"
                  : "Turn on live translation"}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  live
                    ? "border-dl-blue/40 bg-dl-blue-light text-dl-blue"
                    : "border-dl-border bg-white text-dl-muted hover:text-dl-navy"
                }`}
              >
                <Radio className="h-3.5 w-3.5" />
                Live
                {live && livePhase !== "idle" && (
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-dl-blue" />
                )}
              </button>
              <span className="text-xs text-dl-faint select-none tabular-nums">
                {source.trim() ? `${source.trim().split(/\s+/).length.toLocaleString()} words · ` : ""}
                {source.length.toLocaleString()} chars
              </span>
            </div>
          </div>
          </div>

          {/* SWAP BUTTON (vertical divider) */}
          <div className="flex items-center justify-center bg-[#F8F9FA] px-0 py-3 lg:px-2 lg:py-0">
            <button
              onClick={swap}
              aria-label="Swap languages"
              className="
                flex h-10 w-10 items-center justify-center rounded-full
                border border-dl-border bg-white text-dl-muted shadow-xs
                hover:border-dl-blue/60 hover:bg-dl-blue-light hover:text-dl-blue
                transition-all duration-200 active:scale-95
              "
            >
              <ArrowLeftRight className="h-4 w-4" />
            </button>
          </div>

          {/* TARGET PANEL */}
          <div className="flex flex-1 flex-col bg-[#FAFBFE] min-h-0 border-t border-dl-border lg:border-t-0 lg:border-l">
{/* Language bar with formality pills */}
          <LangBar
            selected={tgtLang}
            onSelect={handleSelectTgtLang}
            langs={caps.filter((c: any) => c.translation_supported)}
            right={
              <div className="ml-auto flex items-center gap-0.5 rounded-lg bg-dl-border/60 p-0.5">
                {(["default", "formal", "informal"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setFormality(mode)}
                    className={`
                      rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-all
                      ${formality === mode
                        ? "bg-white text-dl-navy shadow-xs"
                        : "text-dl-muted hover:text-dl-navy"}
                    `}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            }
          />

          {/* Translation display */}
          <div
            className="flex-1 min-h-[200px] p-5 text-[15px] leading-relaxed text-dl-navy"
            aria-live="polite"
            aria-label="Translated text"
          >
            {working && !result && !draft ? (
              <div className="space-y-3 pt-1">
                <div className="skeleton h-5 w-full" />
                <div className="skeleton h-5 w-5/6" />
                <div className="skeleton h-5 w-4/6" />
              </div>
            ) : displayError && !draft ? (
              isSameLangError(displayError) ? (
                <div className="flex flex-col gap-3 rounded-xl border border-blue-200 bg-blue-50/90 p-5 text-sm text-blue-900 shadow-xs">
                  <div className="flex items-center gap-2 font-semibold">
                    <Info className="h-5 w-5 shrink-0 text-blue-600" />
                    <span>Source and target languages are identical ({tgtLang.toUpperCase()})</span>
                  </div>
                  <p className="text-xs text-blue-700">
                    To translate your text, select a different target language from the top bar or pick one below:
                  </p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {[
                      { code: "bho", name: "Bhojpuri (भोजपुरी)" },
                      { code: "es", name: "Spanish (Español)" },
                      { code: "de", name: "German (Deutsch)" },
                      { code: "fr", name: "French (Français)" },
                      { code: "hi", name: "Hindi (हिन्दी)" },
                      { code: "ja", name: "Japanese (日本語)" },
                      { code: "ar", name: "Arabic (العربية)" },
                    ].filter((l) => l.code !== tgtLang).map((l) => (
                      <button
                        key={l.code}
                        type="button"
                        onClick={() => handleSelectTgtLang(l.code)}
                        className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-800 shadow-2xs hover:bg-blue-100/80 transition-colors"
                      >
                        {l.name}
                      </button>
                    ))}
                  </div>
                  {source.trim() && (
                    <div className="mt-3 border-t border-blue-200/60 pt-3">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-600 block mb-1">Original Text:</span>
                      <p className="whitespace-pre-wrap select-text text-sm text-dl-navy">{source}</p>
                    </div>
                  )}
                </div>
              ) : (
                <ErrorState
                  message={displayError.message}
                  code={displayError.code}
                  onRetry={retryTranslation}
                />
              )
            ) : draft ? (
              <div className="space-y-3">
                <p dir={targetRtl ? "rtl" : "ltr"} className="whitespace-pre-wrap select-text text-base leading-relaxed text-dl-navy">
                  {draft.translated_text}
                </p>
                <div className="flex items-center gap-2 text-[11px] font-medium text-dl-muted">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-dl-blue" />
                  Translating live… the final version follows
                </div>
              </div>
            ) : result && result.quality_flags?.some((flag) =>
              /(?:untranslated|dev_provider|dev_echo|source_fallback|empty_translation)/i.test(flag),
            ) ? (
              <ErrorState
                title="Translation unavailable"
                detail="The provider did not return a verified translation. Your original text is still available on the left."
                onRetry={retryTranslation}
              />
            ) : result ? (
              <div className="space-y-4">
                {result.quality_flags?.includes("source_equals_target") && (
                  <div className="flex flex-col gap-2 rounded-lg bg-blue-50/90 border border-blue-200/80 p-3 text-xs text-blue-800">
                    <div className="flex items-center gap-2">
                      <Info className="h-4 w-4 shrink-0 text-blue-600" />
                      <span>Source and target languages are identical ({tgtLang.toUpperCase()}). Select a language to translate:</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {[
                        { code: "bho", name: "Bhojpuri (भोजपुरी)" },
                        { code: "es", name: "Spanish (Español)" },
                        { code: "de", name: "German (Deutsch)" },
                        { code: "fr", name: "French (Français)" },
                        { code: "hi", name: "Hindi (हिन्दी)" },
                        { code: "ja", name: "Japanese (日本語)" },
                      ].filter((l) => l.code !== tgtLang).map((l) => (
                        <button
                          key={l.code}
                          type="button"
                          onClick={() => handleSelectTgtLang(l.code)}
                          className="rounded-md border border-blue-300 bg-white px-2 py-0.5 text-[11px] font-medium text-blue-800 shadow-2xs hover:bg-blue-100/70 transition-colors"
                        >
                          {l.name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <p dir={targetRtl ? "rtl" : "ltr"} className="whitespace-pre-wrap select-text text-base leading-relaxed text-dl-navy">{result.translated_text}</p>
                {result.from_translation_memory && (
                  <Badge tone="good">Matched in translation memory (100%)</Badge>
                )}
                {result.alternatives && result.alternatives.length > 0 && (
                  <div className="pt-3 border-t border-dl-border/60">
                    <span className="text-[11px] font-semibold text-dl-muted uppercase tracking-wider block mb-1.5">
                      Alternatives (click to use)
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {result.alternatives.map((alt, idx) => (
                        <button
                          key={idx}
                          type="button"
                          dir={targetRtl ? "rtl" : "ltr"}
                          onClick={() => setResult({ ...result, translated_text: alt })}
                          className="text-xs px-2.5 py-1 rounded-md bg-white border border-dl-border text-dl-navy hover:border-dl-blue hover:text-dl-blue hover:bg-dl-blue-light/30 transition-all text-start shadow-2xs"
                        >
                          {alt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="select-none text-dl-faint">
                {live ? "Translation appears here as you type…" : "Translation appears here…"}
              </p>
            )}
          </div>

          {/* Footer toolbar */}
          <div className="flex flex-wrap items-center justify-between border-t border-dl-border px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => result && void speakText(result.translated_text, tgtLang)}
                disabled={!result}
                title={isSpeaking ? "Stop audio" : "Listen with server audio"}
                className={`icon-btn ${isSpeaking ? "text-dl-blue" : ""}`}
              >
                <Volume2 className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={copyOut}
                disabled={!result}
                className={`tool-btn ${copied ? "text-emerald-600 hover:text-emerald-700" : ""}`}
              >
                {copied ? (
                  <><Check className="h-4 w-4" /><span>Copied</span></>
                ) : (
                  <><Copy className="h-4 w-4" /><span>Copy</span></>
                )}
              </button>

              <button
                type="button"
                onClick={download}
                disabled={!result}
                className="tool-btn"
              >
                <Download className="h-4 w-4" />
                <span>Download</span>
              </button>

              <button
                type="button"
                onClick={openSaveNoteModal}
                disabled={!result}
                title="Save translation to Notes library"
                className="tool-btn hover:text-blue-600"
              >
                <BookmarkPlus className="h-4 w-4" />
                <span>Save Note</span>
              </button>
            </div>

            {result && (
              <div className="flex flex-wrap items-center gap-2">
                {live && liveStats && (
                  <span
                    className="text-[11px] tabular-nums text-dl-muted"
                    title="Time to the first provisional draft, then the final pass"
                  >
                    live · first draft {liveStats.ttfd_ms === null
                      ? "—"
                      : `${Math.round(liveStats.ttfd_ms)} ms`} · final {Math.round(liveStats.total_ms)} ms
                  </span>
                )}
                <span className="text-[11px] text-dl-faint">
                  {Math.round(result.latency_ms ?? 0)} ms {result.model ? `· ${result.model}` : ""}
                </span>
                {(result.quality_flags ?? [])
                  .filter((f) => f !== "dev_provider")
                  .slice(0, 1)
                  .map((f) => (
                    <Badge
                      key={f}
                      tone={
                        f.includes("untranslated") || f.includes("failed")
                          ? "bad"
                          : f.includes("neural") || f.includes("high") || f.includes("verified")
                          ? "good"
                          : f.includes("pivoted")
                          ? "warn"
                          : "neutral"
                      }
                    >
                      {f.replace(/_/g, " ")}
                    </Badge>
                  ))}
                {result.glossary_note && (
                  <Badge tone="warn">{result.glossary_note}</Badge>
                )}
              </div>
            )}
          </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 min-h-0 flex-col max-w-5xl w-full mx-auto p-4 sm:p-6 gap-3 overflow-y-auto">
          {/* UPPER SOURCE CARD */}
          <div className="flex flex-col bg-white rounded-2xl border border-dl-border shadow-xs overflow-hidden">
{/* Language bar */}
          <LangBar
            selected={srcLang}
            onSelect={handleSelectSrcLang}
            showAuto
            langs={caps}
            detected={
              srcLang === "AUTO" ? (detectedLanguage || (result ? result.source_language : undefined)) : undefined
            }
            detectedConfidence={srcLang === "AUTO" ? detectedConfidence : null}
          />

          {/* Textarea */}
          <div className="relative flex-1 p-5">
            <textarea
              ref={sourceRef}
              dir={sourceRtl ? "rtl" : "ltr"}
              className="w-full h-full min-h-[200px] resize-none border-0 bg-transparent p-0 text-[15px] leading-relaxed text-dl-navy focus:outline-none focus:ring-0 placeholder:text-dl-faint"
              placeholder="Type or paste text…"
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

            {/* Translate just the selected phrase (reference parity, 2026-10-21). */}
            <SelectionTranslate
              editorRef={sourceRef}
              sourceLanguage={srcLang}
              targetLanguage={tgtLang}
            />

            {/* Clear button */}
            {source && (
              <button
                onClick={() => { setSource(""); setResult(null); }}
                className="absolute right-4 top-4 flex h-7 w-7 items-center justify-center rounded-full bg-dl-bg-alt text-dl-muted hover:bg-dl-border hover:text-dl-navy transition-colors"
                title="Clear text"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Footer toolbar */}
          <div className="flex items-center justify-between border-t border-dl-border px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => void speakText(source, srcLang === "AUTO" ? (result?.source_language || "en") : srcLang)}
                disabled={!source.trim()}
                title={isSpeaking ? "Stop audio" : "Listen with server audio"}
                className={`icon-btn ${isSpeaking ? "text-dl-blue" : ""}`}
              >
                <Volume2 className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={() => navigate("/voice?tab=live")}
                title="Open server-backed voice mode"
                className="tool-btn"
              >
                <Mic className="h-4 w-4" /><span>Voice mode</span>
              </button>

              <button
                type="button"
                onClick={() => lookupDictionary(source.slice(0, 30))}
                disabled={!source.trim()}
                className="tool-btn"
              >
                <BookOpen className="h-4 w-4 text-dl-blue" />
                <span>Dictionary</span>
              </button>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => {
                  const next = !live;
                  setLive(next);
                  if (!next) {
                    liveAbort.current?.abort();
                    setDraft(null);
                    setLiveError(null);
                    setLivePhase("idle");
                  }
                }}
                aria-pressed={live}
                title={live
                  ? "Live translation is on — results update while you type"
                  : "Turn on live translation"}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  live
                    ? "border-dl-blue/40 bg-dl-blue-light text-dl-blue"
                    : "border-dl-border bg-white text-dl-muted hover:text-dl-navy"
                }`}
              >
                <Radio className="h-3.5 w-3.5" />
                Live
                {live && livePhase !== "idle" && (
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-dl-blue" />
                )}
              </button>
              <span className="text-xs text-dl-faint select-none tabular-nums">
                {source.trim() ? `${source.trim().split(/\s+/).length.toLocaleString()} words · ` : ""}
                {source.length.toLocaleString()} chars
              </span>
            </div>
          </div>
          </div>

          {/* CENTER SWAP DIVIDER */}
          <div className="flex items-center justify-center -my-2 relative z-10">
            <button
              onClick={swap}
              aria-label="Swap languages"
              className="
                flex h-10 w-10 items-center justify-center rounded-full
                border border-dl-border bg-white text-dl-muted shadow-sm
                hover:border-dl-blue/60 hover:bg-dl-blue-light hover:text-dl-blue
                transition-all duration-200 active:scale-95
              "
            >
              <ArrowLeftRight className="h-4 w-4" />
            </button>
          </div>

          {/* LOWER TARGET CARD */}
          <div className="flex flex-col bg-[#FAFBFE] rounded-2xl border border-dl-border shadow-xs overflow-hidden">
{/* Language bar with formality pills */}
          <LangBar
            selected={tgtLang}
            onSelect={handleSelectTgtLang}
            langs={caps.filter((c: any) => c.translation_supported)}
            right={
              <div className="ml-auto flex items-center gap-0.5 rounded-lg bg-dl-border/60 p-0.5">
                {(["default", "formal", "informal"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setFormality(mode)}
                    className={`
                      rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-all
                      ${formality === mode
                        ? "bg-white text-dl-navy shadow-xs"
                        : "text-dl-muted hover:text-dl-navy"}
                    `}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            }
          />

          {/* Translation display */}
          <div
            className="flex-1 min-h-[200px] p-5 text-[15px] leading-relaxed text-dl-navy"
            aria-live="polite"
            aria-label="Translated text"
          >
            {working && !result && !draft ? (
              <div className="space-y-3 pt-1">
                <div className="skeleton h-5 w-full" />
                <div className="skeleton h-5 w-5/6" />
                <div className="skeleton h-5 w-4/6" />
              </div>
            ) : displayError && !draft ? (
              isSameLangError(displayError) ? (
                <div className="flex flex-col gap-3 rounded-xl border border-blue-200 bg-blue-50/90 p-5 text-sm text-blue-900 shadow-xs">
                  <div className="flex items-center gap-2 font-semibold">
                    <Info className="h-5 w-5 shrink-0 text-blue-600" />
                    <span>Source and target languages are identical ({tgtLang.toUpperCase()})</span>
                  </div>
                  <p className="text-xs text-blue-700">
                    To translate your text, select a different target language from the top bar or pick one below:
                  </p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {[
                      { code: "bho", name: "Bhojpuri (भोजपुरी)" },
                      { code: "es", name: "Spanish (Español)" },
                      { code: "de", name: "German (Deutsch)" },
                      { code: "fr", name: "French (Français)" },
                      { code: "hi", name: "Hindi (हिन्दी)" },
                      { code: "ja", name: "Japanese (日本語)" },
                      { code: "ar", name: "Arabic (العربية)" },
                    ].filter((l) => l.code !== tgtLang).map((l) => (
                      <button
                        key={l.code}
                        type="button"
                        onClick={() => handleSelectTgtLang(l.code)}
                        className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-800 shadow-2xs hover:bg-blue-100/80 transition-colors"
                      >
                        {l.name}
                      </button>
                    ))}
                  </div>
                  {source.trim() && (
                    <div className="mt-3 border-t border-blue-200/60 pt-3">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-600 block mb-1">Original Text:</span>
                      <p className="whitespace-pre-wrap select-text text-sm text-dl-navy">{source}</p>
                    </div>
                  )}
                </div>
              ) : (
                <ErrorState
                  message={displayError.message}
                  code={displayError.code}
                  onRetry={retryTranslation}
                />
              )
            ) : draft ? (
              <div className="space-y-3">
                <p dir={targetRtl ? "rtl" : "ltr"} className="whitespace-pre-wrap select-text text-base leading-relaxed text-dl-navy">
                  {draft.translated_text}
                </p>
                <div className="flex items-center gap-2 text-[11px] font-medium text-dl-muted">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-dl-blue" />
                  Translating live… the final version follows
                </div>
              </div>
            ) : result && result.quality_flags?.some((flag) =>
              /(?:untranslated|dev_provider|dev_echo|source_fallback|empty_translation)/i.test(flag),
            ) ? (
              <ErrorState
                title="Translation unavailable"
                detail="The provider did not return a verified translation. Your original text is still available on the left."
                onRetry={retryTranslation}
              />
            ) : result ? (
              <div className="space-y-4">
                {result.quality_flags?.includes("source_equals_target") && (
                  <div className="flex flex-col gap-2 rounded-lg bg-blue-50/90 border border-blue-200/80 p-3 text-xs text-blue-800">
                    <div className="flex items-center gap-2">
                      <Info className="h-4 w-4 shrink-0 text-blue-600" />
                      <span>Source and target languages are identical ({tgtLang.toUpperCase()}). Select a language to translate:</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {[
                        { code: "bho", name: "Bhojpuri (भोजपुरी)" },
                        { code: "es", name: "Spanish (Español)" },
                        { code: "de", name: "German (Deutsch)" },
                        { code: "fr", name: "French (Français)" },
                        { code: "hi", name: "Hindi (हिन्दी)" },
                        { code: "ja", name: "Japanese (日本語)" },
                      ].filter((l) => l.code !== tgtLang).map((l) => (
                        <button
                          key={l.code}
                          type="button"
                          onClick={() => handleSelectTgtLang(l.code)}
                          className="rounded-md border border-blue-300 bg-white px-2 py-0.5 text-[11px] font-medium text-blue-800 shadow-2xs hover:bg-blue-100/70 transition-colors"
                        >
                          {l.name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <p dir={targetRtl ? "rtl" : "ltr"} className="whitespace-pre-wrap select-text text-base leading-relaxed text-dl-navy">{result.translated_text}</p>
                {result.from_translation_memory && (
                  <Badge tone="good">Matched in translation memory (100%)</Badge>
                )}
                {result.alternatives && result.alternatives.length > 0 && (
                  <div className="pt-3 border-t border-dl-border/60">
                    <span className="text-[11px] font-semibold text-dl-muted uppercase tracking-wider block mb-1.5">
                      Alternatives (click to use)
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {result.alternatives.map((alt, idx) => (
                        <button
                          key={idx}
                          type="button"
                          dir={targetRtl ? "rtl" : "ltr"}
                          onClick={() => setResult({ ...result, translated_text: alt })}
                          className="text-xs px-2.5 py-1 rounded-md bg-white border border-dl-border text-dl-navy hover:border-dl-blue hover:text-dl-blue hover:bg-dl-blue-light/30 transition-all text-start shadow-2xs"
                        >
                          {alt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="select-none text-dl-faint">
                {live ? "Translation appears here as you type…" : "Translation appears here…"}
              </p>
            )}
          </div>

          {/* Footer toolbar */}
          <div className="flex flex-wrap items-center justify-between border-t border-dl-border px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => result && void speakText(result.translated_text, tgtLang)}
                disabled={!result}
                title={isSpeaking ? "Stop audio" : "Listen with server audio"}
                className={`icon-btn ${isSpeaking ? "text-dl-blue" : ""}`}
              >
                <Volume2 className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={copyOut}
                disabled={!result}
                className={`tool-btn ${copied ? "text-emerald-600 hover:text-emerald-700" : ""}`}
              >
                {copied ? (
                  <><Check className="h-4 w-4" /><span>Copied</span></>
                ) : (
                  <><Copy className="h-4 w-4" /><span>Copy</span></>
                )}
              </button>

              <button
                type="button"
                onClick={download}
                disabled={!result}
                className="tool-btn"
              >
                <Download className="h-4 w-4" />
                <span>Download</span>
              </button>

              <button
                type="button"
                onClick={openSaveNoteModal}
                disabled={!result}
                title="Save translation to Notes library"
                className="tool-btn hover:text-blue-600"
              >
                <BookmarkPlus className="h-4 w-4" />
                <span>Save Note</span>
              </button>
            </div>

            {result && (
              <div className="flex flex-wrap items-center gap-2">
                {live && liveStats && (
                  <span
                    className="text-[11px] tabular-nums text-dl-muted"
                    title="Time to the first provisional draft, then the final pass"
                  >
                    live · first draft {liveStats.ttfd_ms === null
                      ? "—"
                      : `${Math.round(liveStats.ttfd_ms)} ms`} · final {Math.round(liveStats.total_ms)} ms
                  </span>
                )}
                <span className="text-[11px] text-dl-faint">
                  {Math.round(result.latency_ms ?? 0)} ms {result.model ? `· ${result.model}` : ""}
                </span>
                {(result.quality_flags ?? [])
                  .filter((f) => f !== "dev_provider")
                  .slice(0, 1)
                  .map((f) => (
                    <Badge
                      key={f}
                      tone={
                        f.includes("untranslated") || f.includes("failed")
                          ? "bad"
                          : f.includes("neural") || f.includes("high") || f.includes("verified")
                          ? "good"
                          : f.includes("pivoted")
                          ? "warn"
                          : "neutral"
                      }
                    >
                      {f.replace(/_/g, " ")}
                    </Badge>
                  ))}
                {result.glossary_note && (
                  <Badge tone="warn">{result.glossary_note}</Badge>
                )}
              </div>
            )}
          </div>
          </div>
        </div>
      )}

      {/* ── Recent translations strip ───────────────────────────── */}
      {recents.length > 0 && (
        <div className="border-t border-dl-border bg-white px-6 py-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-dl-muted">
              <Clock className="h-3.5 w-3.5" />
              Recent translations
              <span className="ml-1 hidden text-[11px] font-normal normal-case tracking-normal text-dl-faint sm:inline">
                · click to restore · ⌘/Ctrl+Shift+K swap · ⌘/Ctrl+Shift+C copy · Esc clear
              </span>
            </div>
            <button
              type="button"
              onClick={clearRecents}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-dl-faint hover:bg-dl-bg-alt hover:text-dl-navy transition-colors"
              title="Clear all recent translations"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </button>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {recents.map((r) => (
              <div
                key={`${r.ts}-${r.sourceText}`}
                className="group relative flex min-w-[220px] max-w-[280px] shrink-0 cursor-pointer flex-col rounded-xl border border-dl-border bg-[#FAFBFC] p-3 text-left transition-all hover:border-dl-blue/50 hover:bg-dl-blue-light/20 hover:shadow-xs"
                onClick={() => restoreRecent(r)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    restoreRecent(r);
                  }
                }}
              >
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeRecent(r);
                  }}
                  className="absolute right-1.5 top-1.5 hidden h-5 w-5 items-center justify-center rounded-full text-dl-faint hover:bg-dl-border hover:text-dl-navy group-hover:flex"
                  title="Remove"
                  aria-label="Remove from recent translations"
                >
                  <X className="h-3 w-3" />
                </button>
                <p className="truncate pr-5 text-[13px] font-medium text-dl-navy">{r.sourceText}</p>
                <p className="truncate text-[13px] text-dl-muted">{r.translatedText}</p>
                <div className="mt-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase text-dl-faint">
                  <span className="rounded bg-white px-1.5 py-0.5 ring-1 ring-dl-border">{r.srcLang}</span>
                  <ArrowLeftRight className="h-2.5 w-2.5" />
                  <span className="rounded bg-white px-1.5 py-0.5 ring-1 ring-dl-border">{r.tgtLang}</span>
                  <span className="ml-auto font-normal normal-case text-dl-faint">{relativeTime(r.ts)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Dictionary drawer ────────────────────────────────────── */}
      {showDict && (
        <div className="border-t border-dl-border bg-white animate-slideDown">
          <div className="mx-auto max-w-5xl p-5">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-dl-blue" />
                <h2 className="text-sm font-bold text-dl-navy">
                  Dictionary &amp; Contextual Meanings
                </h2>
                {dictLoading && (
                  <span className="text-xs text-dl-faint">Loading…</span>
                )}
              </div>
              <button
                onClick={() => setShowDict(false)}
                className="icon-btn"
                title="Close dictionary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {dictData ? (
              <div className="grid gap-6 md:grid-cols-3">
                {/* Word + translations */}
                <div>
                  <div className="flex flex-wrap items-baseline gap-2 mb-3">
                    <span className="text-xl font-bold text-dl-navy">{dictData.word}</span>
                    {dictData.phonetic && (
                      <span className="text-xs text-dl-muted font-mono">{dictData.phonetic}</span>
                    )}
                    <Badge tone="info">{dictData.part_of_speech}</Badge>
                  </div>
                  <p className="text-xs font-semibold text-dl-muted uppercase tracking-wide mb-2">Translations</p>
                  <div className="flex flex-wrap gap-1.5">
                    {dictData.translations.map((t, idx) => (
                      <span
                        key={idx}
                        className="rounded-lg bg-dl-blue-light px-2.5 py-1 text-xs font-medium text-dl-blue"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Definitions */}
                <div>
                  <p className="text-xs font-semibold text-dl-muted uppercase tracking-wide mb-2">
                    Definitions
                  </p>
                  <ul className="space-y-1.5">
                    {dictData.meanings.map((m, idx) => (
                      <li key={idx} className="flex gap-2 text-xs text-dl-navy leading-relaxed">
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-dl-blue/50" />
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Synonyms + example */}
                <div>
                  <p className="text-xs font-semibold text-dl-muted uppercase tracking-wide mb-2">
                    Synonyms
                  </p>
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {dictData.synonyms.map((s, idx) => (
                      <button
                        key={idx}
                        onClick={() => setSource(s)}
                        title="Click to translate this synonym"
                        className="rounded-lg border border-dl-border bg-white px-2.5 py-1 text-xs text-dl-navy hover:border-dl-blue hover:text-dl-blue transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                  {dictData.examples[0] && (
                    <>
                      <p className="text-[11px] font-semibold text-dl-muted uppercase tracking-wide mb-1">
                        Example
                      </p>
                      <p className="text-xs italic text-dl-muted">{dictData.examples[0]}</p>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-dl-muted">
                Select or type a word to see its definitions and synonyms.
              </p>
            )}
          </div>
        </div>
      )}
      {/* ── Save Note Modal ─────────────────────────────────────────── */}
      {showNoteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl border border-dl-border space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-dl-border pb-3">
              <h2 className="text-base font-bold text-dl-navy flex items-center gap-2">
                <BookmarkPlus className="h-5 w-5 text-blue-600" />
                <span>Save to Notes & Annotations</span>
              </h2>
              <button
                type="button"
                onClick={() => setShowNoteModal(false)}
                className="text-dl-muted hover:text-dl-navy p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/60 space-y-2">
                <div className="flex items-center justify-between text-[11px] font-semibold text-dl-muted uppercase">
                  <span>Language Pair</span>
                  <span className="text-blue-600">{(result?.source_language || srcLang).toUpperCase()} → {(result?.target_language || tgtLang).toUpperCase()}</span>
                </div>
                <div className="text-xs text-dl-navy font-medium line-clamp-2">
                  {source}
                </div>
                {result && (
                  <div className="text-xs text-blue-700 font-semibold line-clamp-2 border-t border-slate-200/50 pt-1.5">
                    {result.translated_text}
                  </div>
                )}
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">
                  Title (optional)
                </label>
                <input
                  type="text"
                  className="w-full h-9 rounded-lg border border-dl-border px-3 text-xs"
                  placeholder="e.g. Legal phrase, Bhojpuri dialect"
                  value={noteTitle}
                  onChange={(e) => setNoteTitle(e.target.value)}
                />
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">
                  Personal Note & Explanations
                </label>
                <textarea
                  className="w-full h-20 rounded-lg border border-dl-border p-2.5 text-xs text-dl-navy focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Add grammar notes, context explanations, dialect variations…"
                  value={noteContent}
                  onChange={(e) => setNoteContent(e.target.value)}
                />
              </div>

              <div>
                <label className="font-semibold text-dl-navy block mb-1">Tags</label>
                <div className="flex items-center gap-2 mb-2">
                  <input
                    type="text"
                    className="flex-1 h-8 rounded-lg border border-dl-border px-2.5 text-xs"
                    placeholder="Type tag (e.g. legal, vocabulary) and press Enter"
                    value={noteTagInput}
                    onChange={(e) => setNoteTagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const t = noteTagInput.trim().replace(/^#/, "");
                        if (t && !noteTags.includes(t)) {
                          setNoteTags([...noteTags, t]);
                          setNoteTagInput("");
                        }
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const t = noteTagInput.trim().replace(/^#/, "");
                      if (t && !noteTags.includes(t)) {
                        setNoteTags([...noteTags, t]);
                        setNoteTagInput("");
                      }
                    }}
                    className="h-8 px-3 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium text-dl-navy"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {noteTags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 rounded-md bg-blue-50 border border-blue-200/80 px-2 py-0.5 text-xs text-blue-800"
                    >
                      #{tag}
                      <button
                        type="button"
                        onClick={() => setNoteTags(noteTags.filter((x) => x !== tag))}
                        className="text-blue-400 hover:text-blue-700"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-dl-border">
              <button
                type="button"
                onClick={() => {
                  setShowNoteModal(false);
                  navigate("/notes");
                }}
                className="text-xs text-blue-600 hover:underline font-medium"
              >
                View all notes →
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowNoteModal(false)}
                  className="px-3 py-1.5 rounded-lg border border-dl-border text-xs font-medium text-dl-muted hover:text-dl-navy"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveNote}
                  disabled={savingNote}
                  className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs disabled:opacity-60"
                >
                  {savingNote ? "Saving…" : "Save Note"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <TranslationBenchmarkModal
        isOpen={showBenchmark}
        onClose={() => setShowBenchmark(false)}
      />
    </div>
  );
}
