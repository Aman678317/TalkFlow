/** Toast store — accessible status announcements (PDD §36). */
import { create } from 'zustand';

export type ToastKind = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  detail?: string;
}

export type ToastArg =
  | { kind: ToastKind; title: string; body?: string; detail?: string }
  | ToastKind;

interface ToastState {
  toasts: Toast[];
  push: (kindOrObj: ToastArg, title?: string, detail?: string) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push(kindOrObj, title, detail) {
    let kind: ToastKind = 'info';
    let t = '';
    let d: string | undefined = undefined;

    if (typeof kindOrObj === 'object' && kindOrObj !== null) {
      kind = kindOrObj.kind;
      t = kindOrObj.title;
      d = kindOrObj.body ?? kindOrObj.detail;
    } else {
      kind = kindOrObj as ToastKind;
      t = title ?? '';
      d = detail;
    }

    const id = nextId++;
    set((s) => {
      const exists = s.toasts.some((existing) => existing.title === t && existing.detail === d && existing.kind === kind);
      if (exists) return s;
      return { toasts: [...s.toasts, { id, kind, title: t, detail: d }] };
    });
    setTimeout(
      () => set((s) => ({ toasts: s.toasts.filter((toastItem) => toastItem.id !== id) })),
      kind === 'error' ? 8000 : 4500
    );
  },
  dismiss(id) {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  },
}));

export const toast = {
  success: (title: string, detail?: string) => useToasts.getState().push('success', title, detail),
  error: (title: string, detail?: string) => useToasts.getState().push('error', title, detail),
  info: (title: string, detail?: string) => useToasts.getState().push('info', title, detail),
  warning: (title: string, detail?: string) => useToasts.getState().push('warning', title, detail),
};
