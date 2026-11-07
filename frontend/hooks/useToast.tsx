"use client";
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import clsx from "clsx";

type Tone = "success" | "error" | "info";
interface Toast { id: number; tone: Tone; title: string; description?: string; }
interface ToastApi { push: (t: Omit<Toast, "id">) => void; }

const ToastContext = createContext<ToastApi>({ push: () => {} });

/** Feedback imediato e não bloqueante (Heurística 1 — visibilidade do estado do sistema). Anunciado por leitores de tela. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const seq = useRef(0);
  const dismiss = (id: number) => setItems((all) => all.filter((t) => t.id !== id));
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = ++seq.current;
    setItems((all) => [...all.slice(-3), { ...t, id }]);
    setTimeout(() => dismiss(id), t.tone === "error" ? 9000 : 5000);
  }, []);
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => {
          const Icon = t.tone === "success" ? CheckCircle2 : t.tone === "error" ? AlertTriangle : Info;
          return (
            <div key={t.id} role={t.tone === "error" ? "alert" : "status"}
              className={clsx("pointer-events-auto flex items-start gap-3 rounded-xl border bg-ink-900 p-3 shadow-lg",
                t.tone === "success" ? "border-emerald-500/40" : t.tone === "error" ? "border-rose-500/50" : "border-brand-500/40")}>
              <Icon size={18} className={clsx("mt-0.5 shrink-0", t.tone === "success" ? "text-emerald-300" : t.tone === "error" ? "text-rose-300" : "text-brand-400")} aria-hidden />
              <div className="flex-1 text-sm"><div className="font-medium text-white">{t.title}</div>{t.description && <div className="mt-0.5 text-slate-400">{t.description}</div>}</div>
              <button className="rounded p-1 text-slate-500 hover:text-slate-200" aria-label="Fechar notificação" onClick={() => dismiss(t.id)}><X size={14} /></button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
