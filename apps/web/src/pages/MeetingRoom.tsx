import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  CameraOff,
  Check,
  Copy,
  Download,
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
  Volume2,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { useLanguages, languageLabel } from "../hooks/useLanguages";
import { useLiveKitRoom } from "../hooks/useLiveKitRoom";
import { AudioPlayer, MicCapture, b64ToBytes } from "../lib/audio";
import { MeetingSocket, type SocketState } from "../lib/ws";
import { WebRTCManager } from "../lib/webrtc";
import type { JoinMeetingResponse, Meeting, ParticipantInfo, Preferences, RealtimeEvent, TranscriptItem } from "../lib/types";
import { Button, ErrorState, SegmentedControl, Select, Spinner } from "../components/ui";
import { VideoTile } from "../components/meeting/VideoTile";
import { toast } from "../stores/toasts";
import { useAuth } from "../stores/auth";
import { createVirtualCameraStream } from "../lib/virtualCamera";
import {
  formatAsTxt,
  formatAsJson,
  formatAsSrt,
  formatAsVtt,
  downloadFile,
  type ExportTranscriptItem,
} from "../lib/transcriptExporter";

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
  const [socketState, setSocketState] = React.useState<SocketState>("connecting");
  const [isOnline, setIsOnline] = React.useState(typeof navigator !== "undefined" ? navigator.onLine : true);
  const [isDegradedNetwork, setIsDegradedNetwork] = React.useState(false);
  const [translationStatus, setTranslationStatus] = React.useState<"normal" | "delayed" | "unavailable">("normal");
  const [translationMessage, setTranslationMessage] = React.useState<string | null>(null);

  const [micOn, setMicOn] = React.useState(false);
  const [micPermissionBlocked, setMicPermissionBlocked] = React.useState(false);
  const [showMicGuide, setShowMicGuide] = React.useState(false);

  const [cameraOn, setCameraOn] = React.useState(false);
  const [usingVirtualCamera, setUsingVirtualCamera] = React.useState(false);
  const [cameraPermissionBlocked, setCameraPermissionBlocked] = React.useState(false);
  const [showChromeGuide, setShowChromeGuide] = React.useState(false);
  const virtualCameraCleanupRef = React.useRef<(() => void) | null>(null);

  // Audio & Hardware device selection + DSP
  const [availableMics, setAvailableMics] = React.useState<MediaDeviceInfo[]>([]);
  const [availableSpeakers, setAvailableSpeakers] = React.useState<MediaDeviceInfo[]>([]);
  const [availableCameras, setAvailableCameras] = React.useState<MediaDeviceInfo[]>([]);
  const [selectedMicId, setSelectedMicId] = React.useState<string>("");
  const [selectedSpeakerId, setSelectedSpeakerId] = React.useState<string>("");
  const [selectedCameraId, setSelectedCameraId] = React.useState<string>("");
  const [dspSettings, setDspSettings] = React.useState({
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  });

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
  const [settingsTab, setSettingsTab] = React.useState<"translation" | "devices">("translation");

  const [notice, setNotice] = React.useState<string | null>(null);
  const [summary, setSummary] = React.useState<any>(null);
  const [myParticipantId, setMyParticipantId] = React.useState<string | undefined>();
  const myParticipantIdRef = React.useRef<string | undefined>(myParticipantId);
  myParticipantIdRef.current = myParticipantId;
  const [displayName, setDisplayName] = React.useState(user?.full_name || (user?.email ? user.email.split("@")[0] : "Guest"));
  const [inviteCopied, setInviteCopied] = React.useState(false);
  const [callTime, setCallTime] = React.useState("00:00");
  const [currentLatencyMs, setCurrentLatencyMs] = React.useState<number | null>(null);

  // Pre-Join Lobby & WebRTC mesh state
  const [hasJoined, setHasJoined] = React.useState<boolean>(false);
  const [isJoining, setIsJoining] = React.useState<boolean>(false);
  const [joinTicket, setJoinTicket] = React.useState<string | undefined>(undefined);
  const [remoteStreams, setRemoteStreams] = React.useState<Map<string, MediaStream>>(new Map());
  const [leftParticipantIds, setLeftParticipantIds] = React.useState<Set<string>>(new Set());
  const webrtcRef = React.useRef<WebRTCManager | null>(null);

  const handleExportTranscript = React.useCallback(
    (format: "txt" | "srt" | "vtt" | "json") => {
      if (captions.length === 0) {
        toast.info("No transcripts yet", "Transcripts will be available as soon as someone speaks.");
        return;
      }
      const exportItems: ExportTranscriptItem[] = captions.map((c, i) => ({
        id: c.id || `cap-${i}`,
        speakerName: c.speaker || "Speaker",
        originalText: c.original || "",
        sourceLang: c.language || "en",
        translatedText: c.translated || c.original || "",
        targetLang: c.translatedLang || prefs.listening_language || "en",
        timestamp: callTime || "00:00",
      }));

      const dateStr = new Date().toISOString().slice(0, 10);
      const baseName = `meeting-transcript-${id.slice(0, 8)}-${dateStr}`;

      switch (format) {
        case "txt":
          downloadFile(formatAsTxt(exportItems), `${baseName}.txt`, "text/plain");
          break;
        case "srt":
          downloadFile(formatAsSrt(exportItems), `${baseName}.srt`, "application/x-subrip");
          break;
        case "vtt":
          downloadFile(formatAsVtt(exportItems), `${baseName}.vtt`, "text/vtt");
          break;
        case "json":
          downloadFile(formatAsJson(exportItems), `${baseName}.json`, "application/json");
          break;
      }
      toast.success("Transcript exported", `Saved as .${format.toUpperCase()}`);
    },
    [captions, id, prefs.listening_language, callTime]
  );

  const handleLeaveMeeting = React.useCallback(async () => {
    if (localVideoStream) {
      localVideoStream.getTracks().forEach((t) => t.stop());
    }
    micRef.current?.stop();
    const pid = myParticipantIdRef.current || myParticipantId;
    if (pid) {
      try {
        await api(`/api/v1/meetings/${id}/leave`, {
          method: "POST",
          body: JSON.stringify({ participant_id: pid }),
        });
      } catch { }
    }
    nav(`/meetings?end=${id}`);
  }, [id, localVideoStream, myParticipantId, nav]);

  React.useEffect(() => {
    const onUnload = () => {
      const pid = myParticipantIdRef.current || myParticipantId;
      if (pid) {
        const payload = JSON.stringify({ participant_id: pid });
        const blob = new Blob([payload], { type: "application/json" });
        navigator.sendBeacon(`/api/v1/meetings/${id}/leave`, blob);
      }
    };
    window.addEventListener("pagehide", onUnload);
    return () => window.removeEventListener("pagehide", onUnload);
  }, [id, myParticipantId]);

  const handleJoinMeeting = React.useCallback(async () => {
    if (isJoining) return;
    setIsJoining(true);
    try {
      const guestKeyStorageKey = `gt_guest_key_${id}`;
      let guestKey = sessionStorage.getItem(guestKeyStorageKey);
      if (!guestKey) {
        guestKey = `guest_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`;
        sessionStorage.setItem(guestKeyStorageKey, guestKey);
      }

      const res = await api<JoinMeetingResponse>(`/api/v1/meetings/${id}/join`, {
        method: "POST",
        body: JSON.stringify({
          display_name: displayName.trim() || user?.full_name || (user?.email ? user.email.split("@")[0] : "Guest"),
          speak_lang: prefs.speaking_language === "AUTO" ? "en" : prefs.speaking_language,
          hear_lang: prefs.listening_language,
          audio_mode: prefs.audio_mode,
          guest_key: guestKey,
        }),
      });

      let ticket: string | undefined;
      if (res.rt_url) {
        try {
          const u = new URL(res.rt_url, window.location.origin);
          ticket = u.searchParams.get("ticket") || undefined;
        } catch {
          const match = res.rt_url.match(/ticket=([^&]+)/);
          if (match) ticket = match[1];
        }
      }

      setMyParticipantId(res.participant_id);
      myParticipantIdRef.current = res.participant_id;
      if (ticket) {
        setJoinTicket(ticket);
      }
      setHasJoined(true);
      void meetingQ.refetch();
      void participantsQ.refetch();
      toast.success("Joined meeting", `Connected as ${displayName}`);
    } catch (err: any) {
      const msg = err?.message || "Failed to join meeting. Please verify meeting ID or network.";
      toast.error("Join Failed", msg);
    } finally {
      setIsJoining(false);
    }
  }, [id, isJoining, displayName, user, prefs, meetingQ, participantsQ]);

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

  // Device enumeration
  const refreshDevices = React.useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      setAvailableMics(devices.filter((d) => d.kind === "audioinput"));
      setAvailableSpeakers(devices.filter((d) => d.kind === "audiooutput"));
      setAvailableCameras(devices.filter((d) => d.kind === "videoinput"));
    } catch (e) {
      console.warn("Device enumeration failed", e);
    }
  }, []);

  React.useEffect(() => {
    void refreshDevices();
    navigator.mediaDevices?.addEventListener("devicechange", refreshDevices);
    return () => {
      navigator.mediaDevices?.removeEventListener("devicechange", refreshDevices);
    };
  }, [refreshDevices]);

  // Network & sleep/wake listeners
  React.useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
      setNotice(null);
      toast.success("Network restored", "Reconnecting session...");
      socketRef.current?.reconnectNow();
    }
    function handleOffline() {
      setIsOnline(false);
      setNotice("You are offline. Reconnecting as soon as network is restored.");
    }
    function handleVisibility() {
      if (document.visibilityState === "visible") {
        if (socketState === "closed" || socketState === "error" || socketState === "reconnecting") {
          socketRef.current?.reconnectNow();
        }
      }
    }
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [socketState]);

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
  /** Phase 5: highest sequence number seen per speaker to prevent stale overwrites on reconnect */
  const highestSeqPerSpeaker = React.useRef<Map<string, number>>(new Map());

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

  // ---------------- WebRTC & WebSocket lifecycle ----------------
  React.useEffect(() => {
    if (!hasJoined) return;

    // 1. Initialize WebRTC mesh manager
    const webrtc = new WebRTCManager({
      localParticipantId: myParticipantId || "guest",
      onRemoteStream: (peerId, stream) => {
        const normId = peerId.toLowerCase().trim();
        setRemoteStreams((prev) => {
          const next = new Map(prev);
          next.set(peerId, stream);
          next.set(normId, stream);
          return next;
        });
      },
      onRemoteStreamRemoved: (peerId) => {
        const normId = peerId.toLowerCase().trim();
        setRemoteStreams((prev) => {
          const next = new Map(prev);
          next.delete(peerId);
          next.delete(normId);
          return next;
        });
      },
      sendSignal: (targetId, signal) => {
        socketRef.current?.sendJson({
          type: "signal",
          data: {
            target_id: targetId,
            signal,
          },
        });
      },
    });

    if (localVideoStreamRef.current) {
      const vTrack = localVideoStreamRef.current.getVideoTracks()[0];
      if (vTrack) webrtc.setVideoTrack(vTrack);
    }
    if (micRef.current?.mediaStream) {
      const aTrack = micRef.current.mediaStream.getAudioTracks()[0];
      if (aTrack) webrtc.setAudioTrack(aTrack);
    }
    webrtcRef.current = webrtc;

    // 2. Initialize Audio Player and Meeting Socket
    playerRef.current = new AudioPlayer();
    const socket = new MeetingSocket({
      meetingId: id,
      joinToken: meetingQ.data?.join_token,
      ticket: joinTicket,
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
      socketRef.current = null;
      webrtc.dispose();
      webrtcRef.current = null;
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
  }, [hasJoined, id, joinTicket]);

  // Synchronize local video track with WebRTC mesh
  React.useEffect(() => {
    if (webrtcRef.current) {
      const vTrack = localVideoStream?.getVideoTracks()[0] || null;
      webrtcRef.current.setVideoTrack(vTrack);
    }
  }, [localVideoStream]);

  // Synchronize participants with WebRTC mesh
  React.useEffect(() => {
    if (!hasJoined || !webrtcRef.current) return;
    const parts = participantsQ.data ?? [];
    for (const p of parts) {
      if (p.id !== myParticipantIdRef.current && p.status === "joined") {
        void webrtcRef.current.initiateCallTo(p.id);
      }
    }
  }, [hasJoined, participantsQ.data]);

  function handleEvent(evt: RealtimeEvent) {
    const t = evt.type;
    switch (t) {
      case "signal": {
        const senderId = (evt.data as any)?.sender_id || (evt as any).sender_id;
        const signal = (evt.data as any)?.signal || (evt as any).signal;
        if (senderId && signal) {
          void webrtcRef.current?.handleSignal(senderId, signal);
        }
        break;
      }
      case "session.created":
      case "session.updated":
      case "session.resumed": {
        const pid = (evt.participant_id as string | undefined) || (evt.data as any)?.participant_id;
        if (pid && (!myParticipantIdRef.current || evt.type === "session.created")) {
          setMyParticipantId(pid);
          myParticipantIdRef.current = pid;
        }
        const parts = ((evt.participants || (evt.data as any)?.participants) as any[]) ?? [];
        for (const p of parts) {
          const peerId = p.participant_id || p.id;
          const pName = p.display_name || p.name;
          if (peerId && pName) namesRef.current.set(peerId, pName);
          if (peerId && peerId !== myParticipantIdRef.current) {
            void webrtcRef.current?.initiateCallTo(peerId);
          }
        }
        if (evt.type === "session.resumed")
          toast.success("Reconnected", "Session resumed — missed events replayed.");
        break;
      }
      case "participant.joined": {
        const pid = (evt.participant_id as string) || (evt.data as any)?.participant_id;
        const pName = (evt.display_name as string) || (evt.data as any)?.display_name;
        if (pid) {
          const normPid = pid.toLowerCase().trim();
          setLeftParticipantIds((prev) => {
            if (!prev.has(normPid)) return prev;
            const next = new Set(prev);
            next.delete(normPid);
            return next;
          });
          if (pName) namesRef.current.set(pid, pName);
          if (pid !== myParticipantIdRef.current) {
            void webrtcRef.current?.initiateCallTo(pid);
          }
        }
        qc.invalidateQueries({ queryKey: ["meeting", id, "participants"] });
        break;
      }
      case "participant.left": {
        const pid = (evt.participant_id as string) || (evt.data as any)?.participant_id;
        if (pid) {
          const normPid = pid.toLowerCase().trim();
          setLeftParticipantIds((prev) => new Set(prev).add(normPid));
          webrtcRef.current?.removePeer(pid);
          setRemoteStreams((prev) => {
            const next = new Map(prev);
            next.delete(pid);
            next.delete(normPid);
            return next;
          });
        }
        qc.invalidateQueries({ queryKey: ["meeting", id, "participants"] });
        break;
      }
      case "speech.started":
        setSpeakingNow(evt.speaker_id as string);
        break;
      case "speech.ended":
        setSpeakingNow(null);
        if (typeof evt.utterance_id === "string")
          playerRef.current?.cancelTag(`orig-${(evt.utterance_id as string).slice(0, 16)}`);
        break;
      case "transcript.partial":
      case "transcript.final":
      case "translation.transcript.partial":
      case "translation.transcript.final": {
        const uid =
          (evt.utterance_id as string) || (evt.utteranceId as string) || (evt.segment_id as string);
        if (typeof uid === "string") utterLangRef.current.set(uid.slice(0, 16), evt.language as string);
        const speakerKey = (evt.speaker_id as string) || (evt.speakerId as string) || "";
        const seqNum = (evt.sequence as number) ?? (evt.seq as number) ?? 0;
        const isFinal = t === "transcript.final" || t === "translation.transcript.final";

        if (speakerKey && seqNum > 0) {
          const currentHigh = highestSeqPerSpeaker.current.get(speakerKey) ?? 0;
          if (isFinal) {
            if (seqNum < currentHigh) {
              // Stale final segment from prior reconnect or network lag: do not overwrite newer state
              break;
            }
            highestSeqPerSpeaker.current.set(speakerKey, Math.max(currentHigh, seqNum));
          } else {
            // Discard flutter if speaker already has a newer finalized utterance
            if (seqNum < currentHigh) {
              break;
            }
          }
        }

        const mine =
          prefsRef.current.caption_mode !== "translated" || evt.language === prefsRef.current.listening_language;
        if (!mine && (t === "transcript.partial" || t === "translation.transcript.partial")) break;
        setCaptions((prev) => {
          const line = prev.find((c) => c.id === uid);
          const data: CaptionLine = line ?? {
            id: uid,
            speaker: (evt.display_name as string) || namesRef.current.get(speakerKey) || "Speaker",
            language: evt.language as string,
            originalFinal: false,
            partial: true,
          };
          if (mine) {
            data.original = (evt.source_text as string) || (evt.text as string);
            data.originalFinal = isFinal;
          }
          data.partial = !isFinal;
          return line ? prev.map((c) => (c.id === uid ? { ...data } : c)) : [...prev.slice(-80), data];
        });
        break;
      }
      case "translation.final":
      case "translation.segment.final":
      case "translation.segment.translated": {
        if (evt.latency_ms) setCurrentLatencyMs(Math.round(evt.latency_ms as number));
        if (translationStatus !== "normal") {
          setTranslationStatus("normal");
          setTranslationMessage(null);
        }
        if (isDegradedNetwork) setIsDegradedNetwork(false);
        setNotice((prev) => (prev && (prev.includes("degraded") || prev.includes("latency") || prev.includes("falling behind")) ? null : prev));

        const targetLang =
          (evt.target_language as string) || (evt.targetLanguage as string) || (evt.target_lang as string);
        if (targetLang !== prefsRef.current.listening_language) break;
        if (prefsRef.current.caption_mode === "original") break;

        const speakerKey = (evt.speaker_id as string) || (evt.speakerId as string) || "";
        const seqNum = (evt.sequence as number) ?? (evt.seq as number) ?? 0;
        if (speakerKey && seqNum > 0) {
          const currentHigh = highestSeqPerSpeaker.current.get(speakerKey) ?? 0;
          if (seqNum < currentHigh) {
            // Reconnection guard: older segment cannot overwrite newer translated caption
            break;
          }
          highestSeqPerSpeaker.current.set(speakerKey, Math.max(currentHigh, seqNum));
        }

        const seg =
          (evt.segment_id as string) || (evt.utterance_id as string) || (evt.utteranceId as string);
        const dedupId =
          (evt.dedup_key as string) || (evt.dedupKey as string) || `tr:${seg}:${targetLang}`;
        const translatedText =
          (evt.translated_text as string) || (evt.translatedText as string) || (evt.text as string);
        const sourceLang =
          (evt.source_language as string) || (evt.sourceLanguage as string) || (evt.source_lang as string);

        setCaptions((prev) => {
          const existingIdx = prev.findIndex(
            (c) => c.id === dedupId || c.id === `tr:${seg}:${targetLang}` || (c.id === seg && c.translated)
          );
          if (existingIdx !== -1) {
            return prev.map((c, i) =>
              i === existingIdx
                ? {
                  ...c,
                  translated: translatedText,
                  translatedLang: targetLang,
                  latencyMs: (evt.latency_ms as number) || c.latencyMs,
                }
                : c
            );
          }
          const idx = [...prev]
            .reverse()
            .findIndex(
              (c) =>
                (c.id === seg ||
                  c.speaker === ((evt.display_name as string) || namesRef.current.get(speakerKey))) &&
                !c.translated &&
                !c.id.startsWith("tr:") &&
                (!c.language || c.language === sourceLang)
            );
          if (idx === -1) {
            return [
              ...prev.slice(-80),
              {
                id: dedupId,
                speaker: (evt.display_name as string) || namesRef.current.get(speakerKey) || "Speaker",
                language: sourceLang,
                translated: translatedText,
                translatedLang: targetLang,
                originalFinal: true,
                partial: false,
                latencyMs: evt.latency_ms as number,
              },
            ];
          }
          const target = prev[prev.length - 1 - idx];
          const updated = {
            ...target,
            translated: translatedText,
            translatedLang: targetLang,
            latencyMs: evt.latency_ms as number,
          };
          return prev.map((c) => (c === target ? updated : c));
        });
        break;
      }
      case "translation.failed":
      case "translation.error": {
        if (evt.target_language && evt.target_language !== prefsRef.current.listening_language) break;
        setTranslationStatus("unavailable");
        setTranslationMessage((evt.user_message as string) ?? "Translation unavailable. Original audio is active.");
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
      case "tts.chunk":
      case "translation.tts.ready": {
        const targetLang =
          (evt.target_language as string) || (evt.targetLanguage as string) || (evt.target_lang as string);
        if (targetLang !== prefsRef.current.listening_language) break;
        const mode = prefsRef.current.audio_mode;
        if (mode !== "translated" && mode !== "mixed") break;
        const audio = (evt.audio_base64 as string) || (evt.audio as string);
        if (!audio) break;
        const uid =
          (evt.utterance_id as string | undefined)?.slice(0, 16) ?? (evt.segment_id as string)?.slice(0, 16);
        const seq = (evt.sequence as number) ?? (evt.seq as number) ?? 0;
        const chunkIdx = (evt.chunk_index as number) ?? (evt.chunkIndex as number) ?? 0;
        const speakerId = (evt.speaker_id as string) || (evt.speakerId as string) || "";
        void playerRef.current?.resumeContext();
        void playerRef.current?.enqueueWav(
          b64ToBytes(audio),
          `tts-${uid}-${chunkIdx}`,
          { sequence: seq, chunkIndex: chunkIdx, utteranceId: uid, speakerId }
        );
        break;
      }
      case "tts.completed": {
        const targetLang =
          (evt.target_language as string) || (evt.targetLanguage as string) || (evt.target_lang as string);
        if (targetLang !== prefsRef.current.listening_language) break;
        const mode = prefsRef.current.audio_mode;
        if (mode !== "translated" && mode !== "mixed") break;
        const audio = evt.audio as string;
        if (audio) {
          const uid =
            (evt.utterance_id as string | undefined)?.slice(0, 16) ?? (evt.segment_id as string)?.slice(0, 16);
          const seq = (evt.sequence as number) ?? (evt.seq as number) ?? 0;
          const speakerId = (evt.speaker_id as string) || (evt.speakerId as string) || "";
          void playerRef.current?.resumeContext();
          void playerRef.current?.enqueueWav(
            b64ToBytes(audio),
            `tts-${uid}-final`,
            { sequence: seq, chunkIndex: 9999, utteranceId: uid, speakerId }
          );
        }
        break;
      }
      case "quality.degraded":
        setIsDegradedNetwork(true);
        setTranslationStatus("delayed");
        setTranslationMessage((evt.user_message as string) ?? "Live translation is catching up. Original audio remains active.");
        window.setTimeout(() => {
          setTranslationStatus((s) => (s === "delayed" ? "normal" : s));
          setNotice((prev) => (prev && (prev.includes("degraded") || prev.includes("latency") || prev.includes("falling behind")) ? null : prev));
        }, 5000);
        break;
      case "quality.latency": {
        const ms = (evt.total_e2e_latency_ms as number) || 0;
        if (ms > 0) setCurrentLatencyMs(Math.round(ms));
        if (ms > 2000) {
          setIsDegradedNetwork(true);
          setTranslationStatus("delayed");
          setTranslationMessage(`High translation latency (~${Math.round(ms)}ms). Audio prioritized.`);
        }
        if (evt.target_language !== prefsRef.current.listening_language) break;
        setCaptions((prev) => {
          const idx = [...prev].reverse().findIndex((c) => c.translated && !c.latencyMs);
          if (idx === -1) return prev;
          const target = prev[prev.length - 1 - idx];
          return prev.map((c) => (c === target ? { ...c, latencyMs: ms } : c));
        });
        break;
      }
      case "error": {
        const errCode = (evt as any).code;
        if (errCode === "tts_unavailable" || errCode === "stt_unavailable") {
          setTranslationStatus("unavailable");
          setTranslationMessage((evt as any).message ?? "Speech translation is currently unavailable.");
        }
        break;
      }
      case "chat.message":
        setChat((prev) => {
          if (prev.some((c) => c.id === (evt.message_id as string))) return prev;
          return [
            ...prev,
            {
              id: evt.message_id as string,
              sender: (evt.display_name as string) || "Unknown",
              original: evt.original_text as string,
              language: (evt.language as string) || "",
              mine: evt.participant_id === myParticipantId,
            },
          ];
        });
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
        void mediaRoom.unpublishMicrophone(track).catch(() => { });
      }
      micRef.current?.stop();
      micRef.current = null;
      setMicOn(false);
      webrtcRef.current?.setAudioTrack(null);
      socketRef.current?.sendJson({ type: "audio.stopped" });
      return;
    }
    try {
      await playerRef.current?.resumeContext();
      if (mediaRoom.state === "connected") {
        try {
          await mediaRoom.unlockAudio();
        } catch { }
      }
      const mic = new MicCapture();
      await mic.start(
        SAMPLE_RATE,
        (frame) => socketRef.current?.sendAudio(frame),
        {
          deviceId: selectedMicId || undefined,
          echoCancellation: dspSettings.echoCancellation,
          noiseSuppression: dspSettings.noiseSuppression,
          autoGainControl: dspSettings.autoGainControl,
        }
      );
      micRef.current = mic;
      const track = mic.mediaStream?.getAudioTracks()[0];
      if (track) {
        webrtcRef.current?.setAudioTrack(track);
        if (mediaRoom.state === "connected") {
          try {
            await mediaRoom.publishMicrophone(track);
          } catch { }
        }
      }
      setMicOn(true);
      setMicPermissionBlocked(false);
      toast.success(
        "Microphone active",
        "Speaking in " +
        (prefs.speaking_language === "AUTO"
          ? "auto-detected language"
          : languageLabel(caps, prefs.speaking_language))
      );
    } catch (err: any) {
      micRef.current?.stop();
      micRef.current = null;
      setMicOn(false);
      webrtcRef.current?.setAudioTrack(null);
      const isPermissionDenied =
        err?.name === "NotAllowedError" ||
        err?.name === "PermissionDeniedError" ||
        err?.message?.toLowerCase().includes("permission") ||
        err?.message?.toLowerCase().includes("denied");
      if (isPermissionDenied) {
        setMicPermissionBlocked(true);
      }
      toast.error(
        "Microphone unavailable",
        isPermissionDenied
          ? "Microphone access blocked. Click 'How to Unblock' to enable audio."
          : "Could not access microphone hardware."
      );
    }
  }

  async function retryPhysicalMic() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setMicPermissionBlocked(false);
      setShowMicGuide(false);
      await toggleMic();
    } catch {
      toast.error("Microphone still blocked", "Follow the browser guide below to allow microphone access.");
      setShowMicGuide(true);
    }
  }

  async function handleSpeakerChange(deviceId: string) {
    setSelectedSpeakerId(deviceId);
    if (playerRef.current) {
      await playerRef.current.setSinkId(deviceId);
    }
    if (mediaRoom.audioContainerRef.current) {
      const audios = mediaRoom.audioContainerRef.current.querySelectorAll("audio");
      for (const el of Array.from(audios)) {
        if ("setSinkId" in el && typeof (el as any).setSinkId === "function") {
          try {
            await (el as any).setSinkId(deviceId);
          } catch { }
        }
      }
    }
    toast.success("Speaker updated", "Audio playback routed to selected device.");
  }

  async function restartMicWithSettings(options: {
    micId?: string;
    dsp?: { echoCancellation: boolean; noiseSuppression: boolean; autoGainControl: boolean };
  }) {
    if (!micOn) return;
    try {
      const activeDsp = options.dsp ?? dspSettings;
      const activeMicId = options.micId ?? selectedMicId;
      const track = micRef.current?.mediaStream?.getAudioTracks()[0];
      if (track && mediaRoom.state === "connected") {
        void mediaRoom.unpublishMicrophone(track).catch(() => { });
      }
      micRef.current?.stop();
      const mic = new MicCapture();
      await mic.start(
        SAMPLE_RATE,
        (frame) => socketRef.current?.sendAudio(frame),
        {
          deviceId: activeMicId || undefined,
          echoCancellation: activeDsp.echoCancellation,
          noiseSuppression: activeDsp.noiseSuppression,
          autoGainControl: activeDsp.autoGainControl,
        }
      );
      micRef.current = mic;
      const newTrack = mic.mediaStream?.getAudioTracks()[0];
      if (newTrack) {
        webrtcRef.current?.setAudioTrack(newTrack);
        if (mediaRoom.state === "connected") {
          try {
            await mediaRoom.publishMicrophone(newTrack);
          } catch { }
        }
      }
      toast.success("Audio settings updated", "Microphone DSP and input updated.");
    } catch (err: any) {
      console.warn("Could not restart mic with new settings", err);
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
        } catch { }
      }
      webrtcRef.current?.setVideoTrack(null);
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
        const videoConstraints: MediaTrackConstraints = {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: "user",
        };
        if (selectedCameraId) {
          videoConstraints.deviceId = { exact: selectedCameraId };
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: false,
        });
        setLocalVideoStream(stream);
        const vTrack = stream.getVideoTracks()[0];
        if (vTrack) webrtcRef.current?.setVideoTrack(vTrack);
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
      const vTrack = virtualCam.stream.getVideoTracks()[0];
      if (vTrack) webrtcRef.current?.setVideoTrack(vTrack);
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
      const videoConstraints: MediaTrackConstraints = {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: "user",
      };
      if (selectedCameraId) {
        videoConstraints.deviceId = { exact: selectedCameraId };
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: videoConstraints,
        audio: false,
      });
      // Stop virtual camera
      if (virtualCameraCleanupRef.current) {
        virtualCameraCleanupRef.current();
        virtualCameraCleanupRef.current = null;
      }
      setLocalVideoStream(stream);
      const vTrack = stream.getVideoTracks()[0];
      if (vTrack) webrtcRef.current?.setVideoTrack(vTrack);
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
        } catch { }
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
  const connectionInfo = React.useMemo(() => {
    if (!isOnline) {
      return {
        label: "Offline · Network interrupted",
        dotClass: "bg-red-500",
        canRetry: true,
      };
    }
    if (socketState === "error" || mediaRoom.state === "error") {
      return {
        label: mediaRoom.error || "Connection error · Click to reconnect",
        dotClass: "bg-red-500",
        canRetry: true,
      };
    }
    if (socketState === "reconnecting" || mediaRoom.state === "reconnecting") {
      return {
        label: "Reconnecting… Audio & transcript preserved",
        dotClass: "bg-amber-400 animate-pulse",
        canRetry: false,
      };
    }
    if (socketState === "connecting" || mediaRoom.state === "connecting") {
      return {
        label: "Connecting to secure meeting session…",
        dotClass: "bg-amber-400 animate-pulse",
        canRetry: false,
      };
    }
    if (isDegradedNetwork) {
      return {
        label: "Degraded Network · Audio prioritized, latency optimized",
        dotClass: "bg-amber-400",
        canRetry: false,
      };
    }
    if (mediaRoom.state === "connected" || socketState === "joined") {
      return {
        label: "Connected · Realtime Translation Active",
        dotClass: "bg-emerald-400",
        canRetry: false,
      };
    }
    return {
      label: "Connecting audio & video room…",
      dotClass: "bg-amber-400 animate-pulse",
      canRetry: false,
    };
  }, [isOnline, socketState, mediaRoom.state, mediaRoom.error, isDegradedNetwork]);

  const participants = (participantsQ.data ?? []).filter(
    (participant) =>
      participant.status === "joined" &&
      !leftParticipantIds.has(participant.id.toLowerCase().trim())
  );
  const participantsById = new Map(participants.map((participant) => [participant.id, participant]));

  // Include peers who connected via WebRTC stream even if participantsQ polling is delayed
  const myNormId = (myParticipantId || "").toLowerCase().trim();
  const knownPeerIds = new Set(participants.map((p) => p.id.toLowerCase().trim()));
  const streamOnlyPeers = Array.from(remoteStreams.keys())
    .map((k) => k.toLowerCase().trim())
    .filter((pid, idx, arr) => arr.indexOf(pid) === idx)
    .filter((pid) => pid !== myNormId && !knownPeerIds.has(pid) && !leftParticipantIds.has(pid))
    .map((pid) => ({
      id: pid,
      display_name: namesRef.current.get(pid) || "Remote Participant",
      status: "joined",
      speaking_language: "AUTO",
      listening_language: "en",
      audio_mode: "translated" as const,
      caption_mode: "both" as const,
    }));
  const combinedParticipants = [...participants, ...streamOnlyPeers];

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
      : combinedParticipants.map((participant) => {
        const normId = participant.id.toLowerCase().trim();
        const isSelf = participant.id === myParticipantId || (!!myNormId && normId === myNormId);
        const remoteStream = !isSelf ? (remoteStreams.get(participant.id) || remoteStreams.get(normId) || null) : null;
        return {
          id: participant.id,
          name: participant.display_name,
          stream: isSelf ? localVideoStream : remoteStream,
          isScreenShare: false,
          self: isSelf,
          speakingLanguage: participant.speaking_language,
          listeningLanguage: participant.listening_language,
          speaking: speakingNow === participant.id || (isSelf && micOn && !!speakingNow),
          muted: isSelf ? !micOn : false,
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

  // ---------------- Pre-Join Lobby View (Google Meet Green Room) ----------------
  if (!hasJoined) {
    return (
      <div className="flex min-h-screen w-full flex-col bg-[#131314] text-white">
        {/* Lobby Top Header */}
        <header className="flex h-14 items-center justify-between border-b border-white/10 bg-[#1E1F22] px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => nav("/meetings")}
              className="text-slate-300 hover:text-white hover:bg-white/10 text-xs gap-1.5 h-8 px-2.5 rounded-lg"
            >
              ← Meetings
            </Button>
            <div className="h-4 w-px bg-white/20" />
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm text-white truncate max-w-xs">
                {meetingQ.data?.title || "GlobalTalk Meeting"}
              </span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono">
                {id.slice(0, 8)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void copyInviteLink()}
              className="text-slate-300 hover:text-white hover:bg-white/10 text-xs gap-1.5 h-8 px-2.5 rounded-lg"
            >
              {inviteCopied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{inviteCopied ? "Link Copied!" : "Copy link"}</span>
            </Button>
          </div>
        </header>

        {/* Lobby Main Body */}
        <main className="flex flex-1 items-center justify-center p-4 sm:p-8">
          <div className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            
            {/* Left: Camera Preview & Quick Toggles (7 cols) */}
            <div className="lg:col-span-7 flex flex-col items-center">
              <div className="relative aspect-video w-full max-w-xl rounded-3xl overflow-hidden border border-white/15 bg-[#202124] shadow-2xl flex items-center justify-center">
                {cameraOn && localVideoStream ? (
                  <video
                    ref={(el) => {
                      if (el && localVideoStream && el.srcObject !== localVideoStream) {
                        el.srcObject = localVideoStream;
                      }
                    }}
                    autoPlay
                    playsInline
                    muted
                    className={`h-full w-full object-cover ${usingVirtualCamera ? "" : "-scale-x-100"}`}
                  />
                ) : (
                  <div className="flex flex-col items-center gap-3 text-slate-400">
                    <div className="h-20 w-20 rounded-full bg-white/10 flex items-center justify-center text-white text-2xl font-bold">
                      {(displayName || "U").charAt(0).toUpperCase()}
                    </div>
                    <span className="text-sm font-medium">Camera is off</span>
                  </div>
                )}

                {/* Floating Media Controls on Camera Preview */}
                <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-black/60 backdrop-blur-md px-4 py-2 rounded-full border border-white/10">
                  <button
                    type="button"
                    onClick={() => void toggleMic()}
                    className={`h-11 w-11 rounded-full flex items-center justify-center transition-all ${
                      micOn ? "bg-white/15 hover:bg-white/25 text-white" : "bg-[#EA4335] text-white hover:bg-[#D93025]"
                    }`}
                    title={micOn ? "Mute microphone" : "Unmute microphone"}
                  >
                    {micOn ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => void toggleCamera()}
                    className={`h-11 w-11 rounded-full flex items-center justify-center transition-all ${
                      cameraOn ? "bg-white/15 hover:bg-white/25 text-white" : "bg-[#EA4335] text-white hover:bg-[#D93025]"
                    }`}
                    title={cameraOn ? "Turn off camera" : "Turn on camera"}
                  >
                    {cameraOn ? <Camera className="h-5 w-5" /> : <CameraOff className="h-5 w-5" />}
                  </button>
                </div>

                {usingVirtualCamera && (
                  <div className="absolute top-3 left-3 bg-sky-500/80 backdrop-blur-sm px-2.5 py-1 rounded-full text-[11px] font-semibold text-white">
                    Virtual Studio Camera
                  </div>
                )}
              </div>

              {/* Device Quick Status under video */}
              <div className="w-full max-w-xl mt-4 flex items-center justify-between text-xs text-slate-400 px-2">
                <span>{availableCameras.length > 0 ? `${availableCameras.length} camera(s) detected` : "Default camera ready"}</span>
                <span>{availableMics.length > 0 ? `${availableMics.length} mic(s) detected` : "Default mic ready"}</span>
              </div>
            </div>

            {/* Right: Meeting Information, Name, Preferences & Join Button (5 cols) */}
            <div className="lg:col-span-5 flex flex-col gap-5 bg-[#1E1F22] border border-white/10 rounded-3xl p-6 sm:p-7 shadow-xl">
              <div>
                <h2 className="text-2xl font-bold text-white tracking-tight">Ready to join?</h2>
                <p className="text-xs text-slate-400 mt-1">
                  {participants.length > 0
                    ? `${participants.length} participant${participants.length > 1 ? "s" : ""} in call`
                    : "No one else is here yet"}
                </p>
              </div>

              {/* Display Name Input */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Your Name
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Enter your name"
                  className="w-full rounded-xl bg-white/5 border border-white/15 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-dl-blue transition-all"
                />
              </div>

              {/* Language Selection Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <Globe className="h-3.5 w-3.5 text-dl-blue" />
                    I speak
                  </label>
                  <Select
                    value={prefs.speaking_language}
                    onChange={(e) => updatePrefs({ speaking_language: e.target.value })}
                    className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl text-xs py-2"
                  >
                    <option value="AUTO">Auto-detect</option>
                    {caps.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.native_name})
                      </option>
                    ))}
                  </Select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <Volume2 className="h-3.5 w-3.5 text-emerald-400" />
                    I want to hear
                  </label>
                  <Select
                    value={prefs.listening_language}
                    onChange={(e) => updatePrefs({ listening_language: e.target.value })}
                    className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl text-xs py-2"
                  >
                    {caps.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.native_name})
                      </option>
                    ))}
                  </Select>
                </div>
              </div>

              {/* Audio Mode */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Audio Translation Mode
                </label>
                <SegmentedControl
                  options={[
                    { value: "translated", label: "Translated" },
                    { value: "original", label: "Original" },
                    { value: "mixed", label: "Mixed" },
                  ]}
                  value={prefs.audio_mode}
                  onChange={(v) => updatePrefs({ audio_mode: v as any })}
                  ariaLabel="Audio translation mode"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  {prefs.audio_mode === "translated"
                    ? "Hears translated AI voice in your language; original voice muted."
                    : prefs.audio_mode === "original"
                      ? "Hears speaker's original voice directly with live captions."
                      : "Hears translated AI voice + ducked (20%) original voice."}
                </p>
              </div>

              {/* Join Now Button */}
              <div className="pt-2">
                <Button
                  onClick={() => void handleJoinMeeting()}
                  disabled={isJoining}
                  className="w-full py-3 h-12 bg-dl-blue hover:bg-dl-blue-hover text-white font-semibold rounded-2xl shadow-lg transition-all active:scale-[0.98] text-base flex items-center justify-center gap-2"
                >
                  {isJoining ? (
                    <>
                      <Spinner className="h-5 w-5 text-white" />
                      <span>Joining session...</span>
                    </>
                  ) : (
                    <span>Join now</span>
                  )}
                </Button>
              </div>
            </div>

          </div>
        </main>
      </div>
    );
  }

  // ---------------- Error State (Only after join attempt) ----------------
  if (meetingQ.isError) {
    const err = meetingQ.error as any;
    return (
      <div className="p-6 bg-slate-900 min-h-screen text-white flex flex-col items-center justify-center gap-4">
        <ErrorState
          title={err?.message || "Meeting Not Found or Inaccessible"}
          detail={err?.code || "The meeting session could not be retrieved. Please verify your connection or join link."}
        />
        <div className="flex items-center gap-3 mt-2">
          <Button variant="secondary" onClick={() => nav("/meetings")}>
            ← Back to Meetings
          </Button>
          <Button variant="primary" onClick={() => meetingQ.refetch()}>
            Retry Connection
          </Button>
        </div>
      </div>
    );
  }

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
            onClick={() => void handleLeaveMeeting()}
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
              {currentLatencyMs != null ? `⚡ ~${currentLatencyMs}ms` : "< 350ms"}
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
            <span className={`h-2 w-2 shrink-0 rounded-full ${connectionInfo.dotClass}`} />
            <span>{connectionInfo.label}</span>
            {connectionInfo.canRetry && (
              <button
                type="button"
                onClick={() => socketRef.current?.reconnectNow()}
                className="ml-1 text-xs font-semibold text-amber-300 hover:text-white underline"
              >
                Reconnect
              </button>
            )}
          </div>

          {/* Translation Delayed / Unavailable Degradation Banner */}
          {translationStatus !== "normal" && (
            <div
              className={`mx-auto mb-3 w-full max-w-4xl rounded-2xl border p-3 shadow-lg backdrop-blur-md flex items-center justify-between gap-3 ${translationStatus === "delayed"
                ? "border-amber-500/30 bg-amber-950/70 text-amber-200"
                : "border-red-500/30 bg-red-950/70 text-red-200"
                }`}
              role="status"
            >
              <div className="flex items-center gap-3">
                <span className="text-base" aria-hidden>
                  {translationStatus === "delayed" ? "⏱" : "⚠️"}
                </span>
                <div className="text-xs">
                  <span className="font-semibold">
                    {translationStatus === "delayed" ? "Translation Delayed" : "Translation Unavailable"}
                  </span>
                  <span className="mx-1.5 opacity-60">·</span>
                  <span>
                    {translationMessage ||
                      (translationStatus === "delayed"
                        ? "Neural translation is experiencing latency. Original audio remains active without interruption."
                        : "Realtime translation is temporarily unavailable. Captions fallback is active.")}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setTranslationStatus("normal");
                  setTranslationMessage(null);
                }}
                className="text-xs underline hover:text-white shrink-0 font-medium"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Microphone Permission Blocked Banner */}
          {micPermissionBlocked && (
            <div className="mx-auto mb-3 w-full max-w-4xl rounded-2xl border border-red-500/30 bg-gradient-to-r from-red-950/80 via-slate-900/90 to-red-950/80 p-3.5 shadow-xl backdrop-blur-md">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-red-500/20 text-red-400 border border-red-500/30">
                    <MicOff className="h-4.5 w-4.5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">Browser Microphone Permission Blocked</span>
                      <span className="rounded-full bg-red-500/20 border border-red-500/30 px-2 py-0.5 text-[10px] font-medium text-red-300">
                        Action Required
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-300 mt-0.5">
                      Microphone access was denied. To speak and have your speech translated in real time, unblock the microphone.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowMicGuide((v) => !v)}
                    className="text-xs text-red-300 hover:text-white hover:bg-red-500/20 h-8 px-2.5 rounded-lg border border-red-500/30"
                  >
                    <Info className="h-3.5 w-3.5 mr-1" />
                    How to Unblock
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void retryPhysicalMic()}
                    className="bg-red-500 hover:bg-red-600 text-white font-semibold text-xs h-8 px-3 rounded-lg shadow-sm"
                  >
                    <Mic className="h-3.5 w-3.5 mr-1" />
                    Retry Microphone
                  </Button>
                  <button
                    type="button"
                    onClick={() => setMicPermissionBlocked(false)}
                    className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10"
                    aria-label="Dismiss banner"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {showMicGuide && (
                <div className="mt-3 pt-3 border-t border-red-500/20 text-xs text-slate-300 animate-fadeIn">
                  <p className="font-semibold text-red-200 mb-2">To enable your microphone in the browser:</p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-[11px]">
                    <div className="bg-black/40 border border-white/10 rounded-xl p-2.5">
                      <span className="font-bold text-red-300 block mb-1">Step 1: Address Bar Icon</span>
                      Click the <strong>lock / site settings icon</strong> or <strong>microphone icon with red cross</strong> next to the URL.
                    </div>
                    <div className="bg-black/40 border border-white/10 rounded-xl p-2.5">
                      <span className="font-bold text-red-300 block mb-1">Step 2: Allow Microphone</span>
                      Change the <strong>Microphone</strong> permission from Blocked to <strong>Allow</strong>.
                    </div>
                    <div className="bg-black/40 border border-white/10 rounded-xl p-2.5">
                      <span className="font-bold text-red-300 block mb-1">Step 3: Click Retry</span>
                      Click <strong>Retry Microphone</strong> above to start speaking immediately.
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

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
            className={`grid flex-1 items-center justify-center gap-3 sm:gap-4 w-full max-w-6xl mx-auto my-auto ${finalTiles.length === 1
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
                audioMuted={tile.self || prefs.audio_mode === "translated"}
                audioVolume={prefs.audio_mode === "mixed" ? 0.2 : 1.0}
                className="aspect-video w-full rounded-2xl border border-white/10 shadow-lg bg-[#202124]"
              />
            ))}
          </div>

          {/* Participant Waiting Card (Visible State 9) */}
          {finalTiles.length <= 1 && (
            <div className="mx-auto my-3 w-full max-w-lg rounded-2xl border border-white/10 bg-[#1E1F22]/90 backdrop-blur-md p-5 text-center shadow-lg">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-dl-blue/15 text-dl-blue">
                <Users className="h-6 w-6" />
              </div>
              <h3 className="text-sm font-semibold text-white">Waiting for others to join</h3>
              <p className="mt-1 text-xs text-slate-300">
                Share this meeting link with your team or participants. Realtime multilingual translation and live captions activate automatically as participants speak.
              </p>
              <div className="mt-4 flex items-center justify-center gap-2">
                <Button
                  size="sm"
                  onClick={() => void copyInviteLink()}
                  className="bg-dl-blue hover:bg-dl-blue-hover text-white text-xs h-8 px-3.5 rounded-lg font-medium shadow-sm gap-1.5"
                >
                  {inviteCopied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {inviteCopied ? "Link Copied!" : "Copy Invite Link"}
                </Button>
                <span className="text-[11px] font-mono text-slate-400 bg-white/10 px-2.5 py-1.5 rounded-lg border border-white/10">
                  {meetingQ.data?.room_name || id.slice(0, 8)}
                </span>
              </div>
            </div>
          )}

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
                  className={`flex-1 py-2.5 text-center capitalize transition border-b-2 ${drawerTab === tb
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
                        className={`rounded-xl p-3 text-xs ${m.mine ? "ml-6 bg-dl-blue/20 border border-dl-blue/30 text-white" : "mr-6 bg-white/5 border border-white/10 text-slate-200"
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
                      <div key={t.id} className="p-2.5 rounded-xl bg-white/5 border border-white/10 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="h-8 w-8 rounded-full bg-dl-blue/30 border border-dl-blue/40 flex items-center justify-center font-bold text-xs text-white">
                              {t.name.charAt(0).toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-white truncate">
                                {t.name} {t.self && <span className="text-dl-blue font-normal">(You)</span>}
                              </p>
                              <p className="text-[10px] text-slate-400 truncate">
                                Speaks: {t.speakingLanguage === "AUTO" ? "Auto-detect" : languageLabel(caps, t.speakingLanguage)} · Hears: {languageLabel(caps, t.listeningLanguage)}
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

                        {t.self && (
                          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/5">
                            <div>
                              <label className="text-[10px] text-slate-400 block mb-1">I speak</label>
                              <select
                                value={prefs.speaking_language}
                                onChange={(e) => updatePrefs({ speaking_language: e.target.value })}
                                className="w-full text-xs rounded-lg bg-black/40 border border-white/10 px-2 py-1 text-white focus:outline-none focus:border-dl-blue"
                              >
                                <option value="AUTO">Auto-detect</option>
                                {caps.map((c) => (
                                  <option key={c.code} value={c.code}>
                                    {c.name}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <label className="text-[10px] text-slate-400 block mb-1">Translate to</label>
                              <select
                                value={prefs.listening_language}
                                onChange={(e) => updatePrefs({ listening_language: e.target.value })}
                                className="w-full text-xs rounded-lg bg-black/40 border border-white/10 px-2 py-1 text-white focus:outline-none focus:border-dl-blue"
                              >
                                {caps.map((c) => (
                                  <option key={c.code} value={c.code}>
                                    {c.name}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* TAB 3: CAPTIONS & TRANSCRIPTS */}
              {drawerTab === "captions" && (
                <div className="space-y-3">
                  <div className="flex flex-col gap-2 pb-2 border-b border-white/10">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-300">Live Multilingual Transcript</span>
                      <button
                        type="button"
                        onClick={() => setShowCaptionsOverlay((prev) => !prev)}
                        className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                          showCaptionsOverlay
                            ? "bg-dl-blue/20 border-dl-blue/40 text-dl-blue font-medium"
                            : "bg-white/5 border-white/10 text-slate-400"
                        }`}
                      >
                        Overlay: {showCaptionsOverlay ? "ON" : "OFF"}
                      </button>
                    </div>

                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[10px] text-slate-400">Mode:</span>
                      <div className="flex items-center gap-1 bg-white/5 p-0.5 rounded-lg border border-white/10">
                        {(["both", "translated", "original"] as const).map((m) => (
                          <button
                            key={m}
                            type="button"
                            onClick={() => updatePrefs({ caption_mode: m })}
                            className={`px-2 py-0.5 text-[10px] rounded capitalize transition-all ${
                              prefs.caption_mode === m
                                ? "bg-dl-blue text-white font-medium"
                                : "text-slate-400 hover:text-white"
                            }`}
                          >
                            {m === "translated" ? "My language" : m}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 pt-1">
                      <span className="text-[10px] text-slate-400 flex items-center gap-1">
                        <Download className="h-3 w-3" /> Export:
                      </span>
                      <div className="flex items-center gap-1 ml-auto">
                        {(["srt", "vtt", "txt", "json"] as const).map((fmt) => (
                          <Button
                            key={fmt}
                            size="sm"
                            variant="secondary"
                            className="h-6 px-2 text-[10px] uppercase rounded-md bg-white/5 hover:bg-white/10 text-slate-200 border border-white/10"
                            onClick={() => handleExportTranscript(fmt)}
                          >
                            {fmt}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2.5 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
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
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all ${micOn
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
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all relative ${cameraOn
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
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all ${showCaptionsOverlay
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
            className={`h-11 w-11 sm:h-12 sm:w-12 rounded-full flex items-center justify-center transition-all ${screenOn
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
            onClick={() => void handleLeaveMeeting()}
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
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${drawerOpen && drawerTab === "info" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
              }`}
            title="Meeting details"
            aria-label="Meeting details"
          >
            <Info className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("people")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors relative ${drawerOpen && drawerTab === "people" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
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
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${drawerOpen && drawerTab === "chat" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
              }`}
            title="In-call chat"
            aria-label="In-call chat"
          >
            <MessageSquare className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("captions")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${drawerOpen && drawerTab === "captions" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
              }`}
            title="Captions & Transcripts"
            aria-label="Captions & Transcripts"
          >
            <FileText className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => toggleDrawer("summary")}
            className={`h-10 w-10 rounded-full flex items-center justify-center transition-colors ${drawerOpen && drawerTab === "summary" ? "bg-dl-blue text-white" : "text-slate-300 hover:bg-white/10"
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

            {/* Settings Tab Selector */}
            <div className="flex border-b border-white/10 text-xs font-medium bg-[#1A1B1D] rounded-lg p-0.5">
              <button
                type="button"
                onClick={() => setSettingsTab("translation")}
                className={`flex-1 py-1.5 text-center rounded-md transition ${settingsTab === "translation"
                  ? "bg-dl-blue text-white font-semibold shadow-xs"
                  : "text-slate-400 hover:text-slate-200"
                  }`}
              >
                Translation & Languages
              </button>
              <button
                type="button"
                onClick={() => setSettingsTab("devices")}
                className={`flex-1 py-1.5 text-center rounded-md transition ${settingsTab === "devices"
                  ? "bg-dl-blue text-white font-semibold shadow-xs"
                  : "text-slate-400 hover:text-slate-200"
                  }`}
              >
                Audio, Video & Devices
              </button>
            </div>

            {settingsTab === "translation" ? (
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
            ) : (
              <div className="space-y-4 text-xs">
                {/* Microphone Selection */}
                <div>
                  <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px] flex items-center gap-1.5">
                    <Mic className="h-3.5 w-3.5 text-dl-blue" />
                    Microphone Input
                  </label>
                  <Select
                    aria-label="Microphone input"
                    className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl"
                    value={selectedMicId}
                    onChange={(e) => {
                      const newId = e.target.value;
                      setSelectedMicId(newId);
                      void restartMicWithSettings({ micId: newId });
                    }}
                  >
                    <option value="">Default System Microphone</option>
                    {availableMics.map((mic, idx) => (
                      <option key={mic.deviceId || idx} value={mic.deviceId}>
                        {mic.label || `Microphone ${idx + 1}`}
                      </option>
                    ))}
                  </Select>
                </div>

                {/* Speaker Selection */}
                <div>
                  <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px] flex items-center gap-1.5">
                    <Volume2 className="h-3.5 w-3.5 text-dl-blue" />
                    Speaker Output (Hardware Playback)
                  </label>
                  <Select
                    aria-label="Speaker output"
                    className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl"
                    value={selectedSpeakerId}
                    onChange={(e) => void handleSpeakerChange(e.target.value)}
                  >
                    <option value="">Default System Speaker</option>
                    {availableSpeakers.map((spk, idx) => (
                      <option key={spk.deviceId || idx} value={spk.deviceId}>
                        {spk.label || `Speaker ${idx + 1}`}
                      </option>
                    ))}
                  </Select>
                </div>

                {/* Camera Selection */}
                <div>
                  <label className="block mb-1.5 font-semibold uppercase tracking-wider text-slate-300 text-[11px] flex items-center gap-1.5">
                    <Camera className="h-3.5 w-3.5 text-dl-blue" />
                    Camera Video Input
                  </label>
                  <Select
                    aria-label="Camera video input"
                    className="!bg-[#282A2D] !text-white !border-white/15 w-full rounded-xl"
                    value={selectedCameraId}
                    onChange={(e) => {
                      setSelectedCameraId(e.target.value);
                      if (cameraOn && !usingVirtualCamera) {
                        void retryPhysicalCamera();
                      }
                    }}
                  >
                    <option value="">Default System Camera</option>
                    {availableCameras.map((cam, idx) => (
                      <option key={cam.deviceId || idx} value={cam.deviceId}>
                        {cam.label || `Camera ${idx + 1}`}
                      </option>
                    ))}
                  </Select>
                </div>

                {/* Audio Signal Processing (DSP) Toggles */}
                <div className="pt-2 border-t border-white/10 space-y-2">
                  <span className="block font-semibold uppercase tracking-wider text-slate-300 text-[11px]">
                    Audio Signal Processing (DSP)
                  </span>

                  <label className="flex items-center justify-between p-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 cursor-pointer">
                    <div>
                      <span className="font-medium text-white block text-xs">Acoustic Echo Cancellation</span>
                      <span className="text-[11px] text-slate-400">Prevents speaker audio echoing into microphone</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={dspSettings.echoCancellation}
                      onChange={(e) => {
                        const updated = { ...dspSettings, echoCancellation: e.target.checked };
                        setDspSettings(updated);
                        void restartMicWithSettings({ dsp: updated });
                      }}
                      className="h-4 w-4 rounded accent-dl-blue"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 cursor-pointer">
                    <div>
                      <span className="font-medium text-white block text-xs">Background Noise Suppression</span>
                      <span className="text-[11px] text-slate-400">Reduces background fans, typing, and room hum</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={dspSettings.noiseSuppression}
                      onChange={(e) => {
                        const updated = { ...dspSettings, noiseSuppression: e.target.checked };
                        setDspSettings(updated);
                        void restartMicWithSettings({ dsp: updated });
                      }}
                      className="h-4 w-4 rounded accent-dl-blue"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 cursor-pointer">
                    <div>
                      <span className="font-medium text-white block text-xs">Automatic Gain Control (AGC)</span>
                      <span className="text-[11px] text-slate-400">Stabilizes microphone volume levels</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={dspSettings.autoGainControl}
                      onChange={(e) => {
                        const updated = { ...dspSettings, autoGainControl: e.target.checked };
                        setDspSettings(updated);
                        void restartMicWithSettings({ dsp: updated });
                      }}
                      className="h-4 w-4 rounded accent-dl-blue"
                    />
                  </label>
                </div>
              </div>
            )}

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
