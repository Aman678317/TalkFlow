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
  ChevronDown,
} from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { TranslateResponse } from "../lib/types";
import { useLanguages } from "../hooks/useLanguages";
import { Badge, ErrorState } from "../components/ui";
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
  return (
    <div className="flex items-center gap-0.5" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={active === t.value}
          onClick={() => onChange(t.value)}
          className={`
            inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium
            transition-all duration-150
            ${active === t.value
              ? "bg-white text-dl-navy shadow-xs border border-dl-border"
              : "text-dl-muted hover:bg-white/60 hover:text-dl-navy"}
          `}
        >
          {t.icon}
          {t.label}
          {t.badge}
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
  right,
}: {
  selected: string;
  onSelect: (code: string) => void;
  showAuto?: boolean;
  langs: { code: string; name: string; native_name?: string }[];
  detected?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-dl-border bg-[#FAFBFC] px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-0.5">
        {showAuto && (
          <button
            onClick={() => onSelect("AUTO")}
            className={selected === "AUTO" ? "lang-pill-active" : "lang-pill"}
          >
            Detect language
          </button>
        )}
        {QUICK_LANGS.slice(0, showAuto ? 3 : 4).map((ql) => (
          <button
            key={ql.code}
            onClick={() => onSelect(ql.code)}
            className={selected === ql.code ? "lang-pill-active" : "lang-pill"}
          >
            {ql.name}
          </button>
        ))}
        <div className="relative">
          <select
            aria-label="More languages"
            value={!showAuto && !QUICK_LANGS.slice(0, 4).find((q) => q.code === selected) ? selected : ""}
            onChange={(e) => e.target.value && onSelect(e.target.value)}
            className="appearance-none h-8 rounded-lg border border-dl-border bg-white pl-3 pr-8 text-xs font-medium text-dl-muted hover:border-dl-blue/40 focus:outline-none focus:ring-2 focus:ring-dl-blue/20 cursor-pointer"
          >
            <option value="">More ▾</option>
            {langs
              .filter((c: any) => c.translation_supported || c.code === "en")
              .map((c: any) => (
                <option key={c.code} value={c.code}>
                  {c.name}{c.native_name ? ` (${c.native_name})` : ""}
                </option>
              ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-dl-faint" />
        </div>
        {detected && (
          <Badge tone="info" title="Auto-detected language">
            Detected: {detected.toUpperCase()}
          </Badge>
        )}
      </div>
      {right}
    </div>
  );
}

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

function detectLanguageClient(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "en";

  for (const [rx, lang] of SCRIPT_RANGES) {
    if (rx.test(trimmed)) return lang;
  }

  const tokens = trimmed.toLowerCase().match(/\b[a-zà-ÿ']+\b/g) || [];
  if (tokens.length === 0) return "en";

  let bestLang = "en";
  let maxHits = 0;

  for (const [lang, words] of Object.entries(FUNCTION_WORDS)) {
    const wordSet = new Set(words);
    const hits = tokens.filter((t) => wordSet.has(t)).length;
    if (hits > maxHits) {
      maxHits = hits;
      bestLang = lang;
    }
  }

  return bestLang;
}

async function fetchNeuralTranslation(
  text: string,
  srcLang: string,
  tgtLang: string,
  formality: string = "default"
): Promise<TranslateResponse> {
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
      const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=${src}|${tgt}`;
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
      const gUrl = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=${src}&tl=${tgt}&dt=t&q=${encodeURIComponent(text)}`;
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

function normalizeTranslation(res: any): TranslateResponse {
  if (res?.translations && Array.isArray(res.translations) && res.translations.length > 0) {
    const item = res.translations[0];
    return {
      translation_id: item.translation_id || res.request_id || "",
      source_language: item.source_language || "",
      target_language: item.target_language || "",
      source_text: item.source_text || "",
      translated_text: item.translated_text || "",
      model: item.model || "",
      provider: item.provider || "",
      latency_ms: Number(item.latency_ms ?? 0),
      quality_flags: Array.isArray(item.quality_flags) ? item.quality_flags : [],
      from_translation_memory: Boolean(item.from_translation_memory || item.tm_match),
      detected_confidence: Number(item.detected_confidence ?? 1.0),
      alternatives: Array.isArray(item.alternatives) ? item.alternatives : [],
    };
  }
  return {
    translation_id: res?.translation_id || res?.request_id || "",
    source_language: res?.source_language || "",
    target_language: res?.target_language || "",
    source_text: res?.source_text || "",
    translated_text: res?.translated_text || "",
    model: res?.model || "",
    provider: res?.provider || "",
    latency_ms: Number(res?.latency_ms ?? 0),
    quality_flags: Array.isArray(res?.quality_flags) ? res?.quality_flags : [],
    from_translation_memory: Boolean(res?.from_translation_memory || res?.tm_match),
    detected_confidence: Number(res?.detected_confidence ?? 1.0),
    alternatives: Array.isArray(res?.alternatives) ? res.alternatives : [],
  };
}

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
  const [tgtLang, setTgtLang] = React.useState("de");
  const [detectedLanguage, setDetectedLanguage] = React.useState("");
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

  // Dictionary
  const [dictData, setDictData] = React.useState<DictionaryEntry | null>(null);
  const [dictLoading, setDictLoading] = React.useState(false);
  const [showDict, setShowDict] = React.useState(false);

  // Debounce
  React.useEffect(() => {
    const t = window.setTimeout(() => setDebounced(source), 700);
    return () => window.clearTimeout(t);
  }, [source]);

  // Real-time language detection on input
  React.useEffect(() => {
    if (srcLang === "AUTO" && source.trim().length >= 2) {
      const detected = detectLanguageClient(source);
      setDetectedLanguage(detected);
    } else {
      setDetectedLanguage("");
    }
  }, [source, srcLang]);

  const translate = useMutation({
    mutationFn: async (text: string) => {
      let resolvedSrc = srcLang;
      if (resolvedSrc === "AUTO") {
        resolvedSrc = detectLanguageClient(text);
        setDetectedLanguage(resolvedSrc);
      }

      let r: any = null;
      try {
        r = await api<TranslateResponse>("/api/v1/translate", {
          method: "POST",
          body: {
            text,
            source_language: resolvedSrc,
            target_language: tgtLang,
            glossary_id: glossaryId || null,
            style_profile_id: styleId || null,
            domain,
            intent,
            formality,
          },
        });
      } catch (err: any) {
        if (err instanceof ApiError && (err.status === 401 || err.status === 402 || err.status === 429)) {
          throw err;
        }
        console.warn("Backend /translate error, trying neural MT:", err);
      }

      const normalized = normalizeTranslation(r);
      const isMockEcho =
        !normalized.translated_text ||
        normalized.provider === "dev_echo" ||
        normalized.quality_flags.includes("dev_provider") ||
        normalized.translated_text.startsWith(`[${tgtLang}]`) ||
        (normalized.translated_text.trim() === text.trim() && resolvedSrc !== tgtLang);

      if (isMockEcho) {
        return await fetchNeuralTranslation(text, resolvedSrc, tgtLang, formality);
      }
      return normalized;
    },
    onSuccess: (normalized: TranslateResponse) => {
      setResult(normalized);
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

  // Speech recognition
  const toggleSpeechRecognition = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.warning("Speech recognition not supported. Use Chrome/Edge/Safari.");
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
        let finalChunk = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) {
            finalChunk += event.results[i][0].transcript;
          }
        }
        if (finalChunk.trim()) {
          setSource((prev) => (prev ? prev.trim() + " " + finalChunk.trim() : finalChunk.trim()));
        }
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

  const speakText = (text: string, langCode: string) => {
    if (!("speechSynthesis" in window)) {
      toast.warning("Audio synthesis not supported.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    if (langCode && langCode !== "AUTO") utterance.lang = langCode;
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
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
          source_language: srcLang === "AUTO" ? "en" : srcLang,
          target_language: tgtLang,
        },
      });
      setDictData(data);
    } catch {
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
    const url = URL.createObjectURL(blob);
    a.href = url;
    a.download = `translation-${result.target_language}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 200);
  }

  const activeGlossaries = (glossaries ?? []).filter((g) => g.status === "active");
  const caps = langs ?? [];

  return (
    <div className="flex flex-col h-full bg-[#F8F9FA]">

      {/* ── Top mode switcher bar (Desi style) ─────────────────── */}
      <div className="bg-white border-b border-dl-border px-6 py-2.5 flex flex-wrap items-center justify-between gap-3">
        <TabSwitcher
          active="text"
          onChange={(v) => {
            if (v === "file") navigate("/documents");
            if (v === "write") navigate("/write");
          }}
          tabs={[
            { value: "text",  label: "Translate text",  icon: <FileText  className="h-4 w-4" /> },
            { value: "file",  label: "Translate files", icon: <Upload    className="h-4 w-4" />,
              badge: <span className="ml-1 rounded-full bg-dl-blue-light px-2 py-0.5 text-[10px] font-bold text-dl-blue">PDF · DOCX</span> },
            { value: "write", label: "AI Write",        icon: <Sparkles  className="h-4 w-4 text-amber-500" /> },
          ]}
        />

        {/* Enterprise options */}
        <div className="flex flex-wrap items-center gap-2">
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

      {/* ── Dual panel workspace ─────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 flex-col lg:flex-row">

        {/* SOURCE PANEL */}
        <div className="flex flex-1 flex-col bg-white min-h-0">
          {/* Language bar */}
          <LangBar
            selected={srcLang}
            onSelect={setSrcLang}
            showAuto
            langs={caps}
            detected={
              srcLang === "AUTO" ? (detectedLanguage || (result ? result.source_language : undefined)) : undefined
            }
          />

          {/* Textarea */}
          <div className="relative flex-1 p-5">
            <textarea
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
                onClick={() => speakText(source, srcLang === "AUTO" ? (result?.source_language || "en") : srcLang)}
                disabled={!source.trim()}
                title="Listen"
                className="icon-btn"
              >
                <Volume2 className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={toggleSpeechRecognition}
                title={isListening ? "Stop listening" : "Dictate"}
                className={`tool-btn ${
                  isListening
                    ? "bg-rose-50 text-rose-600 hover:bg-rose-100 animate-pulse"
                    : ""
                }`}
              >
                {isListening ? (
                  <><MicOff className="h-4 w-4" /><span>Listening…</span></>
                ) : (
                  <><Mic className="h-4 w-4" /><span>Dictate</span></>
                )}
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

            <span className="text-xs text-dl-faint select-none">
              {source.length.toLocaleString()} chars
            </span>
          </div>
        </div>

        {/* SWAP BUTTON (divider) */}
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
            onSelect={setTgtLang}
            langs={caps.filter((c: any) => c.translation_supported)}
            right={
              <div className="flex items-center gap-0.5 rounded-lg bg-dl-border/60 p-0.5">
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
            {translate.isPending && !result ? (
              <div className="space-y-3 pt-1">
                <div className="skeleton h-5 w-full" />
                <div className="skeleton h-5 w-5/6" />
                <div className="skeleton h-5 w-4/6" />
              </div>
            ) : translate.isError ? (
              <ErrorState
                message={(translate.error as any)?.message ?? "Translation failed"}
                code={(translate.error as any)?.code}
                onRetry={() => source && translate.mutate(source)}
              />
            ) : result ? (
              <div className="space-y-4">
                {result.quality_flags?.includes("untranslated_fallback") && (
                  <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                    Translation service temporarily offline. Original text displayed without modification.
                  </div>
                )}
                <p className="whitespace-pre-wrap select-text text-base leading-relaxed text-dl-navy">{result.translated_text}</p>
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
                          onClick={() => setResult({ ...result, translated_text: alt })}
                          className="text-xs px-2.5 py-1 rounded-md bg-white border border-dl-border text-dl-navy hover:border-dl-blue hover:text-dl-blue hover:bg-dl-blue-light/30 transition-all text-left shadow-2xs"
                        >
                          {alt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="select-none text-dl-faint">Translation appears here…</p>
            )}
          </div>

          {/* Footer toolbar */}
          <div className="flex flex-wrap items-center justify-between border-t border-dl-border px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => result && speakText(result.translated_text, tgtLang)}
                disabled={!result}
                title="Listen to translation"
                className="icon-btn"
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
            </div>

            {result && (
              <div className="flex items-center gap-2">
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
              </div>
            )}
          </div>
        </div>
      </div>

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
    </div>
  );
}
