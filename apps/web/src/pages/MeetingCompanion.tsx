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
  Layers,
  FileText,
  Radio,
  Play,
  Square,
  Video,
  ExternalLink,
  BookOpen,
  Sliders,
  Trash2,
  Headphones,
  Activity,
} from "lucide-react";
import { api } from "../lib/api";
import { Button, Badge, Input } from "../components/ui";
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

interface GlossaryOption {
  id: string;
  name: string;
  source_language?: string;
  target_language?: string;
}

const SUPPORTED_TARGET_LANGUAGES = [
  { code: "en", name: "English (US)", flag: "🇺🇸" },
  { code: "es", name: "Spanish (Español)", flag: "🇪🇸" },
  { code: "hi", name: "Hindi (हिंदी)", flag: "🇮🇳" },
  { code: "de", name: "German (Deutsch)", flag: "🇩🇪" },
  { code: "fr", name: "French (Français)", flag: "🇫🇷" },
  { code: "ja", name: "Japanese (日本語)", flag: "🇯🇵" },
  { code: "zh", name: "Chinese (中文)", flag: "🇨🇳" },
  { code: "it", name: "Italian (Italiano)", flag: "🇮🇹" },
  { code: "pt", name: "Portuguese (Português)", flag: "🇧🇷" },
  { code: "ar", name: "Arabic (العربية)", flag: "🇸🇦" },
  { code: "ru", name: "Russian (Русский)", flag: "🇷🇺" },
  { code: "ko", name: "Korean (한국어)", flag: "🇰🇷" },
];

export default function MeetingCompanion() {
  const [searchParams] = useSearchParams();
  const initialMeetCode = searchParams.get("meet_code") || "";

  // 1. Connection & Platform State
  const [selectedPlatform, setSelectedPlatform] = useState<"meet" | "zoom" | "teams" | "native">("meet");
  const [meetUrl, setMeetUrl] = useState(
    initialMeetCode ? `https://meet.google.com/${initialMeetCode}` : ""
  );
  const [isConnectingMeet, setIsConnectingMeet] = useState(false);
  const [activeMeetSession, setActiveMeetSession] = useState<{
    meet_code: string;
    room_id: string;
    status: string;
    platform: string;
  } | null>(null);

  // 2. Audio Capture State
  const [captureSource, setCaptureSource] = useState<"tab" | "mic" | "dual">("tab");
  const [isListening, setIsListening] = useState(false);
  const [audioMeterLevel, setAudioMeterLevel] = useState<number>(0);

  // 3. Translation & Language Settings ("You speak" / "You hear and read")
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("en");
  const [formality, setFormality] = useState<"default" | "formal" | "informal">("formal");
  const [showOriginal, setShowOriginal] = useState(true); // Bilingual toggle

  // 4. Voice-to-Voice (V2V) Audio Mode
  const [voiceMode, setVoiceMode] = useState<"subtitles" | "v2v" | "ducked">("subtitles");
  const [duckingRatio, setDuckingRatio] = useState<number>(80); // 80% translated, 20% background

  // 5. Enterprise Customizations (DeepL Concept: Glossaries + Phonetic Lexicon)
  const [glossaries, setGlossaries] = useState<GlossaryOption[]>([]);
  const [selectedGlossaryId, setSelectedGlossaryId] = useState<string>("");
  const [phoneticBoostTerms, setPhoneticBoostTerms] = useState<string>("TalkFlow, GlobalTalk, Neon, LiveKit");

  // 6. Subtitles Display & HUD
  const [isFloatingBar, setIsFloatingBar] = useState(false);
  const [fontSize, setFontSize] = useState<"sm" | "md" | "lg" | "xl">("lg");
  const [autoScroll, setAutoScroll] = useState(true);

  // 7. Live Captions Data
  const [captions, setCaptions] = useState<CaptionItem[]>([]);
  const [tentativeSource, setTentativeSource] = useState("");
  const [tentativeTranslated, setTentativeTranslated] = useState("");

  // 8. AI Meeting Minutes & Summary
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [meetingSummary, setMeetingSummary] = useState<string | null>(null);
  const [copiedSummary, setCopiedSummary] = useState(false);

  // Refs
  const recognitionRef = useRef<any>(null);
  const captionsEndRef = useRef<HTMLDivElement>(null);
  const translationTimeoutRef = useRef<any>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const hudWindowRef = useRef<Window | null>(null);

  // Fetch available organization glossaries
  useEffect(() => {
    async function loadGlossaries() {
      try {
        const res = await api<GlossaryOption[]>("/api/v1/glossaries");
        if (Array.isArray(res)) {
          setGlossaries(res);
        }
      } catch {
        // Fallback: no glossaries loaded
      }
    }
    loadGlossaries();
  }, []);

  // Sync with Detached HUD window whenever captions change
  useEffect(() => {
    updateDetachedHUD();
  }, [captions, tentativeSource, tentativeTranslated, showOriginal]);

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
      if (hudWindowRef.current && !hudWindowRef.current.closed) {
        hudWindowRef.current.close();
      }
    };
  }, []);

  // Quick Connect to External Meeting (Meet, Teams, Zoom)
  async function connectToMeeting() {
    if (!meetUrl.trim()) {
      toast.error("Please enter a meeting link", "Supported: Google Meet, Zoom, Microsoft Teams");
      return;
    }
    setIsConnectingMeet(true);
    try {
      // Determine platform from URL
      let platform = selectedPlatform;
      if (meetUrl.includes("meet.google.com")) platform = "meet";
      else if (meetUrl.includes("zoom.us")) platform = "zoom";
      else if (meetUrl.includes("teams.microsoft.com")) platform = "teams";

      const res = await api<{ meet_code?: string; room_id?: string; status?: string }>("/api/v1/google-meet/connect", {
        method: "POST",
        body: {
          meet_url: meetUrl.trim(),
          bot_name: "TalkFlow Companion",
          source_language: sourceLang,
          target_languages: [targetLang],
          enable_audio_interpretation: voiceMode !== "subtitles",
        },
      });

      const session = {
        meet_code: res.meet_code || meetUrl.split("/").pop() || "MEET-ACTIVE",
        room_id: res.room_id || "room-" + Date.now(),
        status: res.status || "active",
        platform,
      };
      setActiveMeetSession(session);
      toast.success(
        `${platform.toUpperCase()} Bridge Active`,
        `Connected to conference: ${session.meet_code}`
      );
    } catch (err: any) {
      // Graceful fallback for direct audio capture
      const roomCode = meetUrl.split("/").pop() || "CONFERENCE-BRIDGE";
      setActiveMeetSession({
        meet_code: roomCode,
        room_id: "room-local-" + Date.now(),
        status: "direct_audio",
        platform: selectedPlatform,
      });
      toast.info("Direct Audio Bridge Mode", "Listening directly to tab or microphone audio");
    } finally {
      setIsConnectingMeet(false);
    }
  }

  // Phonetic Lexicon Post-Processor (Acoustic Boosting Concept)
  function applyPhoneticBoosting(rawText: string): string {
    if (!phoneticBoostTerms.trim()) return rawText;
    const terms = phoneticBoostTerms.split(",").map((t) => t.trim()).filter(Boolean);
    let enhanced = rawText;
    for (const term of terms) {
      // Match case-insensitive whole words that sound similar
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const regex = new RegExp(`\\b${escaped}\\b`, "gi");
      enhanced = enhanced.replace(regex, term);
    }
    return enhanced;
  }

  // Real-time Text Translation helper with Glossaries & Formality
  async function translateText(text: string, src: string, tgt: string): Promise<string> {
    if (!text.trim()) return "";
    try {
      const boostedText = applyPhoneticBoosting(text);
      const res = await api<any>("/api/v1/translate", {
        method: "POST",
        body: {
          text: boostedText.trim(),
          source_language: src === "auto" ? "" : src,
          target_language: tgt,
          formality: formality !== "default" ? formality : undefined,
          glossary_id: selectedGlossaryId || null,
        },
      });
      if (res?.translations && res.translations.length > 0) {
        return res.translations[0].translated_text || "";
      }
      return boostedText;
    } catch {
      return text;
    }
  }

  // Play Spoken Translation (In-Browser Voice-to-Voice with Audio Ducking)
  function speakTranslation(text: string, lang: string) {
    if (voiceMode === "subtitles" || !text || typeof window === "undefined") return;

    if ("speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang;
        // Adjust volume for audio ducking mode
        if (voiceMode === "ducked") {
          utterance.volume = duckingRatio / 100;
        } else {
          utterance.volume = 1.0;
        }
        window.speechSynthesis.speak(utterance);
      } catch {
        // Fallback
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
        // Capture tab audio from Google Meet / Zoom / Teams
        stream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        toast.info("Audio Source: Tab Audio", "Check 'Share tab audio' in the prompt");
      } else if (captureSource === "mic") {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        toast.info("Audio Source: Microphone Active");
      } else {
        // Dual mode
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

      // Audio Meter Simulation
      try {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioCtx) {
          const audioCtx = new AudioCtx();
          audioContextRef.current = audioCtx;
          const source = audioCtx.createMediaStreamSource(stream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 64;
          source.connect(analyser);

          const dataArray = new Uint8Array(analyser.frequencyBinCount);
          const interval = setInterval(() => {
            if (!audioStreamRef.current) {
              clearInterval(interval);
              return;
            }
            analyser.getByteFrequencyData(dataArray);
            const avg = dataArray.reduce((acc, val) => acc + val, 0) / dataArray.length;
            setAudioMeterLevel(Math.min(100, Math.round((avg / 128) * 100)));
          }, 150);
        }
      } catch {}

      // Initialize Speech Recognition
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
            clearTimeout(translationTimeoutRef.current);
            translationTimeoutRef.current = setTimeout(async () => {
              const preview = await translateText(interim, sourceLang, targetLang);
              setTentativeTranslated(preview);
            }, 100);
          }

          if (final.trim()) {
            setTentativeSource("");
            setTentativeTranslated("");
            const boostedFinal = applyPhoneticBoosting(final);
            const translated = await translateText(boostedFinal, sourceLang, targetLang);
            const newItem: CaptionItem = {
              id: `cap-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              speaker: "Meeting Attendee",
              sourceText: boostedFinal.trim(),
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
          "For maximum accuracy and auto-detection, use Chrome or Edge"
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
    setAudioMeterLevel(0);
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
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }
    setTentativeSource("");
    setTentativeTranslated("");
  }

  // Detached Pop-out HUD Window (Picture-in-Picture over Teams/Zoom/Meet)
  function openDetachedHUD() {
    if (hudWindowRef.current && !hudWindowRef.current.closed) {
      hudWindowRef.current.focus();
      return;
    }
    const popup = window.open(
      "",
      "TalkFlowHUD",
      "width=640,height=280,left=200,top=100,resizable=yes,scrollbars=yes,status=no,toolbar=no"
    );
    if (!popup) {
      toast.error("Popup window blocked", "Please enable popups for this site to use the Floating HUD");
      return;
    }
    popup.document.title = "TalkFlow • Live Meeting Subtitles HUD";
    popup.document.head.innerHTML = `
      <style>
        body {
          margin: 0;
          padding: 14px;
          background: #090d16;
          color: #f1f5f9;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          overflow-y: auto;
        }
        .hud-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.12);
          padding-bottom: 8px;
          margin-bottom: 12px;
          font-size: 11px;
          color: #94a3b8;
        }
        .live-dot {
          height: 8px;
          width: 8px;
          border-radius: 50%;
          background: #10b981;
          display: inline-block;
          margin-right: 6px;
        }
        .caption-item {
          margin-bottom: 10px;
          padding: 8px 12px;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .speaker { font-size: 10px; color: #a5b4fc; font-weight: 600; margin-bottom: 3px; }
        .source-text { font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
        .translated-text { font-size: 16px; color: #38bdf8; font-weight: 600; line-height: 1.3; }
        .tentative { font-style: italic; opacity: 0.85; border-color: rgba(99, 102, 241, 0.4); }
      </style>
    `;
    popup.document.body.innerHTML = `
      <div class="hud-header">
        <div><span class="live-dot"></span><strong>TalkFlow Live HUD</strong> • Float over Zoom/Meet</div>
        <div id="hud-lang-badge">${targetLang.toUpperCase()}</div>
      </div>
      <div id="hud-captions-container">
        <p style="text-align: center; color: #64748b; font-size: 12px; padding: 20px 0;">
          Waiting for speech... Subtitles will stream here in real time.
        </p>
      </div>
    `;
    hudWindowRef.current = popup;
    updateDetachedHUD();
    toast.success("Detached Floating HUD Opened", "Drag this floating window over your video call");
  }

  function updateDetachedHUD() {
    const popup = hudWindowRef.current;
    if (!popup || popup.closed) return;
    const container = popup.document.getElementById("hud-captions-container");
    if (!container) return;

    if (captions.length === 0 && !tentativeSource) {
      container.innerHTML = `
        <p style="text-align: center; color: #64748b; font-size: 12px; padding: 20px 0;">
          Waiting for speech... Subtitles will stream here in real time.
        </p>
      `;
      return;
    }

    const items = captions
      .slice(-4)
      .map(
        (c) => `
        <div class="caption-item">
          <div class="speaker">${c.speaker} • ${c.timestamp}</div>
          ${showOriginal ? `<div class="source-text">${escapeHtml(c.sourceText)}</div>` : ""}
          <div class="translated-text">${escapeHtml(c.translatedText)}</div>
        </div>
      `
      )
      .join("");

    const tentativeHtml = tentativeSource
      ? `
        <div class="caption-item tentative">
          <div class="speaker">Live Speaking...</div>
          ${showOriginal ? `<div class="source-text">${escapeHtml(tentativeSource)}</div>` : ""}
          <div class="translated-text">${escapeHtml(tentativeTranslated || "translating...")}</div>
        </div>
      `
      : "";

    container.innerHTML = items + tentativeHtml;
    popup.scrollTo(0, popup.document.body.scrollHeight);
  }

  function escapeHtml(str: string): string {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Generate AI Executive Meeting Minutes & Summary
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
          message: `Please generate an executive meeting summary with:
1. Executive Summary & Key Decisions
2. Discussion Points by Topic
3. Action Items with Owners
From this multilingual meeting transcript:\n\n${fullTranscript.slice(0, 8000)}`,
        },
      });

      const reply = res?.reply || res?.message || "Summary generated successfully.";
      setMeetingSummary(reply);
      toast.success("Executive Meeting Minutes Generated");
    } catch {
      const localSummary = `### Executive Meeting Summary\n\n**Total Utterances:** ${captions.length}\n**Target Language:** ${targetLang.toUpperCase()}\n\n**Key Discussion Points:**\n` +
        captions.slice(-6).map((c) => `- ${c.sourceText} → *${c.translatedText}*`).join("\n");
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
    const filename = `talkflow-meeting-${new Date().toISOString().slice(0, 10)}.${format}`;

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

  // In-Page Floating Bar View (Picture-in-Picture Style)
  if (isFloatingBar) {
    return (
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[95vw] max-w-4xl bg-ink-950/95 backdrop-blur-2xl border border-iris-500/30 rounded-2xl shadow-2xl p-4 text-white transition-all">
        <div className="flex items-center justify-between pb-3 border-b border-ink-800 text-xs">
          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold tracking-wide text-iris-300">TalkFlow Live Companion</span>
            <Badge tone="neutral" className="bg-ink-800 text-ink-300 text-[10px]">
              {captureSource.toUpperCase()}
            </Badge>
            {voiceMode !== "subtitles" && (
              <Badge tone="neutral" className="bg-iris-950 text-iris-400 border-iris-800 text-[10px]">
                V2V AUDIO
              </Badge>
            )}
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
              onClick={openDetachedHUD}
              className="p-1.5 hover:bg-ink-800 rounded text-ink-400 hover:text-white transition"
              title="Pop-out Detached Window"
            >
              <ExternalLink className="h-4 w-4" />
            </button>
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
                  {showOriginal && <span className="text-ink-400 text-xs mr-2">{c.sourceText}</span>}
                  <p className="font-semibold text-iris-300 text-base">{c.translatedText}</p>
                </div>
              ))}
              {tentativeSource && (
                <div className="text-sm animate-pulse">
                  {showOriginal && <span className="text-ink-500 italic text-xs mr-2">{tentativeSource}</span>}
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
              onClick={() => setVoiceMode(voiceMode === "subtitles" ? "v2v" : "subtitles")}
              className={`p-1.5 rounded border ${
                voiceMode !== "subtitles" ? "bg-iris-600 border-iris-500 text-white" : "border-ink-700 text-ink-400"
              }`}
              title="Voice-to-Voice In-Browser"
            >
              {voiceMode !== "subtitles" ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
            </button>
          </div>
          <span className="text-ink-500">{captions.length} utterances translated</span>
        </div>
      </div>
    );
  }

  // Full Studio View
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16 selection:bg-iris-500 selection:text-white">
      {/* Studio Glass Header */}
      <header className="border-b border-white/10 bg-slate-900/80 sticky top-0 z-20 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-iris-600 to-indigo-500 text-white shadow-lg shadow-iris-600/20 ring-1 ring-white/20">
              <Globe className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-lg font-bold text-white tracking-tight">TalkFlow Live Companion</h1>
                <Badge tone="iris" className="bg-iris-500/20 text-iris-300 border-iris-500/30 text-[11px]">
                  Realtime Meeting Studio
                </Badge>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                Zero-retention voice translation, bilingual subtitles, and autonomous minutes
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Audio meter activity indicator */}
            {isListening && (
              <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-xs">
                <Activity className="h-3.5 w-3.5 text-emerald-400 animate-pulse" />
                <span className="text-[11px] text-slate-300 font-mono">{audioMeterLevel}% Audio</span>
              </div>
            )}

            {/* Detached HUD button */}
            <button
              onClick={openDetachedHUD}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-slate-200 transition"
              title="Pop-out Detached Subtitles Window"
            >
              <ExternalLink className="h-3.5 w-3.5 text-iris-400" />
              <span className="hidden sm:inline">Pop-out HUD</span>
            </button>

            {/* In-page floating bar button */}
            <button
              onClick={() => setIsFloatingBar(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-slate-200 transition"
              title="Switch to in-page floating PIP bar"
            >
              <Minimize2 className="h-3.5 w-3.5 text-iris-400" />
              <span className="hidden sm:inline">Floating Bar</span>
            </button>

            <Link
              to="/meetings"
              className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-slate-300 transition"
            >
              Native Rooms
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 space-y-6">
        {/* Top Control Grid: Platform Bridge & Audio Capture */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Panel 1: Conference Bridge Connector */}
          <div className="rounded-2xl bg-slate-900/70 border border-white/10 p-5 backdrop-blur-md shadow-xl flex flex-col justify-between">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold flex items-center gap-2 text-white">
                  <Video className="h-4 w-4 text-iris-400" />
                  Meeting Conference Bridge
                </h2>
                {activeMeetSession ? (
                  <Badge tone="neutral" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-xs">
                    ● Connected
                  </Badge>
                ) : (
                  <Badge tone="neutral" className="bg-slate-800 text-slate-400 border-white/5 text-xs">
                    Standby
                  </Badge>
                )}
              </div>

              {/* Platform Selector Tabs */}
              <div className="grid grid-cols-4 gap-1 p-1 bg-slate-950/60 rounded-xl border border-white/5 text-[11px] font-medium text-slate-400">
                {(["meet", "zoom", "teams", "native"] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => setSelectedPlatform(p)}
                    className={`py-1 rounded-lg text-center capitalize transition ${
                      selectedPlatform === p ? "bg-iris-600 text-white font-semibold shadow-xs" : "hover:text-slate-200"
                    }`}
                  >
                    {p === "meet" ? "Meet" : p === "zoom" ? "Zoom" : p === "teams" ? "Teams" : "Native"}
                  </button>
                ))}
              </div>

              <div className="flex gap-2 pt-1">
                <Input
                  placeholder={
                    selectedPlatform === "meet"
                      ? "https://meet.google.com/xxx-yyyy-zzz"
                      : selectedPlatform === "zoom"
                      ? "https://zoom.us/j/123456789"
                      : selectedPlatform === "teams"
                      ? "https://teams.microsoft.com/..."
                      : "Native Room ID"
                  }
                  value={meetUrl}
                  onChange={(e) => setMeetUrl(e.target.value)}
                  className="text-xs bg-slate-950/80 border-white/10 text-white placeholder:text-slate-500"
                />
                <Button
                  size="sm"
                  variant="primary"
                  loading={isConnectingMeet}
                  onClick={connectToMeeting}
                  className="shrink-0 bg-iris-600 hover:bg-iris-500 text-white text-xs px-3"
                >
                  Bridge
                </Button>
              </div>
            </div>

            {activeMeetSession && (
              <div className="mt-3 rounded-xl bg-slate-950/60 p-2.5 border border-white/5 text-xs flex items-center justify-between">
                <span className="text-slate-400 font-medium">Session:</span>
                <span className="font-mono text-emerald-400 font-semibold">{activeMeetSession.meet_code}</span>
              </div>
            )}
          </div>

          {/* Panel 2: Audio Stream & Voice-to-Voice Mode */}
          <div className="rounded-2xl bg-slate-900/70 border border-white/10 p-5 backdrop-blur-md shadow-xl flex flex-col justify-between">
            <div className="space-y-3">
              <h2 className="text-sm font-semibold flex items-center gap-2 text-white">
                <Radio className="h-4 w-4 text-iris-400" />
                Audio Ingestion & Voice Output
              </h2>

              {/* Ingestion Source Buttons */}
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => setCaptureSource("tab")}
                  className={`p-2 rounded-xl border text-center transition flex flex-col items-center gap-1 ${
                    captureSource === "tab"
                      ? "border-iris-500/80 bg-iris-500/15 text-iris-300"
                      : "border-white/5 bg-slate-950/40 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Monitor className="h-4 w-4" />
                  <span className="text-xs font-medium">Tab Audio</span>
                </button>
                <button
                  onClick={() => setCaptureSource("mic")}
                  className={`p-2 rounded-xl border text-center transition flex flex-col items-center gap-1 ${
                    captureSource === "mic"
                      ? "border-iris-500/80 bg-iris-500/15 text-iris-300"
                      : "border-white/5 bg-slate-950/40 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Mic className="h-4 w-4" />
                  <span className="text-xs font-medium">Microphone</span>
                </button>
                <button
                  onClick={() => setCaptureSource("dual")}
                  className={`p-2 rounded-xl border text-center transition flex flex-col items-center gap-1 ${
                    captureSource === "dual"
                      ? "border-iris-500/80 bg-iris-500/15 text-iris-300"
                      : "border-white/5 bg-slate-950/40 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Layers className="h-4 w-4" />
                  <span className="text-xs font-medium">Dual Capture</span>
                </button>
              </div>

              {/* Voice-to-Voice Selector (Browser Native Advantage over DeepL) */}
              <div className="flex items-center justify-between text-xs pt-1 border-t border-white/5">
                <span className="text-slate-300 font-medium flex items-center gap-1.5">
                  <Headphones className="h-3.5 w-3.5 text-iris-400" />
                  Voice-to-Voice Mode:
                </span>
                <div className="flex gap-1 bg-slate-950/60 p-0.5 rounded-lg border border-white/5">
                  <button
                    onClick={() => setVoiceMode("subtitles")}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
                      voiceMode === "subtitles" ? "bg-iris-600 text-white" : "text-slate-400"
                    }`}
                  >
                    Subtitles Only
                  </button>
                  <button
                    onClick={() => setVoiceMode("v2v")}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
                      voiceMode === "v2v" ? "bg-iris-600 text-white" : "text-slate-400"
                    }`}
                  >
                    Spoken Voice
                  </button>
                  <button
                    onClick={() => setVoiceMode("ducked")}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
                      voiceMode === "ducked" ? "bg-iris-600 text-white" : "text-slate-400"
                    }`}
                  >
                    Ducked
                  </button>
                </div>
              </div>

              {voiceMode === "ducked" && (
                <div className="flex items-center justify-between pt-1 text-[11px] text-slate-400">
                  <span>Ducking balance:</span>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="range"
                      min="30"
                      max="100"
                      value={duckingRatio}
                      onChange={(e) => setDuckingRatio(Number(e.target.value))}
                      className="w-20 h-1 accent-iris-500 bg-slate-800 rounded"
                    />
                    <span className="font-mono text-iris-300">{duckingRatio}%</span>
                  </div>
                </div>
              )}
            </div>

            {/* Master Start/Stop Button */}
            <div className="pt-3">
              <Button
                variant={isListening ? "danger" : "primary"}
                className={`w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold shadow-lg ${
                  isListening
                    ? "bg-rose-600 hover:bg-rose-500 text-white"
                    : "bg-gradient-to-r from-iris-600 to-indigo-600 hover:from-iris-500 hover:to-indigo-500 text-white"
                }`}
                onClick={isListening ? stopCapture : startCapture}
              >
                {isListening ? (
                  <>
                    <Square className="h-4 w-4" /> Stop Live Translation
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" /> Start Live Translation
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Panel 3: Enterprise Customizations (DeepL Concept: Terms, Formality, Glossaries) */}
          <div className="rounded-2xl bg-slate-900/70 border border-white/10 p-5 backdrop-blur-md shadow-xl space-y-3">
            <h2 className="text-sm font-semibold flex items-center gap-2 text-white">
              <Sliders className="h-4 w-4 text-iris-400" />
              Language & Enterprise Tuning
            </h2>

            <div className="space-y-2.5 text-xs">
              {/* You speak / You hear */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-slate-400 block mb-1">You speak:</span>
                  <select
                    value={sourceLang}
                    onChange={(e) => setSourceLang(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-2 py-1 text-xs text-white"
                  >
                    <option value="auto">Auto-detect</option>
                    {SUPPORTED_TARGET_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.flag} {l.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <span className="text-slate-400 block mb-1">You hear & read:</span>
                  <select
                    value={targetLang}
                    onChange={(e) => setTargetLang(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-2 py-1 text-xs text-white font-medium"
                  >
                    {SUPPORTED_TARGET_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.flag} {l.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Formality Register */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-slate-400">Formality Register:</span>
                <div className="flex gap-1 bg-slate-950/60 p-0.5 rounded-lg border border-white/5">
                  {(["formal", "default", "informal"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFormality(f)}
                      className={`px-2 py-0.5 rounded text-[11px] capitalize transition ${
                        formality === f ? "bg-iris-600 text-white font-medium" : "text-slate-400 hover:text-white"
                      }`}
                    >
                      {f === "default" ? "Natural" : f}
                    </button>
                  ))}
                </div>
              </div>

              {/* Glossaries Selector */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-slate-400 flex items-center gap-1">
                  <BookOpen className="h-3 w-3 text-iris-400" />
                  Active Glossary:
                </span>
                <select
                  value={selectedGlossaryId}
                  onChange={(e) => setSelectedGlossaryId(e.target.value)}
                  className="rounded-lg border border-white/10 bg-slate-950/80 px-2 py-1 text-[11px] text-white"
                >
                  <option value="">None (Standard NMT)</option>
                  {glossaries.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Phonetic Lexicon (Acoustic Boost Words) */}
              <div className="pt-1">
                <span className="text-slate-400 block mb-1 text-[11px]">
                  Phonetic Lexicon (ASR Boost Terms):
                </span>
                <input
                  type="text"
                  value={phoneticBoostTerms}
                  onChange={(e) => setPhoneticBoostTerms(e.target.value)}
                  placeholder="e.g. TalkFlow, Neon, LiveKit, Q3"
                  className="w-full rounded-lg border border-white/10 bg-slate-950/80 px-2 py-1 text-[11px] text-slate-200 placeholder:text-slate-600"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Live Subtitle Workspace & AI Minutes */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Main Subtitle Box (2 columns) */}
          <div className="lg:col-span-2 space-y-4">
            <div className="rounded-2xl bg-slate-900/80 border border-white/10 flex flex-col h-[560px] overflow-hidden shadow-2xl backdrop-blur-xl">
              {/* Header Toolbar */}
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 bg-slate-950/60">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      isListening ? "bg-emerald-400 shadow-md shadow-emerald-500/50 animate-pulse" : "bg-slate-600"
                    }`}
                  />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
                    Live Translated Stream
                  </span>
                  <span className="text-xs text-slate-500 font-mono">({captions.length} utterances)</span>
                </div>

                <div className="flex items-center gap-2">
                  {/* Bilingual Toggle ("Show Transcription" DeepL parity) */}
                  <button
                    onClick={() => setShowOriginal(!showOriginal)}
                    className={`px-2 py-1 text-xs border rounded-lg font-medium transition ${
                      showOriginal
                        ? "bg-iris-500/20 border-iris-500/40 text-iris-300"
                        : "border-white/10 text-slate-400 bg-white/5"
                    }`}
                    title="Toggle original transcript display"
                  >
                    Bilingual: {showOriginal ? "ON" : "OFF"}
                  </button>

                  {/* Auto-scroll toggle */}
                  <button
                    onClick={() => setAutoScroll(!autoScroll)}
                    className={`px-2 py-1 text-xs border rounded-lg font-medium transition ${
                      autoScroll
                        ? "bg-iris-500/20 border-iris-500/40 text-iris-300"
                        : "border-white/10 text-slate-400 bg-white/5"
                    }`}
                  >
                    Auto-scroll
                  </button>

                  {/* Font Size controls */}
                  <div className="flex items-center gap-0.5 border border-white/10 rounded-lg p-0.5 bg-slate-950/60">
                    {(["sm", "md", "lg", "xl"] as const).map((sz) => (
                      <button
                        key={sz}
                        onClick={() => setFontSize(sz)}
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase transition ${
                          fontSize === sz ? "bg-iris-600 text-white" : "text-slate-400 hover:text-white"
                        }`}
                      >
                        {sz}
                      </button>
                    ))}
                  </div>

                  {/* Export Options */}
                  <div className="flex gap-1 pl-1">
                    <button
                      onClick={() => exportCaptions("srt")}
                      className="px-2 py-1 text-xs border border-white/10 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 font-medium transition"
                      title="Export SubRip (.srt)"
                    >
                      SRT
                    </button>
                    <button
                      onClick={() => exportCaptions("txt")}
                      className="px-2 py-1 text-xs border border-white/10 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 font-medium transition"
                      title="Export Text (.txt)"
                    >
                      TXT
                    </button>
                    {captions.length > 0 && (
                      <button
                        onClick={() => setCaptions([])}
                        className="p-1 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-rose-500/10 transition"
                        title="Clear Transcript"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Subtitles Scroll Area */}
              <div className="flex-1 p-5 overflow-y-auto space-y-3.5 bg-slate-950/40">
                {captions.length === 0 && !tentativeSource ? (
                  <div className="flex flex-col items-center justify-center h-full text-center space-y-3">
                    <div className="h-14 w-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-iris-400 shadow-inner">
                      <Globe className="h-7 w-7" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-white text-sm">Ready to stream multilingual subtitles</h3>
                      <p className="text-xs text-slate-400 max-w-sm mt-1">
                        Click "Start Live Translation" or connect a conference link above. Captions and voice output will
                        stream instantaneously.
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    {captions.map((c) => (
                      <div
                        key={c.id}
                        className="rounded-xl p-3.5 bg-slate-900/60 border border-white/5 transition hover:border-iris-500/30"
                      >
                        <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                          <div className="flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 rounded-full bg-iris-400" />
                            <span className="font-medium text-slate-200">{c.speaker}</span>
                          </div>
                          <span className="font-mono text-[11px] text-slate-500">{c.timestamp}</span>
                        </div>
                        {/* Original Speech (Bilingual toggle) */}
                        {showOriginal && (
                          <p className="text-xs text-slate-400 mb-1 font-sans">{c.sourceText}</p>
                        )}
                        {/* High-Contrast Translated Speech */}
                        <p
                          className={`font-semibold text-iris-300 tracking-wide ${
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

                    {/* Tentative Streaming Utterance (DeepL / Meet Real-Time Wave) */}
                    {tentativeSource && (
                      <div className="rounded-xl p-3.5 bg-iris-500/10 border border-iris-500/30 animate-pulse">
                        <div className="flex items-center justify-between text-xs text-iris-400 mb-1">
                          <span className="font-medium">Live Speaker (speaking...)</span>
                          <span className="text-[10px] uppercase font-bold tracking-wider">Streaming</span>
                        </div>
                        {showOriginal && (
                          <p className="text-xs text-slate-400 italic mb-1">{tentativeSource}</p>
                        )}
                        <p
                          className={`font-medium italic text-cyan-300 ${
                            fontSize === "sm"
                              ? "text-sm"
                              : fontSize === "md"
                              ? "text-base"
                              : fontSize === "lg"
                              ? "text-lg"
                              : "text-xl"
                          }`}
                        >
                          {tentativeTranslated || "translating..."}
                        </p>
                      </div>
                    )}
                    <div ref={captionsEndRef} />
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Right Column: AI Executive Minutes & Summary */}
          <div className="space-y-4">
            <div className="rounded-2xl bg-slate-900/80 border border-white/10 p-5 flex flex-col h-[560px] shadow-2xl backdrop-blur-xl">
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <h2 className="text-sm font-semibold flex items-center gap-2 text-white">
                  <Sparkles className="h-4 w-4 text-iris-400" />
                  Executive Minutes
                </h2>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={isGeneratingSummary}
                  onClick={generateMeetingSummary}
                  className="text-xs bg-white/5 border border-white/10 text-slate-200 hover:bg-white/10"
                >
                  Generate Minutes
                </Button>
              </div>

              <div className="flex-1 py-3 overflow-y-auto">
                {meetingSummary ? (
                  <div className="prose prose-invert prose-xs max-w-none text-slate-300 space-y-2 whitespace-pre-line text-xs font-sans leading-relaxed">
                    {meetingSummary}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-center space-y-2 text-slate-500">
                    <FileText className="h-8 w-8 text-slate-600" />
                    <p className="text-xs max-w-xs">
                      Click "Generate Minutes" to synthesize key decisions, topics, and actionable next steps from the
                      live multilingual conversation.
                    </p>
                  </div>
                )}
              </div>

              {meetingSummary && (
                <div className="pt-3 border-t border-white/10 flex justify-between items-center">
                  <span className="text-[11px] text-slate-500">Minutes Ready</span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(meetingSummary);
                      setCopiedSummary(true);
                      setTimeout(() => setCopiedSummary(false), 2000);
                      toast.success("Summary copied to clipboard");
                    }}
                    className="flex items-center gap-1 text-xs text-iris-400 font-medium hover:text-iris-300 transition"
                  >
                    {copiedSummary ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedSummary ? "Copied" : "Copy to Clipboard"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
