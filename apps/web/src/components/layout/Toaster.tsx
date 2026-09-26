import { useToasts } from '@/stores/toasts';
import { cn } from '@/lib/utils';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const TONES = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
  info: 'border-iris-200 bg-iris-50 text-iris-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
};

export default function Toaster() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);
  return (
    <div aria-live="polite" aria-atomic="false"
         className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div key={t.id} role="status"
               className={cn('pointer-events-auto flex items-start gap-2.5 rounded-xl2 border px-4 py-3 shadow-lift animate-slide-up',
                 TONES[t.kind])}>
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{t.title}</p>
              {t.detail && <p className="mt-0.5 break-words text-xs opacity-80">{t.detail}</p>}
            </div>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss notification"
                    className="text-xs opacity-60 hover:opacity-100">✕</button>
          </div>
        );
      })}
    </div>
  );
}
