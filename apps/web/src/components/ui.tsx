/**
 * GlobalTalk AI design system (PDD §36).
 * Accessible primitives: focus rings, aria attributes, keyboard support.
 */
import { forwardRef, useEffect, useId, useRef, type ButtonHTMLAttributes,
         type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes,
         type TextareaHTMLAttributes } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';
import { springSheet, springSnappy, TAP_TRANSITION, PRESS_SCALE, EASE_STANDARD } from '@/lib/motion';
export { Field, SegmentedControl } from './ui/index';

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent';
type Size = 'sm' | 'md' | 'lg' | 'icon';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-iris-600 text-white shadow-xs hover:-translate-y-0.5 hover:bg-iris-700 hover:shadow-accent active:bg-iris-800 disabled:bg-ink-300',
  secondary: 'border border-border bg-surface-panel text-ink-700 shadow-xs hover:-translate-y-0.5 hover:bg-surface-subtle active:bg-ink-100 disabled:text-ink-400',
  ghost: 'text-ink-600 hover:bg-surface-subtle hover:text-ink-950 active:bg-ink-100',
  danger: 'bg-rose-600 text-white shadow-xs hover:-translate-y-0.5 hover:bg-rose-700 active:bg-rose-800 disabled:bg-rose-300',
  accent: 'bg-lagoon-600 text-white shadow-xs hover:-translate-y-0.5 hover:bg-lagoon-700 hover:shadow-accent active:bg-lagoon-800 disabled:bg-ink-300',
};

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs rounded-lg gap-1.5',
  md: 'h-10 px-4 text-sm rounded-xl2 gap-2',
  lg: 'h-12 px-6 text-base rounded-xl2 gap-2',
  icon: 'h-9 w-9 rounded-lg justify-center',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, className, children, disabled, ...props }, ref) => {
    const reducedMotion = useReducedMotion();
    // motion.button redefines drag/animation handlers; buttons don't use them
    const { onDrag, onDragStart, onDragEnd, onAnimationStart, onAnimationEnd,
            onAnimationIteration, onTransitionEnd, ...rest } = props as ButtonHTMLAttributes<HTMLButtonElement> &
      Record<'onDrag' | 'onDragStart' | 'onDragEnd' | 'onAnimationStart' | 'onAnimationEnd' |
        'onAnimationIteration' | 'onTransitionEnd', unknown>;
    return (
      <motion.button
        ref={ref}
        whileTap={reducedMotion || disabled || loading ? undefined : { scale: PRESS_SCALE }}
        transition={reducedMotion ? undefined : TAP_TRANSITION}
        className={cn(
          'inline-flex select-none items-center font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-standard',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
          'disabled:cursor-not-allowed',
          VARIANTS[variant], SIZES[size], className)}
        disabled={disabled || loading}
        {...rest}>
        {loading && <Spinner className="h-4 w-4" />}
        {children}
      </motion.button>
    );
  });
Button.displayName = 'Button';

// ---------------------------------------------------------------------------
// Spinner / Skeleton
// ---------------------------------------------------------------------------

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn('animate-spin', className)} viewBox="0 0 24 24" fill="none"
         role="status" aria-label="Loading">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse-soft rounded-lg bg-ink-100', className)}
              aria-hidden="true" />;
}

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> &
  { label?: string; error?: string }>(
  ({ label, error, className, id, ...props }, ref) => {
    const autoId = useRef(`in-${Math.random().toString(36).slice(2, 8)}`);
    const inputId = id ?? autoId.current;
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-ink-700">
            {label}
          </label>
        )}
        <input
          ref={ref} id={inputId}
          aria-invalid={!!error} aria-describedby={error ? `${inputId}-err` : undefined}
          className={cn(
            'h-10 w-full rounded-xl2 border bg-surface-panel px-3 text-sm text-ink-900 placeholder:text-ink-400',
            'transition-[background-color,border-color,box-shadow] duration-200 focus:border-iris-600 focus:outline-none focus:ring-4 focus:ring-iris-600/10',
            'disabled:bg-ink-50 disabled:text-ink-400',
            error ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-500/10' : 'border-border', className)}
          {...props} />
         {error && <p id={`${inputId}-err`} className="mt-1 text-xs text-rose-700" role="alert">{error}</p>}
      </div>
    );
  });
Input.displayName = 'Input';

export const Textarea = forwardRef<HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }>(
  ({ label, className, id, ...props }, ref) => {
    const autoId = useRef(`ta-${Math.random().toString(36).slice(2, 8)}`);
    const taId = id ?? autoId.current;
    return (
      <div className="w-full">
         {label && <label htmlFor={taId} className="mb-1.5 block text-sm font-medium text-ink-700">{label}</label>}
        <textarea ref={ref} id={taId}
          className={cn(
            'w-full rounded-xl2 border border-border bg-surface-panel p-3 text-sm text-ink-900',
            'placeholder:text-ink-400 transition-[background-color,border-color,box-shadow] duration-200 focus:border-iris-600 focus:outline-none focus:ring-4 focus:ring-iris-600/10',
            className)}
          {...props} />
      </div>
    );
  });
Textarea.displayName = 'Textarea';

export const Select = forwardRef<HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement> & { label?: string }>(
  ({ label, className, id, children, ...props }, ref) => {
    const autoId = useRef(`sel-${Math.random().toString(36).slice(2, 8)}`);
    const selId = id ?? autoId.current;
    return (
      <div className="w-full">
         {label && <label htmlFor={selId} className="mb-1.5 block text-sm font-medium text-ink-700">{label}</label>}
        <select ref={ref} id={selId}
          className={cn(
            'h-10 w-full rounded-xl2 border border-border bg-surface-panel px-3 text-sm text-ink-900',
            'transition-[background-color,border-color,box-shadow] duration-200 focus:border-iris-600 focus:outline-none focus:ring-4 focus:ring-iris-600/10',
            'disabled:bg-ink-50 disabled:text-ink-400', className)}
          {...props}>
          {children}
        </select>
      </div>
    );
  });
Select.displayName = 'Select';

export function Toggle({ checked, onChange, label, id }:
  { checked: boolean; onChange: (v: boolean) => void; label: string; id?: string }) {
  const reducedMotion = useReducedMotion();
  return (
    <button id={id} type="button" role="switch" aria-checked={checked} aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn('relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
        checked ? 'bg-iris-600' : 'bg-ink-300')}>
      <motion.span
        layout={reducedMotion ? undefined : true}
        transition={reducedMotion ? undefined : springSnappy}
        className={cn('inline-block h-4 w-4 rounded-full bg-white shadow-xs',
          checked ? 'ml-6' : 'ml-1')} />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Surfaces
// ---------------------------------------------------------------------------

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}

export function Card({ className, children, title, subtitle, action, ...rest }: CardProps) {
  return (
    <div className={cn('overflow-hidden rounded-2xl border border-border bg-surface-panel shadow-card', className)} {...rest}>
      {(title !== undefined || subtitle !== undefined || action !== undefined) && (
        <CardHeader title={title} subtitle={subtitle} action={action} />
      )}
      <div className={title !== undefined || subtitle !== undefined || action !== undefined ? "p-5" : undefined}>
        {children}
      </div>
    </div>
  );
}

export function CardHeader({ title, subtitle, action }:
  { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-4">
      <div>
        <h2 className="text-base font-semibold text-ink-950">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const BADGE_TONES: Record<string, string> = {
  neutral: 'bg-ink-100 text-ink-700 border-ink-200',
  good: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warn: 'bg-amber-50 text-amber-700 border-amber-200',
  bad: 'bg-rose-50 text-rose-700 border-rose-200',
  info: 'bg-sky-50 text-sky-700 border-sky-200',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-700 border-amber-200',
  red: 'bg-rose-50 text-rose-700 border-rose-200',
  iris: 'bg-iris-50 text-iris-700 border-iris-200',
  lagoon: 'bg-lagoon-50 text-lagoon-700 border-lagoon-200',
};

export function Badge({ tone = 'neutral', children, className, title }:
  { tone?: string; children: ReactNode; className?: string; title?: string }) {
  const toneClass = BADGE_TONES[tone] || BADGE_TONES.neutral;
  return (
    <span title={title} className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
      toneClass, className)}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Modal (focus-trapped, Esc to close)
// ---------------------------------------------------------------------------

export function Modal({ open, onClose, title, children, wide }:
  { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const focusables = ref.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    focusables?.[0]?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog"
             aria-modal="true" aria-label={typeof title === 'string' ? title : 'Dialog'}>
           <motion.div className="absolute inset-0 bg-black/40 backdrop-blur-md" onClick={onClose}
                initial={reducedMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }}
                exit={reducedMotion ? { opacity: 1 } : { opacity: 0 }}
                transition={reducedMotion ? undefined : { duration: 0.2, ease: EASE_STANDARD }} />
           <motion.div ref={ref}
                initial={reducedMotion ? false : { opacity: 0, scale: 0.96, y: 14 }}
                animate={reducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
                exit={reducedMotion ? { opacity: 1 } : { opacity: 0, scale: 0.97, y: 8, transition: { duration: 0.16, ease: 'easeIn' } }}
                transition={reducedMotion ? undefined : springSheet}
                className={cn('relative w-full rounded-3xl border border-black/10 bg-surface-panel/95 backdrop-blur-2xl shadow-2xl',
                  wide ? 'max-w-3xl' : 'max-w-lg')}>
             <div className="flex items-center justify-between border-b border-ink-100/80 px-6 py-4">
               <h2 className="text-base font-semibold tracking-title text-ink-950">{title}</h2>
              <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close dialog">✕</Button>
            </div>
            <div className="px-5 py-4">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

export function EmptyState({ icon, title, hint, body, action }:
  { icon?: ReactNode; title: string; hint?: string; body?: string; action?: ReactNode }) {
  const desc = hint || body;
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-ink-300 bg-surface-canvas px-6 py-12 text-center">
      {icon && <div className="text-2xl text-ink-400">{icon}</div>}
      <p className="text-sm font-semibold text-ink-700">{title}</p>
      {desc && <p className="max-w-sm text-xs text-ink-500">{desc}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ title, detail, message, code, retry, onRetry }:
  { title?: string; detail?: string; message?: string; code?: string; retry?: () => void; onRetry?: () => void }) {
  const heading = title || message || 'Something went wrong';
  const sub = detail || (code ? `Error code: ${code}` : undefined);
  const handleRetry = retry || onRetry;
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-6 py-8 text-center"
         role="alert">
      <p className="text-sm font-semibold text-rose-800">{heading}</p>
      {sub && <p className="max-w-md text-xs text-rose-600">{sub}</p>}
      {handleRetry && <Button size="sm" variant="secondary" onClick={handleRetry} className="mt-1">Retry</Button>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabs (keyboard accessible)
// ---------------------------------------------------------------------------

export function Tabs({ tabs, active, onChange }:
  { tabs: Array<{ id: string; label: ReactNode }>; active: string;
     onChange: (id: string) => void }) {
  const groupId = useId();
  const reducedMotion = useReducedMotion();
  return (
    <div role="tablist" aria-label="Tabs" className="flex gap-1 rounded-xl2 bg-ink-100 p-1">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={active === t.id}
          tabIndex={active === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => {
            const i = tabs.findIndex((x) => x.id === active);
            if (e.key === 'ArrowRight') onChange(tabs[(i + 1) % tabs.length].id);
            if (e.key === 'ArrowLeft') onChange(tabs[(i - 1 + tabs.length) % tabs.length].id);
          }}
          className={cn('relative rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
             'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus',
             active === t.id ? 'text-ink-950' : 'text-ink-500 hover:text-ink-800')}>
          {active === t.id && (
            <motion.span layout={reducedMotion ? undefined : true} layoutId={reducedMotion ? undefined : `tab-pill-${groupId}`}
              transition={reducedMotion ? undefined : springSnappy}
               className="absolute inset-0 rounded-lg bg-surface-panel shadow-xs" />
          )}
          <span className="relative z-10">{t.label}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-200 text-left text-xs uppercase tracking-wide text-ink-500">
            {head.map((h, i) => <th key={i} className="px-4 py-3 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">{children}</tbody>
      </table>
    </div>
  );
}
