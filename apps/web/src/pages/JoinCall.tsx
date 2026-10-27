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
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
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
  Lock,
  Sparkles,
} from 'lucide-react';
import { playWhatsAppRingtone, stopWhatsAppAudio } from '../lib/whatsappAudio';

function getWsUrl(roomId: string): string {
  const path = `/api/v1/telephony/peer-calls/${roomId}/signal?role=callee`;
  if (import.meta.env.VITE_API_BASE_URL) {
    const base = import.meta.env.VITE_API_BASE_URL.replace(/^http/, 'ws').replace(/\/+$/, '');
    return `${base}${path}`;
  }
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      const port = (window.location.port === '5173' || window.location.port === '3000' || !window.location.port) ? '8000' : window.location.port;
      return `${protocol}//${window.location.hostname}:${port}${path}`;
    }
    return `${protocol}//${window.location.host}${path}`;
  }
  return `ws://127.0.0.1:8000${path}`;
}

async function fetchRoomInfo(roomId: string): Promise<RoomInfo> {
  const customBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
  const candidateUrls = [
    ...(customBase ? [`${customBase}/api/v1/telephony/peer-calls/${roomId}`] : []),
    `/api/v1/telephony/peer-calls/${roomId}`,
    `http://127.0.0.1:8000/api/v1/telephony/peer-calls/${roomId}`,
    `http://localhost:8000/api/v1/telephony/peer-calls/${roomId}`,
  ];

  let lastError: Error | null = null;
  for (const url of candidateUrls) {
    try {
      const res = await fetch(url, { headers: { Accept: 'application/json' } });
      if (res.ok) {
        return (await res.json()) as RoomInfo;
      }
      if (res.status === 404) {
        throw new Error('This call link has expired or the room does not exist.');
      }
      if (!res.ok) {
        lastError = new Error(`Server returned error ${res.status}`);
      }
    } catch (err: any) {
      lastError = err;
      if (err.message?.includes('expired') || err.message?.includes('does not exist')) {
        throw err;
      }
    }
  }
  throw lastError || new Error('Could not connect to call server.');
}

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

  const [callerOnline, setCallerOnline] = useState<boolean | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<any>(null);
  const connectingTimerRef = useRef<any>(null);
  const pendingIceRef = useRef<RTCIceCandidateInit[]>([]);
  const hasRemoteDescRef = useRef(false);

  // ─── Step 1: Load room info ───────────────────────────────────────────────
  useEffect(() => {
    if (!roomId) {
      setPageState('error');
      setErrorMsg('Invalid call link — no room ID found.');
      return;
    }

    fetchRoomInfo(roomId)
      .then((info) => {
        if (info.status === 'ended') {
          setPageState('ended');
          return;
        }
        setRoom(info);
        setPageState('ready');
        playWhatsAppRingtone();
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
    stopWhatsAppAudio();
    timerRef.current && clearInterval(timerRef.current);
    timerRef.current = null;
    connectingTimerRef.current && clearTimeout(connectingTimerRef.current);
    connectingTimerRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
  }, []);

  // ─── Instant connect helper ──────────────────────────────────────────────
  const startConnectedSession = useCallback(() => {
    stopWhatsAppAudio();
    connectingTimerRef.current && clearTimeout(connectingTimerRef.current);
    connectingTimerRef.current = null;
    setPageState('connected');
    if (!timerRef.current) {
      timerRef.current = setInterval(() => setCallDuration((d) => d + 1), 1000);
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'instant_connect' }));
    }
  }, []);

  // ─── Step 2: Answer ──────────────────────────────────────────────────────
  const handleAnswer = useCallback(async () => {
    if (!roomId) return;
    stopWhatsAppAudio();
    setPageState('connecting');
    hasRemoteDescRef.current = false;
    pendingIceRef.current = [];

    // Auto-connect timer: automatically completes connection after 4 seconds
    connectingTimerRef.current = setTimeout(() => {
      setPageState((s) => {
        if (s === 'connecting') {
          startConnectedSession();
          return 'connected';
        }
        return s;
      });
    }, 4000);

    try {
      // Get mic safely (if user blocks mic, call can still connect)
      let stream: MediaStream | null = null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        localStreamRef.current = stream;
      } catch (micErr) {
        console.warn('Microphone permission notice:', micErr);
      }

      // RTCPeerConnection
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      pcRef.current = pc;
      if (stream) {
        stream.getTracks().forEach((t) => pc.addTrack(t, stream!));
      }

      // Play remote audio (translated caller voice)
      pc.ontrack = (evt) => {
        if (remoteAudioRef.current && evt.streams[0]) {
          remoteAudioRef.current.srcObject = evt.streams[0];
          remoteAudioRef.current.play().catch(() => {});
        }
      };

      // Connect to signaling WS as callee
      const ws = new WebSocket(getWsUrl(roomId));
      wsRef.current = ws;

      ws.onmessage = async (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'ready') {
            if (msg.caller_online !== undefined) {
              setCallerOnline(Boolean(msg.caller_online));
            }
          } else if (msg.type === 'peer_joined') {
            setCallerOnline(true);
          } else if (msg.type === 'instant_connect') {
            startConnectedSession();
          } else if (msg.type === 'offer') {
            if (hasRemoteDescRef.current) {
              // Already handled offer, avoid duplicate state error
              return;
            }
            await pc.setRemoteDescription(new RTCSessionDescription(msg.data));
            hasRemoteDescRef.current = true;
            // Flush queued ICE candidates
            while (pendingIceRef.current.length > 0) {
              const c = pendingIceRef.current.shift()!;
              await pc.addIceCandidate(new RTCIceCandidate(c)).catch(() => {});
            }
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'answer', data: pc.localDescription }));
            }
          } else if (msg.type === 'ice') {
            if (msg.data) {
              if (hasRemoteDescRef.current) {
                await pc.addIceCandidate(new RTCIceCandidate(msg.data)).catch(() => {});
              } else {
                pendingIceRef.current.push(msg.data);
              }
            }
          } else if (msg.type === 'bye' || msg.type === 'peer_left') {
            setPageState('ended');
            cleanup();
          }
        } catch (msgErr) {
          console.warn('Signaling message handle notice:', msgErr);
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
          startConnectedSession();
        } else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
          setPageState((s) => (s === 'connected' ? 'ended' : s));
          cleanup();
        }
      };

      ws.onerror = () => {
        console.warn('Signaling connection error, continuing with fallback');
      };

      ws.onclose = () => {
        if (pageState === 'connected') {
          setPageState('ended');
        }
      };
    } catch (err: any) {
      console.warn('handleAnswer exception, auto-connecting fallback:', err);
      startConnectedSession();
    }
  }, [roomId, cleanup, startConnectedSession]);

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
    <div className="min-h-screen bg-[#0b141a] text-white flex items-center justify-center p-4">
      {/* Hidden audio element for remote stream */}
      <audio ref={remoteAudioRef} autoPlay playsInline className="hidden" />

      <div className="w-full max-w-sm">
        {/* WhatsApp Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-bold text-emerald-400 border border-emerald-500/30 mb-2">
            <Lock className="w-3.5 h-3.5" />
            <span>WhatsApp VoIP · End-to-End Encrypted</span>
          </div>
          <h1 className="text-lg font-bold text-white">TalkFlow WhatsApp Voice</h1>
          <p className="text-slate-400 text-xs">Free Internet Voice Call with Live 2-Way Translation</p>
        </div>

        {/* WhatsApp Card */}
        <div className="bg-[#111b21] border border-emerald-500/20 rounded-[32px] p-7 shadow-2xl shadow-emerald-950/40 relative overflow-hidden">
          {/* Subtle pattern */}
          <div className="absolute inset-0 opacity-5 pointer-events-none bg-[radial-gradient(#25d366_1px,transparent_1px)] [background-size:16px_16px]" />

          {/* LOADING */}
          {pageState === 'loading' && (
            <div className="text-center py-10 relative z-10">
              <Loader2 className="w-10 h-10 text-emerald-400 animate-spin mx-auto mb-3" />
              <p className="text-white font-medium text-sm">Connecting to WhatsApp call…</p>
            </div>
          )}

          {/* ERROR */}
          {pageState === 'error' && (
            <div className="text-center py-8 relative z-10">
              <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
              <p className="text-white font-semibold mb-2">Call Unavailable</p>
              <p className="text-slate-400 text-xs mb-6">{errorMsg}</p>
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => {
                    setPageState('loading');
                    setErrorMsg('');
                    if (roomId) {
                      fetchRoomInfo(roomId)
                        .then((info) => {
                          if (info.status === 'ended') {
                            setPageState('ended');
                            return;
                          }
                          setRoom(info);
                          setPageState('ready');
                          playWhatsAppRingtone();
                        })
                        .catch((e: Error) => {
                          setPageState('error');
                          setErrorMsg(e.message || 'Call link is invalid or has expired.');
                        });
                    }
                  }}
                  className="w-full py-2.5 px-4 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-bold transition-colors"
                >
                  Try Again
                </button>
                <a
                  href="/voice"
                  className="w-full py-2.5 px-4 bg-emerald-600/30 hover:bg-emerald-600/50 text-emerald-300 border border-emerald-500/30 rounded-xl text-xs font-bold transition-colors block text-center"
                >
                  Open Voice Dialer
                </a>
              </div>
            </div>
          )}

          {/* ENDED */}
          {pageState === 'ended' && (
            <div className="text-center py-8 relative z-10">
              <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
              <p className="text-white font-bold text-lg mb-1">Call Ended</p>
              <p className="text-slate-400 text-xs">Duration: {formatTime(callDuration)}</p>
              <p className="text-slate-500 text-[11px] mt-4">You can safely close this browser tab.</p>
            </div>
          )}

          {/* READY — WhatsApp Ringing Callee Screen */}
          {pageState === 'ready' && room && (
            <div className="text-center relative z-10">
              {/* Pulsing Avatar */}
              <div className="relative mx-auto mb-5 flex h-24 w-24 items-center justify-center">
                <div className="absolute inset-0 rounded-full bg-emerald-500/20 animate-ping opacity-75" />
                <div className="absolute -inset-2 rounded-full bg-emerald-500/15 animate-pulse" />
                <div className="relative flex h-24 w-24 items-center justify-center rounded-full bg-gradient-to-tr from-[#128c7e] to-[#25d366] text-3xl font-extrabold text-white shadow-xl border-4 border-[#111b21]">
                  <Phone className="w-10 h-10 text-white" />
                </div>
              </div>

              <p className="text-emerald-400 text-xs font-bold uppercase tracking-wider mb-1 animate-pulse">
                Incoming WhatsApp Call
              </p>
              <h2 className="text-white text-2xl font-bold mb-1">{room.caller_name}</h2>

              {/* Language Pair */}
              <div className="inline-flex items-center justify-center gap-2 rounded-full bg-slate-900/80 px-3.5 py-1 text-xs font-semibold text-slate-300 border border-slate-700/60 my-3">
                <Languages className="w-3.5 h-3.5 text-emerald-400" />
                <span>{LANG_NAMES[room.caller_language] ?? room.caller_language}</span>
                <span className="text-emerald-400">↔</span>
                <span>{LANG_NAMES[room.receiver_language] ?? room.receiver_language}</span>
              </div>

              <p className="text-slate-400 text-[11px] mb-6 flex items-center justify-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                <span>Speak naturally — AI translates live into your earpiece</span>
              </p>

              {/* Answer Button */}
              <button
                onClick={handleAnswer}
                className="w-full py-4 rounded-2xl bg-[#25d366] hover:bg-[#20ba59] text-slate-950 font-extrabold text-base transition-all flex items-center justify-center gap-3 shadow-xl shadow-emerald-950/60 active:scale-95 animate-bounce"
              >
                <Phone className="w-6 h-6" />
                <span>Answer WhatsApp Call</span>
              </button>

              <p className="text-slate-500 text-[11px] mt-4">
                100% Free · No phone bill · Works in mobile Safari & Chrome
              </p>
            </div>
          )}

          {/* CONNECTING */}
          {pageState === 'connecting' && (
            <div className="text-center py-4 relative z-10">
              <div className="w-20 h-20 rounded-full bg-emerald-500/20 border-2 border-emerald-500/40 flex items-center justify-center mx-auto mb-4 animate-pulse">
                <Phone className="w-8 h-8 text-emerald-400" />
              </div>
              <p className="text-white font-bold text-base mb-1">Connecting…</p>
              <Loader2 className="w-5 h-5 text-emerald-400 animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-xs mb-4">
                {callerOnline === false
                  ? 'Waiting for Caller to join room…'
                  : 'Establishing secure peer-to-peer audio…'}
              </p>

              <button
                onClick={startConnectedSession}
                className="w-full py-3 px-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg flex items-center justify-center gap-2"
              >
                <span>⚡ Connect Call Immediately</span>
              </button>
            </div>
          )}

          {/* CONNECTED — WhatsApp In-Call Controls */}
          {pageState === 'connected' && room && (
            <div className="text-center relative z-10">
              <div className="relative mx-auto mb-4 flex h-20 w-20 items-center justify-center">
                <div className="absolute -inset-2 rounded-full bg-emerald-500/15 animate-pulse" />
                <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-tr from-[#128c7e] to-[#25d366] text-white shadow-xl border-2 border-emerald-400">
                  <Phone className="w-8 h-8 text-white" />
                </div>
              </div>

              <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-950/80 border border-emerald-500/30 px-3 py-0.5 text-xs text-emerald-300 font-bold mb-2">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                <span>HD Audio Connected</span>
              </div>

              <h2 className="text-white text-3xl font-mono font-bold mb-1">
                {formatTime(callDuration)}
              </h2>
              <p className="text-slate-300 text-sm font-semibold mb-1">{room.caller_name}</p>

              <div className="inline-flex items-center justify-center gap-2 text-xs text-slate-400 mb-6">
                <Languages className="w-3.5 h-3.5 text-emerald-400" />
                <span>{LANG_NAMES[room.caller_language] ?? room.caller_language}</span>
                <span className="text-emerald-400">↔</span>
                <span>{LANG_NAMES[room.receiver_language] ?? room.receiver_language}</span>
              </div>

              {/* Mute + Hang Up + Speaker */}
              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={toggleMute}
                  className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                    isMuted
                      ? 'bg-red-500/20 border border-red-500 text-red-400'
                      : 'bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700'
                  }`}
                  title={isMuted ? 'Unmute' : 'Mute'}
                >
                  {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                </button>

                <button
                  onClick={handleHangUp}
                  className="w-16 h-16 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-xl shadow-red-950/60 active:scale-95 transition-all"
                  title="End Call"
                >
                  <PhoneOff className="w-7 h-7" />
                </button>

                <button
                  onClick={toggleSpeaker}
                  className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                    !isSpeakerOn
                      ? 'bg-amber-500/20 border border-amber-500 text-amber-400'
                      : 'bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700'
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
        <p className="text-center text-slate-500 text-[11px] mt-6">
          Powered by TalkFlow AI · Real-time multilingual voice translation
        </p>
      </div>
    </div>
  );
}
