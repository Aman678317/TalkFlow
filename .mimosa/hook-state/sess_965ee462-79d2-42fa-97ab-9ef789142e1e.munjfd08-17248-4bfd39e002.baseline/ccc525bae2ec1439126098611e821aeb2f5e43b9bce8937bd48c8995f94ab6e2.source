import { useEffect, useRef, useState } from 'react';
import { Hand, Maximize2, Mic, MicOff, MonitorUp, Pin, PinOff, UserRound } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface VideoTileProps {
  name: string;
  lang: string;
  hear: string;
  stream?: MediaStream | null;
  videoOn?: boolean;
  isScreenShare?: boolean;
  speaking?: boolean;
  muted?: boolean;
  level?: number;
  self?: boolean;
  handRaised?: boolean;
  isPinned?: boolean;
  onTogglePin?: () => void;
  className?: string;
}

export function VideoTile({
  name,
  lang,
  hear,
  stream,
  videoOn = false,
  isScreenShare = false,
  speaking = false,
  muted = false,
  level = 0,
  self = false,
  handRaised = false,
  isPinned = false,
  onTogglePin,
  className,
}: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!stream) return;

    const bindStream = () => {
      if (videoRef.current && (videoOn || isScreenShare)) {
        if (videoRef.current.srcObject !== stream) {
          videoRef.current.srcObject = stream;
        }
        void videoRef.current.play().catch(() => {});
      }
      if (audioRef.current && !self) {
        if (audioRef.current.srcObject !== stream) {
          audioRef.current.srcObject = stream;
        }
        void audioRef.current.play().catch(() => {});
      }
    };

    bindStream();
    stream.addEventListener('addtrack', bindStream);
    stream.addEventListener('removetrack', bindStream);

    return () => {
      stream.removeEventListener('addtrack', bindStream);
      stream.removeEventListener('removetrack', bindStream);
    };
  }, [stream, videoOn, isScreenShare, self]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      void containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      void document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const initial = (name || 'P').trim().charAt(0).toUpperCase();
  const hasLiveVideo =
    !!stream &&
    (videoOn || isScreenShare) &&
    (self || stream.getVideoTracks().some((t) => t.readyState === 'live' && t.enabled));

  return (
    <div
      ref={containerRef}
      className={cn(
        'group relative flex min-h-48 w-full flex-col items-center justify-center overflow-hidden rounded-2xl border bg-slate-900 shadow-md transition-all duration-300',
        speaking
          ? 'border-lagoon-500 ring-4 ring-lagoon-500/20'
          : 'border-slate-800 hover:border-slate-700',
        isPinned && 'ring-2 ring-iris-500',
        className
      )}
    >
      {/* Dedicated audio element for remote peer audio playback */}
      {!self && (
        <audio ref={audioRef} autoPlay playsInline />
      )}

      {/* 1. Live Video Stream */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted={self} // Prevent self audio echo loop
        className={cn(
          'h-full w-full',
          isScreenShare ? 'bg-black object-contain' : 'object-cover',
          self && !isScreenShare && 'scale-x-[-1]', // Mirror self camera like Google Meet
          !hasLiveVideo && 'hidden'
        )}
      />

      {/* 2. Avatar Fallback when Camera is Off */}
      {!hasLiveVideo && (
        <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-slate-850 to-slate-925 p-4 text-center">
          <div className="relative">
            {speaking && (
              <span className="absolute -inset-3 animate-ping rounded-full bg-lagoon-400/20" />
            )}
            <div
              className={cn(
                'relative flex h-16 w-16 items-center justify-center rounded-full text-xl font-bold shadow-lg transition-transform duration-300',
                self ? 'bg-iris-600 text-white' : 'bg-slate-700 text-slate-100',
                speaking && 'scale-105 ring-4 ring-lagoon-400/40'
              )}
            >
              {initial ? initial : <UserRound className="h-8 w-8" />}
            </div>
          </div>
        </div>
      )}

      {/* 3. Screen Share Indicator Badge */}
      {isScreenShare && (
        <div className="absolute left-3 top-3 z-10 flex items-center gap-1.5 rounded-lg bg-iris-600/90 px-2.5 py-1 text-xs font-medium text-white shadow-md backdrop-blur">
          <MonitorUp className="h-3.5 w-3.5" />
          <span>Screen Share</span>
        </div>
      )}

      {/* 4. Hand Raised Badge */}
      {handRaised && (
        <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-lg bg-amber-500/95 px-2.5 py-1 text-xs font-bold text-slate-950 shadow-lg animate-bounce">
          <Hand className="h-4 w-4" />
          <span>Hand Raised</span>
        </div>
      )}

      {/* 5. Hover Actions (Pin / Fullscreen) */}
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
        {onTogglePin && (
          <button
            onClick={onTogglePin}
            className="rounded-lg bg-slate-900/80 p-1.5 text-slate-300 backdrop-blur hover:bg-slate-800 hover:text-white"
            title={isPinned ? 'Unpin tile' : 'Pin to stage'}
          >
            {isPinned ? <PinOff className="h-4 w-4 text-iris-400" /> : <Pin className="h-4 w-4" />}
          </button>
        )}
        <button
          onClick={toggleFullscreen}
          className="rounded-lg bg-slate-900/80 p-1.5 text-slate-300 backdrop-blur hover:bg-slate-800 hover:text-white"
          title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>

      {/* 6. Bottom Metadata Overlay: Name, Languages & Mic Status */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-end justify-between bg-gradient-to-t from-black/85 via-black/40 to-transparent p-3 pt-6">
        <div className="min-w-0 pr-2">
          <div className="flex items-center gap-2">
            <span className="truncate text-xs font-semibold text-white drop-shadow">
              {name || 'Participant'}{self && ' (you)'}
            </span>
            {speaking && (
              <div className="flex items-center gap-0.5">
                <span className="h-2 w-0.5 animate-bounce rounded-full bg-lagoon-400 [animation-delay:-0.3s]" />
                <span className="h-3.5 w-0.5 animate-bounce rounded-full bg-lagoon-400 [animation-delay:-0.15s]" />
                <span className="h-2 w-0.5 animate-bounce rounded-full bg-lagoon-400" />
              </div>
            )}
          </div>
          <p className="truncate text-[10px] text-slate-300/90">
            speaks <span className="font-medium text-slate-100">{lang}</span> · hears <span className="font-medium text-slate-100">{hear}</span>
          </p>
        </div>

        {/* Mic mute state */}
        <div
          className={cn(
            'flex h-6 w-6 shrink-0 items-center justify-center rounded-full shadow',
            muted ? 'bg-rose-600 text-white' : 'bg-slate-800/80 text-emerald-400 backdrop-blur'
          )}
          title={muted ? 'Muted' : 'Microphone active'}
        >
          {muted ? <MicOff className="h-3 w-3" /> : <Mic className="h-3 w-3" />}
        </div>
      </div>

      {/* Audio Level Bar for speaking self */}
      {speaking && level > 0 && (
        <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden bg-slate-800" aria-hidden="true">
          <div
            className="h-full bg-lagoon-400 transition-all duration-75"
            style={{ width: `${Math.min(100, level * 300)}%` }}
          />
        </div>
      )}
    </div>
  );
}
