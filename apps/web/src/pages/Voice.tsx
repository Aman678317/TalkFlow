import { useState, useRef, useMemo, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Languages,
  Video,
  Play,
  RotateCcw,
  Copy,
  Download,
  Sparkles,
  Users,
  Square,
  ArrowLeftRight,
  Check,
  Radio,
  Phone,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import { AudioPlayer, MicCapture, b64ToBytes } from "@/lib/audio";
import { translateCanonical } from "@/lib/translation";
import { MeetingSocket, normId } from "@/lib/ws";
import type { RealtimeEvent } from "@/lib/types";
import { Button, Card, Select } from "@/components/ui";
import { toast } from "@/stores/toasts";
import { useAuth } from "@/stores/auth";
import TranscriptExportModal from "@/components/voice/TranscriptExportModal";
import PhoneCallingTab from "@/components/voice/PhoneCallingTab";

interface TranscriptItem {
  id: string;
  speaker: "speaker1" | "speaker2" | "live";
  speakerName: string;
  originalText: string;
  sourceLang: string;
  translatedText: string;
  targetLang: string;
  timestamp: string;
}

const VOICE_LANGUAGES = [
  { code: "en", name: "English (US)", locale: "en-US" },
  { code: "de", name: "German (Deutsch)", locale: "de-DE" },
  { code: "es", name: "Spanish (Español)", locale: "es-ES" },
  { code: "fr", name: "French (Français)", locale: "fr-FR" },
  { code: "hi", name: "Hindi (हिन्दी)", locale: "hi-IN" },
  { code: "ja", name: "Japanese (日本語)", locale: "ja-JP" },
  { code: "zh", name: "Chinese (中文)", locale: "zh-CN" },
  { code: "it", name: "Italian (Italiano)", locale: "it-IT" },
  { code: "pt", name: "Portuguese (Português)", locale: "pt-BR" },
  { code: "ar", name: "Arabic (العربية)", locale: "ar-SA" },
  { code: "ru", name: "Russian (Русский)", locale: "ru-RU" },
  { code: "nl", name: "Dutch (Nederlands)", locale: "nl-NL" },
  { code: "pl", name: "Polish (Polski)", locale: "pl-PL" },
  { code: "ko", name: "Korean (한국어)", locale: "ko-KR" },
];

/*
// Legacy client-side translation fallback implementation intentionally disabled.
async function translateLiveText(
  text: string,
  sourceLang: string,
  targetLang: string
): Promise<string> {
  const trimmed = text.trim();
  if (!trimmed) return "";

  const src = sourceLang === "auto" ? "en" : sourceLang.toLowerCase().split("-")[0];
  const tgt = targetLang.toLowerCase().split("-")[0];

  const cleaned = trimmed
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

  if (src === tgt) return cleaned;

  // Direct fast matching for standard greeting & demo phrases
  const lower = cleaned.toLowerCase().replace(/[.,!?;:]/g, "").trim();

  // Special match for the DeepL reference sample
  if (
    src === "en" &&
    tgt === "de" &&
    (lower.includes("name is") || lower.includes("shandilya") || lower.includes("yaman") || lower.includes("great day") || lower.includes("what are you doing"))
  ) {
    let result = trimmed;
    result = result.replace(/hello[!,.]?/gi, "Hallo,");
    result = result.replace(/my name is ([a-z0-9\s]+?)(?=[.!?]|$)/gi, "mein Name ist $1.");
    result = result.replace(/what are you doing\??/gi, "Was machst du gerade?");
    result = result.replace(/today is my great day[.]?/gi, "Heute ist mein großer Tag.");
    // Clean up spacing around punctuation
    result = result.replace(/\s+([.,!?])/g, "$1 ").replace(/\s{2,}/g, " ").trim();
    if (result !== trimmed) return result;
  }

  // Special match for greeting & introduction phrases in Hindi
  if (src === "en" && tgt === "hi") {
    let result = trimmed;
    result = result.replace(/\bhello\b[!,.]?/gi, "नमस्ते,");
    result = result.replace(/\bmy name is ([a-z0-9\s]+?)(?=[.!?]|$)/gi, "मेरा नाम $1 है.");
    result = result.replace(/\bwhat are you doing\??/gi, "आप क्या कर रहे हैं?");
    result = result.replace(/\btoday is my great day[.]?/gi, "आज मेरा बहुत अच्छा दिन है.");
    result = result.replace(/\btoday is (?:the|a) great day[.]?/gi, "आज एक महान दिन है.");
    result = result.replace(/\bnice to meet you[.]?/gi, "आपसे मिलकर खुशी हुई.");
    result = result.replace(/\s+([.,!?])/g, "$1 ").replace(/\s{2,}/g, " ").trim();
    if (result !== trimmed) return result;
  }

  // Common quick phrase book
  const phraseBook: Record<string, Record<string, string>> = {
    "hello": { de: "Hallo", es: "Hola", fr: "Bonjour", hi: "नमस्ते", it: "Ciao", ja: "こんにちは", zh: "你好" },
    "how are you": { de: "Wie geht es dir?", es: "¿Cómo estás?", fr: "Comment allez-vous?", hi: "आप कैसे हैं?", it: "Come stai?" },
    "good morning": { de: "Guten Morgen", es: "Buenos días", fr: "Bonjour", hi: "शुभ प्रभात", it: "Buongiorno" },
    "thank you": { de: "Danke schön", es: "Gracias", fr: "Merci", hi: "धन्यवाद", it: "Grazie" },
    "nice to meet you": { de: "Schön, Sie kennenzulernen", es: "Mucho gusto", fr: "Ravi de vous rencontrer", hi: "आपसे मिलकर खुशी हुई" },
  };

  if (phraseBook[lower] && phraseBook[lower][tgt]) {
    return phraseBook[lower][tgt];
  }

  // 1. Try backend /api/v1/translate
  try {
    const res = await api<{
      translated_text?: string;
      translations?: Array<{ translated_text: string }>;
    }>("/api/v1/translate", {
      method: "POST",
      body: {
        text: trimmed,
        source_language: src,
        target_language: tgt,
        intent: "latency_optimized",
      },
      timeoutMs: 2500,
    });
    const candidate =
      res?.translated_text || res?.translations?.[0]?.translated_text;
    if (candidate && candidate.trim()) {
      return candidate.trim();
    }
  } catch (backendErr) {
    // Backend offline or timed out; proceed to next tier
  }

  // 2. Try online neural MT
  try {
    const pair = `${src}|${tgt}`;
    const url = ""; // legacy browser provider removed
    const resp = await fetch(url, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      const data = await resp.json();
      const raw = data?.responseData?.translatedText;
      if (raw && !raw.startsWith("MYMEMORY WARNING")) {
        return raw.trim();
      }
    }
  } catch (neuralErr) {
    // Online MT unavailable
  }

  // 3. Fallback: rule-based word transformation
  const introMatch = trimmed.match(/^(?:my name is|i am|i'm)\s+(.+)$/i);
  if (introMatch) {
    const name = introMatch[1].trim();
    if (tgt === "de") return `Mein Name ist ${name}`;
    if (tgt === "es") return `Mi nombre es ${name}`;
    if (tgt === "fr") return `Je m'appelle ${name}`;
    if (tgt === "hi") return `मेरा नाम ${name} है`;
    if (tgt === "it") return `Mi chiamo ${name}`;
    if (tgt === "pt") return `Meu nome é ${name}`;
  }

  return trimmed;
}
*/

export default function Voice() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const user = useAuth((s) => s.user);

  // Tab: "live" (Live Speech Translation reference), "facetoface", "meeting", "phone" (International Call)
  const [activeTab, setActiveTab] = useState<"live" | "facetoface" | "meeting" | "phone">(
    searchParams.get("tab") === "phone" || searchParams.get("tab") === "international" ? "phone" : "live"
  );

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab === "phone" || tab === "international") {
      setActiveTab("phone");
    }
  }, [searchParams]);

  // === LIVE TRANSLATION STATE ===
  const [liveSourceLang, setLiveSourceLang] = useState("en");
  const [liveTargetLang, setLiveTargetLang] = useState("de"); // Default English -> German as in user screenshot
  const [liveDetectedLanguage, setLiveDetectedLanguage] = useState("");
  const [liveDetectedConfidence, setLiveDetectedConfidence] = useState<number | null>(null);
  const [liveTranslationError, setLiveTranslationError] = useState<string | null>(null);
  const [isLiveListening, setIsLiveListening] = useState(false);
  const [liveOriginalText, setLiveOriginalText] = useState("");
  const [liveTranslatedText, setLiveTranslatedText] = useState("");
  const [liveInterimOriginal, setLiveInterimOriginal] = useState("");
  const [liveInterimTranslated, setLiveInterimTranslated] = useState("");
  const [isLiveTranslating, setIsLiveTranslating] = useState(false);
  const [autoPlayLiveAudio, setAutoPlayLiveAudio] = useState(true);
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [liveTtsStatus, setLiveTtsStatus] = useState<"idle" | "ready" | "blocked" | "unavailable">("idle");
  const [liveTtsError, setLiveTtsError] = useState<string | null>(null);
  const [copiedOriginal, setCopiedOriginal] = useState(false);
  const [copiedTranslated, setCopiedTranslated] = useState(false);
  const liveSourceLangRef = useRef(liveSourceLang);
  const liveTargetLangRef = useRef(liveTargetLang);
  const audioEnabledRef = useRef(audioEnabled);
  const autoPlayLiveAudioRef = useRef(autoPlayLiveAudio);

  // === FACE-TO-FACE STATE ===
  const [speaker1Lang, setSpeaker1Lang] = useState("en");
  const [speaker2Lang, setSpeaker2Lang] = useState("es");
  const [speaker1Name, setSpeaker1Name] = useState(user?.name || "Speaker 1");
  const [speaker2Name, setSpeaker2Name] = useState("Speaker 2");
  const [activeMic, setActiveMic] = useState<"speaker1" | "speaker2" | null>(null);
  const [autoPlayAudio, setAutoPlayAudio] = useState(true);
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);
  const [currentSpokenText, setCurrentSpokenText] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  // Computed transcript list for export (supports both Live and Face-to-Face modes)
  const exportItems: TranscriptItem[] = useMemo(() => {
    if (activeTab === "live") {
      if (!liveOriginalText && !liveTranslatedText) return [];
      return [
        {
          id: "live-session",
          speaker: "live",
          speakerName: user?.name || "Speaker",
          originalText: liveOriginalText,
          sourceLang: liveSourceLang,
          translatedText: liveTranslatedText,
          targetLang: liveTargetLang,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        },
      ];
    }
    return transcripts;
  }, [activeTab, liveOriginalText, liveTranslatedText, liveSourceLang, liveTargetLang, user?.name, transcripts]);

  // Refs
  const micStreamRef = useRef<MediaStream | null>(null);
  const liveFinalOriginalRef = useRef("");
  const liveFinalTranslatedRef = useRef("");
  const isSimulatingRef = useRef(false);
  const isLiveListeningRef = useRef(false);
  const transcriptBottomRef = useRef<HTMLDivElement>(null);
  const [quickInputText, setQuickInputText] = useState("");
  const [isSpeakingTts, setIsSpeakingTts] = useState<boolean>(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const liveMicCaptureRef = useRef<MicCapture | null>(null);
  const liveSocketRef = useRef<MeetingSocket | null>(null);
  const liveAudioPlayerRef = useRef<AudioPlayer | null>(null);
  const liveFinalUtterancesRef = useRef<Set<string>>(new Set());
  const liveFinalTranslationsRef = useRef<Set<string>>(new Set());
  const liveCaptureStartedRef = useRef(false);
  const liveSessionIdRef = useRef(0);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsQueueRef = useRef<Array<{ text: string; langCode: string }>>([]);
  const ttsDrainingRef = useRef(false);
  const ttsGenerationRef = useRef(0);
  const currentTtsResolveRef = useRef<(() => void) | null>(null);
  const faceMicStreamRef = useRef<MediaStream | null>(null);
  const faceAudioContextRef = useRef<AudioContext | null>(null);
  const faceAudioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const faceAudioChunksRef = useRef<Float32Array[]>([]);
  const faceCaptureSpeakerRef = useRef<"speaker1" | "speaker2" | null>(null);

  useEffect(() => {
    liveSourceLangRef.current = liveSourceLang;
    liveTargetLangRef.current = liveTargetLang;
    audioEnabledRef.current = audioEnabled;
    autoPlayLiveAudioRef.current = autoPlayLiveAudio;
  }, [liveSourceLang, liveTargetLang, audioEnabled, autoPlayLiveAudio]);

  const requestLiveTranslation = async (text: string, sourceLang: string, targetLang: string) => {
    try {
      const { response, sourceLanguage, detectedConfidence } = await translateCanonical(
        text,
        sourceLang,
        targetLang,
        { intent: "latency_optimized" },
      );
      if (sourceLang.toLowerCase() === "auto") {
        setLiveDetectedLanguage(sourceLanguage);
        setLiveDetectedConfidence(detectedConfidence);
      }
      setLiveTranslationError(null);
      return response.translated_text;
    } catch (err) {
      const message = friendlyMessage(err);
      setLiveTranslationError(message);
      toast.error("Translation unavailable", message);
      return null;
    }
  };

  const ensureLiveAudioPlayer = () => {
    if (!liveAudioPlayerRef.current) {
      liveAudioPlayerRef.current = new AudioPlayer(
        (message) => {
          setLiveTtsStatus("unavailable");
          setLiveTtsError(message);
          setIsSpeakingTts(false);
        },
        (_turn, state) => {
          if (state === "playing") {
            setIsSpeakingTts(true);
            setLiveTtsStatus("ready");
            setLiveTtsError(null);
          } else if (state === "played" || state === "dropped") {
            setIsSpeakingTts(false);
          }
        },
        (state) => {
          if (state === "running") {
            setLiveTtsStatus("ready");
            setLiveTtsError(null);
          }
        },
      );
    }
    return liveAudioPlayerRef.current;
  };

  const appendLiveText = (current: string, next: string) => {
    const clean = next.trim();
    if (!clean) return current;
    return current ? `${current} ${clean}` : clean;
  };

  const handleLiveRealtimeEvent = (event: RealtimeEvent) => {
    const evt = event as RealtimeEvent & Record<string, unknown>;
    const target = String(evt.target_language ?? evt.target_lang ?? "");
    const source = String(evt.language ?? evt.source_language ?? evt.source_lang ?? "");
    const text = String(evt.text ?? evt.source_text ?? "").trim();
    const turnId = String(evt.utterance_id ?? evt.segment_id ?? "");

    if (event.type === "transcript.partial") {
      if (text) setLiveInterimOriginal(text);
      if (source && source !== "auto") {
        setLiveDetectedLanguage(source);
        if (typeof evt.confidence === "number") setLiveDetectedConfidence(evt.confidence);
      }
      return;
    }

    if (event.type === "transcript.final") {
      if (turnId && liveFinalUtterancesRef.current.has(turnId)) return;
      if (turnId) liveFinalUtterancesRef.current.add(turnId);
      if (text) {
        const updated = appendLiveText(liveFinalOriginalRef.current, text);
        liveFinalOriginalRef.current = updated;
        setLiveOriginalText(updated);
      }
      setLiveInterimOriginal("");
      if (source && source !== "auto") {
        setLiveDetectedLanguage(source);
        if (typeof evt.confidence === "number") setLiveDetectedConfidence(evt.confidence);
      }
      return;
    }

    if (event.type === "language.detected") {
      if (typeof evt.language === "string") setLiveDetectedLanguage(evt.language);
      if (typeof evt.confidence === "number") setLiveDetectedConfidence(evt.confidence);
      return;
    }

    if (event.type === "translation.started") {
      if (!target || target === liveTargetLangRef.current) setIsLiveTranslating(true);
      return;
    }

    if (event.type === "translation.final" || event.type === "translation.segment.final") {
      if (target !== liveTargetLangRef.current) return;
      const translated = String(evt.translated_text ?? evt.translatedText ?? evt.text ?? "").trim();
      if (!translated) return;
      const translationKey = `${turnId || evt.sequence || translated}:${target}`;
      if (liveFinalTranslationsRef.current.has(translationKey)) return;
      liveFinalTranslationsRef.current.add(translationKey);
      const updated = appendLiveText(liveFinalTranslatedRef.current, translated);
      liveFinalTranslatedRef.current = updated;
      setLiveTranslatedText(updated);
      setLiveInterimTranslated("");
      setIsLiveTranslating(false);
      return;
    }

    if (event.type === "tts.started") {
      if (!target || target === liveTargetLangRef.current) setLiveTtsStatus("idle");
      return;
    }

    if (event.type === "tts.chunk") {
      if (target !== liveTargetLangRef.current || !audioEnabledRef.current || !autoPlayLiveAudioRef.current) return;
      const audio = String(evt.audio_base64 ?? evt.audio ?? "");
      if (!audio) return;
      const player = ensureLiveAudioPlayer();
      const tag = normId(String(evt.segment_id ?? evt.utterance_id ?? ""));
      void player.deliver(b64ToBytes(audio), tag, {
        source: "json",
        sequence: Number(evt.sequence ?? evt.seq ?? 0),
        chunkIndex: Number(evt.chunk_index ?? evt.chunkIndex ?? 0),
        speakerId: typeof evt.speaker_id === "string" ? evt.speaker_id : undefined,
        utteranceId: typeof evt.utterance_id === "string" ? evt.utterance_id : undefined,
      }).catch(() => undefined);
      return;
    }

    if (event.type === "translation.failed" || event.type === "translation.error") {
      if (!target || target === liveTargetLangRef.current) {
        setIsLiveTranslating(false);
        setLiveTranslationError(String(evt.message ?? evt.user_message ?? "Translation is temporarily unavailable."));
      }
      return;
    }

    if (event.type === "error") {
      const code = String(evt.code ?? "");
      const message = String(evt.message ?? "Realtime voice service is unavailable.");
      if (code === "tts_unavailable") {
        setLiveTtsStatus("unavailable");
        setLiveTtsError(message);
      } else {
        setLiveTranslationError(message);
      }
      return;
    }

    if (event.type === "quality.degraded") {
      setLiveTranslationError(String(evt.message ?? evt.user_message ?? "Live translation is temporarily delayed."));
    }
  };

  const handleLiveRealtimeBinary = (frame: {
    kind: "original" | "tts";
    shortId: string;
    language: string;
    chunkIndex?: number;
    pcm: ArrayBuffer;
  }) => {
    if (frame.kind !== "tts" || frame.language !== liveTargetLangRef.current
      || !audioEnabledRef.current || !autoPlayLiveAudioRef.current) return;
    const player = liveAudioPlayerRef.current;
    if (!player) return;
    void player.deliver(new Uint8Array(frame.pcm), frame.shortId, {
      source: "binary",
      chunkIndex: frame.chunkIndex ?? 0,
    }).catch(() => undefined);
  };

  // Spacebar toggle listener for Live Voice
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (activeTab !== "live") return;
      const target = e.target as HTMLElement | null;
      if (
        e.code === "Space" &&
        !(
          target instanceof HTMLInputElement ||
          target instanceof HTMLTextAreaElement ||
          target?.isContentEditable
        )
      ) {
        e.preventDefault();
        if (isLiveListeningRef.current) {
          stopLiveListening();
        } else {
          startLiveListening();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeTab]);

  const enableAudio = async () => {
    try {
      const AudioContextCtor = window.AudioContext || (window as typeof window & {
        webkitAudioContext?: typeof AudioContext;
      }).webkitAudioContext;
      if (AudioContextCtor) {
        const context = audioContextRef.current || new AudioContextCtor();
        audioContextRef.current = context;
        await context.resume();
      }
      await ensureLiveAudioPlayer().resumeContext();
      setAudioEnabled(true);
      audioEnabledRef.current = true;
      setLiveTtsError(null);
      setLiveTtsStatus("idle");
    } catch {
      setAudioEnabled(false);
      setLiveTtsStatus("blocked");
      setLiveTtsError("Browser audio is blocked. Allow audio for TalkFlow and try again.");
    }
  };

  // Server-side TTS only. Browser speech synthesis is deliberately not used as a
  // translation fallback because it can make an unavailable provider look ready.
  const playTtsItem = async (item: { text: string; langCode: string }, generation: number) => {
    try {
      const res = await api<{ audio_base64?: string; format?: string }>("/api/v1/voice/tts", {
        method: "POST",
        body: { text: item.text, language: item.langCode },
        timeoutMs: 9000,
      });

      // Stopping the live session invalidates an in-flight provider response.
      if (generation !== ttsGenerationRef.current) return;
      if (!res?.audio_base64) {
        setLiveTtsStatus("unavailable");
        setLiveTtsError("Translated audio is unavailable. Captions remain available.");
        return;
      }

      const mime = res.format === "wav" ? "audio/wav" : "audio/mpeg";
      const audio = new Audio(`data:${mime};base64,${res.audio_base64}`);
      currentAudioRef.current = audio;
      setIsSpeakingTts(true);
      setLiveTtsStatus("ready");
      setLiveTtsError(null);

      await new Promise<void>((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          if (currentTtsResolveRef.current === finish) currentTtsResolveRef.current = null;
          if (currentAudioRef.current === audio) currentAudioRef.current = null;
          setIsSpeakingTts(false);
          resolve();
        };
        currentTtsResolveRef.current = finish;
        audio.onended = finish;
        audio.onerror = () => {
          if (generation !== ttsGenerationRef.current) {
            finish();
            return;
          }
          setLiveTtsStatus("unavailable");
          setLiveTtsError("Translated audio could not be played. Captions remain available.");
          finish();
        };
        void audio.play().catch(() => {
          setLiveTtsStatus("blocked");
          setLiveTtsError("Browser blocked audio playback. Enable audio and try again.");
          finish();
        });
      });
    } catch (err) {
      if (generation !== ttsGenerationRef.current) return;
      const message = friendlyMessage(err);
      setLiveTtsStatus("unavailable");
      setLiveTtsError(message || "Translated audio is unavailable. Captions remain available.");
      setIsSpeakingTts(false);
    }
  };

  const drainTtsQueue = async () => {
    if (ttsDrainingRef.current) return;
    ttsDrainingRef.current = true;
    const generation = ttsGenerationRef.current;
    try {
      while (ttsQueueRef.current.length > 0 && generation === ttsGenerationRef.current) {
        const item = ttsQueueRef.current.shift();
        if (item) await playTtsItem(item, generation);
      }
    } finally {
      ttsDrainingRef.current = false;
      // A new utterance may have arrived while the previous item was ending or
      // while cancellation was resolving its current audio promise.
      if (ttsQueueRef.current.length > 0) void drainTtsQueue();
    }
  };

  const cancelTts = () => {
    ttsGenerationRef.current += 1;
    ttsQueueRef.current = [];
    currentTtsResolveRef.current?.();
    currentTtsResolveRef.current = null;
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.pause();
        currentAudioRef.current.currentTime = 0;
      } catch { }
      currentAudioRef.current = null;
    }
    setIsSpeakingTts(false);
  };

  const speakUtterance = (text: string, langCode: string) => {
    const clean = text?.trim();
    if (!clean) return;
    if (!audioEnabled) {
      setLiveTtsStatus("blocked");
      setLiveTtsError("Enable audio before playing translated speech.");
      return;
    }
    ttsQueueRef.current.push({ text: clean, langCode });
    void drainTtsQueue();
  };

  // Swap Live Languages
  const swapLiveLanguages = () => {
    if (liveSourceLang === "auto") return;
    const temp = liveSourceLang;
    setLiveSourceLang(liveTargetLang);
    setLiveTargetLang(temp);

    // Also swap texts if present
    const orig = liveOriginalText;
    const trans = liveTranslatedText;
    setLiveOriginalText(trans);
    setLiveTranslatedText(orig);
    liveFinalOriginalRef.current = trans;
    liveFinalTranslatedRef.current = orig;
  };

  const startLiveRealtimeCapture = async (stream: MediaStream, sessionId: number) => {
    const track = stream.getAudioTracks()[0];
    const socket = liveSocketRef.current;
    if (!track || !socket) return;

    try {
      liveMicCaptureRef.current?.stop();
      const capture = new MicCapture();
      liveMicCaptureRef.current = capture;
      liveCaptureStartedRef.current = true;
      await capture.startFromTrack(
        track,
        16000,
        (frame) => {
          if (!isLiveListeningRef.current || sessionId !== liveSessionIdRef.current) return;
          liveSocketRef.current?.sendAudio(frame);
        },
        (reason) => {
          if (sessionId !== liveSessionIdRef.current || !isLiveListeningRef.current) return;
          setLiveTranslationError(
            reason === "mute"
              ? "The microphone was muted. Check your input device and try again."
              : "The microphone became unavailable. Check your input device and try again.",
          );
          stopLiveListening();
        },
      );
      if (sessionId !== liveSessionIdRef.current || !isLiveListeningRef.current) {
        capture.stop();
      }
    } catch (err) {
      liveCaptureStartedRef.current = false;
      liveMicCaptureRef.current?.stop();
      liveMicCaptureRef.current = null;
      setLiveTranslationError("Microphone capture could not start. Please try again.");
      console.warn("Realtime microphone capture note:", err);
    }
  };

  const startLiveRealtimeSession = async (stream: MediaStream, sessionId: number) => {
    const created = await api<{ session_id?: string; streaming_url?: string }>("/v3/voice/realtime", {
      method: "POST",
      body: {
        source_language: liveSourceLang,
        target_languages: [liveTargetLang],
        message_format: "json",
        audio_mode: "translated",
      },
    });
    const meetingId = created.session_id;
    if (!meetingId || !created.streaming_url) {
      throw new Error("Realtime voice session did not return a streaming URL.");
    }
    const ticket = new URL(created.streaming_url, window.location.origin).searchParams.get("ticket");
    if (!ticket) throw new Error("Realtime voice session did not return a session ticket.");

    const socket = new MeetingSocket({
      meetingId,
      ticket: undefined,
      refreshTicket: async () => {
        const refreshed = await api<{ ticket?: string }>(`/api/v1/meetings/${meetingId}/join-ticket`, {
          method: "POST",
          body: {},
        });
        return refreshed.ticket ?? null;
      },
      displayName: user?.name || "Speaker",
      preferences: {
        speaking_language: liveSourceLang,
        listening_language: liveTargetLang,
        audio_mode: "translated",
        caption_mode: "both",
        latency_mode: "ultra_low_latency",
        captions_enabled: true,
      },
      onEvent: handleLiveRealtimeEvent,
      onBinary: handleLiveRealtimeBinary,
      onStateChange: (state) => {
        if (sessionId !== liveSessionIdRef.current) return;
        if (state === "joined") {
          setLiveTranslationError(null);
          socket.sendJson({ type: "audio.start", sample_rate: 16000, channels: 1 });
          if (!liveCaptureStartedRef.current) void startLiveRealtimeCapture(stream, sessionId);
        } else if (state === "error") {
          setLiveTranslationError("Realtime voice service is unavailable. Captions cannot start yet.");
          setIsLiveListening(false);
          isLiveListeningRef.current = false;
          liveCaptureStartedRef.current = false;
          liveMicCaptureRef.current?.stop();
          liveMicCaptureRef.current = null;
          micStreamRef.current?.getTracks().forEach((track) => track.stop());
          micStreamRef.current = null;
        }
      },
    });
    socket.setTicket(ticket);
    liveSocketRef.current = socket;
    socket.connect();
  };

  // Start microphone capture and stream 16 kHz mono PCM16 frames into the
  // canonical realtime pipeline. The server owns VAD, STT, translation and TTS.
  const startLiveListening = async () => {
    if (isLiveListeningRef.current) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      toast.error("Microphone unavailable", "This browser cannot provide microphone audio to TalkFlow.");
      return;
    }

    let micStream: MediaStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = micStream;
    } catch (err) {
      toast.error("Microphone access denied", "Allow microphone access and try again.");
      console.warn("Realtime microphone stream note:", err);
      return;
    }

    const sessionId = ++liveSessionIdRef.current;
    liveCaptureStartedRef.current = false;
    liveFinalUtterancesRef.current.clear();
    liveFinalTranslationsRef.current.clear();
    isLiveListeningRef.current = true;
    setIsLiveListening(true);
    setLiveTranslationError(null);
    try {
      await startLiveRealtimeSession(micStream, sessionId);
    } catch (err) {
      isLiveListeningRef.current = false;
      setIsLiveListening(false);
      micStream.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
      setLiveTranslationError(friendlyMessage(err));
      toast.error("Could not start live voice", friendlyMessage(err));
    }
  };

  const stopLiveListening = () => {
    isLiveListeningRef.current = false;
    liveCaptureStartedRef.current = false;
    if (isSimulatingRef.current) isSimulatingRef.current = false;

    const socket = liveSocketRef.current;
    liveSocketRef.current = null;
    if (socket) {
      socket.sendJson({ type: "audio.stop" });
      socket.close();
    }
    liveMicCaptureRef.current?.stop();
    liveMicCaptureRef.current = null;
    if (micStreamRef.current) {
      try {
        micStreamRef.current.getTracks().forEach((track) => track.stop());
      } catch { }
      micStreamRef.current = null;
    }
    void liveAudioPlayerRef.current?.stopAll();
    cancelTts();
    setIsLiveListening(false);
    setLiveInterimOriginal("");
    setLiveInterimTranslated("");
    setIsLiveTranslating(false);
  };

  useEffect(() => () => {
    isLiveListeningRef.current = false;
    liveSocketRef.current?.close();
    liveSocketRef.current = null;
    liveMicCaptureRef.current?.stop();
    liveMicCaptureRef.current = null;
    liveAudioPlayerRef.current?.dispose();
    liveAudioPlayerRef.current = null;
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
  }, []);

  // Instant Translation for Quick Dictation & Phrase Prompts
  const handleTranslateInput = async (inputText: string) => {
    const trimmed = inputText.trim();
    if (!trimmed) return;
    setQuickInputText("");

    const updatedOriginal = liveFinalOriginalRef.current
      ? `${liveFinalOriginalRef.current} ${trimmed}`
      : trimmed;
    liveFinalOriginalRef.current = updatedOriginal;
    setLiveOriginalText(updatedOriginal);
    setLiveInterimOriginal("");

    setIsLiveTranslating(true);
    const translatedChunk = await requestLiveTranslation(trimmed, liveSourceLang, liveTargetLang);
    if (!translatedChunk) {
      setIsLiveTranslating(false);
      return;
    }
    const updatedTranslated = liveFinalTranslatedRef.current
      ? `${liveFinalTranslatedRef.current} ${translatedChunk}`
      : translatedChunk;
    liveFinalTranslatedRef.current = updatedTranslated;
    setLiveTranslatedText(updatedTranslated);
    setLiveInterimTranslated("");
    setIsLiveTranslating(false);

    if (autoPlayLiveAudio && translatedChunk) {
      void speakUtterance(translatedChunk, liveTargetLang);
    }
  };

  // SIMULATE NATURAL SPEECH (English -> German demo)
  const runSampleSimulation = async () => {
    stopLiveListening();
    setLiveSourceLang("en");
    setLiveTargetLang("de");
    setLiveOriginalText("");
    setLiveTranslatedText("");
    setLiveInterimOriginal("");
    setLiveInterimTranslated("");
    liveFinalOriginalRef.current = "";
    liveFinalTranslatedRef.current = "";

    isSimulatingRef.current = true;
    isLiveListeningRef.current = true;
    setIsLiveListening(true);

    const userName = user?.name || "Shandilya";
    const sentences = [
      `Hello, my name is ${userName}.`,
      "What are you doing?",
      "Today is my great day.",
    ];

    let fullOrig = "";
    let fullTrans = "";

    for (const item of sentences) {
      if (!isSimulatingRef.current) break;

      // Word by word interim stream
      const words = item.split(" ");
      let partial = "";
      for (const w of words) {
        if (!isSimulatingRef.current) break;
        partial += (partial ? " " : "") + w;
        setLiveInterimOriginal(partial);
        await new Promise((r) => setTimeout(r, 120));
      }

      if (!isSimulatingRef.current) break;
      fullOrig = fullOrig ? `${fullOrig} ${item}` : item;
      const translated = await requestLiveTranslation(item, "en", "de");
      if (!translated) {
        setIsLiveTranslating(false);
        break;
      }
      fullTrans = fullTrans ? `${fullTrans} ${translated}` : translated;

      liveFinalOriginalRef.current = fullOrig;
      liveFinalTranslatedRef.current = fullTrans;
      setLiveOriginalText(fullOrig);
      setLiveTranslatedText(fullTrans);
      setLiveInterimOriginal("");
      setLiveInterimTranslated("");

      if (autoPlayLiveAudio) {
        void speakUtterance(translated, "de");
      }

      await new Promise((r) => setTimeout(r, 600));
    }

    setIsLiveListening(false);
    isSimulatingRef.current = false;
  };

  // Copy helpers
  const handleCopyOriginal = async () => {
    const text = liveOriginalText + (liveInterimOriginal ? ` ${liveInterimOriginal}` : "");
    if (!text.trim()) return;
    await navigator.clipboard.writeText(text);
    setCopiedOriginal(true);
    setTimeout(() => setCopiedOriginal(false), 2000);
    toast.success("Original speech copied");
  };

  const handleCopyTranslated = async () => {
    const text = liveTranslatedText + (liveInterimTranslated ? ` ${liveInterimTranslated}` : "");
    if (!text.trim()) return;
    await navigator.clipboard.writeText(text);
    setCopiedTranslated(true);
    setTimeout(() => setCopiedTranslated(false), 2000);
    toast.success("Translation copied");
  };

  const clearLiveSession = () => {
    if (isSimulatingRef.current) {
      isSimulatingRef.current = false;
    }
    setLiveOriginalText("");
    setLiveTranslatedText("");
    setLiveInterimOriginal("");
    setLiveInterimTranslated("");
    liveFinalOriginalRef.current = "";
    liveFinalTranslatedRef.current = "";
    liveFinalUtterancesRef.current.clear();
    liveFinalTranslationsRef.current.clear();
    void liveAudioPlayerRef.current?.stopAll();
    toast.info("Transcript cleared");
  };

  const handleTargetLangChange = async (newTarget: string) => {
    setLiveTargetLang(newTarget);
    liveTargetLangRef.current = newTarget;
    liveSocketRef.current?.updatePreferences({ listening_language: newTarget });
    const existing = liveFinalOriginalRef.current || liveOriginalText;
    if (existing.trim()) {
      setIsLiveTranslating(true);
      const source = liveSourceLang === "auto" ? (liveDetectedLanguage || "auto") : liveSourceLang;
      const retranslated = await requestLiveTranslation(existing.trim(), source, newTarget);
      if (!retranslated) {
        setIsLiveTranslating(false);
        return;
      }
      liveFinalTranslatedRef.current = retranslated;
      setLiveTranslatedText(retranslated);
      setIsLiveTranslating(false);
      if (autoPlayLiveAudio && retranslated) {
        void speakUtterance(retranslated, newTarget);
      }
    } else {
      liveFinalTranslatedRef.current = "";
      setLiveTranslatedText("");
    }
  };

  const handleSourceLangChange = (newSource: string) => {
    setLiveSourceLang(newSource);
    liveSourceLangRef.current = newSource;
    setLiveTranslationError(null);
    liveSocketRef.current?.updatePreferences({ speaking_language: newSource });
    if (newSource !== "auto") {
      setLiveDetectedLanguage("");
      setLiveDetectedConfidence(null);
    }
  };

  // === FACE-TO-FACE SERVER STT (Two-Speaker Mode) ===
  const transcribeFaceAudio = async (
    speaker: "speaker1" | "speaker2",
    chunks: Float32Array[],
  ) => {
    if (chunks.length === 0) return;

    let totalLength = 0;
    for (const chunk of chunks) totalLength += chunk.length;
    const pcm = new Int16Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      for (let i = 0; i < chunk.length; i++) {
        const sample = Math.max(-1, Math.min(1, chunk[i]));
        pcm[offset + i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      offset += chunk.length;
    }

    const bytes = new Uint8Array(pcm.buffer);
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);

    setIsTranslating(true);
    try {
      const result = await api<{ text?: string }>('/api/v1/voice/transcribe', {
        method: 'POST',
        body: {
          audio_base64: btoa(binary),
          sample_rate: 16000,
          language: speaker === "speaker1" ? speaker1Lang : speaker2Lang,
        },
      });
      const text = result?.text?.trim();
      if (!text) {
        toast.info("No speech detected", "Try speaking closer to the microphone.");
        return;
      }
      setCurrentSpokenText(text);
      await processVoiceUtterance(speaker, text);
    } catch (err) {
      toast.error("Speech recognition unavailable", friendlyMessage(err));
    } finally {
      setIsTranslating(false);
      setCurrentSpokenText("");
    }
  };

  const startListening = async (speaker: "speaker1" | "speaker2") => {
    if (activeMic === speaker) {
      await stopListening();
      return;
    }
    if (activeMic) await stopListening();

    if (!navigator.mediaDevices?.getUserMedia) {
      toast.error("Microphone unavailable", "This browser cannot provide microphone audio to TalkFlow.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioCtx = window.AudioContext || (window as typeof window & {
        webkitAudioContext?: typeof AudioContext;
      }).webkitAudioContext;
      if (!AudioCtx) throw new Error("Web Audio is not supported in this browser.");

      const context = new AudioCtx({ sampleRate: 16000 });
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const muteGain = context.createGain();
      muteGain.gain.setValueAtTime(0, context.currentTime);

      faceMicStreamRef.current = stream;
      faceAudioContextRef.current = context;
      faceAudioProcessorRef.current = processor;
      faceAudioChunksRef.current = [];
      faceCaptureSpeakerRef.current = speaker;

      processor.onaudioprocess = (event) => {
        if (faceCaptureSpeakerRef.current !== speaker) return;
        const input = event.inputBuffer.getChannelData(0);
        const copy = new Float32Array(input.length);
        copy.set(input);
        faceAudioChunksRef.current.push(copy);
      };
      source.connect(processor);
      processor.connect(muteGain);
      muteGain.connect(context.destination);
      if (context.state === "suspended") await context.resume();

      setCurrentSpokenText("Capturing audio for server transcription…");
      setActiveMic(speaker);
    } catch (err) {
      toast.error("Microphone access failed", friendlyMessage(err));
      faceMicStreamRef.current?.getTracks().forEach((track) => track.stop());
      faceMicStreamRef.current = null;
      setActiveMic(null);
    }
  };

  const stopListening = async () => {
    const speaker = faceCaptureSpeakerRef.current;
    const chunks = faceAudioChunksRef.current;
    faceCaptureSpeakerRef.current = null;
    faceAudioChunksRef.current = [];

    try {
      faceAudioProcessorRef.current?.disconnect();
    } catch { }
    faceAudioProcessorRef.current = null;
    try {
      await faceAudioContextRef.current?.close();
    } catch { }
    faceAudioContextRef.current = null;
    faceMicStreamRef.current?.getTracks().forEach((track) => track.stop());
    faceMicStreamRef.current = null;
    setActiveMic(null);
    setCurrentSpokenText("");

    if (speaker) await transcribeFaceAudio(speaker, chunks);
  };

  const processVoiceUtterance = async (speaker: "speaker1" | "speaker2", text: string) => {
    setIsTranslating(true);
    const sourceLang = speaker === "speaker1" ? speaker1Lang : speaker2Lang;
    const targetLang = speaker === "speaker1" ? speaker2Lang : speaker1Lang;
    const sName = speaker === "speaker1" ? speaker1Name : speaker2Name;

    try {
      const translated = await requestLiveTranslation(text, sourceLang, targetLang);
      if (!translated) return;
      const newItem: TranscriptItem = {
        id: "tx_" + Date.now(),
        speaker,
        speakerName: sName,
        originalText: text,
        sourceLang,
        translatedText: translated,
        targetLang,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      };

      setTranscripts((prev) => [...prev, newItem]);

      if (autoPlayAudio) {
        void speakUtterance(translated, targetLang);
      }
    } catch (err: any) {
      toast.error("Live translation error", err?.message ?? String(err));
    } finally {
      setIsTranslating(false);
    }
  };

  // Copy Face-to-Face transcript
  const copyTranscript = async () => {
    const text = transcripts
      .map(
        (t) =>
          `[${t.timestamp}] ${t.speakerName} (${t.sourceLang.toUpperCase()}): ${t.originalText}\n -> (${t.targetLang.toUpperCase()}): ${t.translatedText}`
      )
      .join("\n\n");
    await navigator.clipboard.writeText(text);
    toast.success("Transcript copied to clipboard");
  };

  // Remote WebRTC Meeting Starter
  const startMeeting = useMutation({
    mutationFn: () =>
      api<{ session_id: string }>("/api/v1/voice/session", {
        method: "POST",
        body: { speak_lang: speaker1Lang, hear_langs: [speaker2Lang], audio_mode: "translated" },
      }),
    onSuccess: (r) => navigate(`/meeting/${r.session_id}`),
    onError: (e) => toast.error("Could not start voice session", friendlyMessage(e)),
  });

  // Target language display name
  const currentTargetLangObj = VOICE_LANGUAGES.find((l) => l.code === liveTargetLang) || {
    name: "German",
  };
  const currentSourceLangObj = VOICE_LANGUAGES.find((l) => l.code === liveSourceLang) || {
    name: "English",
  };

  return (
    <div className="mx-auto max-w-6xl p-4 lg:p-6 space-y-6">
      {/* HEADER & TOP NAVIGATION */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-dl-blue text-white shadow-xs">
              <Mic className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                GlobalTalk Voice
                <span className="rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Live Speech
                </span>
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Instant speech-to-speech translation with real-time recognition, audio release, and multi-language live captions.
              </p>
            </div>
          </div>
        </div>

        {/* MODE TABS */}
        <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 border border-slate-200/80">
          <button
            type="button"
            onClick={() => {
              stopListening();
              setActiveTab("live");
            }}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${activeTab === "live"
              ? "bg-white text-slate-900 shadow-xs"
              : "text-slate-600 hover:text-slate-900"
              }`}
          >
            <Sparkles className="h-3.5 w-3.5 text-dl-blue" />
            Live Voice
          </button>
          <button
            type="button"
            onClick={() => {
              stopLiveListening();
              setActiveTab("facetoface");
            }}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${activeTab === "facetoface"
              ? "bg-white text-slate-900 shadow-xs"
              : "text-slate-600 hover:text-slate-900"
              }`}
          >
            <Users className="h-3.5 w-3.5 text-dl-blue" />
            Face-to-Face Mode
          </button>
          <button
            type="button"
            onClick={() => {
              stopLiveListening();
              stopListening();
              setActiveTab("phone");
            }}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${activeTab === "phone"
              ? "bg-white text-slate-900 shadow-xs"
              : "text-slate-600 hover:text-slate-900"
              }`}
          >
            <Phone className="h-3.5 w-3.5 text-emerald-600" />
            International Call
          </button>
          <button
            type="button"
            onClick={() => {
              stopLiveListening();
              stopListening();
              setActiveTab("meeting");
            }}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${activeTab === "meeting"
              ? "bg-white text-slate-900 shadow-xs"
              : "text-slate-600 hover:text-slate-900"
              }`}
          >
            <Video className="h-3.5 w-3.5 text-dl-blue" />
            Virtual Meeting
          </button>
        </div>
      </div>

      {/* ======================================================== */}
      {/* TAB 0: GLOBAL PHONE CALL (PSTN International Calling)    */}
      {/* ======================================================== */}
      {activeTab === "phone" && (
        <PhoneCallingTab />
      )}

      {/* ======================================================== */}
      {/* TAB 1: LIVE VOICE (Real-Time Live Translation Canvas) */}
      {/* ======================================================== */}
      {activeTab === "live" && (
        <div className="space-y-4">
          {/* MAIN DUAL-PANE CARD */}
          <div className="relative rounded-2xl border border-slate-200 bg-white shadow-xs overflow-hidden transition-all">
            {/* CARD TOP BAR: LANGUAGE SELECTOR & TOOLBAR */}
            <div className="flex flex-wrap items-center justify-between border-b border-slate-100 bg-slate-50/70 px-5 py-3 text-xs font-medium gap-3">
              <div className="flex flex-wrap items-center gap-2">
                {/* Source Language Selector */}
                <div className="flex items-center gap-1.5 rounded-xl border border-slate-200/80 bg-white px-2.5 py-1.5 shadow-2xs">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">From</span>
                  <select
                    aria-label="Source Language"
                    value={liveSourceLang}
                    onChange={(e) => handleSourceLangChange(e.target.value)}
                    className="cursor-pointer border-0 bg-transparent py-0 pl-1 pr-6 text-xs font-bold text-slate-800 focus:outline-none focus:ring-0"
                  >
                    <option value="auto">Auto-detect ({currentSourceLangObj.name})</option>
                    {VOICE_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Swap Direction */}
                <button
                  type="button"
                  onClick={swapLiveLanguages}
                  disabled={liveSourceLang === "auto"}
                  className="rounded-xl border border-slate-200 bg-white p-2 text-slate-500 shadow-2xs hover:bg-slate-50 hover:text-slate-800 disabled:opacity-30 transition-all active:scale-95"
                  title="Swap languages"
                >
                  <ArrowLeftRight className="h-3.5 w-3.5" />
                </button>

                {/* Target Language Selector */}
                <div className="flex items-center gap-1.5 rounded-xl border border-slate-200/80 bg-white px-2.5 py-1.5 shadow-2xs">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Into</span>
                  <select
                    aria-label="Target Language"
                    value={liveTargetLang}
                    onChange={(e) => void handleTargetLangChange(e.target.value)}
                    className="cursor-pointer border-0 bg-transparent py-0 pl-1 pr-6 text-xs font-bold text-slate-800 focus:outline-none focus:ring-0"
                  >
                    {VOICE_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Status and auto-play audio toggle */}
              <div className="flex items-center gap-2">
                {!audioEnabled && (
                  <button
                    type="button"
                    onClick={() => void enableAudio()}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 shadow-2xs transition-all hover:bg-amber-100 active:scale-95"
                  >
                    <Volume2 className="h-3.5 w-3.5" />
                    <span>Enable audio</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    const next = !autoPlayLiveAudio;
                    autoPlayLiveAudioRef.current = next;
                    setAutoPlayLiveAudio(next);
                    if (!next) void liveAudioPlayerRef.current?.stopAll();
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold shadow-2xs transition-all active:scale-95 ${autoPlayLiveAudio
                    ? "border-blue-200 bg-blue-50 text-dl-blue hover:bg-blue-100/70"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  aria-pressed={autoPlayLiveAudio}
                >
                  {autoPlayLiveAudio ? (
                    <>
                      <Volume2 className="h-3.5 w-3.5 text-dl-blue" />
                      <span>Audio auto-play (On)</span>
                    </>
                  ) : (
                    <>
                      <VolumeX className="h-3.5 w-3.5 text-slate-400" />
                      <span>Audio muted</span>
                    </>
                  )}
                </button>

                {(liveOriginalText || liveTranslatedText) && (
                  <button
                    type="button"
                    onClick={clearLiveSession}
                    className="text-xs text-slate-400 hover:text-rose-600 transition-colors font-medium px-2 py-1 rounded-md hover:bg-rose-50"
                  >
                    Clear text
                  </button>
                )}
              </div>
            </div>

            {/* DUAL-COLUMN LIVE CONTENT */}
            <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100 min-h-[300px]">
              {/* LEFT COLUMN: SPOKEN SPEECH */}
              <div className="flex flex-col justify-between p-6">
                <div>
                  <div className="flex items-center justify-between pb-3">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                      {isLiveListening ? (
                        <span className="flex items-center gap-1.5 text-rose-600">
                          <span className="flex items-center gap-0.5 h-3" aria-hidden="true">
                            <span className="w-1 h-3 bg-rose-500 rounded-full animate-pulse" />
                            <span className="w-1 h-2 bg-rose-500 rounded-full animate-pulse" />
                            <span className="w-1 h-3.5 bg-rose-500 rounded-full animate-pulse" />
                          </span>
                          Listening to voice…
                        </span>
                      ) : (
                        <span>
                          Spoken speech ({currentSourceLangObj.name})
                          {liveSourceLang === "auto" && liveDetectedLanguage && (
                            <span className="ml-2 normal-case font-medium text-dl-blue">
                              Detected {liveDetectedLanguage.toUpperCase()}
                            </span>
                          )}
                          {liveSourceLang === "auto" && liveDetectedConfidence !== null && liveDetectedConfidence < 0.75 && (
                            <span className="ml-2 normal-case font-semibold text-amber-600">
                              Low confidence ({Math.round(liveDetectedConfidence * 100)}%)
                            </span>
                          )}
                        </span>
                      )}
                    </span>
                    {liveOriginalText && (
                      <button
                        type="button"
                        onClick={handleCopyOriginal}
                        className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                        title="Copy original speech"
                      >
                        {copiedOriginal ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>{copiedOriginal ? "Copied" : "Copy"}</span>
                      </button>
                    )}
                  </div>

                  <div className="min-h-[200px] text-base lg:text-lg text-slate-800 font-normal leading-relaxed">
                    {liveOriginalText || liveInterimOriginal ? (
                      <p>
                        <span>{liveOriginalText}</span>
                        {liveInterimOriginal && (
                          <span className="text-dl-blue italic ml-1.5">
                            {liveInterimOriginal}
                          </span>
                        )}
                      </p>
                    ) : (
                      <div className="flex flex-col items-center justify-center min-h-[180px] text-center text-slate-400">
                        <Mic className="h-8 w-8 mb-2 text-slate-300" />
                        <p className="text-sm font-medium text-slate-600">
                          {isLiveListening
                            ? "Speak into your microphone now…"
                            : "Click 'Start speaking' to begin live speech translation."}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">Audio is processed in real time with sub-second speech synthesis.</p>
                      </div>
                    )}
                  </div>

                  {/* Interactive Quick Dictation & Phrase Prompts */}
                  <div className="mt-4 pt-3 border-t border-slate-100/80">
                    <div className="flex items-center gap-2 mb-2">
                      <input
                        type="text"
                        value={quickInputText}
                        onChange={(e) => setQuickInputText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            handleTranslateInput(quickInputText);
                          }
                        }}
                        placeholder="Type or dictate a sentence to translate (e.g. Hello, what are you doing?)..."
                        className="flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-800 placeholder-slate-400 focus:border-dl-blue focus:outline-none focus:ring-1 focus:ring-dl-blue shadow-2xs transition-all"
                      />
                      <button
                        type="button"
                        onClick={() => handleTranslateInput(quickInputText)}
                        disabled={!quickInputText.trim()}
                        className="rounded-xl bg-dl-blue px-3.5 py-2 text-xs font-semibold text-white hover:bg-dl-blue-hover disabled:opacity-40 transition-all shadow-2xs shrink-0 active:scale-95"
                      >
                        Translate
                      </button>
                    </div>

                    {/* Quick test chips */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-slate-400 mr-0.5">Quick phrases:</span>
                      {[
                        "Hello, my name is Alex.",
                        "What are you doing?",
                        "Today is my great day.",
                        "Where is the train station?",
                        "Nice to meet you!",
                      ].map((phrase) => (
                        <button
                          key={phrase}
                          type="button"
                          onClick={() => handleTranslateInput(phrase)}
                          className="rounded-lg border border-slate-200/90 bg-slate-50/80 px-2 py-1 text-[11px] font-medium text-slate-600 hover:bg-blue-50 hover:border-blue-200 hover:text-dl-blue transition-all active:scale-95 shadow-2xs"
                        >
                          {phrase}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="pt-4 flex items-center justify-between text-xs text-slate-400 border-t border-slate-100">
                  <span>
                    {(liveOriginalText + (liveInterimOriginal ? " " + liveInterimOriginal : "")).trim()
                      ? `${(liveOriginalText + " " + liveInterimOriginal).trim().split(/\s+/).length} words`
                      : "0 words"}
                  </span>
                  {isLiveListening && (
                    <span className="flex items-center gap-1.5 text-emerald-600 font-medium">
                      <Radio className="h-3.5 w-3.5 text-emerald-500" /> Live mic active
                    </span>
                  )}
                </div>
              </div>

              {/* RIGHT COLUMN: REAL-TIME TRANSLATION */}
              <div className="flex flex-col justify-between p-6 bg-slate-50/20">
                <div>
                  <div className="flex items-center justify-between pb-3">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <span>Live translation ({currentTargetLangObj.name})</span>
                      {isLiveTranslating && (
                        <Sparkles className="h-3 w-3 text-dl-blue animate-spin" />
                      )}
                    </span>
                    <div className="flex items-center gap-2">
                      {liveTranslatedText && (
                        <>
                          <button
                            type="button"
                            onClick={() => void speakUtterance(liveTranslatedText, liveTargetLang)}
                            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                            title="Speak translation"
                          >
                            <Volume2 className={`h-3.5 w-3.5 ${isSpeakingTts ? "text-dl-blue animate-pulse" : ""}`} />
                            <span className={isSpeakingTts ? "text-dl-blue font-semibold" : ""}>
                              {isSpeakingTts ? "Playing..." : "Listen"}
                            </span>
                          </button>
                          <button
                            type="button"
                            onClick={handleCopyTranslated}
                            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                            title="Copy translation"
                          >
                            {copiedTranslated ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                            <span>{copiedTranslated ? "Copied" : "Copy"}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setIsExportModalOpen(true)}
                            className="flex items-center gap-1 text-xs text-dl-blue hover:text-dl-blue-hover font-medium ml-1"
                            title="Export live transcript & subtitles"
                          >
                            <Download className="h-3.5 w-3.5" />
                            <span>Export</span>
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="min-h-[200px] text-base lg:text-lg text-slate-900 font-normal leading-relaxed">
                    {liveTtsError && !liveTranslationError && (
                      <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                        <p className="font-semibold">Captions only</p>
                        <p className="mt-1">{liveTtsError}</p>
                      </div>
                    )}
                    {liveTranslationError ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                        <p className="font-semibold">Translation unavailable</p>
                        <p className="mt-1 text-xs">{liveTranslationError}</p>
                        <button
                          type="button"
                          onClick={() => {
                            const retryText = liveFinalOriginalRef.current || liveOriginalText;
                            if (retryText.trim()) void handleTargetLangChange(liveTargetLang);
                          }}
                          className="mt-3 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
                        >
                          Retry translation
                        </button>
                      </div>
                    ) : liveTranslatedText || liveInterimTranslated ? (
                      <p>
                        <span>{liveTranslatedText}</span>
                        {liveInterimTranslated && (
                          <span className="text-slate-500 italic ml-1.5">
                            {liveInterimTranslated}
                          </span>
                        )}
                      </p>
                    ) : (
                      <div className="flex flex-col items-center justify-center min-h-[180px] text-center text-slate-400">
                        <Languages className="h-8 w-8 mb-2 text-slate-300" />
                        <p className="text-sm font-medium text-slate-600">Translation output</p>
                        <p className="text-xs text-slate-400 mt-1">Translated text will appear here simultaneously in real time as you speak.</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="pt-4 flex items-center justify-between text-xs text-slate-400 border-t border-slate-100">
                  <span>Target: {currentTargetLangObj.name}</span>
                  <div className="flex items-center gap-2">
                    {liveTranslationError ? (
                      <span className="flex items-center gap-1 text-rose-600 font-medium">
                        <span className="h-2 w-2 rounded-full bg-rose-500" /> Translation unavailable
                      </span>
                    ) : isLiveTranslating ? (
                      <span className="flex items-center gap-1 text-dl-blue font-medium">
                        <span className="h-2 w-2 rounded-full bg-dl-blue animate-pulse" /> Translating
                      </span>
                    ) : liveTtsStatus === "ready" ? (
                      <span className="flex items-center gap-1 text-emerald-600 font-medium">
                        <span className="h-2 w-2 rounded-full bg-emerald-500" /> Translated audio active
                      </span>
                    ) : liveTtsStatus === "blocked" || liveTtsStatus === "unavailable" || !audioEnabled ? (
                      <span className="flex items-center gap-1 text-amber-700 font-medium" title={liveTtsError || undefined}>
                        <span className="h-2 w-2 rounded-full bg-amber-500" /> Captions only
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-slate-500 font-medium">
                        <span className="h-2 w-2 rounded-full bg-slate-300" /> Translation delayed
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* CARD BOTTOM ACTION BAR: START / STOP BUTTON */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 border-t border-slate-100 bg-white p-5">
              {!isLiveListening ? (
                <button
                  type="button"
                  onClick={startLiveListening}
                  className="group relative flex h-12 items-center gap-2.5 rounded-full bg-dl-blue hover:bg-dl-blue-hover text-white px-8 text-sm font-semibold shadow-xs hover:shadow-md transition-all active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-dl-blue focus:ring-offset-2"
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/20 group-hover:scale-110 transition-transform">
                    <Mic className="h-3.5 w-3.5 text-white" />
                  </span>
                  <span>Start speaking</span>
                  <kbd className="ml-1 hidden sm:inline-block rounded bg-white/20 px-1.5 py-0.5 text-[10px] font-mono text-white/90">
                    Space
                  </kbd>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={stopLiveListening}
                  className="relative flex h-12 items-center gap-2.5 rounded-full bg-rose-600 hover:bg-rose-700 text-white px-8 text-sm font-semibold shadow-md transition-all active:scale-[0.98] focus:outline-none ring-4 ring-rose-200/60 animate-pulse"
                >
                  <Square className="h-3.5 w-3.5 fill-white text-white" />
                  <span>Stop speaking</span>
                  <div className="flex items-center gap-0.5 ml-1" aria-hidden="true">
                    <span className="w-1 h-3 bg-white rounded-full animate-pulse" />
                    <span className="w-1 h-2 bg-white rounded-full animate-pulse" />
                    <span className="w-1 h-3.5 bg-white rounded-full animate-pulse" />
                  </div>
                </button>
              )}

              {/* Sample simulation button */}
              <button
                type="button"
                onClick={runSampleSimulation}
                className="rounded-full border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 px-4 py-2 text-xs font-semibold transition-all active:scale-[0.98] shadow-2xs hover:border-slate-300"
                title="Simulate speech stream: English to German"
              >
                Try sample: English → German
              </button>
            </div>
          </div>

          {/* PRIVACY FOOTER NOTE */}
          <p className="text-center text-xs text-slate-500">
            When you select <span className="font-semibold text-slate-700">Start speaking</span>, GlobalTalk Voice uses your microphone to translate your speech in real time. Your audio isn't stored after the session.
          </p>
        </div>
      )}

      {/* ======================================================== */}
      {/* TAB 2: FACE-TO-FACE CONVERSATION (Two-Speaker Mode) */}
      {/* ======================================================== */}
      {activeTab === "facetoface" && (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {/* SPEAKER 1 CONSOLE */}
            <div
              className={`relative flex flex-col justify-between rounded-2xl border bg-white p-6 shadow-xs transition-all ${activeMic === "speaker1"
                ? "border-dl-blue ring-4 ring-dl-blue/15 shadow-md"
                : "border-slate-200 hover:border-slate-300"
                }`}
            >
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="flex h-3 w-3 rounded-full bg-dl-blue ring-4 ring-blue-100" />
                    <input
                      type="text"
                      value={speaker1Name}
                      onChange={(e) => setSpeaker1Name(e.target.value)}
                      className="border-0 bg-transparent p-0 text-sm font-bold text-slate-900 focus:outline-none"
                    />
                  </div>
                  <Select
                    aria-label="Speaker 1 language"
                    value={speaker1Lang}
                    onChange={(e) => setSpeaker1Lang(e.target.value)}
                    className="h-8 w-44 text-xs font-semibold rounded-xl"
                  >
                    {VOICE_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name}
                      </option>
                    ))}
                  </Select>
                </div>

                <div className="my-8 flex flex-col items-center justify-center text-center">
                  <div className="relative mb-6">
                    <button
                      type="button"
                      onClick={() => startListening("speaker1")}
                      className={`relative flex h-20 w-20 items-center justify-center rounded-full shadow-lg transition-all transform active:scale-95 ${activeMic === "speaker1"
                        ? "bg-rose-500 text-white ring-8 ring-rose-200/70 animate-pulse"
                        : "bg-dl-blue text-white hover:bg-dl-blue-hover hover:shadow-xl hover:scale-105"
                        }`}
                      title={activeMic === "speaker1" ? "Stop recording" : "Click to speak"}
                    >
                      {activeMic === "speaker1" ? (
                        <MicOff className="h-8 w-8" />
                      ) : (
                        <Mic className="h-8 w-8" />
                      )}
                    </button>
                  </div>

                  <p className="text-sm font-semibold text-slate-900">
                    {activeMic === "speaker1"
                      ? "Listening to your voice…"
                      : `Click to speak in ${VOICE_LANGUAGES.find((l) => l.code === speaker1Lang)?.name ||
                      speaker1Lang
                      }`}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Utterance will translate and play back in {speaker2Name}'s language.
                  </p>
                </div>
              </div>

              {activeMic === "speaker1" && currentSpokenText && (
                <div className="rounded-xl bg-blue-50/80 p-3 text-xs text-slate-900 border border-blue-200">
                  <p className="font-semibold text-[10px] uppercase text-dl-blue mb-1">Live voice detected:</p>
                  <p className="italic font-medium">"{currentSpokenText}"</p>
                </div>
              )}
            </div>

            {/* SPEAKER 2 CONSOLE */}
            <div
              className={`relative flex flex-col justify-between rounded-2xl border bg-white p-6 shadow-xs transition-all ${activeMic === "speaker2"
                ? "border-emerald-600 ring-4 ring-emerald-600/15 shadow-md"
                : "border-slate-200 hover:border-slate-300"
                }`}
            >
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="flex h-3 w-3 rounded-full bg-emerald-600 ring-4 ring-emerald-100" />
                    <input
                      type="text"
                      value={speaker2Name}
                      onChange={(e) => setSpeaker2Name(e.target.value)}
                      className="border-0 bg-transparent p-0 text-sm font-bold text-slate-900 focus:outline-none"
                    />
                  </div>
                  <Select
                    aria-label="Speaker 2 language"
                    value={speaker2Lang}
                    onChange={(e) => setSpeaker2Lang(e.target.value)}
                    className="h-8 w-44 text-xs font-semibold rounded-xl"
                  >
                    {VOICE_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name}
                      </option>
                    ))}
                  </Select>
                </div>

                <div className="my-8 flex flex-col items-center justify-center text-center">
                  <div className="relative mb-6">
                    <button
                      type="button"
                      onClick={() => startListening("speaker2")}
                      className={`relative flex h-20 w-20 items-center justify-center rounded-full shadow-lg transition-all transform active:scale-95 ${activeMic === "speaker2"
                        ? "bg-rose-500 text-white ring-8 ring-rose-200/70 animate-pulse"
                        : "bg-emerald-600 text-white hover:bg-emerald-700 hover:shadow-xl hover:scale-105"
                        }`}
                      title={activeMic === "speaker2" ? "Stop recording" : "Click to speak"}
                    >
                      {activeMic === "speaker2" ? (
                        <MicOff className="h-8 w-8" />
                      ) : (
                        <Mic className="h-8 w-8" />
                      )}
                    </button>
                  </div>

                  <p className="text-sm font-semibold text-slate-900">
                    {activeMic === "speaker2"
                      ? "Listening to partner's voice…"
                      : `Click to speak in ${VOICE_LANGUAGES.find((l) => l.code === speaker2Lang)?.name ||
                      speaker2Lang
                      }`}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Utterance will translate and play back in {speaker1Name}'s language.
                  </p>
                </div>
              </div>

              {activeMic === "speaker2" && currentSpokenText && (
                <div className="rounded-xl bg-emerald-50/80 p-3 text-xs text-slate-900 border border-emerald-200">
                  <p className="font-semibold text-[10px] uppercase text-emerald-700 mb-1">Live voice detected:</p>
                  <p className="italic font-medium">"{currentSpokenText}"</p>
                </div>
              )}
            </div>
          </div>

          {/* AUDIO CONTROLS BAR */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-3.5 text-xs shadow-2xs">
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => setAutoPlayAudio(!autoPlayAudio)}
                className="flex items-center gap-2.5 cursor-pointer select-none font-semibold text-slate-700 focus:outline-none"
              >
                <div
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${autoPlayAudio ? "bg-dl-blue" : "bg-slate-300"
                    }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${autoPlayAudio ? "translate-x-4" : "translate-x-0"
                      }`}
                  />
                </div>
                {autoPlayAudio ? (
                  <span className="flex items-center gap-1.5 text-dl-blue font-semibold">
                    <Volume2 className="h-4 w-4" /> Smooth Audio Auto-Play (ON)
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-slate-500">
                    <VolumeX className="h-4 w-4" /> Audio Auto-Play (Muted)
                  </span>
                )}
              </button>

              {isTranslating && (
                <span className="flex items-center gap-1.5 text-dl-blue font-semibold">
                  <Sparkles className="h-3.5 w-3.5 animate-spin" /> Translating voice…
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsExportModalOpen(true)}
                disabled={transcripts.length === 0}
                className="gap-1.5 text-xs text-dl-blue hover:text-dl-blue-hover"
              >
                <Download className="h-3.5 w-3.5" /> Export
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={copyTranscript}
                disabled={transcripts.length === 0}
                className="gap-1.5 text-xs"
              >
                <Copy className="h-3.5 w-3.5" /> Copy
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setTranscripts([])}
                disabled={transcripts.length === 0}
                className="gap-1 text-xs text-rose-600 hover:text-rose-700"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Clear
              </Button>
            </div>
          </div>

          {/* REAL-TIME BILINGUAL LIVE TRANSCRIPT FEED */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <h2 className="text-sm font-bold text-slate-900 mb-3 flex items-center justify-between">
              <span>Bilingual Live Transcript ({transcripts.length} exchanges)</span>
              <span className="text-xs font-normal text-slate-500">Chronological feed</span>
            </h2>

            <div className="min-h-[140px] max-h-[380px] space-y-3 overflow-y-auto pr-2">
              {transcripts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-6 text-center text-slate-500">
                  <Languages className="h-8 w-8 mb-2 opacity-50" />
                  <p className="text-xs font-medium text-slate-900">No voice utterances yet.</p>
                  <p className="text-xs text-slate-500 mt-1">Click either microphone above to start the conversation.</p>
                </div>
              ) : (
                transcripts.map((t) => (
                  <div
                    key={t.id}
                    className={`rounded-xl p-3.5 border transition-all ${t.speaker === "speaker1"
                      ? "bg-blue-50/40 border-blue-100 ml-0 mr-8"
                      : "bg-emerald-50/40 border-emerald-100 ml-8 mr-0"
                      }`}
                  >
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-bold ${t.speaker === "speaker1" ? "text-dl-blue" : "text-emerald-700"
                            }`}
                        >
                          {t.speakerName}
                        </span>
                        <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-[10px] uppercase font-mono">
                          {t.sourceLang} → {t.targetLang}
                        </span>
                      </div>
                      <span className="text-xs text-slate-500">{t.timestamp}</span>
                    </div>

                    <div className="space-y-1">
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-500">Spoke:</span> "{t.originalText}"
                      </p>
                      <p className="text-sm font-medium text-slate-900">
                        <span className="font-semibold text-slate-500 text-xs">Translation:</span>{" "}
                        {t.translatedText}
                      </p>
                    </div>

                    <div className="mt-2 flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => speakUtterance(t.translatedText, t.targetLang)}
                        className="flex items-center gap-1 rounded px-2 py-0.5 text-[11px] text-slate-600 hover:bg-white hover:shadow-xs transition-colors"
                        title="Replay translated audio"
                      >
                        <Play className="h-3 w-3" /> Replay audio
                      </button>
                    </div>
                  </div>
                ))
              )}
              <div ref={transcriptBottomRef} />
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* TAB 3: VIRTUAL VOICE MEETING ROOM */}
      {/* ======================================================== */}
      {activeTab === "meeting" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-5xl mx-auto">
          {/* LEFT 7 COLS: LAUNCH / HOST MEETING CARD */}
          <Card className="lg:col-span-7 space-y-6 p-7 border-slate-200 shadow-xs rounded-2xl">
            <div className="flex items-center gap-3.5 pb-4 border-b border-slate-100">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-dl-blue shadow-2xs">
                <Video className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Virtual Meeting with Real-time Translation
                </h2>
                <p className="text-xs text-slate-500">
                  Instant WebRTC room with live per-participant speech translation.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select
                label="I speak"
                value={speaker1Lang}
                onChange={(e) => setSpeaker1Lang(e.target.value)}
                className="rounded-xl font-semibold text-xs"
              >
                {VOICE_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </Select>

              <Select
                label="I want to hear"
                value={speaker2Lang}
                onChange={(e) => setSpeaker2Lang(e.target.value)}
                className="rounded-xl font-semibold text-xs"
              >
                {VOICE_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </Select>
            </div>

            <Button
              size="lg"
              className="w-full bg-dl-blue hover:bg-dl-blue-hover text-white shadow-xs font-bold rounded-xl py-3 active:scale-[0.99] transition-all"
              onClick={() => startMeeting.mutate()}
              loading={startMeeting.isPending}
            >
              <Video className="h-4 w-4 mr-2" /> Launch Meeting Room
            </Button>

            <p className="text-xs text-slate-400 leading-relaxed">
              Participants can join instantly using your meeting URL from any device. Audio is
              processed securely with self-hosted AI models.
            </p>
          </Card>

          {/* RIGHT 5 COLS: PRE-FLIGHT HARDWARE TEST & JOIN WITH CODE */}
          <div className="lg:col-span-5 space-y-4">
            {/* JOIN EXISTING MEETING */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-3">
              <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                <Users className="h-4 w-4 text-dl-blue" />
                Join with Meeting Code
              </span>
              <p className="text-xs text-slate-500">
                Have an existing room code or URL invite from a colleague?
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g. gt-room-9428"
                  className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-dl-blue"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  className="rounded-xl text-xs font-semibold px-4 text-dl-blue hover:bg-blue-50"
                  onClick={() => toast.info("Enter a valid room ID to join")}
                >
                  Join
                </Button>
              </div>
            </div>

            {/* PRE-FLIGHT HARDWARE TEST */}
            <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5 shadow-2xs space-y-3">
              <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-emerald-600" />
                Pre-Flight Hardware Check
              </span>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between p-2 rounded-xl bg-white border border-slate-200/80">
                  <span className="text-slate-600 font-medium">Microphone</span>
                  <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-600">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    Ready (Default Audio)
                  </span>
                </div>
                <div className="flex items-center justify-between p-2 rounded-xl bg-white border border-slate-200/80">
                  <span className="text-slate-600 font-medium">Neural STT Engine</span>
                  <span className="text-[11px] font-bold text-dl-blue">Whisper Large v3</span>
                </div>
                <div className="flex items-center justify-between p-2 rounded-xl bg-white border border-slate-200/80">
                  <span className="text-slate-600 font-medium">Latency Target</span>
                  <span className="text-[11px] font-mono text-slate-700">&lt; 350ms streaming</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TRANSCRIPT & SUBTITLES EXPORT MODAL */}
      <TranscriptExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        transcripts={exportItems}
        title={activeTab === "live" ? "Export Live Speech Translation" : "Export Bilingual Meeting Transcript"}
      />
    </div>
  );
}
