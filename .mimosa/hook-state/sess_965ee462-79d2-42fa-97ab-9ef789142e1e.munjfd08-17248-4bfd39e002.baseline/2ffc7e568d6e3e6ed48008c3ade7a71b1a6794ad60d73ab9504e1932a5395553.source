import { create } from "zustand";

export interface Toast {
  id: number;
  kind: "info" | "success" | "warn" | "error";
  title: string;
  body?: string;
  /** human-readable recovery guidance for realtime issues (section 37) */
}

interface ToastState {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    window.setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
      t.kind === "error" ? 9000 : 5000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

export function ToastHost() {
  const { toasts, dismiss } = useToasts();
  const tones = {
    info: "border-ink-200 bg-white",
    success: "border-signal-200 bg-signal-50",
    warn: "border-amber-200 bg-amber-50",
    error: "border-red-200 bg-red-50",
  };
  const icons = { info: "ℹ", success: "✓", warn: "⚠", error: "✕" };
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2"
         aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id}
             className={`pointer-events-auto rounded-lg border p-3 shadow-pop ${tones[t.kind]}`}>
          <div className="flex items-start gap-2">
            <span aria-hidden className="mt-0.5 text-sm">{icons[t.kind]}</span>
            <div className="flex-1">
              <p className="text-sm font-medium text-ink-900">{t.title}</p>
              {t.body && <p className="mt-0.5 text-xs text-ink-500">{t.body}</p>}
            </div>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss notification"
                    className="text-ink-400 hover:text-ink-700">✕</button>
          </div>
        </div>
      ))}
    </div>
  );
}
