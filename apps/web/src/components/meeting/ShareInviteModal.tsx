import { useState } from 'react';
import { Check, Copy, Share2, Users, X } from 'lucide-react';
import { Button, Card } from '@/components/ui';
import { toast } from '@/stores/toasts';

interface ShareInviteModalProps {
  open: boolean;
  onClose: () => void;
  meetingId: string;
  meetingTitle?: string;
  roomName?: string;
}

export function ShareInviteModal({
  open,
  onClose,
  meetingId,
  meetingTitle,
  roomName,
}: ShareInviteModalProps) {
  const [copied, setCopied] = useState(false);

  if (!open) return null;

  const joinUrl = `${window.location.origin}/meeting/${meetingId}`;

  const copyToClipboard = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(joinUrl);
      } else {
        const input = document.createElement('input');
        input.value = joinUrl;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
      }
      setCopied(true);
      toast.success('Invite link copied!', 'Anyone with this link can join this call.');
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error('Failed to copy', 'Please copy the link manually.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <Card className="relative w-full max-w-md border-slate-700 bg-slate-900 p-6 text-white shadow-2xl">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-iris-600/20 text-iris-400">
            <Share2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Share Meeting Invite</h2>
            <p className="text-xs text-slate-400">Invite teammates and external guests to join</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3.5">
            <div className="mb-1.5 flex items-center justify-between text-xs text-slate-400">
              <span>Meeting: <strong className="text-slate-200">{meetingTitle || 'GlobalTalk Call'}</strong></span>
              {roomName && <span className="text-[11px] text-slate-500">#{roomName}</span>}
            </div>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={joinUrl}
                className="flex-1 select-all rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-iris-500"
              />
              <Button
                size="sm"
                onClick={copyToClipboard}
                variant={copied ? 'primary' : 'secondary'}
                className="shrink-0 gap-1.5"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-300" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>

          <div className="rounded-xl bg-slate-800/40 p-3 text-xs text-slate-400">
            <p className="flex items-center gap-2 font-medium text-slate-300">
              <Users className="h-4 w-4 text-iris-400" /> Realtime Multilingual Bridge
            </p>
            <p className="mt-1 text-[11px] leading-relaxed">
              Participants can join in their native language — speech is automatically translated in realtime with live captions.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={onClose}>
              Done
            </Button>
            <Button onClick={copyToClipboard} className="gap-2">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? 'Link Copied!' : 'Copy Meeting Link'}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
