import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
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
  Share2,
  Sparkles,
  Users,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import { Badge, Button, Card, Select } from "@/components/ui";
import { useLanguages } from "@/hooks/useLanguages";
import { toast } from "@/stores/toasts";
import { useAuth } from "@/stores/auth";

interface TranscriptItem {
  id: string;
  speaker: "speaker1" | "speaker2";
  speakerName: string;
  originalText: string;
  sourceLang: string;
  translatedText: string;
  targetLang: string;
  timestamp: string;
}

const COMMON_VOICE_LANGS = [
  { code: "en", name: "English (US)" },
  { code: "es", name: "Spanish (Español)" },
  { code: "hi", name: "Hindi (हिन्दी)" },
  { code: "de", name: "German (Deutsch)" },
  { code: "fr", name: "French (Français)" },
  { code: "ja", name: "Japanese (日本語)" },
  { code: "zh", name: "Chinese (中文)" },
  { code: "ar", name: "Arabic (العربية)" },
  { code: "pt", name: "Portuguese (Português)" },
];

export default function Voice() {
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const { data: langs } = useLanguages("realtime");

  const [activeTab, setActiveTab] = useState<"facetoface" | "meeting">("facetoface");

  // Speaker configuration
  const [speaker1Lang, setSpeaker1Lang] = useState("en");
  const [speaker2Lang, setSpeaker2Lang] = useState("es");
  const [speaker1Name, setSpeaker1Name] = useState(user?.name || "Speaker 1");
  const [speaker2Name, setSpeaker2Name] = useState("Speaker 2");

  // Mic & Live state
  const [activeMic, setActiveMic] = useState<"speaker1" | "speaker2" | null>(null);
  const [autoPlayAudio, setAutoPlayAudio] = useState(true);
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);
  const [currentSpokenText, setCurrentSpokenText] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);

  const recognitionRef = useRef<any>(null);
  const transcriptBottomRef = useRef<HTMLDivElement>(null);

  // Auto scroll transcript to bottom
  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcripts, currentSpokenText]);

  // Speech Recognition Handling
  const startListening = (speaker: "speaker1" | "speaker2") => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.warning("Speech recognition is not supported in this browser. Please use Chrome or Edge.");
      return;
    }

    if (activeMic === speaker && recognitionRef.current) {
      // Toggle off
      stopListening();
      return;
    }

    // Stop existing if any
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {}
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false; // single utterance mode for smooth translation release
      recognition.interimResults = true;
      recognition.lang = speaker === "speaker1" ? speaker1Lang : speaker2Lang;

      recognition.onstart = () => {
        setActiveMic(speaker);
        setCurrentSpokenText("");
      };

      recognition.onresult = (event: any) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          interim += event.results[i][0].transcript;
        }
        setCurrentSpokenText(interim);
      };

      recognition.onerror = (event: any) => {
        console.error("Speech recognition error:", event);
        setActiveMic(null);
      };

      recognition.onend = async () => {
        setActiveMic(null);
        if (currentSpokenText.trim().length > 0) {
          await processVoiceUtterance(speaker, currentSpokenText.trim());
          setCurrentSpokenText("");
        }
      };

      recognition.start();
      recognitionRef.current = recognition;
    } catch (err: any) {
      toast.error("Microphone access failed", err?.message ?? String(err));
      setActiveMic(null);
    }
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }
    setActiveMic(null);
  };

  // Process completed voice utterance: Translate + Smooth Audio Release (TTS)
  const processVoiceUtterance = async (speaker: "speaker1" | "speaker2", text: string) => {
    setIsTranslating(true);
    const sourceLang = speaker === "speaker1" ? speaker1Lang : speaker2Lang;
    const targetLang = speaker === "speaker1" ? speaker2Lang : speaker1Lang;
    const sName = speaker === "speaker1" ? speaker1Name : speaker2Name;

    try {
      const res = await api<{ translated_text: string }>("/api/v1/translate", {
        method: "POST",
        body: {
          text,
          source_language: sourceLang,
          target_language: targetLang,
          intent: "latency_optimized",
        },
      });

      const translated = res.translated_text;

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

      // DeepL Voice "Smooth Audio Release": auto speak in listener's language
      if (autoPlayAudio) {
        speakUtterance(translated, targetLang);
      }
    } catch (err: any) {
      toast.error("Live translation error", err?.message ?? String(err));
    } finally {
      setIsTranslating(false);
    }
  };

  // Text-To-Speech Playback
  const speakUtterance = (text: string, langCode: string) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    if (langCode && langCode !== "auto") {
      utterance.lang = langCode;
    }
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  };

  // Copy transcript
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

  // Export transcript
  const exportTranscript = () => {
    const text = transcripts
      .map(
        (t) =>
          `[${t.timestamp}] ${t.speakerName} (${t.sourceLang.toUpperCase()}):\nOriginal: ${t.originalText}\nTranslated: ${t.translatedText}\n`
      )
      .join("\n----------------------------------------\n\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `voice-transcript-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  // Remote WebRTC Meeting Starter
  const startMeeting = useMutation({
    mutationFn: () =>
      api<{ session_id: string }>("/api/v1/voice/session", {
        body: { speak_lang: speaker1Lang, hear_langs: [speaker2Lang], audio_mode: "translated" },
      }),
    onSuccess: (r) => navigate(`/meeting/${r.session_id}`),
    onError: (e) => toast.error("Could not start voice session", friendlyMessage(e)),
  });

  return (
    <div className="mx-auto max-w-6xl p-4 lg:p-6 space-y-6">
      {/* HEADER & MODE SELECTOR */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-iris-600 text-white shadow-sm">
              <Mic className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                DeepL Voice
                <span className="rounded-full bg-iris-100 px-2.5 py-0.5 text-xs font-semibold text-iris-700">
                  Live Real-Time
                </span>
              </h1>
              <p className="text-xs text-slate-500">
                Speech-to-speech instant translation with audio playback and live bilingual transcript.
              </p>
            </div>
          </div>
        </div>

        {/* MODE TABS */}
        <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
          <button
            onClick={() => setActiveTab("facetoface")}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
              activeTab === "facetoface"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Users className="h-3.5 w-3.5 text-iris-600" />
            Face-to-Face Mode
          </button>
          <button
            onClick={() => setActiveTab("meeting")}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
              activeTab === "meeting"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Video className="h-3.5 w-3.5 text-lagoon-600" />
            Virtual Voice Meeting
          </button>
        </div>
      </div>

      {activeTab === "facetoface" ? (
        <div className="space-y-6">
          {/* DUAL-SPEAKER FACE-TO-FACE CONSOLE */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* SPEAKER 1 CONSOLE */}
            <div
              className={`relative flex flex-col justify-between rounded-2xl border bg-white p-6 shadow-sm transition-all ${
                activeMic === "speaker1"
                  ? "border-iris-500 ring-2 ring-iris-500/20 shadow-md"
                  : "border-slate-200"
              }`}
            >
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="flex h-3 w-3 rounded-full bg-iris-500" />
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
                    className="h-8 w-44 text-xs font-medium"
                  >
                    {COMMON_VOICE_LANGS.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name}
                      </option>
                    ))}
                  </Select>
                </div>

                <div className="my-8 flex flex-col items-center justify-center text-center">
                  {/* SOUNDWAVE PULSE ANIMATION */}
                  <div className="relative mb-6">
                    {activeMic === "speaker1" && (
                      <div className="absolute -inset-4 rounded-full bg-iris-400/20 animate-ping" />
                    )}
                    <button
                      type="button"
                      onClick={() => startListening("speaker1")}
                      className={`relative flex h-20 w-20 items-center justify-center rounded-full shadow-lg transition-all transform active:scale-95 ${
                        activeMic === "speaker1"
                          ? "bg-rose-500 text-white ring-4 ring-rose-200 animate-pulse"
                          : "bg-iris-600 text-white hover:bg-iris-700 hover:shadow-xl"
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

                  <p className="text-sm font-semibold text-slate-800">
                    {activeMic === "speaker1"
                      ? "Listening to your voice…"
                      : `Click to speak in ${
                          COMMON_VOICE_LANGS.find((l) => l.code === speaker1Lang)?.name ||
                          speaker1Lang
                        }`}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Utterance will translate and play back in {speaker2Name}'s language.
                  </p>
                </div>
              </div>

              {activeMic === "speaker1" && currentSpokenText && (
                <div className="rounded-xl bg-iris-50 p-3 text-xs text-iris-900 border border-iris-100">
                  <p className="font-semibold text-[10px] uppercase text-iris-500 mb-1">Live voice detected:</p>
                  <p className="italic">"{currentSpokenText}"</p>
                </div>
              )}
            </div>

            {/* SPEAKER 2 CONSOLE */}
            <div
              className={`relative flex flex-col justify-between rounded-2xl border bg-white p-6 shadow-sm transition-all ${
                activeMic === "speaker2"
                  ? "border-lagoon-500 ring-2 ring-lagoon-500/20 shadow-md"
                  : "border-slate-200"
              }`}
            >
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="flex h-3 w-3 rounded-full bg-lagoon-500" />
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
                    className="h-8 w-44 text-xs font-medium"
                  >
                    {COMMON_VOICE_LANGS.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name}
                      </option>
                    ))}
                  </Select>
                </div>

                <div className="my-8 flex flex-col items-center justify-center text-center">
                  {/* SOUNDWAVE PULSE ANIMATION */}
                  <div className="relative mb-6">
                    {activeMic === "speaker2" && (
                      <div className="absolute -inset-4 rounded-full bg-lagoon-400/20 animate-ping" />
                    )}
                    <button
                      type="button"
                      onClick={() => startListening("speaker2")}
                      className={`relative flex h-20 w-20 items-center justify-center rounded-full shadow-lg transition-all transform active:scale-95 ${
                        activeMic === "speaker2"
                          ? "bg-rose-500 text-white ring-4 ring-rose-200 animate-pulse"
                          : "bg-lagoon-600 text-white hover:bg-lagoon-700 hover:shadow-xl"
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

                  <p className="text-sm font-semibold text-slate-800">
                    {activeMic === "speaker2"
                      ? "Listening to partner's voice…"
                      : `Click to speak in ${
                          COMMON_VOICE_LANGS.find((l) => l.code === speaker2Lang)?.name ||
                          speaker2Lang
                        }`}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Utterance will translate and play back in {speaker1Name}'s language.
                  </p>
                </div>
              </div>

              {activeMic === "speaker2" && currentSpokenText && (
                <div className="rounded-xl bg-lagoon-50 p-3 text-xs text-lagoon-900 border border-lagoon-100">
                  <p className="font-semibold text-[10px] uppercase text-lagoon-500 mb-1">Live voice detected:</p>
                  <p className="italic">"{currentSpokenText}"</p>
                </div>
              )}
            </div>
          </div>

          {/* AUDIO CONTROLS BAR */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer select-none font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={autoPlayAudio}
                  onChange={(e) => setAutoPlayAudio(e.target.checked)}
                  className="rounded border-slate-300 text-iris-600 focus:ring-iris-500"
                />
                {autoPlayAudio ? (
                  <span className="flex items-center gap-1.5 text-iris-700">
                    <Volume2 className="h-4 w-4" /> Smooth Audio Auto-Play (ON)
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-slate-500">
                    <VolumeX className="h-4 w-4" /> Audio Auto-Play (Muted)
                  </span>
                )}
              </label>

              {isTranslating && (
                <span className="flex items-center gap-1 text-iris-600 font-medium">
                  <Sparkles className="h-3.5 w-3.5 animate-spin" /> Translating voice…
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
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
                onClick={exportTranscript}
                disabled={transcripts.length === 0}
                className="gap-1.5 text-xs"
              >
                <Download className="h-3.5 w-3.5" /> Export
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
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900 mb-3 flex items-center justify-between">
              <span>Bilingual Live Transcript ({transcripts.length} exchanges)</span>
              <span className="text-[11px] font-normal text-slate-400">Chronological feed</span>
            </h2>

            <div className="min-h-[220px] max-h-[380px] space-y-3 overflow-y-auto pr-2">
              {transcripts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400">
                  <Languages className="h-8 w-8 mb-2 opacity-50" />
                  <p className="text-xs font-medium">No voice utterances yet.</p>
                  <p className="text-[11px]">Click either microphone above to start the conversation.</p>
                </div>
              ) : (
                transcripts.map((t) => (
                  <div
                    key={t.id}
                    className={`rounded-xl p-3.5 border transition-all ${
                      t.speaker === "speaker1"
                        ? "bg-iris-50/40 border-iris-100 ml-0 mr-8"
                        : "bg-lagoon-50/40 border-lagoon-100 ml-8 mr-0"
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-bold ${
                            t.speaker === "speaker1" ? "text-iris-700" : "text-lagoon-700"
                          }`}
                        >
                          {t.speakerName}
                        </span>
                        <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-[10px] uppercase font-mono">
                          {t.sourceLang} → {t.targetLang}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400">{t.timestamp}</span>
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
      ) : (
        /* VIRTUAL VOICE & VIDEO MEETING ROOM TAB */
        <Card className="max-w-2xl mx-auto space-y-6 p-8 text-center border-slate-200 shadow-sm">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-lagoon-50 text-lagoon-600">
            <Video className="h-8 w-8" />
          </div>

          <div>
            <h2 className="text-xl font-bold text-slate-900">
              Virtual Meeting with Real-time Translation
            </h2>
            <p className="mt-2 text-sm text-slate-500 max-w-md mx-auto">
              Join or host a multi-party WebRTC video & audio call with live speech recognition,
              per-participant translated audio, screen sharing, and meeting links.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 text-left">
            <Select
              label="I speak"
              value={speaker1Lang}
              onChange={(e) => setSpeaker1Lang(e.target.value)}
            >
              {COMMON_VOICE_LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </Select>

            <Select
              label="I want to hear"
              value={speaker2Lang}
              onChange={(e) => setSpeaker2Lang(e.target.value)}
            >
              {COMMON_VOICE_LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </Select>
          </div>

          <Button
            size="lg"
            className="w-full bg-lagoon-600 hover:bg-lagoon-700 text-white shadow-md"
            onClick={() => startMeeting.mutate()}
            loading={startMeeting.isPending}
          >
            <Video className="h-4 w-4 mr-2" /> Launch Meeting Room
          </Button>

          <p className="text-xs text-slate-400">
            Participants can join instantly using your meeting URL from any device. Audio is
            processed securely with self-hosted AI models.
          </p>
        </Card>
      )}
    </div>
  );
}
