/**
 * WhatsAppCallLinkModal.tsx
 *
 * Modal for creating and sharing WhatsApp Voice Call Links:
 * - Direct one-tap share via WhatsApp (wa.me)
 * - Copyable universal call link (works in any browser, zero login)
 * - Instant QR code for mobile camera scanning
 */
import { useState } from 'react';
import {
  Share2,
  Copy,
  Check,
  X,
  Lock,
  Sparkles,
  PhoneCall,
  QrCode,
} from 'lucide-react';

interface WhatsAppCallLinkModalProps {
  isOpen: boolean;
  onClose: () => void;
  joinUrl: string;
  phoneNumber?: string;
  contactName?: string;
  callerLanguage?: string;
  receiverLanguage?: string;
}

export default function WhatsAppCallLinkModal({
  isOpen,
  onClose,
  joinUrl,
  phoneNumber = '',
  contactName = '',
  callerLanguage = 'Hindi',
  receiverLanguage = 'Japanese',
}: WhatsAppCallLinkModalProps) {
  const [copied, setCopied] = useState(false);
  const [showQr, setShowQr] = useState(false);

  if (!isOpen) return null;

  const displayName = contactName || phoneNumber || 'Contact';

  const handleCopy = () => {
    navigator.clipboard.writeText(joinUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  const handleShareWhatsApp = () => {
    const cleanPhone = phoneNumber.replace(/\D/g, '');
    const message = encodeURIComponent(
      `📞 Join my WhatsApp Voice Call on TalkFlow with live 2-way AI translation:\n${joinUrl}\n\n(No app download needed — tap link to answer directly in your browser)`
    );
    const waUrl = cleanPhone
      ? `https://api.whatsapp.com/send?phone=${cleanPhone}&text=${message}`
      : `https://api.whatsapp.com/send?text=${message}`;
    window.open(waUrl, '_blank', 'noopener,noreferrer');
  };

  // Generate lightweight QR code SVG data URL or render QR image
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(joinUrl)}&color=075e54`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-xs p-4 animate-in fade-in zoom-in-95 duration-200">
      <div className="relative w-full max-w-md rounded-3xl bg-[#111b21] p-6 text-white shadow-2xl border border-emerald-500/25 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-400">
              <PhoneCall className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Create WhatsApp Call Link</h3>
              <p className="text-[11px] text-slate-400">Share with {displayName} for instant free voice calling</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="mt-5 space-y-4">
          {/* WhatsApp Features Pill */}
          <div className="rounded-2xl bg-[#0b141a] p-3.5 border border-emerald-500/15 space-y-2">
            <div className="flex items-center gap-2 text-xs text-emerald-400 font-semibold">
              <Lock className="h-3.5 w-3.5 flex-shrink-0" />
              <span>100% Free VoIP · Zero Carrier Toll · E2E Encrypted</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Anyone with this link can answer directly in their phone browser without installing an app or signing in.
            </p>
            <div className="flex items-center gap-2 text-[11px] text-slate-300 font-medium pt-1 border-t border-slate-800">
              <Sparkles className="h-3 w-3 text-teal-400" />
              <span>Includes Live AI Translation: {callerLanguage} ↔ {receiverLanguage}</span>
            </div>
          </div>

          {/* Link Display Box */}
          <div className="rounded-2xl bg-slate-900/90 p-3 border border-slate-800 flex items-center justify-between gap-2">
            <div className="truncate text-xs font-mono text-emerald-300 select-all">
              {joinUrl}
            </div>
            <button
              type="button"
              onClick={handleCopy}
              className="flex items-center gap-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white transition-all flex-shrink-0 shadow-xs"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied!' : 'Copy'}</span>
            </button>
          </div>

          {/* QR Code Toggle */}
          {showQr && (
            <div className="flex flex-col items-center justify-center p-4 bg-white rounded-2xl shadow-inner animate-in fade-in zoom-in-95">
              <img src={qrUrl} alt="WhatsApp Call QR Code" className="h-44 w-44 rounded-lg" />
              <p className="text-xs text-slate-600 font-medium mt-2">
                Scan with any mobile camera to join call instantly
              </p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              type="button"
              onClick={() => setShowQr((s) => !s)}
              className="flex items-center justify-center gap-2 rounded-2xl bg-slate-800 hover:bg-slate-700 border border-slate-700 py-3 text-xs font-bold text-slate-200 transition-all"
            >
              <QrCode className="h-4 w-4 text-slate-400" />
              <span>{showQr ? 'Hide QR Code' : 'Scan QR Code'}</span>
            </button>

            <button
              type="button"
              onClick={handleShareWhatsApp}
              className="flex items-center justify-center gap-2 rounded-2xl bg-[#25d366] hover:bg-[#20ba59] py-3 text-xs font-bold text-slate-950 transition-all shadow-lg shadow-emerald-950/50 active:scale-95"
            >
              <Share2 className="h-4 w-4" />
              <span>Share on WhatsApp</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
