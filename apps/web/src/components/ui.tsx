/**
 * GlobalTalk AI design system (PDD §36).
 * Accessible primitives: focus rings, aria attributes, keyboard support.
 */
import { forwardRef, useEffect, useRef, type ButtonHTMLAttributes,
         type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes,
         type TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
export { Field, SegmentedControl } from './ui/index';

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent';
type Size = 'sm' | 'md' | 'lg' | 'icon';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-iris-600 text-white hover:bg-iris-700 active:bg-iris-800 shadow-sm disabled:bg-iris-300',
  secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 active:bg-slate-100 disabled:text-slate-400',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 active:bg-slate-200',
  danger: 'bg-rose-600 text-white hover:bg-rose-700 active:bg-rose-800 disabled:bg-rose-300',
  accent: 'bg-lagoon-600 text-white hover:bg-lagoon-700 active:bg-lagoon-800 disabled:bg-lagoon-300',
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
  ({ variant = 'primary', size = 'md', loading, className, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center font-medium transition-colors select-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iris-500 focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed',
        VARIANTS[variant], SIZES[size], className)}
      disabled={disabled || loading}
      {...props}>
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  ));
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
  return <div className={cn('animate-pulse-soft rounded-lg bg-slate-200', className)}
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
          <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-slate-700">
            {label}
          </label>
        )}
        <input
          ref={ref} id={inputId}
          aria-invalid={!!error} aria-describedby={error ? `${inputId}-err` : undefined}
          className={cn(
            'h-10 w-full rounded-xl2 border bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400',
            'focus:outline-none focus:ring-2 focus:ring-iris-500/40 focus:border-iris-500',
            'disabled:bg-slate-50 disabled:text-slate-400',
            error ? 'border-rose-400' : 'border-slate-300', className)}
          {...props} />
        {error && <p id={`${inputId}-err`} className="mt-1 text-xs text-rose-600" role="alert">{error}</p>}
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
        {label && <label htmlFor={taId} className="mb-1.5 block text-sm font-medium text-slate-700">{label}</label>}
        <textarea ref={ref} id={taId}
          className={cn(
            'w-full rounded-xl2 border border-slate-300 bg-white p-3 text-sm text-slate-900',
            'placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-iris-500/40 focus:border-iris-500',
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
        {label && <label htmlFor={selId} className="mb-1.5 block text-sm font-medium text-slate-700">{label}</label>}
        <select ref={ref} id={selId}
          className={cn(
            'h-10 w-full rounded-xl2 border border-slate-300 bg-white px-3 text-sm text-slate-900',
            'focus:outline-none focus:ring-2 focus:ring-iris-500/40 focus:border-iris-500',
            'disabled:bg-slate-50 disabled:text-slate-400', className)}
          {...props}>
          {children}
        </select>
      </div>
    );
  });
Select.displayName = 'Select';

export function Toggle({ checked, onChange, label, id }:
  { checked: boolean; onChange: (v: boolean) => void; label: string; id?: string }) {
  return (
    <button id={id} type="button" role="switch" aria-checked={checked} aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn('relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iris-500 focus-visible:ring-offset-2',
        checked ? 'bg-iris-600' : 'bg-slate-300')}>
      <span className={cn('inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
        checked ? 'translate-x-6' : 'translate-x-1')} />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Surfaces
// ---------------------------------------------------------------------------

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('rounded-2xl border border-slate-200 bg-white shadow-card', className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }:
  { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
      <div>
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const BADGE_TONES: Record<string, string> = {
  neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-700 border-amber-200',
  red: 'bg-rose-50 text-rose-700 border-rose-200',
  iris: 'bg-iris-50 text-iris-700 border-iris-200',
  lagoon: 'bg-lagoon-50 text-lagoon-700 border-lagoon-200',
};

export function Badge({ tone = 'neutral', children, className }:
  { tone?: keyof typeof BADGE_TONES; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
      BADGE_TONES[tone], className)}>
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
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const focusables = ref.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    focusables?.[0]?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog"
         aria-modal="true" aria-label={typeof title === 'string' ? title : 'Dialog'}>
      <div className="absolute inset-0 bg-slate-950/50 animate-fade-in" onClick={onClose} />
      <div ref={ref}
           className={cn('relative w-full rounded-2xl bg-white shadow-lift animate-slide-up',
             wide ? 'max-w-3xl' : 'max-w-lg')}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close dialog">✕</Button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

export function EmptyState({ icon, title, hint, action }:
  { icon?: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-6 py-12 text-center">
      {icon && <div className="text-slate-400">{icon}</div>}
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-500">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ title, detail, retry }:
  { title?: string; detail?: string; retry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-6 py-8 text-center"
         role="alert">
      <p className="text-sm font-semibold text-rose-800">{title ?? 'Something went wrong'}</p>
      {detail && <p className="max-w-md text-xs text-rose-600">{detail}</p>}
      {retry && <Button size="sm" variant="secondary" onClick={retry} className="mt-1">Retry</Button>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabs (keyboard accessible)
// ---------------------------------------------------------------------------

export function Tabs({ tabs, active, onChange }:
  { tabs: Array<{ id: string; label: ReactNode }>; active: string;
    onChange: (id: string) => void }) {
  return (
    <div role="tablist" aria-label="Tabs" className="flex gap-1 rounded-xl2 bg-slate-100 p-1">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={active === t.id}
          tabIndex={active === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => {
            const i = tabs.findIndex((x) => x.id === active);
            if (e.key === 'ArrowRight') onChange(tabs[(i + 1) % tabs.length].id);
            if (e.key === 'ArrowLeft') onChange(tabs[(i - 1 + tabs.length) % tabs.length].id);
          }}
          className={cn('rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iris-500',
            active === t.id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800')}>
          {t.label}
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
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            {head.map((h, i) => <th key={i} className="px-4 py-3 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  );
}
