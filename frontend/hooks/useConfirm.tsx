"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

interface ConfirmOptions { title: string; description?: string; confirmLabel?: string; cancelLabel?: string; tone?: "danger" | "primary"; }
const ConfirmContext = createContext<(o: ConfirmOptions) => Promise<boolean>>(async () => false);

/** Diálogo de confirmação acessível (Heurísticas 3 e 5 — controle do usuário e prevenção de erros):
 *  foco inicial em "Cancelar", Esc fecha, foco preso no diálogo e devolvido ao elemento de origem. */
export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<(v: boolean) => void>(() => {});
  const previous = useRef<Element | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const confirm = useCallback((o: ConfirmOptions) => {
    previous.current = document.activeElement;
    setOpts(o);
    return new Promise<boolean>((resolve) => { resolver.current = resolve; });
  }, []);
  const close = (v: boolean) => {
    setOpts(null);
    resolver.current(v);
    const el = previous.current as HTMLElement | null;
    if (el && typeof el.focus === "function") setTimeout(() => el.focus(), 0);
  };
  useEffect(() => {
    if (!opts) return;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(false);
      if (e.key === "Tab" && dialogRef.current) {
        const f = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button"));
        if (f.length === 0) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [opts]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {opts && (
        <div className="fixed inset-0 z-[80] grid place-items-center bg-black/50 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) close(false); }}>
          <div ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-desc"
            className="w-full max-w-md rounded-xl border border-ink-600 bg-ink-900 p-5 shadow-2xl">
            <div className="flex items-start gap-3">
              {opts.tone === "danger" && <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-rose-950 text-rose-300"><AlertTriangle size={18} aria-hidden /></span>}
              <div>
                <h2 id="confirm-title" className="text-base font-semibold text-white">{opts.title}</h2>
                {opts.description && <p id="confirm-desc" className="mt-1 text-sm text-slate-400">{opts.description}</p>}
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button ref={cancelRef} className="btn-ghost" onClick={() => close(false)}>{opts.cancelLabel || "Cancelar"}</button>
              <button className={opts.tone === "danger" ? "btn bg-rose-700 text-[#FFFFFF] hover:bg-rose-500" : "btn-primary"} onClick={() => close(true)}>{opts.confirmLabel || "Confirmar"}</button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmContext);
