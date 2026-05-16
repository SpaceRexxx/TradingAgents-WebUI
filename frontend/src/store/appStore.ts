import { create } from "zustand";

interface Toast { id: number; kind: "ok" | "err"; text: string; }

interface AppState {
  toasts: Toast[];
  pushToast: (kind: "ok" | "err", text: string) => void;
  dismissToast: (id: number) => void;
  activeRunId: string | null;
  setActiveRunId: (id: string | null) => void;
}

let toastSeq = 1;

export const useAppStore = create<AppState>((set) => ({
  toasts: [],
  pushToast: (kind, text) => set((s) => ({ toasts: [...s.toasts, { id: toastSeq++, kind, text }] })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  activeRunId: null,
  setActiveRunId: (id) => set({ activeRunId: id }),
}));
