/**
 * WhatsAppCallModal.tsx
 *
 * Authentic WhatsApp VoIP In-Call & Incoming Call Screen for TalkFlow:
 * - End-to-end encrypted badge
 * - Contact avatar with audio-reactive pulsing rings
 * - Real-time call states: 'calling' -> 'ringing' -> 'connected' -> 'ended'
 * - Web Audio API synthesized WhatsApp dial tone and incoming ringtone
 * - Live AI bilingual speech translation captions floating in WhatsApp chat bubbles
 * - Floating round call controls (Mute, Speaker, Captions, Share Link, Hang Up)
 */
import { useEffect, useState } from 'react';
import {
  Phone,
  PhoneOff,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Lock,
  Share2,
  Subtitles,
  Sparkles,
  ArrowLeftRight,
  Check,
  Copy,
} from 'lucide-react';
import {
  playWhatsAppDialTone,
  playWhatsAppRingtone,
  stopWhatsAppAudio,
} from '../../lib/whatsappAudio';

export interface WhatsAppCallData {
  roomId: string;
  contactName: string;
  phoneNumber: string;
  callerLanguage: string;
  receiverLanguage: string;
  isIncoming?: boolean;
  joinUrl?: string;
}

export interface LiveTranscriptMessage {
  id: string;
  speaker: 'self' | 'peer';
  speakerName: string;
  sourceText: string;
  sourceLang: string;
  translatedText: string;
  targetLang: string;
  timestamp: string;
}

interface WhatsAppCallModalProps {
  isOpen: boolean;
  callData: WhatsAppCallData | null;
  callState: 'calling' | 'ringing' | 'connected' | 'ended';
  callDuration: number;
  transcripts?: LiveTranscriptMessage[];
  onAnswer?: () => void;
  onDecline?: () => void;
  onEndCall?: () => void;
  onToggleMute?: () => void;
  isMuted?: boolean;
  onToggleSpeaker?: () => void;
  isSpeakerOn?: boolean;
}

export default function WhatsAppCallModal({
  isOpen,
  callData,
  callState,
  callDuration,
  transcripts = [],
  onAnswer,
  onDecline,
  onEndCall,
  onToggleMute,
  isMuted = false,
  onToggleSpeaker,
  isSpeakerOn = true,
}: WhatsAppCallModalProps) {
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [copiedLink, setCopiedLink] = useState(false);

  // Manage sound effects based on call state
  useEffect(() => {
    if (!isOpen || !callData) {
      stopWhatsAppAudio();
      return;
    }

    if (callState === 'calling' && !callData.isIncoming) {
      playWhatsAppDialTone();
    } else if (callState === 'ringing' && callData.isIncoming) {
      playWhatsAppRingtone();
    } else {
      stopWhatsAppAudio();
    }

    return () => {
      stopWhatsAppAudio();
    };
  }, [isOpen, callState, callData]);

  if (!isOpen || !callData) return null;

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const getInitials = (name: string) => {
    if (!name) return 'WA';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  };

  const copyCallLink = () => {
    if (callData.joinUrl) {
      navigator.clipboard.writeText(callData.joinUrl).then(() => {
        setCopiedLink(true);
        setTimeout(() => setCopiedLink(false), 2500);
      });
    }
  };

  const shareViaWhatsApp = () => {
    if (!callData.joinUrl) return;
    const cleanPhone = callData.phoneNumber.replace(/\D/g, '');
    const text = encodeURIComponent(
      `Join my secure WhatsApp Voice Call on TalkFlow with live 2-way AI translation:\n${callData.joinUrl}`
    );
    const waUrl = cleanPhone
      ? `https://api.whatsapp.com/send?phone=${cleanPhone}&text=${text}`
      : `https://api.whatsapp.com/send?text=${text}`;
    window.open(waUrl, '_blank', 'noopener,noreferrer');
  };

  // ──────────────────────────────────────────────────────────────────────────
  // 1. INCOMING CALL SCREEN (Ringing callee modal)
  // ──────────────────────────────────────────────────────────────────────────
  if (callData.isIncoming && callState === 'ringing') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 backdrop-blur-md p-4 animate-in fade-in zoom-in-95 duration-200">
        <div className="relative w-full max-w-sm rounded-[32px] bg-gradient-to-b from-[#111b21] via-[#0b141a] to-[#075e54]/30 p-8 text-center text-white shadow-2xl border border-emerald-500/20 overflow-hidden">
          {/* WhatsApp Brand Badge */}
          <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-[11px] font-bold text-emerald-400 border border-emerald-500/30 mb-6">
            <Lock className="h-3 w-3" />
            <span>WhatsApp VoIP · End-to-End Encrypted</span>
          </div>

          {/* Pulsing Avatar */}
          <div className="relative mx-auto my-4 flex h-28 w-28 items-center justify-center">
            <div className="absolute inset-0 rounded-full bg-emerald-500/20 animate-ping opacity-75" />
            <div className="absolute -inset-3 rounded-full bg-emerald-500/10 animate-pulse" />
            <div className="relative flex h-28 w-28 items-center justify-center rounded-full bg-gradient-to-tr from-emerald-600 to-teal-500 text-3xl font-black text-white shadow-xl border-4 border-[#111b21]">
              {getInitials(callData.contactName)}
            </div>
          </div>

          {/* Caller Details */}
          <div className="mt-4 space-y-1">
            <h3 className="text-2xl font-bold tracking-tight text-white">{callData.contactName}</h3>
            <p className="text-sm font-mono text-emerald-300 font-medium">{callData.phoneNumber}</p>
            <p className="text-xs text-slate-400 animate-pulse">Incoming WhatsApp Voice Call...</p>
          </div>

          {/* Language Pair Indicator */}
          <div className="mt-4 inline-flex items-center gap-2 rounded-full bg-slate-900/80 px-3.5 py-1 text-xs font-semibold text-slate-300 border border-slate-700/60">
            <span className="uppercase text-[11px] text-emerald-400">{callData.callerLanguage}</span>
            <ArrowLeftRight className="h-3 w-3 text-emerald-400" />
            <span className="uppercase text-[11px] text-teal-300">{callData.receiverLanguage}</span>
            <span className="text-[10px] text-slate-400 ml-1">Live Translation</span>
          </div>

          {/* Call Actions */}
          <div className="mt-9 flex items-center justify-center gap-6">
            {/* Decline */}
            <div className="flex flex-col items-center gap-1.5">
              <button
                type="button"
                onClick={onDecline}
                className="flex h-16 w-16 items-center justify-center rounded-full bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/40 active:scale-95 transition-all"
                title="Decline Call"
              >
                <PhoneOff className="h-7 w-7" />
              </button>
              <span className="text-[11px] font-semibold text-slate-400">Decline</span>
            </div>

            {/* Accept */}
            <div className="flex flex-col items-center gap-1.5">
              <button
                type="button"
                onClick={onAnswer}
                className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 hover:bg-emerald-400 text-white shadow-xl shadow-emerald-900/50 active:scale-95 transition-all animate-bounce"
                title="Answer Call"
              >
                <Phone className="h-7 w-7" />
              </button>
              <span className="text-[11px] font-semibold text-emerald-400">Answer</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ──────────────────────────────────────────────────────────────────────────
  // 2. ACTIVE IN-CALL / OUTBOUND CALL SCREEN
  // ──────────────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 backdrop-blur-md p-3 sm:p-4 animate-in fade-in duration-200">
      <div className="relative flex flex-col justify-between w-full max-w-md h-[92vh] max-h-[700px] rounded-[36px] bg-[#0b141a] text-white shadow-2xl border border-emerald-500/25 overflow-hidden">
        {/* Background WhatsApp decorative subtle pattern */}
        <div className="absolute inset-0 opacity-5 pointer-events-none bg-[radial-gradient(#25d366_1px,transparent_1px)] [background-size:16px_16px]" />

        {/* ── Top Bar ── */}
        <div className="relative z-10 flex items-center justify-between px-6 pt-6 pb-2">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
            <Lock className="h-3 w-3 text-emerald-400" />
            <span className="text-[11px] text-emerald-400/90 font-semibold">End-to-end encrypted</span>
          </div>

          <div className="flex items-center gap-2">
            {callData.joinUrl && (
              <button
                type="button"
                onClick={shareViaWhatsApp}
                className="flex items-center gap-1.5 rounded-full bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 px-3 py-1 text-xs font-semibold border border-emerald-500/30 transition-all"
                title="Send link on WhatsApp"
              >
                <Share2 className="h-3.5 w-3.5" />
                <span>Invite via WA</span>
              </button>
            )}
          </div>
        </div>

        {/* ── Center Stage: Contact & Call Status ── */}
        <div className="relative z-10 flex flex-col items-center justify-center px-6 py-2 text-center">
          {/* Avatar with pulse ripples */}
          <div className="relative flex items-center justify-center my-3">
            {callState === 'connected' && (
              <>
                <div className="absolute -inset-4 rounded-full bg-emerald-500/10 animate-ping opacity-60" />
                <div className="absolute -inset-2 rounded-full bg-emerald-500/15 animate-pulse" />
              </>
            )}
            {callState === 'calling' && (
              <div className="absolute -inset-3 rounded-full bg-teal-500/15 animate-pulse" />
            )}
            <div className="relative flex h-24 w-24 sm:h-28 sm:w-28 items-center justify-center rounded-full bg-gradient-to-tr from-[#128c7e] to-[#25d366] text-3xl font-extrabold text-white shadow-2xl border-4 border-[#111b21]">
              {getInitials(callData.contactName)}
            </div>
          </div>

          {/* Contact Details */}
          <h2 className="text-2xl font-bold tracking-tight text-white mt-2">
            {callData.contactName}
          </h2>
          <p className="text-sm font-mono text-emerald-300 font-semibold mt-0.5">
            {callData.phoneNumber}
          </p>

          {/* Call Status Badge */}
          <div className="mt-2.5">
            {callState === 'calling' && (
              <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400 font-medium animate-pulse">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                Calling...
              </span>
            )}
            {callState === 'ringing' && (
              <span className="inline-flex items-center gap-1.5 text-xs text-teal-300 font-medium animate-pulse">
                <span className="h-2 w-2 rounded-full bg-teal-400" />
                Ringing...
              </span>
            )}
            {callState === 'connected' && (
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-950/70 border border-emerald-500/30 px-3.5 py-1">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-sm font-mono font-bold text-emerald-300">
                  {formatTime(callDuration)}
                </span>
                <span className="text-[10px] uppercase font-bold text-emerald-400/80">HD VoIP</span>
              </div>
            )}
            {callState === 'ended' && (
              <span className="text-xs text-slate-400 font-medium">Call Ended</span>
            )}
          </div>
        </div>

        {/* ── Middle Layer: Floating Translated Subtitles (TalkFlow Superpower) ── */}
        <div className="relative z-10 flex-1 px-5 py-2 overflow-y-auto space-y-2 max-h-[220px]">
          {showSubtitles && transcripts.length > 0 ? (
            transcripts.slice(-3).map((item) => (
              <div
                key={item.id}
                className={`flex flex-col p-3 rounded-2xl text-xs backdrop-blur-md transition-all ${
                  item.speaker === 'self'
                    ? 'ml-auto max-w-[85%] bg-[#005c4b]/80 border border-emerald-500/20 text-emerald-50 rounded-tr-xs'
                    : 'mr-auto max-w-[85%] bg-[#202c33]/90 border border-slate-700/60 text-slate-100 rounded-tl-xs'
                }`}
              >
                <div className="flex items-center justify-between text-[10px] text-emerald-300 font-semibold mb-1">
                  <span>{item.speakerName}</span>
                  <span className="opacity-70">{item.timestamp}</span>
                </div>
                {/* Original Source */}
                <p className="text-slate-300 text-[11px] leading-relaxed italic opacity-85">
                  "{item.sourceText}"
                </p>
                {/* Live Translation */}
                <div className="mt-1 flex items-start gap-1 font-semibold text-white">
                  <Sparkles className="h-3 w-3 text-emerald-400 mt-0.5 flex-shrink-0" />
                  <span>{item.translatedText}</span>
                </div>
              </div>
            ))
          ) : showSubtitles ? (
            <div className="flex flex-col items-center justify-center py-6 text-center text-slate-500 text-xs">
              <Sparkles className="h-5 w-5 text-emerald-500/40 mb-1 animate-pulse" />
              <p className="text-[11px] text-slate-400">Live AI Speech Translation Active</p>
              <p className="text-[10px] text-slate-500">
                Speak naturally in your language — translated subtitles float here
              </p>
            </div>
          ) : null}
        </div>

        {/* ── WhatsApp Call Link Banner (if waiting or sharing) ── */}
        {callData.joinUrl && callState !== 'connected' && (
          <div className="relative z-10 mx-5 mb-2 rounded-2xl bg-[#111b21] p-3 border border-slate-800 text-xs flex items-center justify-between gap-2 shadow-inner">
            <div className="truncate text-slate-300 font-mono text-[11px]">
              {callData.joinUrl}
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <button
                type="button"
                onClick={copyCallLink}
                className="flex items-center gap-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 px-2.5 py-1 text-[11px] font-semibold transition-all"
                title="Copy Link"
              >
                {copiedLink ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                <span>{copiedLink ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>
        )}

        {/* ── Bottom Controls Dock ── */}
        <div className="relative z-10 bg-[#111b21]/90 backdrop-blur-md px-6 py-5 border-t border-slate-800/80 rounded-b-[36px]">
          <div className="flex items-center justify-around gap-3">
            {/* Mute Mic */}
            <button
              type="button"
              onClick={onToggleMute}
              className={`flex h-13 w-13 items-center justify-center rounded-full transition-all active:scale-95 ${
                isMuted
                  ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700/60'
              }`}
              title={isMuted ? 'Unmute Microphone' : 'Mute Microphone'}
            >
              {isMuted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>

            {/* Speaker Toggle */}
            <button
              type="button"
              onClick={onToggleSpeaker}
              className={`flex h-13 w-13 items-center justify-center rounded-full transition-all active:scale-95 ${
                !isSpeakerOn
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700/60'
              }`}
              title={isSpeakerOn ? 'Speaker On' : 'Speaker Off'}
            >
              {isSpeakerOn ? <Volume2 className="h-5 w-5" /> : <VolumeX className="h-5 w-5" />}
            </button>

            {/* Live Subtitles Toggle */}
            <button
              type="button"
              onClick={() => setShowSubtitles((s) => !s)}
              className={`flex h-13 w-13 items-center justify-center rounded-full transition-all active:scale-95 ${
                showSubtitles
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-slate-700/60'
              }`}
              title="Toggle Translated Subtitles"
            >
              <Subtitles className="h-5 w-5" />
            </button>

            {/* Hang Up (Red Floating Action Button) */}
            <button
              type="button"
              onClick={onEndCall}
              className="flex h-15 w-15 items-center justify-center rounded-full bg-red-600 hover:bg-red-500 text-white shadow-xl shadow-red-950/60 active:scale-95 transition-all"
              title="End Call"
            >
              <PhoneOff className="h-6 w-6" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
