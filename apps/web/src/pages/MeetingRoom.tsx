import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  CameraOff,
  Check,
  Copy,
  FileText,
  Globe,
  Info,
  MessageSquare,
  Mic,
  MicOff,
  MonitorUp,
  PhoneOff,
  Settings,
  Share2,
  ShieldCheck,
  Sparkles,
  Subtitles,
  Users,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { useLanguages, languageLabel } from "../hooks/useLanguages";
import { useLiveKitRoom } from "../hooks/useLiveKitRoom";
import { AudioPlayer, MicCapture, b64ToBytes } from "../lib/audio";
import { MeetingSocket, type SocketState } from "../lib/ws";
import type { Meeting, ParticipantInfo, Preferences, RealtimeEvent, TranscriptItem } from "../lib/types";
import { Button, ErrorState, SegmentedControl, Select, Spinner } from "../components/ui";
import { VideoTile } from "../components/meeting/VideoTile";
import { toast } from "../stores/toasts";
import { useAuth } from "../stores/auth";
import { createVirtualCameraStream } from "../lib/virtualCamera";

interface CaptionLine {
  id: string;
  speaker: string;
  language: string;
  original?: string;
  originalFinal: boolean;
  translated?: string;
  translatedLang?: string;
  partial: boolean;
  failed?: string;
  latencyMs?: number;
}

interface ChatLine {
  id: string;
  sender: string;
  original: string;
  language: string;
  translated?: string;
  mine: boolean;
}

const SAMPLE_RATE = 16000;

export default function MeetingRoom() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const { data: langs } = useLanguages();
  const caps = langs ?? [];
  const [localVideoStream, setLocalVideoStream] = React.useState<MediaStream | null>(null);
  const localVideoStreamRef = React.useRef<MediaStream | null>(null);
  localVideoStreamRef.current = localVideoStream;

  const meetingQ = useQuery({ queryKey: ["meeting", id], queryFn: () => api<Meeting>(`/api/v1/meetings/${id}`) });
  const participantsQ = useQuery({
    queryKey: ["meeting", id, "participants"],
    queryFn: () => api<ParticipantInfo[]>(`/api/v1/meetings/${id}/participants`),
    refetchInterval: 10_000,
  });

  // ---------------- local state ----------------
  const [prefs, setPrefs] = React.useState<Preferences>({
    speaking_language: "AUTO",
    listening_language: user?.default_language || "en",
    audio_mode: "translated",
    caption_mode: "both",
    latency_mode: "balanced",
  });
  const [, setSocketState] = React.useState<SocketState>("connecting");
  const [micOn, setMicOn] = React.useState(false);
  const [cameraOn, setCameraOn] = React.useState(false);
  const [usingVirtualCamera, setUsingVirtualCamera] = React.useState(false);
  const [cameraPermissionBlocked, setCameraPermissionBlocked] = React.useState(false);
  const [showChromeGuide, setShowChromeGuide] = React.useState(false);
  const virtualCameraCleanupRef = React.useRef<(() => void) | null>(null);
  const [screenOn, setScreenOn] = React.useState(false);
  const [speakingNow, setSpeakingNow] = React.useState<string | null>(null);
  const [captions, setCaptions] = React.useState<CaptionLine[]>([]);
  const [showCaptionsOverlay, setShowCaptionsOverlay] = React.useState(true);
  const [chat, setChat] = React.useState<ChatLine[]>([]);
  const [chatDraft, setChatDraft] = React.useState("");
  const [chatDisplay, setChatDisplay] = React.useState<"original" | "mine" | "both">("both");
  
  // Google Meet Side Drawer State
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [drawerTab, setDrawerTab] = React.useState<"info" | "people" | "chat" | "captions" | "summary">("chat");
  const [settingsOpen, setSettingsOpen] = React.useState(false);

  const [notice, setNotice] = React.useState<string | null>(null);
  const [summary, setSummary] = React.useState<any>(null);
  const [myParticipantId, setMyParticipantId] = React.useState<string | undefined>();
  const [displayName, setDisplayName] = React.useState(user?.full_name || "Guest");
  const [inviteCopied, setInviteCopied] = React.useState(false);
  const [callTime, setCallTime] = React.useState("00:00");

  // Call timer effect
  React.useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      const diff = Math.floor((Date.now() - start) / 1000);
      const m = Math.floor(diff / 60).toString().padStart(2, "0");
      const s = (diff % 60).toString().padStart(2, "0");
      setCallTime(`${m}:${s}`);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const mediaRoom = useLiveKitRoom({
    enabled: meetingQ.data?.transport === "livekit" && !!meetingQ.data.livekit_url,
    meetingId: id,
    participantId: myParticipantId,
    audioMode: prefs.audio_mode,
  });

  const socketRef = React.useRef<MeetingSocket | null>(null);
  const micRef = React.useRef<MicCapture | null>(null);
  const playerRef = React.useRef<AudioPlayer | null>(null);
  const mediaRoomStateRef = React.useRef(mediaRoom.state);
  mediaRoomStateRef.current = mediaRoom.state;
  const prefsRef = React.useRef(prefs);
  prefsRef.current = prefs;
  /** utterance short-id → language (to decide original-relay playback) */
  const utterLangRef = React.useRef<Map<string, string>>(new Map());
  const namesRef = React.useRef<Map<string, string>>(new Map());

  React.useEffect(() => {
    const self = mediaRoom.peers.find((peer) => peer.self);
    if (!self) return;
    setCameraOn(self.cameraOn);
    setScreenOn(self.screenShareOn);
  }, [mediaRoom.peers]);

  useQuery({
    queryKey: ["meeting", id, "transcript"],
    queryFn: () => api<TranscriptItem[]>(`/api/v1/meetings/${id}/transcript`),
    enabled: drawerOpen && drawerTab === "captions",
    refetchInterval: drawerOpen && drawerTab === "captions" ? 8000 : false,
  });

  // ---------------- websocket lifecycle ----------------
  React.useEffect(() => {
    if (!meetingQ.data) return;
    const meeting = meetingQ.data;
    playerRef.current = new AudioPlayer();
    const socket = new MeetingSocket({
      meetingId: id,
      joinToken: meeting.join_token,
      displayName,
      preferences: { ...prefsRef.current },
      participantId: myParticipantId,
      onStateChange: (s) => {
        setSocketState(s);
        if (s === "reconnecting") setNotice("Connection lost — reconnecting. Your transcript and preferences are safe.");
        if (s === "joined") setNotice(null);
      },
      onBinary: (frame) => {
        const player = playerRef.current!;
        const mode = prefsRef.current.audio_mode;
        if (frame.kind === "original") {
          const lang = utterLangRef.current.get(frame.shortId);
          const understoodNatively = lang && lang === prefsRef.current.listening_language;
          const liveKitConnected = mediaRoomStateRef.current === "connected";
          if (
            (liveKitConnected && mode === "translated" && understoodNatively) ||
            (!liveKitConnected &&
              (mode === "original" || mode === "mixed" || (mode === "translated" && understoodNatively)))
          ) {
            player.enqueuePcm16(frame.pcm, SAMPLE_RATE, `orig-${frame.shortId}`);
          }
        } else {
          if (mode === "translated" || mode === "mixed") {
            player.enqueuePcm16(frame.pcm, SAMPLE_RATE, `tts-${frame.shortId}`);
          }
        }
      },
      onEvent: (evt) => handleEvent(evt),
    });
    socketRef.current = socket;
    socket.connect();
    return () => {
      socket.close();
      micRef.current?.stop();
      playerRef.current?.dispose();
      if (virtualCameraCleanupRef.current) {
        virtualCameraCleanupRef.current();
        virtualCameraCleanupRef.current = null;
      }
      if (localVideoStreamRef.current) {
        localVideoStreamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meetingQ.data?.id]);

  function handleEvent(evt: RealtimeEvent) {
    const t = evt.type;
    switch (t) {
      case "session.created":
      case "session.updated":
      case "session.resumed": {
        const pid = evt.participant_id as string | undefined;
        if (pid && (!myParticipantId || evt.type === "session.created")) setMyParticipantId(pid);
        const parts = (evt.participants as any[]) ?? [];
        for (const p of parts) namesRef.current.set(p.participant_id, p.display_name);
        if (evt.type === "session.resumed")
          toast.success("Reconnected", "Session resumed — missed events replayed.");
        break;
      }
      case "participant.joined": {
        namesRef.current.set(evt.participant_id as string, evt.display_name as string);
        qc.invalidateQueries({ queryKey: ["meeting", id, "participants"] });
        break;
      }
      case "participant.left":
        qc.invalidateQueries({ queryKey: ["meeting", id, "participants"] });
        break;
      case "speech.started":
        setSpeakingNow(evt.speaker_id as string);
        break;
      case "speech.ended":
        setSpeakingNow(null);
        if (typeof evt.utterance_id === "string")
          playerRef.current?.cancelTag(`orig-${(evt.utterance_id as string).slice(0, 16)}`);
        break;
      case "transcript.partial":
      case "transcript.final": {
        const uid = evt.utterance_id as string;
        if (typeof uid === "string") utterLangRef.current.set(uid.slice(0, 16), evt.language as string);
        const mine =
          prefsRef.current.caption_mode !== "translated" || evt.language === prefsRef.current.listening_language;
        if (!mine && t === "transcript.partial") break;
        setCaptions((prev) => {
          const line = prev.find((c) => c.id === uid);
          const data: CaptionLine = line ?? {
            id: uid,
            speaker: (evt.display_name as string) || namesRef.current.get(evt.speaker_id as string) || "Speaker",
            language: evt.language as string,
            originalFinal: false,
            partial: true,
          };
          if (mine) {
            data.original = evt.text as string;
            data.originalFinal = t === "transcript.final";
          }
          data.partial = t === "transcript.partial";
          return line ? prev.map((c) => (c.id === uid ? { ...data } : c)) : [...prev.slice(-80), data];
        });
        break;
      }
      case "translation.final": {
        if (evt.target_language !== prefsRef.current.listening_language) break;
        if (prefsRef.current.caption_mode === "original") break;
        const seg = evt.segment_id as string;
        setCaptions((prev) => {
          const idx = [...prev]
            .reverse()
            .findIndex(
              (c) =>
                c.speaker === ((evt.display_name as string) || namesRef.current.get(evt.speaker_id as string)) &&
                !c.translated &&
                !c.id.startsWith("tr:") &&
                c.language === evt.source_language
            );
          if (idx === -1) {
            return [
              ...prev.slice(-80),
              {
                id: `tr:${seg}:${evt.target_language}`,
                speaker: (evt.display_name as string) || namesRef.current.get(evt.speaker_id as string) || "Speaker",
                language: evt.source_language as string,
                translated: evt.text as string,
                translatedLang: evt.target_language as string,
                originalFinal: true,
                partial: false,
                latencyMs: evt.latency_ms as number,
              },
            ];
          }
          const target = prev[prev.length - 1 - idx];
          const updated = {
            ...target,
            translated: evt.text as string,
            translatedLang: evt.target_language as string,
            latencyMs: evt.latency_ms as number,
          };
          return prev.map((c) => (c === target ? updated : c));
        });
        break;
      }
      case "translation.failed": {
        if (evt.target_language !== prefsRef.current.listening_language) break;
        setNotice((evt.user_message as string) ?? "Translation delayed. The original audio is still active.");
        const seg = evt.segment_id as string;
        setCaptions((prev) =>
          prev.some((c) => c.id === `fail:${seg}`)
            ? prev
            : [
                ...prev.slice(-80),
                {
                  id: `fail:${seg}`,
                  speaker: namesRef.current.get(evt.speaker_id as string) || "Speaker",
                  language: "",
                  originalFinal: true,
                  partial: false,
                  failed: (evt.user_message as string) ?? "Translation unavailable",
                },
              ]
        );
        break;
      }
      case "tts.completed": {
        if (evt.target_language !== prefsRef.current.listening_language) break;
        const mode = prefsRef.current.audio_mode;
        if (mode !== "translated" && mode !== "mixed") break;
        const audio = evt.audio as string;
        if (!audio) break;
        const uid =
          (evt.utterance_id as string | undefined)?.slice(0, 16) ?? (evt.segment_id as string).slice(0, 16);
        void playerRef.current?.resumeContext();
        void playerRef.current?.enqueueWav(b64ToBytes(audio), `tts-${uid}`);
        break;
      }
      case "quality.degraded":
        setNotice((evt.user_message as string) ?? "Live translation is temporarily degraded.");
        break;
      case "quality.latency": {
        if (evt.target_language !== prefsRef.current.listening_language) break;
        const ms = evt.total_e2e_latency_ms as number;
        setCaptions((prev) => {
          const idx = [...prev].reverse().findIndex((c) => c.translated && !c.latencyMs);
          if (idx === -1) return prev;
          const target = prev[prev.length - 1 - idx];
          return prev.map((c) => (c === target ? { ...c, latencyMs: ms } : c));
        });
        break;
      }
      case "chat.message":
        setChat((prev) => [
          ...prev,
          {
            id: evt.message_id as string,
            sender: (evt.display_name as string) || "Unknown",
            original: evt.original_text as string,
            language: (evt.language as string) || "",
            mine: evt.participant_id === myParticipantId,
          },
        ]);
        break;
      case "chat.translation":
        if (evt.target_language !== prefsRef.current.listening_language) break;
        setChat((prev) =>
          prev.map((c) => (c.id === evt.message_id ? { ...c, translated: evt.text as string } : c))
        );
        break;
      case "language.changed":
        qc.invalidateQueries({ queryKey: ["meeting", id, "participants"] });
        break;
      default:
        break;
    }
  }

  // ---------------- media controls ----------------
  async function toggleMic() {
    if (micOn) {
      const track = micRef.current?.mediaStream?.getAudioTracks()[0];
      if (track && mediaRoom.state === "connected") {
        void mediaRoom.unpublishMicrophone(track).catch(() => {});
      }
      micRef.current?.stop();
      micRef.current = null;
      setMicOn(false);
      socketRef.current?.sendJson({ type: "audio.stopped" });
      return;
    }
    try {
      await playerRef.current?.resumeContext();
      if (mediaRoom.state === "connected") {
        try {
          await mediaRoom.unlockAudio();
        } catch {}
      }
      const mic = new MicCapture();
      await mic.start(SAMPLE_RATE, (frame) => socketRef.current?.sendAudio(frame));
      micRef.current = mic;
      const track = mic.mediaStream?.getAudioTracks()[0];
      if (track && mediaRoom.state === "connected") {
        try {
          await mediaRoom.publishMicrophone(track);
        } catch {}
      }
      setMicOn(true);
      toast.success(
        "Microphone active",
        "Speaking in " +
          (prefs.speaking_language === "AUTO"
            ? "auto-detected language"
            : languageLabel(caps, prefs.speaking_language))
      );
    } catch {
      micRef.current?.stop();
      micRef.current = null;
      setMicOn(false);
      toast.error("Microphone unavailable", "Grant microphone permission to speak in this meeting.");
    }
  }

  async function toggleCamera() {
    if (cameraOn) {
      if (virtualCameraCleanupRef.current) {
        virtualCameraCleanupRef.current();
        virtualCameraCleanupRef.current = null;
      }
      if (localVideoStream) {
        localVideoStream.getTracks().forEach((t) => t.stop());
        setLocalVideoStream(null);
      }
      if (mediaRoom.state === "connected") {
        try {
          await mediaRoom.setCameraEnabled(false);
        } catch {}
      }
      setCameraOn(false);
      setUsingVirtualCamera(false);
      return;
    }

    try {
      if (mediaRoom.state === "connected") {
        await mediaRoom.setCameraEnabled(true);
        setCameraOn(true);
        setUsingVirtualCamera(false);
        setCameraPermissionBlocked(false);
        toast.success("Camera active", "Hardware webcam feed is live");
      } else {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
          audio: false,
        });
        setLocalVideoStream(stream);
        setCameraOn(true);
        setUsingVirtualCamera(false);
        setCameraPermissionBlocked(false);
        toast.success("Camera active", "Hardware webcam feed is live");
      }
    } catch (err: any) {
      // Browser permission blocked or hardware camera not detected
      // Gracefully switch to Virtual Studio Camera so video feed is active
      if (virtualCameraCleanupRef.current) {
        virtualCameraCleanupRef.current();
        virtualCameraCleanupRef.current = null;
      }
      const virtualCam = createVirtualCameraStream(displayName);
      virtualCameraCleanupRef.current = virtualCam.stop;
      setLocalVideoStream(virtualCam.stream);
      setCameraOn(true);
      setUsingVirtualCamera(true);
      setCameraPermissionBlocked(true);

      const isPermissionDenied =
        err?.name === "NotAllowedError" ||
        err?.name === "PermissionDeniedError" ||
        err?.message?.toLowerCase().includes("permission") ||
        err?.message?.toLowerCase().includes("denied");

      if (isPermissionDenied) {
        toast.warning(
          "Camera Permission Blocked in Browser",
          "Switched to Virtual Studio Camera. Click the camera icon in Chrome's URL bar to enable physical webcam."
        );
      } else {
        toast.warning(
          "Hardware Camera Unavailable",
          "Switched to Virtual Studio Camera."
        );
      }
    }
  }

  async function retryPhysicalCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false,
      });
      // Stop virtual camera
      if (virtualCameraCleanupRef.current) {
        virtualCameraCleanupRef.current();
        virtualCameraCleanupRef.current = null;
      }
      setLocalVideoStream(stream);
      setCameraOn(true);
      setUsingVirtualCamera(false);
      setCameraPermissionBlocked(false);
      setShowChromeGuide(false);
      toast.success("Webcam connected!", "Your live hardware camera is now streaming.");
    } catch {
      toast.error(
        "Camera still blocked",
        "Chrome is still blocking camera access. Follow the guide above to allow localhost access in Chrome."
      );
      setShowChromeGuide(true);
    }
  }

  async function toggleScreen() {
    if (screenOn) {
      if (mediaRoom.state === "connected") {
        try {
          await mediaRoom.setScreenShareEnabled(false);
        } catch {}
      }
      setScreenOn(false);
      return;
    }
    try {
      if (mediaRoom.state === "connected") {
        await mediaRoom.setScreenShareEnabled(true);
        setScreenOn(true);
      } else {
        const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        setLocalVideoStream(screenStream);
        setScreenOn(true);
        screenStream.getVideoTracks()[0].onended = () => {
          setScreenOn(false);
          setLocalVideoStream(null);
        };
      }
    } catch {
      toast.info("Screen sharing cancelled");
    }
  }

  async function copyInviteLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setInviteCopied(true);
      toast.success("Meeting link copied", "Share with teammates or participants to join");
      window.setTimeout(() => setInviteCopied(false), 2000);
    } catch {
      toast.error("Could not copy meeting link");
    }
  }

  function updatePrefs(patch: Partial<Preferences>) {
    setPrefs((p) => ({ ...p, ...patch }));
    socketRef.current?.updatePreferences(patch);
  }

  function toggleDrawer(tabName: "info" | "people" | "chat" | "captions" | "summary") {
    if (drawerOpen && drawerTab === tabName) {
      setDrawerOpen(false);
    } else {
      setDrawerTab(tabName);
      setDrawerOpen(true);
    }
  }

  const summaryMut = useMutation({
    mutationFn: () => api(`/api/v1/meetings/${id}/summary`, { method: "POST" }),
    onSuccess: (r) => setSummary(r),
  });

  // ---------------- render calculations ----------------
  if (meetingQ.isError) {
    return (
      <div className="p-6 bg-slate-900 min-h-screen text-white flex items-center justify-center">
        <ErrorState title={(meetingQ.error as any).message} detail={(meetingQ.error as any).code} />
      </div>
    );
  }

  const participants = (participantsQ.data ?? []).filter((participant) => participant.status === "joined");
  const participantsById = new Map(participants.map((participant) => [participant.id, participant]));

  const callTiles =
    mediaRoom.state === "connected"
      ? mediaRoom.peers.map((peer) => {
          const participant = participantsById.get(peer.id);
          const speakingLanguage = participant?.speaking_language ?? (peer.self ? prefs.speaking_language : "AUTO");
          const listeningLanguage = participant?.listening_language ?? (peer.self ? prefs.listening_language : "en");
          return {
            id: peer.id,
            name: peer.name,
            stream: peer.self ? peer.stream || localVideoStream : peer.stream,
            isScreenShare: peer.isScreenShare,
            self: peer.self,
            speakingLanguage,
            listeningLanguage,
            speaking: speakingNow === peer.id || (peer.self && micOn && !!speakingNow),
            muted: peer.self ? !micOn : !peer.microphoneOn,
            isVirtualCamera: peer.self ? usingVirtualCamera : false,
          };
        })
      : participants.map((participant) => {
          const isSelf = participant.id === myParticipantId;
          return {
            id: participant.id,
            name: participant.display_name,
            stream: isSelf ? localVideoStream : null,
            isScreenShare: false,
            self: isSelf,
            speakingLanguage: participant.speaking_language,
            listeningLanguage: participant.listening_language,
            speaking: speakingNow === participant.id || (isSelf && micOn && !!speakingNow),
            muted: isSelf ? !micOn : true,
            isVirtualCamera: isSelf ? usingVirtualCamera : false,
          };
        });

  const hasSelfTile = callTiles.some((t) => t.self);
  const finalTiles = hasSelfTile
    ? callTiles
    : [
        {
          id: myParticipantId || "me",
          name: displayName + " (You)",
          stream: localVideoStream,
          isScreenShare: screenOn,
          self: true,
          speakingLanguage: prefs.speaking_language,
          listeningLanguage: prefs.listening_language,
          speaking: micOn && !!speakingNow,
          muted: !micOn,
          isVirtualCamera: usingVirtualCamera,
        },
        ...callTiles,
      ];

  const latestCaption = captions.length > 0 ? captions[captions.length - 1] : null;

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[#131314] text-white select-none">
      {/* =========================================================================
          TOP MINIMAL HEADER (Google Meet Standard)
         ========================================================================= */}
      <div className="flex h-14 items-center justify-between border-b border-white/10 bg-[#1E1F22] px-4 shrink-0 z-20">
        {/* Left: Leave / Room Title & Connection status */}
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => nav("/meetings")}
            className="text-slate-300 hover:text-white hover:bg-white/10 text-xs gap-1.5 h-8 px-2.5 rounded-lg"
          >
            ← Meetings
          </Button>

          <div className="h-4 w-px bg-white/20 hidden sm:block" />

          <div className="flex items-center gap-2 min-w-0">
            <h1 className="text-sm font-semibold text-white truncate max-w-[180px] sm:max-w-xs md:max-w-md">
              {meetingQ.data?.title ?? "Meeting Room"}
            </h1>

            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>

            <span className="hidden md:inline-flex text-[11px] px-2 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono">
              room: {meetingQ.data?.room_name || id.slice(0, 8)}
            </span>
          </div>
        </div>

        {/* Center: Live Language Routing Tag (Google Meet Multilingual Pill) */}
        <div className="hidden lg:flex items-center">
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/15 border border-white/10 text-xs text-slate-200 transition-all hover:scale-[1.02]"
            title="Click to adjust audio translation preferences"
          >
            <Globe className="h-3.5 w-3.5 text-dl-blue" />
            <span className="font-medium">
              I speak: {languageLabel(caps, prefs.speaking_language)} ➔ Hear: {languageLabel(caps, prefs.listening_language)}
            </span>
            <span className="text-[10px] text-emerald-400 font-mono bg-emerald-950/60 border border-emerald-800/40 px-1.5 py-0.2 rounded-full">
              &lt; 350ms
            </span>
          </button>
        </div>

        {/* Right: Quick Invite & User Name Chip */}
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void copyInviteLink()}
            className="text-slate-300 hover:text-white hover:bg-white/10 text-xs gap-1.5 h-8 px-2.5 rounded-lg"
            title="Copy invitation link"
          >
            {inviteCopied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">{inviteCopied ? "Copied" : "Copy invite"}</span>
          </Button>

          <div className="flex items-center gap-1.5 pl-2 border-l border-white/10">
            <input
              id="display-name"
              className="w-24 sm:w-28 rounded-md bg-white/10 border border-white/15 px-2 py-1 text-xs text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-dl-blue"
              value={displayName}
              placeholder="Your Name"
              onChange={(e) => setDisplayName(e.target.value)}
              title="Edit your display name"
            />
          </div>
        </div>
      </div>

      {notice && (
        <div className="flex items-center gap-2 border-b border-amber-500/20 bg-amber-950/60 px-4 py-2 text-xs text-amber-200 shrink-0" role="status">
          <span aria-hidden>⚠</span>
          <span className="flex-1">{notice}</span>
          <button className="font-semibold underline hover:text-white" onClick={() => setNotice(null)}>
            dismiss
          </button>
        </div>
      )}

      {/* =========================================================================
          MAIN STAGE: VIDEO CANVAS & COLLAPSIBLE DRAWER
         ========================================================================= */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {/* Left / Center: Video Stage */}
        <div className="flex flex-1 flex-col min-w-0 p-3 sm:p-5 relative justify-between overflow-y-auto">
          {/* Connection Status Pill Banner */}
          <div className="mx-auto mb-3 flex items-center gap-2 rounded-full border border-white/10 bg-[#1E1F22]/90 backdrop-blur-md px-3.5 py-1 text-xs text-slate-300 shadow-sm" role="status">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                mediaRoom.state === "connected"
                  ? "bg-emerald-400"
                  : mediaRoom.state === "error"
                  ? "bg-red-400"
                  : "bg-amber-400 animate-pulse"
              }`}
            />
            <span>
              {mediaRoom.state === "connected" && "Neural audio & camera stream connected"}
              {mediaRoom.state === "connecting" && "Connecting audio & video room…"}
              {mediaRoom.state === "reconnecting" && "Reconnecting to media server…"}
              {mediaRoom.state === "error" && (mediaRoom.error ?? "Failed to connect to video room")}
              {mediaRoom.state === "unavailable" && "WebRTC mesh active · Live translation ready"}
            </span>
          </div>

          {/* Camera Permission Denied / Virtual Camera Notification Banner */}
          {cameraPermissionBlocked && (
            <div className="mx-auto mb-3 w-full max-w-4xl rounded-2xl border border-amber-500/30 bg-gradient-to-r from-amber-950/80 via-slate-900/90 to-amber-950/80 p-3.5 shadow-xl backdrop-blur-md">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
                    <CameraOff className="h-4.5 w-4.5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">Browser Camera Permission Blocked</span>
                      <span className="rounded-full bg-sky-500/20 border border-sky-500/30 px-2 py-0.5 text-[10px] font-medium text-sky-300">
                        Virtual Studio Camera Active
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-300 mt-0.5">
                      Your browser denied webcam access. GlobalTalk is streaming an animated studio avatar so you are visible in the meeting.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowChromeGuide((v) => !v)}
                    className="text-xs text-amber-300 hover:text-white hover:bg-amber-500/20 h-8 px-2.5 rounded-lg border border-amber-500/30"
                  >
                    <Info className="h-3.5 w-3.5 mr-1" />
                    How to Unblock
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void retryPhysicalCamera()}
                    className="bg-amber-500 hover:bg-amber-600 text-slate-950 font-semibold text-xs h-8 px-3 rounded-lg shadow-sm"
                  >
                    <Camera className="h-3.5 w-3.5 mr-1 text-slate-950" />
                    Retry Webcam
                  </Button>
                  <button
                    type="button"
                    onClick={() => setCameraPermissionBlocked(false)}
                    className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10"
                    aria-label="Dismiss banner"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Chrome Unblock Step-by-Step Instructions */}
              {showChromeGuide && (
                <div className="mt-3 pt-3 border-t border-amber-500/20 text-xs text-slate-300 animate-fadeIn">
                  <p className="font-semibold text-amber-200 mb-2">To enable your physical camera in Chrome:</p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-[11px]">
                    <div className="bg-black/40 border border-white/10 rounded-xl p-2.5">
                      <span className="font-bold text-amber-300 block mb-1">Step 1: URL Bar Icon</span>
                      Look at Chrome address bar at top. Click the <strong>lock / tune icon</strong> or <strong>camera icon with red cross</strong> next to <code className="text-sky-300">localhost:5173</code>.
                    </div>
                    <div className="bg-black/40 border border-white/10 rounded-xl p-2.5">
                      <span className="font-bold text-amber-300 block mb-1">Step 2: Allow Camera</span>
                      In the permission popup, switch the <strong>Camera</strong> toggle from Blocked to <strong>Allow</strong>.
                    </div>
                    <div className="bg-black/40 border border-white/10 rounded-xl p-2.5">
                      <span className="font-bold text-amber-300 block mb-1">Step 3: Click Retry</span>
                      Click the <strong>Retry Webcam</strong> button above. Your live physical webcam will immediately replace the virtual studio feed.
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Dynamic Video Grid (Responsive 1-tile, 2-tile, or multi-peer) */}
          <div
            className={`grid flex-1 items-center justify-center gap-3 sm:gap-4 w-full max-w-6xl mx-auto my-auto ${
              finalTiles.length === 1
                ? "grid-cols-1 max-w-3xl"
                : finalTiles.length === 2
                ? "grid-cols-1 md:grid-cols-2"
                : finalTiles.length <= 4
                ? "grid-cols-1 sm:grid-cols-2"
                : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
            }`}
          >
            {finalTiles.map((tile) => (
              <VideoTile
                key={tile.id}
                name={tile.name}
                lang={languageLabel(caps, tile.speakingLanguage === "AUTO" ? "en" : tile.speakingLanguage)}
                hear={languageLabel(caps, tile.listeningLanguage)}
                stream={tile.stream}
                videoOn={tile.self ? cameraOn && !!tile.stream : !!tile.stream}
                isVirtualCamera={tile.isVirtualCamera}
                isScreenShare={tile.isScreenShare}
                speaking={tile.speaking}
                muted={tile.muted}
                self={tile.self}
                className="aspect-video w-full rounded-2xl border border-white/10 shadow-lg bg-[#202124]"
              />
            ))}
          </div>

          <div ref={mediaRoom.audioContainerRef} className="sr-only" aria-hidden="true" />

          {/* Google Meet Live Multilingual Floating Subtitles Overlay */}
          {showCaptionsOverlay && latestCaption && (
            <div className="pointer-events-none mt-2 w-full max-w-2xl mx-auto z-10 animate-fade-in">
              <div className="rounded-xl border border-white/15 bg-black/80 backdrop-blur-md px-4 py-2.5 text-center text-sm shadow-xl">
                <div className="flex items-center justify-center gap-2 text-[11px] text-sky-300 font-medium mb-0.5">
                  <span>{latestCaption.speaker}</span>
                  {latestCaption.language && (
                    <span className="uppercase text-[10px] px-1.5 py-0.2 rounded bg-white/15 text-slate-200">
                      {latestCaption.language}
                    </span>
                  )}
                  {latestCaption.latencyMs && (
                    <span className="text-slate-400 text-[10px]">~{Math.round(latestCaption.latencyMs)}ms</span>
                  )}
                </div>
                <p className="text-white font-medium text-sm sm:text-base leading-snug">
                  {latestCaption.translated || latestCaption.original}
                </p>
                {latestCaption.translated && latestCaption.original && (
                  <p className="text-slate-400 text-xs italic mt-0.5">{latestCaption.original}</p>
                )}
              </div>
            </div>
          )}

          {micOn && (
            <p className="mt-2 text-center text-[11px] text-slate-400" role="status">
              <Spinner className="mr-1 inline h-3 w-3 text-emerald-400" />
              Microphone listening in {prefs.speaking_language === "AUTO" ? "any language" : languageLabel(caps, prefs.speaking_language)}
            </p>
          )}
        </div>

        {/* Right Side: Google Meet Collapsible Slide-Out Drawer */}
        {drawerOpen && (
          <aside
            className="w-full sm:w-96 border-l border-white/10 bg-[#1E1F22] flex flex-col h-full z-30 transition-all duration-300 shrink-0"
            aria-label="Meeting side panel"
          >
            {/* Drawer Header */}
            <div className="flex h-14 items-center justify-between border-b border-white/10 px-4">
              <div className="flex items-center gap-2">
                {drawerTab === "chat" && <MessageSquare className="h-4 w-4 text-dl-blue" />}
                {drawerTab === "people" && <Users className="h-4 w-4 text-dl-blue" />}
                {drawerTab === "captions" && <Subtitles className="h-4 w-4 text-dl-blue" />}
                {drawerTab === "summary" && <Sparkles className="h-4 w-4 text-amber-400" />}
                {drawerTab === "info" && <Info className="h-4 w-4 text-dl-blue" />}
                <h2 className="text-sm font-semibold text-white capitalize">
                  {drawerTab === "chat"
                    ? "In-call Messages"
                    : drawerTab === "people"
                    ? `People (${finalTiles.length})`
                    : drawerTab === "captions"
                    ? "Live Captions & Transcripts"
                    : drawerTab === "summary"
                    ? "AI Meeting Summary"
                    : "Meeting Details"}
                </h2>
              </div>

              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="h-8 w-8 rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                aria-label="Close side panel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Drawer Tab Navigation */}
            <div className="flex border-b border-white/10 text-xs font-medium bg-[#1A1B1D]">
              {(["chat", "people", "captions", "summary", "info"] as const).map((tb) => (
                <button
                  key={tb}
                  onClick={() => setDrawerTab(tb)}
                  className={`flex-1 py-2.5 text-center capitalize transition border-b-2 ${
                    drawerTab === tb
                      ? "border-dl-blue text-white font-semibold"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {tb === "captions" ? "Captions" : tb}
                </button>
              ))}
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-4 min-h-0">
              {/* TAB 1: IN-CALL CHAT */}
              {drawerTab === "chat" && (
                <div className="flex h-full flex-col">
                  <div className="mb-3 flex items-center justify-between pb-2 border-b border-white/10">
                    <span className="text-[11px] text-slate-400">Translate messages:</span>
                    <SegmentedControl
                      ariaLabel="Chat display mode"
                      value={chatDisplay}
                      onChange={setChatDisplay}
                      options={[
                        { value: "original", label: "Original" },
                        { value: "mine", label: "My language" },
                        { value: "both", label: "Both" },
                      ]}
                    />
                  </div>

                  <div className="flex-1 space-y-2.5 overflow-y-auto pr-1 min-h-0" aria-live="polite">
                    {chat.map((m) => (
                      <div
                        key={m.id}
                        className={`rounded-xl p-3 text-xs ${
                          m.mine ? "ml-6 bg-dl-blue/20 border border-dl-blue/30 text-white" : "mr-6 bg-white/5 border border-white/10 text-slate-200"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1 text-[10px] text-slate-400">
                          <span className="font-semibold text-slate-300">{m.sender}</span>
                          {m.language && <span className="uppercase">{m.language}</span>}
                        </div>
                        {(chatDisplay === "original" || chatDisplay === "both") && (
                          <p className="text-slate-200 leading-relaxed">{m.original}</p>
                        )}
                        {(chatDisplay === "mine" || chatDisplay === "both") && (
                          <p className={chatDisplay === "both" ? "mt-1 font-semibold text-white" : "text-white"}>
                            {m.translated ?? <span className="italic text-slate-400">(same language)</span>}
                          </p>
                        )}
                      </div>
                    ))}
                    {chat.length === 0 && (
                      <div className="py-12 text-center text-xs text-slate-400">
                        <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-40 text-slate-400" />
                        <p>Messages are translated automatically per listener.</p>
                      </div>
                    )}
                  </div>

                  <form
                    className="mt-3 flex gap-2 pt-2 border-t border-white/10"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (!chatDraft.trim()) return;
                      socketRef.current?.sendChat(chatDraft.trim());
                      setChatDraft("");
                    }}
                  >
                    <input
                      className="flex-1 rounded-xl bg-white/10 border border-white/15 px-3 py-2 text-xs text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-dl-blue"
                      placeholder="Send a message in any language…"
                      aria-label="Chat message"
                      value={chatDraft}
                      onChange={(e) => setChatDraft(e.target.value)}
                    />
                    <Button type="submit" size="sm" className="bg-dl-blue hover:bg-dl-blue-hover text-white rounded-xl">
                      Send
                    </Button>
                  </form>
                </div>
              )}

              {/* TAB 2: PEOPLE / PARTICIPANTS */}
              {drawerTab === "people" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-white/10">
                    <span className="text-xs font-semibold text-slate-300">In this meeting ({finalTiles.length})</span>
                    <Button variant="ghost" size="sm" onClick={() => void copyInviteLink()} className="text-xs text-dl-blue hover:bg-white/10 h-7">
                      <Share2 className="h-3.5 w-3.5 mr-1" /> Invite
                    </Button>
                  </div>

                  <div className="space-y-2">
                    {finalTiles.map((t) => (
                      <div key={t.id} className="flex items-center justify-between p-2.5 rounded-xl bg-white/5 border border-white/10">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="h-8 w-8 rounded-full bg-dl-blue/30 border border-dl-blue/40 flex items-center justify-center font-bold text-xs text-white">
                            {t.name.charAt(0).toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-white truncate">{t.name}</p>
                            <p className="text-[10px] text-slate-400 truncate">
                              Speaks: {t.speakingLanguage} · Hears: {t.listeningLanguage}
                            </p>
                          </div>
                        </div>
                        <div>
                          {t.muted ? (
                            <MicOff className="h-3.5 w-3.5 text-slate-500" />
                          ) : (
                            <Mic className="h-3.5 w-3.5 text-emerald-400" />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* TAB 3: CAPTIONS & TRANSCRIPTS */}
              {drawerTab === "captions" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-white/10">
                    <span className="text-xs font-semibold text-slate-300">Live Multilingual Transcript</span>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-7 text-xs rounded-lg"
                      onClick={() => window.open(`/api/v1/meetings/${id}/transcript/export?fmt=csv`, "_blank")}
                    >
                      Export CSV
                    </Button>
                  </div>

                  <div className="space-y-2.5">
                    {captions.map((c) => (
                      <div key={c.id} className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs space-y-1">
                        <div className="flex items-center justify-between text-[10px] text-slate-400">
                          <span className="font-semibold text-slate-200">{c.speaker}</span>
                          <div className="flex items-center gap-1.5">
                            {c.language && <span className="uppercase">{c.language}</span>}
                            {c.latencyMs != null && <span className="text-emerald-400">{Math.round(c.latencyMs)}ms</span>}
                          </div>
                        </div>
                        {c.original && <p className="text-slate-400 italic">{c.original}</p>}
                        {c.translated && <p className="text-white font-medium">{c.translated}</p>}
                      </div>
                    ))}
                    {captions.length === 0 && (
                      <p className="py-8 text-center text-xs text-slate-400">
                        Speech will appear here transcribed and translated in real time.
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 4: AI SUMMARY */}
              {drawerTab === "summary" && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-400">
                    Generate an instant AI meeting summary and action items based on the canonical speech transcript.
                  </p>
                  <Button
                    size="sm"
                    loading={summaryMut.isPending}
                    onClick={() => summaryMut.mutate()}
                    className="w-full bg-dl-blue hover:bg-dl-blue-hover text-white rounded-xl"
                  >
                    <Sparkles className="h-3.5 w-3.5 mr-1.5" /> Generate summary
                  </Button>
                  {summary && (
                    <div className="space-y-3 text-xs bg-white/5 border border-white/10 rounded-xl p-3">
                      <div>
                        <h4 className="font-bold text-white mb-1 uppercase text-[10px] tracking-wider text-slate-400">Overview</h4>
                        <p className="text-slate-200 leading-relaxed">{summary.summary}</p>
                      </div>
                      {summary.key_points?.length > 0 && (
                        <div>
                          <h4 className="font-bold text-white mb-1 uppercase text-[10px] tracking-wider text-slate-400">Key Points</h4>
                          <ul className="list-disc pl-4 space-y-1 text-slate-300">
                            {summary.key_points.map((kp: string, idx: number) => (
                              <li key={idx}>{kp}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: MEETING INFO */}
              {drawerTab === "info" && (
                <div className="space-y-4 text-xs">
                  <div>
                    <h4 className="font-semibold text-white mb-1">Joining info</h4>
                    <p className="text-slate-400 mb-2">Share this link to invite guests without an account:</p>
                    <code className="block break-all rounded-lg bg-black/40 border border-white/10 p-2.5 text-[11px] font-mono text-slate-300">
                      {window.location.href}
                    </code>
                    <Button size="sm" variant="secondary" className="mt-2 w-full text-xs" onClick={() => void copyInviteLink()}>
                      <Copy className="h-3.5 w-3.5 mr-1" /> Copy joining info
                    </Button>
                  </div>

                  <div className="pt-3 border-t border-white/10 space-y-2">
                    <div className="flex justify-between text-slate-400">
                      <span>Room code</span>
                      <span className="font-mono text-white">{meetingQ.data?.room_name || id.slice(0, 8)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>Security</span>
                      <span className="text-emerald-400 flex items-center gap-1">
                        <ShieldCheck className="h-3 w-3" /> Token Authenticated
                      </span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>Engine</span>
                      <span className="text-white">LiveKit & Whisper Large v3</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      {/* =========================================================================
          BOTTOM FLOATING ACTION DOCK (Google Meet Signature Dock)
         ========================================================================= */}
      <footer className="h-20 bg-[#1E1F22] border-t border-white/10 px-4 sm:px-6 flex items-center justify-between shrink-0 z-30">
        {/* Left: Meeting Code & Live Call Clock */}
        <div className="hidden md:flex items-center gap-3 text-xs text-slate-300">
          <span className="font-mono text-slate-200">{callTime}</span>
          <span className="text-white/20">|</span>
          <button
            type="button"
            onClick={() => void copyInviteLink()}
            className="flex items-center gap-1.5 font-mono text-slate-300 hover:text-white transition-colors"
            title="Click to copy room code"
          >
            <span>{meetingQ.data?.room_name || id.slice(0, 10)}</span>
            <Copy className="h-3 w-3 opacity-60" />
          </button>
        </div>

        {/* Center: Circular In-Call Controls */}
        <div className="flex items-center gap-2.5 sm:gap-3 mx-auto md:mx-0">
          {/* Microphone */}
          <button
            type="button"
            onClick={toggleMic}
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all ${
              micOn
                ? "bg-[#3C4043] hover:bg-[#434649] text-white"
                : "bg-red-600 hover:bg-red-700 text-white ring-2 ring-red-500/30"
            }`}
            aria-label={micOn ? "Mute microphone" : "Start microphone"}
            title={micOn ? "Mute microphone" : "Start microphone"}
          >
            {micOn ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
          </button>

          {/* Camera */}
          <button
            type="button"
            onClick={toggleCamera}
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all relative ${
              cameraOn
                ? usingVirtualCamera
                  ? "bg-sky-600 hover:bg-sky-500 text-white ring-2 ring-sky-400/50 shadow-md shadow-sky-600/30"
                  : "bg-[#3C4043] hover:bg-[#434649] text-white"
                : "bg-red-600 hover:bg-red-700 text-white ring-2 ring-red-500/30"
            }`}
            aria-label={cameraOn ? (usingVirtualCamera ? "Stop virtual camera" : "Stop camera") : "Start camera"}
            title={
              cameraOn
                ? usingVirtualCamera
                  ? "Virtual Studio Camera active (Click to stop, or use banner above to connect webcam)"
                  : "Stop camera"
                : "Start camera"
            }
          >
            {cameraOn ? <Camera className="h-5 w-5" /> : <CameraOff className="h-5 w-5" />}
            {cameraOn && usingVirtualCamera && (
              <span
                className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-sky-400 text-[9px] font-extrabold text-slate-950 shadow-sm"
                title="Virtual Studio Camera"
              >
                V
              </span>
            )}
          </button>

          {/* Captions Overlay Toggle (Google Meet CC Button) */}
          <button
            type="button"
            onClick={() => setShowCaptionsOverlay((prev) => !prev)}
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all ${
              showCaptionsOverlay
                ? "bg-dl-blue text-white shadow-md shadow-dl-blue/30"
                : "bg-[#3C4043] hover:bg-[#434649] text-white"
            }`}
            aria-label={showCaptionsOverlay ? "Turn off captions" : "Turn on captions"}
            title="Toggle live multilingual captions on screen"
          >
            <Subtitles className="h-5 w-5" />
          </button>

          {/* Screen Share */}
          <button
            type="button"
            onClick={toggleScreen}
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all ${
              screenOn
                ? "bg-dl-blue text-white shadow-md shadow-dl-blue/30"
                : "bg-[#3C4043] hover:bg-[#434649] text-white"
            }`}
            aria-label={screenOn ? "Stop sharing" : "Share screen"}
            title="Share your screen"
          >
            <MonitorUp className="h-5 w-5" />
          </button>

          {/* Language & Audio Settings Button */}
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center bg-[#3C4043] hover:bg-[#434649] text-white transition-all"
            aria-label="Language & Audio settings"
            title="Language & Audio Translation preferences"
          >
            <Settings className="h-5 w-5" />
          </button>

          {/* End Call / Leave Meeting (Red Pill) */}
          <button
            type="button"
            onClick={() => {
              if (localVideoStream) {
                localVideoStream.getTracks().forEach((t) => t.stop());
              }
              micRef.current?.stop();
              nav(`/meetings?end=${id}`);
            }}
            className="h-11 px-5 sm:h-12 sm:px-6 rounded-full flex items-center justify-center gap-2 bg-[#EA4335] hover:bg-[#D93025] text-white font-medium shadow-md transition-all active:scale-95"
            aria-label="Leave call"
            title="Leave this meeting"
          >
            <PhoneOff className="h-5 w-5" />
            <span className="hidden sm:inline text-xs font-semibold">Leave</span>
          </button>
        </div>

        {/* Right: Drawer Triggers (Info, People, Chat, Transcripts) */}
        <div className="hidden md:flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => toggleDrawer("info")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${
              drawerOpen && drawerTab === "info" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
            }`}
            title="Meeting details"
            aria-label="Meeting details"
          >
            <Info className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("people")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors relative ${
              drawerOpen && drawerTab === "people" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
            }`}
            title="People"
            aria-label="People"
          >
            <Users className="h-5 w-5" />
            <span className="absolute top-1 right-1 text-[9px] bg-slate-700 px-1 rounded-full font-mono text-white">
              {finalTiles.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("chat")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${
              drawerOpen && drawerTab === "chat" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
            }`}
            title="In-call chat"
            aria-label="In-call chat"
          >
            <MessageSquare className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("captions")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${
              drawerOpen && drawerTab === "captions" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
            }`}
            title="Captions & Transcripts"
            aria-label="Captions & Transcripts"
          >
            <FileText className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("summary")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${
              drawerOpen && drawerTab === "summary" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
            }`}
            title="AI Summary"
            aria-label="AI Summary"
          >
            <Sparkles className="h-5 w-5" />
          </button>
        </div>
      </footer>

      {/* =========================================================================
          LANGUAGE & AUDIO SETTINGS DIALOG (Google Meet Settings Modal)
         ========================================================================= */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-2xl border border-white/15 bg-[#1E1F22] p-6 shadow-2xl space-y-5 animate-scale-in text-white">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <Globe className="h-5 w-5 text-dl-blue" />
                <h3 className="text-base font-bold text-white">Audio & Multilingual Translation Settings</h3>
              </div>
              <button
                type="button"
                onClick={() => setSettingsOpen(false)}
                className="h-8 w-8 rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              {/* I speak */}
              <div>
                <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px]">
                  I speak (My native language)
                </label>
                <Select
                  aria-label="I speak"
                  className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl"
                  value={prefs.speaking_language}
                  onChange={(e) => updatePrefs({ speaking_language: e.target.value })}
                >
                  <option value="AUTO">Auto detect</option>
                  {caps
                    .filter((c) => c.speech_input_supported)
                    .map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name} ({c.native_name})
                      </option>
                    ))}
                </Select>
              </div>

              {/* I want to hear */}
              <div>
                <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px]">
                  I want to hear (Translate incoming audio into)
                </label>
                <Select
                  aria-label="I want to hear"
                  className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl"
                  value={prefs.listening_language}
                  onChange={(e) => updatePrefs({ listening_language: e.target.value })}
                >
                  {caps
                    .filter((c) => c.translation_supported || c.speech_input_supported)
                    .map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name} ({c.native_name})
                        {c.speech_output_supported ? "" : " — captions only"}
                      </option>
                    ))}
                </Select>
              </div>

              {/* Audio Routing Mode */}
              <div>
                <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px]">
                  Audio Playback Mode
                </label>
                <SegmentedControl
                  ariaLabel="Audio mode"
                  value={prefs.audio_mode}
                  onChange={(v) => updatePrefs({ audio_mode: v })}
                  options={[
                    { value: "original", label: "Original", title: "Only the speakers' original voices" },
                    {
                      value: "translated",
                      label: "Translated",
                      title: "Translated voice; original when you understand the source",
                    },
                    { value: "mixed", label: "Mixed", title: "Original and translated voices together" },
                  ]}
                />
              </div>

              {/* Caption display */}
              <div>
                <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px]">
                  Captions Mode
                </label>
                <SegmentedControl
                  ariaLabel="Caption mode"
                  value={prefs.caption_mode}
                  onChange={(v) => updatePrefs({ caption_mode: v })}
                  options={[
                    { value: "original", label: "Original" },
                    { value: "translated", label: "My language" },
                    { value: "both", label: "Both" },
                  ]}
                />
              </div>
            </div>

            <div className="flex justify-end pt-3 border-t border-white/10">
              <Button
                type="button"
                onClick={() => setSettingsOpen(false)}
                className="bg-dl-blue hover:bg-dl-blue-hover text-white rounded-xl px-5"
              >
                Done
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
