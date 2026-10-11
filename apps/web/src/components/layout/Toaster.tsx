import { AnimatePresence, motion } from 'motion/react';
import { useToasts } from '@/stores/toasts';
import { cn } from '@/lib/utils';
import { springSheet, TAP_TRANSITION, PRESS_SCALE } from '@/lib/motion';
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
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const Icon = ICONS[t.kind];
          return (
            <motion.div key={t.id} role="status"
                 layout
                 initial={{ opacity: 0, y: 16, scale: 0.96 }}
                 animate={{ opacity: 1, y: 0, scale: 1 }}
                 exit={{ opacity: 0, scale: 0.95, y: 6, transition: { duration: 0.16, ease: 'easeIn' } }}
                 transition={springSheet}
                 className={cn('pointer-events-auto flex items-start gap-2.5 rounded-xl2 border px-4 py-3 shadow-lift backdrop-blur-sm',
                   TONES[t.kind])}>
              <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{t.title}</p>
                {t.detail && <p className="mt-0.5 break-words text-xs opacity-80">{t.detail}</p>}
              </div>
              <motion.button onClick={() => dismiss(t.id)} aria-label="Dismiss notification"
                      whileTap={{ scale: PRESS_SCALE }} transition={TAP_TRANSITION}
                      className="text-xs opacity-60 transition-opacity hover:opacity-100">✕</motion.button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
