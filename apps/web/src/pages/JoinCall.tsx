/**
 * JoinCall.tsx  –  Public "Join a GlobalTalk Call" page
 *
 * The OTHER person (callee) opens this URL on their phone browser.
 * No login, no app install, no Twilio/carrier needed.
 * Uses WebRTC peer-to-peer audio via the /api/v1/telephony/peer-calls/{room}/signal
 * signaling WebSocket on the backend.
 *
 * Flow:
 *  1. Page loads → fetch room info from /api/v1/telephony/peer-calls/{room_id}
 *  2. User taps "Answer" → getUserMedia → RTCPeerConnection
 *  3. Connect to signaling WS as role=callee
 *  4. Exchange offer/answer/ICE → audio flows P2P (or via TURN if needed)
 *  5. Caller's translated voice plays in callee's earpiece; callee's voice is sent to caller
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Globe,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  Volume2,
  VolumeX,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Languages,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const WS_BASE = API_BASE.replace(/^http/, 'ws');

interface RoomInfo {
  room_id: string;
  caller_language: string;
  receiver_language: string;
  caller_name: string;
  status: string;
}

type PageState =
  | 'loading'
  | 'ready'
  | 'connecting'
  | 'connected'
  | 'ended'
  | 'error';

const LANG_NAMES: Record<string, string> = {
  hi: 'Hindi (हिन्दी)',
  en: 'English',
  ja: 'Japanese (日本語)',
  ru: 'Russian (Русский)',
  de: 'German (Deutsch)',
  fr: 'French (Français)',
  es: 'Spanish (Español)',
  ar: 'Arabic (العربية)',
  zh: 'Chinese (中文)',
  ko: 'Korean (한국어)',
  pt: 'Portuguese (Português)',
  it: 'Italian (Italiano)',
};

// STUN servers for NAT traversal (free public STUN from Google)
const ICE_SERVERS = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
];

export default function JoinCall() {
  const { roomId } = useParams<{ roomId: string }>();
  const [pageState, setPageState] = useState<PageState>('loading');
  const [room, setRoom] = useState<RoomInfo | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const [isSpeakerOn, setIsSpeakerOn] = useState(true);
  const [callDuration, setCallDuration] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<any>(null);

  // ─── Step 1: Load room info ───────────────────────────────────────────────
  useEffect(() => {
    if (!roomId) {
      setPageState('error');
      setErrorMsg('Invalid call link — no room ID found.');
      return;
    }

    fetch(`${API_BASE}/api/v1/telephony/peer-calls/${roomId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Room not found (${r.status})`);
        return r.json() as Promise<RoomInfo>;
      })
      .then((info) => {
        if (info.status === 'ended') {
          setPageState('ended');
          return;
        }
        setRoom(info);
        setPageState('ready');
      })
      .catch((e: Error) => {
        setPageState('error');
        setErrorMsg(e.message || 'Call link is invalid or has expired.');
      });

    return () => {
      cleanup();
    };
  }, [roomId]);

  const cleanup = useCallback(() => {
    timerRef.current && clearInterval(timerRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
  }, []);

  // ─── Step 2: Answer ──────────────────────────────────────────────────────
  const handleAnswer = useCallback(async () => {
    if (!roomId) return;
    setPageState('connecting');

    try {
      // Get mic
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      localStreamRef.current = stream;

      // RTCPeerConnection
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      pcRef.current = pc;
      stream.getTracks().forEach((t) => pc.addTrack(t, stream));

      // Play remote audio (translated caller voice)
      pc.ontrack = (evt) => {
        if (remoteAudioRef.current && evt.streams[0]) {
          remoteAudioRef.current.srcObject = evt.streams[0];
          remoteAudioRef.current.play().catch(() => {});
        }
      };

      // Connect to signaling WS as callee
      const ws = new WebSocket(
        `${WS_BASE}/api/v1/telephony/peer-calls/${roomId}/signal?role=callee`
      );
      wsRef.current = ws;

      ws.onmessage = async (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'ready') {
          // Connected to signaling — nothing to do, wait for offer from caller
        } else if (msg.type === 'offer') {
          await pc.setRemoteDescription(new RTCSessionDescription(msg.data));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          ws.send(JSON.stringify({ type: 'answer', data: pc.localDescription }));
        } else if (msg.type === 'ice') {
          if (msg.data) {
            await pc.addIceCandidate(new RTCIceCandidate(msg.data)).catch(() => {});
          }
        } else if (msg.type === 'bye' || msg.type === 'peer_left') {
          setPageState('ended');
          cleanup();
        }
      };

      // Forward ICE candidates to caller via signaling
      pc.onicecandidate = ({ candidate }) => {
        if (candidate && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ice', data: candidate }));
        }
      };

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'connected') {
          setPageState('connected');
          timerRef.current = setInterval(() => setCallDuration((d) => d + 1), 1000);
        } else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
          setPageState('ended');
          cleanup();
        }
      };

      ws.onerror = () => {
        setPageState('error');
        setErrorMsg('Signaling connection failed. Please try again.');
        cleanup();
      };

      ws.onclose = () => {
        if (pageState === 'connecting' || pageState === 'connected') {
          setPageState('ended');
        }
      };
    } catch (err: any) {
      setPageState('error');
      setErrorMsg(err.message ?? 'Could not access microphone. Please allow microphone permission.');
      cleanup();
    }
  }, [roomId, cleanup]);

  // ─── Hang up ─────────────────────────────────────────────────────────────
  const handleHangUp = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: 'bye' }));
    setPageState('ended');
    cleanup();
  }, [cleanup]);

  // ─── Mute / Speaker ──────────────────────────────────────────────────────
  const toggleMute = () => {
    localStreamRef.current?.getAudioTracks().forEach((t) => {
      t.enabled = isMuted; // flip
    });
    setIsMuted((m) => !m);
  };

  const toggleSpeaker = () => {
    if (remoteAudioRef.current) {
      remoteAudioRef.current.muted = isSpeakerOn; // flip
    }
    setIsSpeakerOn((s) => !s);
  };

  const formatTime = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-iris-950 flex items-center justify-center p-4">
      {/* Hidden audio element for remote stream */}
      <audio ref={remoteAudioRef} autoPlay playsInline className="hidden" />

      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 text-white mb-2">
            <Globe className="w-7 h-7 text-iris-400" />
            <span className="text-xl font-bold">GlobalTalk AI</span>
          </div>
          <p className="text-slate-400 text-sm">Instant translated phone call</p>
        </div>

        {/* Card */}
        <div className="bg-slate-800/80 backdrop-blur border border-slate-700 rounded-2xl p-6 shadow-2xl">

          {/* LOADING */}
          {pageState === 'loading' && (
            <div className="text-center py-8">
              <Loader2 className="w-10 h-10 text-iris-400 animate-spin mx-auto mb-3" />
              <p className="text-white font-medium">Loading call…</p>
            </div>
          )}

          {/* ERROR */}
          {pageState === 'error' && (
            <div className="text-center py-8">
              <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
              <p className="text-white font-semibold mb-2">Call unavailable</p>
              <p className="text-slate-400 text-sm">{errorMsg}</p>
            </div>
          )}

          {/* ENDED */}
          {pageState === 'ended' && (
            <div className="text-center py-8">
              <CheckCircle2 className="w-12 h-12 text-green-400 mx-auto mb-3" />
              <p className="text-white font-semibold mb-2">Call ended</p>
              <p className="text-slate-400 text-sm">Duration: {formatTime(callDuration)}</p>
              <p className="text-slate-500 text-xs mt-4">You can close this tab.</p>
            </div>
          )}

          {/* READY — show caller info + Answer button */}
          {pageState === 'ready' && room && (
            <div className="text-center">
              {/* Caller avatar */}
              <div className="w-20 h-20 rounded-full bg-iris-600/30 border-2 border-iris-500 flex items-center justify-center mx-auto mb-4">
                <Phone className="w-9 h-9 text-iris-300" />
              </div>

              <p className="text-slate-400 text-sm mb-1">Incoming translated call from</p>
              <p className="text-white text-xl font-bold mb-1">{room.caller_name}</p>

              {/* Language pair */}
              <div className="flex items-center justify-center gap-2 text-sm text-slate-400 mb-6">
                <Languages className="w-4 h-4 text-iris-400" />
                <span>{LANG_NAMES[room.caller_language] ?? room.caller_language}</span>
                <span className="text-iris-400">↔</span>
                <span>{LANG_NAMES[room.receiver_language] ?? room.receiver_language}</span>
              </div>

              <p className="text-slate-500 text-xs mb-6">
                🎙️ Speak naturally in your language — AI translates in real time
              </p>

              {/* Answer button */}
              <button
                onClick={handleAnswer}
                className="w-full py-4 rounded-xl bg-green-500 hover:bg-green-400 text-white font-bold text-lg transition-all flex items-center justify-center gap-3 shadow-lg shadow-green-900/40"
              >
                <Phone className="w-6 h-6" />
                Answer Call
              </button>

              <p className="text-slate-600 text-xs mt-4">
                No app download required · Works in any browser
              </p>
            </div>
          )}

          {/* CONNECTING */}
          {pageState === 'connecting' && (
            <div className="text-center py-4">
              <div className="w-20 h-20 rounded-full bg-iris-600/30 border-2 border-iris-500 flex items-center justify-center mx-auto mb-4 animate-pulse">
                <Phone className="w-9 h-9 text-iris-300" />
              </div>
              <p className="text-white font-semibold mb-2">Connecting…</p>
              <Loader2 className="w-6 h-6 text-iris-400 animate-spin mx-auto mb-4" />
              <p className="text-slate-500 text-xs">Establishing secure audio connection</p>
            </div>
          )}

          {/* CONNECTED — active call controls */}
          {pageState === 'connected' && room && (
            <div className="text-center">
              {/* Animated avatar */}
              <div className="w-20 h-20 rounded-full bg-green-600/20 border-2 border-green-500 flex items-center justify-center mx-auto mb-4 animate-pulse">
                <Phone className="w-9 h-9 text-green-400" />
              </div>

              <p className="text-green-400 font-semibold mb-1">Connected</p>
              <p className="text-white text-2xl font-mono font-bold mb-1">
                {formatTime(callDuration)}
              </p>
              <p className="text-slate-400 text-sm mb-1">{room.caller_name}</p>

              <div className="flex items-center justify-center gap-2 text-xs text-slate-500 mb-6">
                <Languages className="w-3 h-3 text-iris-400" />
                <span>{LANG_NAMES[room.caller_language] ?? room.caller_language}</span>
                <span className="text-iris-400">↔</span>
                <span>{LANG_NAMES[room.receiver_language] ?? room.receiver_language}</span>
                <span className="text-iris-400 font-medium ml-1">AI Translation LIVE</span>
              </div>

              {/* Mute + Speaker + Hang up */}
              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={toggleMute}
                  className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                    isMuted
                      ? 'bg-red-600/20 border border-red-500 text-red-400'
                      : 'bg-slate-700 border border-slate-600 text-slate-300 hover:bg-slate-600'
                  }`}
                  title={isMuted ? 'Unmute' : 'Mute'}
                >
                  {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                </button>

                <button
                  onClick={handleHangUp}
                  className="w-16 h-16 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-lg shadow-red-900/40 transition-all"
                  title="End Call"
                >
                  <PhoneOff className="w-7 h-7" />
                </button>

                <button
                  onClick={toggleSpeaker}
                  className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                    !isSpeakerOn
                      ? 'bg-red-600/20 border border-red-500 text-red-400'
                      : 'bg-slate-700 border border-slate-600 text-slate-300 hover:bg-slate-600'
                  }`}
                  title={isSpeakerOn ? 'Mute speaker' : 'Unmute speaker'}
                >
                  {isSpeakerOn ? <Volume2 className="w-6 h-6" /> : <VolumeX className="w-6 h-6" />}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-slate-600 text-xs mt-6">
          Powered by GlobalTalk AI · Real-time multilingual translation
        </p>
      </div>
    </div>
  );
}
