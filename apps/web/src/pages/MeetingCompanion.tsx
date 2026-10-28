import { useState, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Volume2,
  VolumeX,
  Mic,
  Monitor,
  Sparkles,
  Copy,
  Check,
  Maximize2,
  Minimize2,
  Globe,
  Settings2,
  Layers,
  FileText,
  Radio,
  Play,
  Square,
  Video,
} from "lucide-react";
import { api } from "../lib/api";
import { Button, Card, Badge, Input } from "../components/ui";
import { toast } from "../stores/toasts";

interface CaptionItem {
  id: string;
  speaker: string;
  sourceText: string;
  translatedText: string;
  sourceLang: string;
  targetLang: string;
  timestamp: string;
}

const SUPPORTED_TARGET_LANGUAGES = [
  { code: "en", name: "English", flag: "🇬🇧" },
  { code: "es", name: "Spanish", flag: "🇪🇸" },
  { code: "hi", name: "Hindi (हिंदी)", flag: "🇮🇳" },
  { code: "fr", name: "French", flag: "🇫🇷" },
  { code: "de", name: "German", flag: "🇩🇪" },
  { code: "ja", name: "Japanese (日本語)", flag: "🇯🇵" },
  { code: "zh", name: "Chinese (中文)", flag: "🇨🇳" },
  { code: "it", name: "Italian", flag: "🇮🇹" },
  { code: "pt", name: "Portuguese", flag: "🇧🇷" },
  { code: "ar", name: "Arabic (العربية)", flag: "🇸🇦" },
  { code: "ru", name: "Russian", flag: "🇷🇺" },
  { code: "ko", name: "Korean (한국어)", flag: "🇰🇷" },
];

export default function MeetingCompanion() {
  const [searchParams] = useSearchParams();
  const initialMeetCode = searchParams.get("meet_code") || "";

  // Connection & Capture State
  const [meetUrl, setMeetUrl] = useState(
    initialMeetCode ? `https://meet.google.com/${initialMeetCode}` : ""
  );
  const [isConnectingMeet, setIsConnectingMeet] = useState(false);
  const [activeMeetSession, setActiveMeetSession] = useState<{
    meet_code: string;
    room_id: string;
    status: string;
  } | null>(null);

  // Audio capture state
  const [captureSource, setCaptureSource] = useState<"tab" | "mic" | "dual">("tab");
  const [isListening, setIsListening] = useState(false);

  // Translation Preferences
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("hi");
  const [formality, setFormality] = useState<"default" | "formal" | "informal">("default");
  const [ttsEnabled, setTtsEnabled] = useState(false);

  // Subtitle Display State
  const [isFloatingBar, setIsFloatingBar] = useState(false);
  const [fontSize, setFontSize] = useState<"sm" | "md" | "lg" | "xl">("lg");
  const [autoScroll, setAutoScroll] = useState(true);

  // Live Captions & Streaming
  const [captions, setCaptions] = useState<CaptionItem[]>([]);
  const [tentativeSource, setTentativeSource] = useState("");
  const [tentativeTranslated, setTentativeTranslated] = useState("");

  // AI Meeting Minutes & Summary
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [meetingSummary, setMeetingSummary] = useState<string | null>(null);
  const [copiedSummary, setCopiedSummary] = useState(false);

  // Refs
  const recognitionRef = useRef<any>(null);
  const captionsEndRef = useRef<HTMLDivElement>(null);
  const translationTimeoutRef = useRef<any>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);

  // Auto-scroll subtitles
  useEffect(() => {
    if (autoScroll && captionsEndRef.current) {
      captionsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [captions, tentativeSource, autoScroll]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCapture();
    };
  }, []);

  // Quick Connect to Google Meet via TalkFlow Backend Bridge
  async function connectToGoogleMeet() {
    if (!meetUrl.trim()) {
      toast.error("Please enter a valid Google Meet URL");
      return;
    }
    setIsConnectingMeet(true);
    try {
      const res = await api<{ meet_code: string; room_id: string; status: string }>("/api/v1/google-meet/connect", {
        method: "POST",
        body: {
          meet_url: meetUrl.trim(),
          bot_name: "TalkFlow Subtitle Companion",
          source_language: sourceLang,
          target_languages: [targetLang],
          enable_audio_interpretation: ttsEnabled,
        },
      });
      setActiveMeetSession(res);
      toast.success("Google Meet Translation Bridge Active", `Connected to room: ${res.meet_code}`);
    } catch (err: any) {
      toast.error("Failed to connect Google Meet bridge", err?.message || "Verify the Meet URL");
    } finally {
      setIsConnectingMeet(false);
    }
  }

  // Real-time Text Translation helper
  async function translateText(text: string, src: string, tgt: string): Promise<string> {
    if (!text.trim()) return "";
    try {
      const res = await api<any>("/api/v1/translate", {
        method: "POST",
        body: {
          text: text.trim(),
          source_language: src === "auto" ? "" : src,
          target_language: tgt,
          formality: formality !== "default" ? formality : undefined,
        },
      });
      if (res?.translations && res.translations.length > 0) {
        return res.translations[0].translated_text || "";
      }
      return text;
    } catch {
      // Fallback: Echo text if offline
      return text;
    }
  }

  // Play Spoken Translation (TTS)
  function speakTranslation(text: string, lang: string) {
    if (!ttsEnabled || !text || typeof window === "undefined") return;

    if ("speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang;
        window.speechSynthesis.speak(utterance);
      } catch {
        // Voice synthesis fallback
      }
    }
  }

  // Start Capturing Audio & Real-Time Recognition
  async function startCapture() {
    try {
      let stream: MediaStream | null = null;

      if (captureSource === "tab") {
        if (!navigator.mediaDevices?.getDisplayMedia) {
          toast.error("Browser does not support tab/display media capture");
          return;
        }
        // Capture tab/screen audio from Google Meet / Zoom
        stream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        toast.info("Audio Source: Tab Audio", "Ensure you checked 'Share tab audio' in browser prompt");
      } else if (captureSource === "mic") {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        toast.info("Audio Source: Microphone active");
      } else {
        // Dual mode: Mic + Display
        const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        let dispStream: MediaStream | null = null;
        try {
          dispStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        } catch {}
        stream = dispStream || micStream;
      }

      audioStreamRef.current = stream;

      // Handle stream termination by user
      stream.getVideoTracks().forEach((track) => {
        track.onended = () => stopCapture();
      });

      // Initialize Client-Assisted Speech Recognition (Google Meet pattern)
      const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRec) {
        const recognizer = new SpeechRec();
        recognizer.continuous = true;
        recognizer.interimResults = true;
        recognizer.lang = sourceLang === "auto" ? "en-US" : sourceLang;

        recognizer.onresult = async (event: any) => {
          let interim = "";
          let final = "";

          for (let i = event.resultIndex; i < event.results.length; ++i) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              final += transcript;
            } else {
              interim += transcript;
            }
          }

          if (interim.trim()) {
            setTentativeSource(interim);
            // Debounced tentative translation for streaming previews
            clearTimeout(translationTimeoutRef.current);
            translationTimeoutRef.current = setTimeout(async () => {
              const preview = await translateText(interim, sourceLang, targetLang);
              setTentativeTranslated(preview);
            }, 120);
          }

          if (final.trim()) {
            setTentativeSource("");
            setTentativeTranslated("");
            const translated = await translateText(final, sourceLang, targetLang);
            const newItem: CaptionItem = {
              id: `cap-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              speaker: "Meeting Attendee",
              sourceText: final.trim(),
              translatedText: translated.trim(),
              sourceLang: sourceLang,
              targetLang: targetLang,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            };
            setCaptions((prev) => [...prev, newItem]);
            speakTranslation(translated, targetLang);
          }
        };

        recognizer.onerror = (err: any) => {
          if (err.error !== "no-speech") {
            console.warn("Speech recognition warning:", err.error);
          }
        };

        recognizer.onend = () => {
          if (isListening && recognitionRef.current) {
            try {
              recognizer.start();
            } catch {}
          }
        };

        recognizer.start();
        recognitionRef.current = recognizer;
      } else {
        toast.warning(
          "Browser speech recognition engine not available",
          "For full Chrome/Edge performance, use Google Chrome or Microsoft Edge"
        );
      }

      setIsListening(true);
    } catch (err: any) {
      toast.error("Failed to start audio capture", err?.message || "Permission denied");
      stopCapture();
    }
  }

  // Stop Audio Capture & Recognition
  function stopCapture() {
    setIsListening(false);
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {}
      recognitionRef.current = null;
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((t) => t.stop());
      audioStreamRef.current = null;
    }
    setTentativeSource("");
    setTentativeTranslated("");
  }

  // Generate AI Meeting Minutes & Summary
  async function generateMeetingSummary() {
    if (captions.length === 0) {
      toast.info("No captions recorded yet", "Start speaking or capturing audio first");
      return;
    }
    setIsGeneratingSummary(true);
    try {
      const fullTranscript = captions
        .map((c) => `[${c.timestamp}] ${c.speaker}: ${c.sourceText} (${c.translatedText})`)
        .join("\n");

      const res = await api<any>("/api/v1/assistant/chat", {
        method: "POST",
        body: {
          message: `Please generate a structured, executive meeting summary with Key Decisions, Discussion Points, and Action Items from the following multilingual meeting transcript:\n\n${fullTranscript.slice(0, 8000)}`,
        },
      });

      const reply = res?.reply || res?.message || "Summary generated successfully.";
      setMeetingSummary(reply);
      toast.success("AI Meeting Minutes Generated");
    } catch {
      const localSummary = `### Meeting Summary & Minutes\n\n**Total Utterances:** ${captions.length}\n**Target Language:** ${targetLang.toUpperCase()}\n\n**Key Discussion Points:**\n` +
        captions.slice(-5).map((c) => `- ${c.sourceText} → *${c.translatedText}*`).join("\n");
      setMeetingSummary(localSummary);
      toast.success("Meeting Summary generated locally");
    } finally {
      setIsGeneratingSummary(false);
    }
  }

  // Export Captions (SRT, VTT, JSON, TXT)
  function exportCaptions(format: "srt" | "vtt" | "json" | "txt") {
    if (captions.length === 0) {
      toast.info("No captions to export");
      return;
    }
    let content = "";
    let mimeType = "text/plain";
    const filename = `talkflow-meet-subtitles-${new Date().toISOString().slice(0, 10)}.${format}`;

    if (format === "srt") {
      content = captions
        .map((c, i) => `${i + 1}\n00:00:${i < 10 ? "0" + i : i},000 --> 00:00:${i + 1 < 10 ? "0" + (i + 1) : i + 1},000\n${c.sourceText}\n${c.translatedText}\n`)
        .join("\n");
    } else if (format === "vtt") {
      content = "WEBVTT\n\n" + captions
        .map((c, i) => `00:00:${i < 10 ? "0" + i : i}.000 --> 00:00:${i + 1 < 10 ? "0" + (i + 1) : i + 1}.000\n${c.sourceText}\n${c.translatedText}\n`)
        .join("\n");
    } else if (format === "json") {
      content = JSON.stringify(captions, null, 2);
      mimeType = "application/json";
    } else {
      content = captions
        .map((c) => `[${c.timestamp}] ${c.speaker}: ${c.sourceText}\n  -> [${c.targetLang}]: ${c.translatedText}`)
        .join("\n\n");
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported as .${format.toUpperCase()}`);
  }

  // Compact Floating Bar View (Picture-in-Picture Style)
  if (isFloatingBar) {
    return (
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[95vw] max-w-4xl bg-ink-950/95 backdrop-blur-xl border border-iris-500/40 rounded-2xl shadow-2xl p-4 text-white transition-all">
        <div className="flex items-center justify-between pb-3 border-b border-ink-800 text-xs">
          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold tracking-wide text-iris-300">TalkFlow Live Companion</span>
            <Badge tone="neutral" className="bg-ink-800 text-ink-300 text-[10px]">
              {captureSource.toUpperCase()} AUDIO
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              className="bg-ink-800 border border-ink-700 rounded px-2 py-1 text-xs text-white"
            >
              {SUPPORTED_TARGET_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.flag} {l.name}
                </option>
              ))}
            </select>
            <button
              onClick={() => setIsFloatingBar(false)}
              className="p-1.5 hover:bg-ink-800 rounded text-ink-400 hover:text-white transition"
              title="Expand to Full View"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Live Subtitle Stream */}
        <div className="py-3 min-h-[90px] max-h-[140px] overflow-y-auto">
          {captions.length === 0 && !tentativeSource ? (
            <p className="text-center text-ink-500 text-sm italic py-4">
              Listening for meeting speech... Subtitles will stream here in real time.
            </p>
          ) : (
            <div className="space-y-2">
              {captions.slice(-2).map((c) => (
                <div key={c.id} className="text-sm">
                  <span className="text-ink-400 text-xs mr-2">{c.sourceText}</span>
                  <p className="font-semibold text-iris-300 text-base">{c.translatedText}</p>
                </div>
              ))}
              {tentativeSource && (
                <div className="text-sm animate-pulse">
                  <span className="text-ink-500 italic text-xs mr-2">{tentativeSource}</span>
                  <p className="font-medium text-iris-400/80 italic text-base">
                    {tentativeTranslated || "translating..."}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Quick controls */}
        <div className="flex items-center justify-between pt-2 border-t border-ink-800 text-xs">
          <div className="flex items-center gap-2">
            <button
              onClick={() => (isListening ? stopCapture() : startCapture())}
              className={`flex items-center gap-1.5 px-3 py-1 rounded font-medium ${
                isListening ? "bg-rose-600 text-white" : "bg-iris-600 text-white"
              }`}
            >
              {isListening ? <Square className="h-3 w-3" /> : <Play className="h-3 w-3" />}
              {isListening ? "Stop Capturing" : "Resume"}
            </button>
            <button
              onClick={() => setTtsEnabled(!ttsEnabled)}
              className={`p-1.5 rounded border ${
                ttsEnabled ? "bg-iris-600 border-iris-500 text-white" : "border-ink-700 text-ink-400"
              }`}
              title="Voice Interpreter TTS"
            >
              {ttsEnabled ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
            </button>
          </div>
          <span className="text-ink-500">{captions.length} utterances translated</span>
        </div>
      </div>
    );
  }

  // Full Suite View
  return (
    <div className="min-h-screen bg-surface-subtle text-ink-900 pb-16">
      {/* Top Banner */}
      <header className="border-b border-border bg-surface-panel sticky top-0 z-20 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-iris-600 text-white shadow-md">
              <Globe className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-ink-950">TalkFlow Live Companion</h1>
                <Badge tone="iris" className="text-xs">
                  Google Meet & Live Stream AI
                </Badge>
              </div>
              <p className="text-xs text-ink-500">
                Real-time person-to-person translation, bilingual subtitles, and AI minutes
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsFloatingBar(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-surface hover:bg-surface-subtle text-ink-700 transition"
              title="Switch to floating subtitle bar"
            >
              <Minimize2 className="h-3.5 w-3.5 text-iris-600" />
              Floating Bar (PIP)
            </button>
            <Link
              to="/meetings"
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-surface hover:bg-surface-subtle text-ink-700 transition"
            >
              TalkFlow Meetings
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 space-y-6">
        {/* Top Control Grid: Source & Target Configuration */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Panel 1: Connect External Meeting */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold flex items-center gap-2 text-ink-950">
                <Video className="h-4 w-4 text-iris-600" />
                Google Meet Bridge
              </h2>
              {activeMeetSession && (
                <Badge tone="neutral" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">
                  Connected
                </Badge>
              )}
            </div>
            <p className="text-xs text-ink-500">
              Paste your Google Meet, Zoom, or Teams link to bridge TalkFlow's real-time AI interpreter into the call.
            </p>
            <div className="flex gap-2">
              <Input
                placeholder="https://meet.google.com/xxx-yyyy-zzz"
                value={meetUrl}
                onChange={(e) => setMeetUrl(e.target.value)}
                className="text-xs"
              />
              <Button
                size="sm"
                variant="primary"
                loading={isConnectingMeet}
                onClick={connectToGoogleMeet}
                className="shrink-0"
              >
                Connect
              </Button>
            </div>
            {activeMeetSession && (
              <div className="rounded-lg bg-surface-subtle p-3 border border-border text-xs space-y-1">
                <div className="flex justify-between text-ink-600">
                  <span>Room Code:</span>
                  <span className="font-mono font-medium text-ink-900">{activeMeetSession.meet_code}</span>
                </div>
                <div className="flex justify-between text-ink-600">
                  <span>Session Status:</span>
                  <span className="text-emerald-600 font-medium">Active Bridge</span>
                </div>
              </div>
            )}
          </Card>

          {/* Panel 2: Audio Capture Source */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2 text-ink-950">
              <Radio className="h-4 w-4 text-iris-600" />
              Audio Input Stream
            </h2>
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => setCaptureSource("tab")}
                className={`p-2.5 rounded-xl border text-center transition flex flex-col items-center gap-1.5 ${
                  captureSource === "tab"
                    ? "border-iris-600 bg-iris-50/60 text-iris-900"
                    : "border-border hover:bg-surface-subtle text-ink-600"
                }`}
              >
                <Monitor className="h-4 w-4" />
                <span className="text-xs font-medium">Tab Audio</span>
              </button>
              <button
                onClick={() => setCaptureSource("mic")}
                className={`p-2.5 rounded-xl border text-center transition flex flex-col items-center gap-1.5 ${
                  captureSource === "mic"
                    ? "border-iris-600 bg-iris-50/60 text-iris-900"
                    : "border-border hover:bg-surface-subtle text-ink-600"
                }`}
              >
                <Mic className="h-4 w-4" />
                <span className="text-xs font-medium">Microphone</span>
              </button>
              <button
                onClick={() => setCaptureSource("dual")}
                className={`p-2.5 rounded-xl border text-center transition flex flex-col items-center gap-1.5 ${
                  captureSource === "dual"
                    ? "border-iris-600 bg-iris-50/60 text-iris-900"
                    : "border-border hover:bg-surface-subtle text-ink-600"
                }`}
              >
                <Layers className="h-4 w-4" />
                <span className="text-xs font-medium">Dual Capture</span>
              </button>
            </div>

            <Button
              variant={isListening ? "danger" : "primary"}
              className="w-full flex items-center justify-center gap-2"
              onClick={isListening ? stopCapture : startCapture}
            >
              {isListening ? (
                <>
                  <Square className="h-4 w-4" /> Stop Live Subtitles
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" /> Start Live Subtitles
                </>
              )}
            </Button>
          </Card>

          {/* Panel 3: Translation & Voice Output Options */}
          <Card className="p-5 space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2 text-ink-950">
              <Settings2 className="h-4 w-4 text-iris-600" />
              Language & Voice Settings
            </h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-700">Source Language:</span>
                <select
                  value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}
                  className="rounded-lg border border-border bg-surface px-2.5 py-1 text-xs text-ink-900 font-medium"
                >
                  <option value="auto">Auto-detect</option>
                  {SUPPORTED_TARGET_LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.flag} {l.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-700">Target Language:</span>
                <select
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                  className="rounded-lg border border-border bg-surface px-2.5 py-1 text-xs text-ink-900 font-medium"
                >
                  {SUPPORTED_TARGET_LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.flag} {l.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-700">DeepL Formality:</span>
                <div className="flex gap-1">
                  {(["default", "formal", "informal"] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setFormality(mode)}
                      className={`px-2 py-0.5 rounded text-[11px] capitalize border ${
                        formality === mode
                          ? "bg-iris-600 text-white border-iris-600"
                          : "border-border text-ink-600 hover:bg-surface-subtle"
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between gap-2 pt-1 border-t border-border">
                <span className="text-xs font-medium text-ink-700 flex items-center gap-1.5">
                  <Volume2 className="h-3.5 w-3.5 text-iris-600" />
                  Voice Overlay (TTS):
                </span>
                <button
                  onClick={() => setTtsEnabled(!ttsEnabled)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                    ttsEnabled ? "bg-iris-600 text-white" : "bg-ink-100 text-ink-600"
                  }`}
                >
                  {ttsEnabled ? "Active" : "Muted"}
                </button>
              </div>
            </div>
          </Card>
        </div>

        {/* Live Subtitle Workspace */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Subtitle Box (2 columns) */}
          <div className="lg:col-span-2 space-y-4">
            <Card className="flex flex-col h-[520px] overflow-hidden border-iris-100 shadow-sm">
              {/* Header Toolbar */}
              <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-surface-subtle">
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      isListening ? "bg-emerald-500 animate-pulse" : "bg-ink-300"
                    }`}
                  />
                  <span className="text-xs font-semibold uppercase tracking-wider text-ink-700">
                    Live Translated Subtitles
                  </span>
                  <span className="text-xs text-ink-400">({captions.length} segments)</span>
                </div>

                <div className="flex items-center gap-2">
                  {/* Auto-scroll toggle */}
                  <button
                    onClick={() => setAutoScroll(!autoScroll)}
                    className={`px-2 py-1 text-xs border rounded-md font-medium transition ${
                      autoScroll ? "bg-iris-50 border-iris-300 text-iris-700" : "border-border text-ink-500"
                    }`}
                  >
                    Auto-scroll: {autoScroll ? "ON" : "OFF"}
                  </button>

                  {/* Font Size controls */}
                  <div className="flex items-center gap-1 border border-border rounded-lg p-0.5 bg-surface">
                    {(["sm", "md", "lg", "xl"] as const).map((sz) => (
                      <button
                        key={sz}
                        onClick={() => setFontSize(sz)}
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                          fontSize === sz ? "bg-iris-600 text-white" : "text-ink-600 hover:text-ink-950"
                        }`}
                      >
                        {sz}
                      </button>
                    ))}
                  </div>

                  {/* Export Menu */}
                  <div className="flex gap-1">
                    <button
                      onClick={() => exportCaptions("srt")}
                      className="px-2 py-1 text-xs border border-border rounded-md hover:bg-surface text-ink-700 font-medium"
                      title="Export as SubRip (.srt)"
                    >
                      SRT
                    </button>
                    <button
                      onClick={() => exportCaptions("txt")}
                      className="px-2 py-1 text-xs border border-border rounded-md hover:bg-surface text-ink-700 font-medium"
                      title="Export as Text (.txt)"
                    >
                      TXT
                    </button>
                  </div>
                </div>
              </div>

              {/* Subtitles Scroll Area */}
              <div className="flex-1 p-5 overflow-y-auto space-y-4 bg-surface">
                {captions.length === 0 && !tentativeSource ? (
                  <div className="flex flex-col items-center justify-center h-full text-center space-y-3">
                    <div className="h-12 w-12 rounded-2xl bg-iris-50 flex items-center justify-center text-iris-600">
                      <Globe className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-ink-900">Ready to transcribe and translate</h3>
                      <p className="text-xs text-ink-500 max-w-sm mt-1">
                        Click "Start Live Subtitles" above or connect your Google Meet conference to begin real-time
                        bilingual captions.
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    {captions.map((c) => (
                      <div
                        key={c.id}
                        className="rounded-xl p-3.5 bg-surface-subtle/70 border border-border/60 transition hover:border-iris-200"
                      >
                        <div className="flex items-center justify-between text-xs text-ink-400 mb-1.5">
                          <span className="font-medium text-ink-700">{c.speaker}</span>
                          <span className="font-mono text-[11px]">{c.timestamp}</span>
                        </div>
                        {/* Original Speech */}
                        <p className="text-xs text-ink-500 mb-1">{c.sourceText}</p>
                        {/* DeepL/NMT Translated Speech */}
                        <p
                          className={`font-semibold text-iris-700 ${
                            fontSize === "sm"
                              ? "text-sm"
                              : fontSize === "md"
                              ? "text-base"
                              : fontSize === "lg"
                              ? "text-lg"
                              : "text-xl"
                          }`}
                        >
                          {c.translatedText}
                        </p>
                      </div>
                    ))}

                    {/* Tentative In-flight Speech (Google Meet Streaming Design) */}
                    {tentativeSource && (
                      <div className="rounded-xl p-3.5 bg-iris-50/50 border border-iris-200/80 animate-pulse">
                        <div className="flex items-center justify-between text-xs text-iris-500 mb-1">
                          <span className="font-medium">Live Speaker (speaking...)</span>
                          <span className="text-[10px] uppercase font-bold tracking-wider">Streaming</span>
                        </div>
                        <p className="text-xs text-ink-400 italic mb-1">{tentativeSource}</p>
                        <p
                          className={`font-medium italic text-iris-600 ${
                            fontSize === "sm"
                              ? "text-sm"
                              : fontSize === "md"
                              ? "text-base"
                              : fontSize === "lg"
                              ? "text-lg"
                              : "text-xl"
                          }`}
                        >
                          {tentativeTranslated || "translating speech in real-time..."}
                        </p>
                      </div>
                    )}
                    <div ref={captionsEndRef} />
                  </>
                )}
              </div>
            </Card>
          </div>

          {/* Right Column: AI Minutes & Meeting Summary */}
          <div className="space-y-4">
            <Card className="p-5 flex flex-col h-[520px]">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <h2 className="text-sm font-semibold flex items-center gap-2 text-ink-950">
                  <Sparkles className="h-4 w-4 text-iris-600" />
                  AI Meeting Minutes
                </h2>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={isGeneratingSummary}
                  onClick={generateMeetingSummary}
                  className="text-xs"
                >
                  Generate Summary
                </Button>
              </div>

              <div className="flex-1 py-3 overflow-y-auto">
                {meetingSummary ? (
                  <div className="prose prose-xs max-w-none text-ink-800 space-y-2 whitespace-pre-line text-xs">
                    {meetingSummary}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-center space-y-2 text-ink-400">
                    <FileText className="h-8 w-8 text-ink-300" />
                    <p className="text-xs">
                      Once attendees speak during the meeting, click "Generate Summary" to produce instant meeting
                      minutes, key decisions, and action items.
                    </p>
                  </div>
                )}
              </div>

              {meetingSummary && (
                <div className="pt-3 border-t border-border flex justify-between items-center">
                  <span className="text-[11px] text-ink-400">AI Minutes ready</span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(meetingSummary);
                      setCopiedSummary(true);
                      setTimeout(() => setCopiedSummary(false), 2000);
                      toast.success("Summary copied to clipboard");
                    }}
                    className="flex items-center gap-1 text-xs text-iris-600 font-medium hover:text-iris-700"
                  >
                    {copiedSummary ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedSummary ? "Copied" : "Copy to Clipboard"}
                  </button>
                </div>
              )}
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
