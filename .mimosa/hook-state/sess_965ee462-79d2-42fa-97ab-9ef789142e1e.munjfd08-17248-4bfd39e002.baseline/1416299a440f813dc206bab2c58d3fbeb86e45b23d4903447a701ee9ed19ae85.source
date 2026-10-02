import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CameraOff, Copy, Mic, MicOff, MonitorUp, PhoneOff } from "lucide-react";
import { api } from "../lib/api";
import { useLanguages, languageLabel } from "../hooks/useLanguages";
import { useLiveKitRoom } from "../hooks/useLiveKitRoom";
import { AudioPlayer, MicCapture, b64ToBytes } from "../lib/audio";
import { MeetingSocket, type SocketState } from "../lib/ws";
import type { Meeting, ParticipantInfo, Preferences, RealtimeEvent, TranscriptItem } from "../lib/types";
import { Badge, Button, ErrorState, SegmentedControl, Select, Spinner } from "../components/ui";
import { VideoTile } from "../components/meeting/VideoTile";
import { toast } from "../stores/toasts";
import { useAuth } from "../stores/auth";

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
  const [micOn, setMicOn] = React.useState(false);
  const [cameraOn, setCameraOn] = React.useState(false);
  const [screenOn, setScreenOn] = React.useState(false);
  const [speakingNow, setSpeakingNow] = React.useState<string | null>(null);
  const [captions, setCaptions] = React.useState<CaptionLine[]>([]);
  const [chat, setChat] = React.useState<ChatLine[]>([]);
  const [chatDraft, setChatDraft] = React.useState("");
  const [chatDisplay, setChatDisplay] = React.useState<"original" | "mine" | "both">("both");
  const [tab, setTab] = React.useState<"captions" | "transcript" | "chat" | "summary">("captions");
  const [notice, setNotice] = React.useState<string | null>(null);
  const [summary, setSummary] = React.useState<any>(null);
  const [myParticipantId, setMyParticipantId] = React.useState<string | undefined>();
  const [displayName, setDisplayName] = React.useState(user?.full_name || "Guest");
  const [inviteCopied, setInviteCopied] = React.useState(false);

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

  const transcriptQ = useQuery({
    queryKey: ["meeting", id, "transcript"],
    queryFn: () => api<TranscriptItem[]>(`/api/v1/meetings/${id}/transcript`),
    enabled: tab === "transcript",
    refetchInterval: tab === "transcript" ? 8000 : false,
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
          if ((liveKitConnected && mode === "translated" && understoodNatively) ||
              (!liveKitConnected && (mode === "original" || mode === "mixed" ||
                (mode === "translated" && understoodNatively)))) {
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
        const mine = prefsRef.current.caption_mode !== "translated" || evt.language === prefsRef.current.listening_language;
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
        // attach by matching the pending line for this speaker/segment
        setCaptions((prev) => {
          const idx = [...prev].reverse().findIndex(
            (c) => c.speaker === ((evt.display_name as string) || namesRef.current.get(evt.speaker_id as string)) &&
                   !c.translated && !c.id.startsWith("tr:") && c.language === evt.source_language);
          if (idx === -1) {
            // standalone translated line (e.g. after resume replay)
            return [...prev.slice(-80), {
              id: `tr:${seg}:${evt.target_language}`,
              speaker: (evt.display_name as string) || namesRef.current.get(evt.speaker_id as string) || "Speaker",
              language: evt.source_language as string,
              translated: evt.text as string,
              translatedLang: evt.target_language as string,
              originalFinal: true,
              partial: false,
              latencyMs: evt.latency_ms as number,
            }];
          }
          const target = prev[prev.length - 1 - idx];
          const updated = { ...target, translated: evt.text as string,
                            translatedLang: evt.target_language as string,
                            latencyMs: evt.latency_ms as number };
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
            : [...prev.slice(-80), {
                id: `fail:${seg}`,
                speaker: namesRef.current.get(evt.speaker_id as string) || "Speaker",
                language: "",
                originalFinal: true,
                partial: false,
                failed: (evt.user_message as string) ?? "Translation unavailable",
              }],
        );
        break;
      }
      case "tts.completed": {
        if (evt.target_language !== prefsRef.current.listening_language) break;
        const mode = prefsRef.current.audio_mode;
        if (mode !== "translated" && mode !== "mixed") break;
        const audio = evt.audio as string;
        if (!audio) break;
        const uid = (evt.utterance_id as string | undefined)?.slice(0, 16) ?? (evt.segment_id as string).slice(0, 16);
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
        setChat((prev) => [...prev, {
          id: evt.message_id as string,
          sender: (evt.display_name as string) || "Unknown",
          original: evt.original_text as string,
          language: (evt.language as string) || "",
          mine: evt.participant_id === myParticipantId,
        }]);
        break;
      case "chat.translation":
        if (evt.target_language !== prefsRef.current.listening_language) break;
        setChat((prev) => prev.map((c) =>
          c.id === evt.message_id ? { ...c, translated: evt.text as string } : c));
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
        try { await mediaRoom.unlockAudio(); } catch {}
      }
      const mic = new MicCapture();
      await mic.start(SAMPLE_RATE, (frame) => socketRef.current?.sendAudio(frame));
      micRef.current = mic;
      const track = mic.mediaStream?.getAudioTracks()[0];
      if (track && mediaRoom.state === "connected") {
        try { await mediaRoom.publishMicrophone(track); } catch {}
      }
      setMicOn(true);
      toast.success("Microphone active", "Speaking in " + (prefs.speaking_language === "AUTO" ? "auto-detected language" : languageLabel(caps, prefs.speaking_language)));
    } catch {
      micRef.current?.stop();
      micRef.current = null;
      setMicOn(false);
      toast.error("Microphone unavailable", "Grant microphone permission to speak in this meeting.");
    }
  }

  async function toggleCamera() {
    if (cameraOn) {
      if (localVideoStream) {
        localVideoStream.getTracks().forEach((t) => t.stop());
        setLocalVideoStream(null);
      }
      if (mediaRoom.state === "connected") {
        try { await mediaRoom.setCameraEnabled(false); } catch {}
      }
      setCameraOn(false);
      return;
    }
    try {
      if (mediaRoom.state === "connected") {
        await mediaRoom.setCameraEnabled(true);
        setCameraOn(true);
      } else {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
          audio: false,
        });
        setLocalVideoStream(stream);
        setCameraOn(true);
      }
      toast.success("Camera active", "Video feed is live");
    } catch (err: any) {
      toast.error("Camera unavailable", err?.message ?? "Check camera permission and try again.");
    }
  }

  async function toggleScreen() {
    if (screenOn) {
      if (mediaRoom.state === "connected") {
        try { await mediaRoom.setScreenShareEnabled(false); } catch {}
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

  const summaryMut = useMutation({
    mutationFn: () => api(`/api/v1/meetings/${id}/summary`, { method: "POST" }),
    onSuccess: (r) => setSummary(r),
  });

  // ---------------- render ----------------
  if (meetingQ.isError) {
    return <div className="p-6"><ErrorState title={(meetingQ.error as any).message} detail={(meetingQ.error as any).code} /></div>;
  }
  const participants = (participantsQ.data ?? []).filter((participant) => participant.status === "joined");
  const participantsById = new Map(participants.map((participant) => [participant.id, participant]));
  const callTiles = mediaRoom.state === "connected"
    ? mediaRoom.peers.map((peer) => {
        const participant = participantsById.get(peer.id);
        const speakingLanguage = participant?.speaking_language ?? (peer.self ? prefs.speaking_language : "AUTO");
        const listeningLanguage = participant?.listening_language ?? (peer.self ? prefs.listening_language : "en");
        return {
          id: peer.id,
          name: peer.name,
          stream: peer.self ? (peer.stream || localVideoStream) : peer.stream,
          isScreenShare: peer.isScreenShare,
          self: peer.self,
          speakingLanguage,
          listeningLanguage,
          speaking: speakingNow === peer.id || (peer.self && micOn && !!speakingNow),
          muted: peer.self ? !micOn : !peer.microphoneOn,
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
        },
        ...callTiles,
      ];
  const stateTone = socketState === "joined" ? "good" : socketState === "reconnecting" ? "warn" : "neutral";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* top bar */}
      <div className="flex flex-wrap items-center gap-3 border-b border-ink-100 bg-white px-4 py-2.5">
        <Button variant="ghost" size="sm" onClick={() => nav("/meetings")}>← Meetings</Button>
        <h1 className="text-sm font-bold text-ink-900">{meetingQ.data?.title ?? "…"}</h1>
        <Badge tone={stateTone as any}>
          {socketState === "joined" ? "● live" : socketState === "reconnecting" ? "reconnecting…" : socketState}
        </Badge>
        {meetingQ.data?.transport === "livekit" && <Badge tone="info">LiveKit room</Badge>}
        <div className="flex-1" />
        <Button variant="ghost" size="sm" onClick={() => void copyInviteLink()} title="Copy this meeting link">
          <Copy className="h-4 w-4" /> {inviteCopied ? "Copied" : "Copy invite"}
        </Button>
        <div className="flex items-center gap-2">
          <label className="text-xs text-ink-500" htmlFor="display-name">Name</label>
          <input id="display-name" className="gt-input !w-36 !py-1 text-xs" value={displayName}
                 onChange={(e) => setDisplayName(e.target.value)} />
        </div>
      </div>

      {notice && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800" role="status">
          <span aria-hidden>⚠</span>
          <span className="flex-1">{notice}</span>
          <button className="font-semibold hover:underline" onClick={() => setNotice(null)}>dismiss</button>
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[1fr_360px]">
        {/* left: stage + participants + controls */}
        <div className="flex min-h-0 flex-col overflow-y-auto bg-ink-950 p-4">
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-ink-800 bg-ink-900 px-3 py-2 text-xs text-ink-300" role="status">
            <span className={`h-2 w-2 shrink-0 rounded-full ${mediaRoom.state === "connected" ? "bg-emerald-400" : mediaRoom.state === "error" ? "bg-red-400" : "bg-amber-400"}`} />
            {mediaRoom.state === "connected" && "Camera and room audio are connected. Live translation follows your language settings."}
            {mediaRoom.state === "connecting" && "Connecting video and room audio… You can set your language while the room connects."}
            {mediaRoom.state === "reconnecting" && "Reconnecting video and room audio. Translation will continue when the connection returns."}
            {mediaRoom.state === "error" && (mediaRoom.error ?? "Could not connect to the video room.")}
            {mediaRoom.state === "unavailable" && "Live translation is available. Video calling needs a configured LiveKit media server."}
          </div>

          {/* my language controls — the core product concept */}
          <div className="mb-4 grid gap-3 rounded-xl border border-ink-800 bg-ink-900 p-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400">I speak</p>
              <Select aria-label="I speak" className="!bg-ink-800 !text-white !border-ink-700"
                      value={prefs.speaking_language}
                      onChange={(e) => updatePrefs({ speaking_language: e.target.value })}>
                <option value="AUTO">Auto detect</option>
                {caps.filter((c) => c.speech_input_supported).map((c) => (
                  <option key={c.code} value={c.code}>{c.name} ({c.native_name})</option>
                ))}
              </Select>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400">I want to hear</p>
              <Select aria-label="I want to hear" className="!bg-ink-800 !text-white !border-ink-700"
                      value={prefs.listening_language}
                      onChange={(e) => updatePrefs({ listening_language: e.target.value })}>
                {caps.filter((c) => c.translation_supported || c.speech_input_supported).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name} ({c.native_name}){c.speech_output_supported ? "" : " — captions"}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Audio</p>
              <SegmentedControl ariaLabel="Audio mode" value={prefs.audio_mode}
                onChange={(v) => updatePrefs({ audio_mode: v })}
                options={[
                  { value: "original", label: "Original", title: "Only the speakers' original voices" },
                  { value: "translated", label: "Translated", title: "Translated voice; original when you understand the source" },
                  { value: "mixed", label: "Mixed", title: "Original and translated together" },
                ]} />
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Captions</p>
              <SegmentedControl ariaLabel="Caption mode" value={prefs.caption_mode}
                onChange={(v) => updatePrefs({ caption_mode: v })}
                options={[
                  { value: "original", label: "Original" },
                  { value: "translated", label: "My language" },
                  { value: "both", label: "Both" },
                ]} />
            </div>
          </div>

          {/* participant media grid */}
          <div className="grid flex-1 auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {finalTiles.map((tile) => (
              <VideoTile
                key={tile.id}
                name={tile.name}
                lang={languageLabel(caps, tile.speakingLanguage === "AUTO" ? "en" : tile.speakingLanguage)}
                hear={languageLabel(caps, tile.listeningLanguage)}
                stream={tile.stream}
                videoOn={tile.self ? (cameraOn && !!tile.stream) : !!tile.stream}
                isScreenShare={tile.isScreenShare}
                speaking={tile.speaking}
                muted={tile.muted}
                self={tile.self}
                className="min-h-48 aspect-video border-ink-800"
              />
            ))}
            {finalTiles.length === 0 && (
              <div className="col-span-full flex min-h-48 items-center justify-center text-sm text-ink-500">
                Waiting for participants to connect…
              </div>
            )}
          </div>
          <div ref={mediaRoom.audioContainerRef} className="sr-only" aria-hidden="true" />

          {/* control bar */}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 rounded-xl border border-ink-800 bg-ink-900 p-3">
            <ControlButton on={micOn} onClick={toggleMic} label={micOn ? "Mute microphone" : "Start microphone"}
                           icon={micOn ? <Mic /> : <MicOff />} />
            <ControlButton on={cameraOn} onClick={toggleCamera} label={cameraOn ? "Stop camera" : "Start camera"}
                           icon={cameraOn ? <Camera /> : <CameraOff />} />
            <ControlButton on={screenOn} onClick={toggleScreen} label={screenOn ? "Stop sharing" : "Share screen"}
                           icon={<MonitorUp />} />
            <div className="mx-2 h-8 w-px bg-ink-800" aria-hidden />
            <Button variant="danger" size="sm" onClick={() => nav(`/meetings?end=${id}`)}>
              <PhoneOff className="h-4 w-4" /> Leave meeting
            </Button>
          </div>
          {micOn && (
            <p className="mt-2 text-center text-[11px] text-ink-500" role="status">
              <Spinner className="mr-1 inline h-3 w-3" /> Listening — speak naturally in {prefs.speaking_language === "AUTO" ? "any language" : languageLabel(caps, prefs.speaking_language)}
            </p>
          )}
        </div>

        {/* right panel */}
        <div className="flex min-h-0 flex-col border-l border-ink-100 bg-white">
          <div className="flex border-b border-ink-100 text-xs font-medium" role="tablist" aria-label="Meeting panels">
            {(["captions", "transcript", "chat", "summary"] as const).map((tb) => (
              <button key={tb} role="tab" aria-selected={tab === tb}
                      className={`flex-1 border-b-2 px-2 py-2.5 capitalize transition ${
                        tab === tb ? "border-signal-600 text-signal-700" : "border-transparent text-ink-400 hover:text-ink-700"}`}
                      onClick={() => setTab(tb)}>
                {tb}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {tab === "captions" && (
              <div className="space-y-2.5" aria-live="polite" aria-label="Live captions">
                {captions.length === 0 && (
                  <p className="py-8 text-center text-xs text-ink-400">
                    Live captions appear here once someone speaks.
                  </p>
                )}
                {captions.map((c) => (
                  <div key={c.id} className={`rounded-lg border p-2.5 text-sm ${c.failed ? "border-amber-200 bg-amber-50" : "border-ink-100 bg-ink-50/60"}`}>
                    <div className="mb-1 flex items-center gap-2 text-[11px] text-ink-400">
                      <span className="font-semibold text-ink-600">{c.speaker}</span>
                      {c.language && <Badge>{languageLabel(caps, c.language)}</Badge>}
                      {c.partial && <span className="italic opacity-60">…</span>}
                      {c.latencyMs != null && <span title="speech start → translated audio delivered">{Math.round(c.latencyMs)} ms</span>}
                    </div>
                    {c.failed ? (
                      <p className="text-xs text-amber-700">{c.failed}</p>
                    ) : (
                      <>
                        {(prefs.caption_mode === "original" || prefs.caption_mode === "both") && c.original && (
                          <p className={`caption-line ${c.partial ? "text-ink-400 italic" : "text-ink-700"}`}>{c.original}</p>
                        )}
                        {(prefs.caption_mode === "translated" || prefs.caption_mode === "both") && c.translated && (
                          <p className="caption-line mt-0.5 font-medium text-ink-900">{c.translated}</p>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {tab === "transcript" && (
              <div className="space-y-2">
                {(transcriptQ.data ?? []).map((s) => (
                  <div key={s.id} className="rounded-lg border border-ink-100 p-2.5 text-sm">
                    <div className="mb-1 flex items-center gap-2 text-[11px] text-ink-400">
                      <span className="font-semibold text-ink-600">{s.speaker}</span>
                      <Badge>{languageLabel(caps, s.language)}</Badge>
                      <span>#{s.sequence}</span>
                      <span title="STT confidence">{Math.round(s.confidence * 100)}%</span>
                    </div>
                    <p className="text-ink-800">{s.text}</p>
                    {s.translations.map((tr) => (
                      <p key={tr.id} className="mt-1 border-l-2 border-signal-200 pl-2 text-xs text-ink-500">
                        <b className="text-ink-600">{tr.target_language.toUpperCase()}:</b> {tr.text}
                        {tr.tts_audio_key && <span title="translated audio generated"> 🔊</span>}
                      </p>
                    ))}
                  </div>
                ))}
                {transcriptQ.data?.length === 0 && (
                  <p className="py-8 text-center text-xs text-ink-400">The stored transcript appears here (canonical source + derivatives).</p>
                )}
                <div className="flex gap-2 pt-2">
                  <Button size="sm" variant="secondary"
                          onClick={() => window.open(`/api/v1/meetings/${id}/transcript/export?fmt=csv`, "_blank")}>
                    Export CSV
                  </Button>
                </div>
              </div>
            )}

            {tab === "chat" && (
              <div className="flex h-full flex-col">
                <div className="mb-2 flex items-center justify-between">
                  <SegmentedControl ariaLabel="Chat display mode" value={chatDisplay} onChange={setChatDisplay}
                    options={[{ value: "original", label: "Original" }, { value: "mine", label: "My language" }, { value: "both", label: "Both" }]} />
                </div>
                <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1" aria-live="polite">
                  {chat.map((m) => (
                    <div key={m.id} className={`rounded-lg p-2 text-sm ${m.mine ? "ml-6 bg-signal-50" : "mr-6 bg-ink-50"}`}>
                      <p className="text-[11px] font-semibold text-ink-500">{m.sender} <Badge>{m.language}</Badge></p>
                      {(chatDisplay === "original" || chatDisplay === "both") &&
                        <p className="text-ink-800">{m.original}</p>}
                      {(chatDisplay === "mine" || chatDisplay === "both") &&
                        <p className={chatDisplay === "both" ? "mt-0.5 font-medium text-ink-900" : "text-ink-900"}>
                          {m.translated ?? <span className="italic text-ink-400">(original — same language)</span>}
                        </p>}
                    </div>
                  ))}
                  {chat.length === 0 && <p className="py-6 text-center text-xs text-ink-400">Messages are translated per listener. Originals are never replaced.</p>}
                </div>
                <form className="mt-2 flex gap-2" onSubmit={(e) => {
                  e.preventDefault();
                  if (!chatDraft.trim()) return;
                  socketRef.current?.sendChat(chatDraft.trim());
                  setChatDraft("");
                }}>
                  <input className="gt-input flex-1" placeholder={`Message in any language…`}
                         aria-label="Chat message" value={chatDraft} onChange={(e) => setChatDraft(e.target.value)} />
                  <Button type="submit" size="sm">Send</Button>
                </form>
              </div>
            )}

            {tab === "summary" && (
              <div className="space-y-3">
                <p className="text-xs text-ink-400">
                  The assistant reads only the <b>stable canonical transcript</b> — summaries are derivative artifacts and never become the source of truth.
                </p>
                <Button size="sm" loading={summaryMut.isPending} onClick={() => summaryMut.mutate()}>
                  Generate summary
                </Button>
                {summary && (
                  <div className="space-y-3 text-sm">
                    <Badge tone="info">method: {summary.method}</Badge>
                    <section>
                      <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-ink-400">Summary</h3>
                      <p className="text-ink-800">{summary.summary}</p>
                    </section>
                    {summary.key_points?.length > 0 && (
                      <section>
                        <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-ink-400">Key points</h3>
                        <ul className="list-inside list-disc space-y-0.5 text-ink-700">
                          {summary.key_points.map((k: string, i: number) => <li key={i}>{k}</li>)}
                        </ul>
                      </section>
                    )}
                    {summary.action_items?.length > 0 && (
                      <section>
                        <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-ink-400">Action items</h3>
                        <ul className="list-inside list-disc space-y-0.5 text-ink-700">
                          {summary.action_items.map((a: any, i: number) => <li key={i}>{a.text}</li>)}
                        </ul>
                      </section>
                    )}
                    {summary.unanswered_questions?.length > 0 && (
                      <section>
                        <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-ink-400">Open questions</h3>
                        <ul className="list-inside list-disc space-y-0.5 text-ink-700">
                          {summary.unanswered_questions.map((q: string, i: number) => <li key={i}>{q}</li>)}
                        </ul>
                      </section>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ControlButton({ on, onClick, label, icon, disabled = false }: {
  on: boolean; onClick: () => void; label: string; icon: React.ReactNode; disabled?: boolean;
}) {
  return (
    <button onClick={onClick} aria-label={label} aria-pressed={on} title={label} disabled={disabled}
            className={`flex h-11 w-11 items-center justify-center rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400 disabled:cursor-not-allowed disabled:opacity-40 ${
              on ? "bg-signal-600 text-white hover:bg-signal-500" : "bg-ink-800 text-ink-300 hover:bg-ink-700 hover:text-white"}`}>
      {icon}
    </button>
  );
}
