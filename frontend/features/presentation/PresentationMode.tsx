"use client";
import clsx from "clsx";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Mic, Play, Presentation, X } from "lucide-react";
import { ApiError } from "@/services/api";
import { emitRefresh, emitTourTab } from "./events";
import { STEPS, type LiveFigure, type TourCtx } from "./steps";

/** Modo apresentação: tour guiado pelas páginas reais do GoOps para o pitch.
 *  Estado na sessionStorage (sobrevive à navegação); teclado: → avança, ← volta, Esc sai. */
interface Ctx { active: boolean; index: number; start: (i?: number) => void; stop: () => void; go: (i: number) => void }
const PresentationCtx = createContext<Ctx>({ active: false, index: 0, start: () => {}, stop: () => {}, go: () => {} });
export const usePresentation = () => useContext(PresentationCtx);

const KEY = "goops:presentation";
function load(): { active: boolean; index: number } {
  try { const v = JSON.parse(sessionStorage.getItem(KEY) || "null"); if (v && typeof v.index === "number") return v; } catch { /* sem storage */ }
  return { active: false, index: 0 };
}
function save(v: { active: boolean; index: number }) { try { sessionStorage.setItem(KEY, JSON.stringify(v)); } catch { /* sem storage */ } }

export function PresentationProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState({ active: false, index: 0 });
  useEffect(() => { setState(load()); }, []);
  const set = useCallback((v: { active: boolean; index: number }) => { setState(v); save(v); }, []);
  const value = useMemo<Ctx>(() => ({
    active: state.active, index: state.index,
    start: (i = 0) => set({ active: true, index: i }),
    stop: () => set({ active: false, index: state.index }),
    go: (i: number) => set({ active: true, index: Math.max(0, Math.min(STEPS.length - 1, i)) }),
  }), [state, set]);
  return <PresentationCtx.Provider value={value}>{children}{state.active && <PresentationOverlay />}</PresentationCtx.Provider>;
}

/** Botão da barra superior. */
export function PresentationButton() {
  const { active, start, stop } = usePresentation();
  return (
    <button className={clsx("btn-ghost", active && "border-brand-500 text-brand-300")} onClick={() => (active ? stop() : start(0))}
      aria-pressed={active} title={active ? "Sair do modo apresentação" : "Modo apresentação (tour do pitch)"}>
      <Presentation size={16} aria-hidden /><span className="hidden xl:inline">{active ? "Sair da apresentação" : "Apresentar"}</span>
    </button>
  );
}

function visible(el: Element) { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
function findTarget(name: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`));
  return all.find(visible) || null;
}

/** Escolhe o canto da tela onde o cartão menos cobre o elemento destacado. */
function placeCard(rect: DOMRect | null, el: HTMLDivElement | null, pad: number): React.CSSProperties {
  if (typeof window === "undefined") return { right: 16, bottom: 16 };
  const W = window.innerWidth, H = window.innerHeight, m = 16;
  if (W < 640) return { left: m, bottom: m };
  const cw = Math.min(400, W - 2 * m), ch = el?.offsetHeight || 360;
  const spots = [
    { left: W - cw - m, top: H - ch - m }, { left: m, top: H - ch - m },
    { left: W - cw - m, top: 72 }, { left: m, top: 72 },
  ];
  if (!rect) return spots[0];
  const r = { l: rect.left - pad, t: rect.top - pad, r: rect.right + pad, b: rect.bottom + pad };
  const overlap = (s: { left: number; top: number }) =>
    Math.max(0, Math.min(r.r, s.left + cw) - Math.max(r.l, s.left)) * Math.max(0, Math.min(r.b, s.top + ch) - Math.max(r.t, s.top));
  return spots.reduce((best, s) => (overlap(s) < overlap(best) ? s : best), spots[0]);
}

function PresentationOverlay() {
  const { index, go, stop } = usePresentation();
  const router = useRouter();
  const pathname = usePathname();
  const step = STEPS[index];
  const ctx = useRef<TourCtx>({ cache: {} });
  const [path, setPath] = useState<string | null>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [live, setLive] = useState<LiveFigure[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [notes, setNotes] = useState(true);
  const [missing, setMissing] = useState(false);
  const card = useRef<HTMLDivElement>(null);

  // 1) resolve a rota da etapa e navega
  useEffect(() => {
    let alive = true;
    setRect(null); setLive(null); setResult(null); setPath(null); setMissing(false);
    (async () => {
      let p = "/atendimento";
      try { p = typeof step.path === "string" ? step.path : await step.path(ctx.current); } catch { /* fica na rota padrão */ }
      if (!alive) return;
      setPath(p);
      const cur = window.location.pathname + window.location.search;
      if (cur !== p && pathname + window.location.search !== p) router.push(p);
    })();
    return () => { alive = false; };
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  // 2) números ao vivo
  useEffect(() => {
    let alive = true;
    if (step.live) step.live(ctx.current).then((v) => { if (alive) setLive(v); }).catch(() => { if (alive) setLive([]); });
    return () => { alive = false; };
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  // 3) espera o elemento, abre a aba pedida e acompanha a posição
  useEffect(() => {
    if (!path || !step.target) return;
    let el: HTMLElement | null = null;
    let tabSent = false;
    const started = Date.now();
    const tick = () => {
      el = findTarget(step.target!);
      // pede a aba até o alvo aparecer (o alvo pode estar dentro da aba) e uma vez depois de encontrá-lo
      if (step.tab && (!el || !tabSent)) { if (el) tabSent = true; emitTourTab(step.tab); }
      if (el) { setRect(el.getBoundingClientRect()); setMissing(false); }
      else if (Date.now() - started > 8000) { setRect(null); setMissing(true); }
    };
    const first = window.setInterval(() => {
      tick();
      if (el) { window.clearInterval(first); el.scrollIntoView({ block: el.getBoundingClientRect().height > window.innerHeight * 0.7 ? "start" : "center", behavior: "smooth" }); }
    }, 150);
    const follow = window.setInterval(tick, 300);
    window.addEventListener("resize", tick);
    return () => { window.clearInterval(first); window.clearInterval(follow); window.removeEventListener("resize", tick); };
  }, [path, index]); // eslint-disable-line react-hooks/exhaustive-deps

  // teclado
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); go(index + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); go(index - 1); }
      else if (e.key === "Escape") stop();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [index, go, stop]);

  const runAction = async () => {
    if (!step.action) return;
    setBusy(true); setResult(null);
    try {
      const text = await step.action.run(ctx.current);
      setResult({ ok: true, text });
      ctx.current.cache = {}; // dados mudaram: a próxima etapa busca de novo
      emitRefresh();
      if (step.live) step.live(ctx.current).then(setLive).catch(() => {});
    } catch (e) {
      setResult({ ok: false, text: (e as ApiError)?.message || "Não foi possível concluir a ação." });
    } finally { setBusy(false); }
  };

  const center = step.placement === "center";
  const last = index === STEPS.length - 1;
  const pad = 8;
  const pos = placeCard(rect, card.current, pad);

  return (
    <>
      {center && <div className="fixed inset-0 z-[70] bg-ink-950/70 backdrop-blur-[2px]" aria-hidden />}
      {!center && rect && (
        <div aria-hidden className="pointer-events-none fixed z-[70] rounded-xl ring-2 ring-brand-400 transition-all duration-300"
          style={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2,
            boxShadow: "0 0 0 9999px rgba(5, 10, 20, 0.55)" }} />
      )}
      <div ref={card} role="dialog" aria-modal="false" aria-labelledby="tour-title" style={center ? undefined : pos}
        className={clsx("fixed z-[80] w-[calc(100%-2rem)] rounded-2xl border border-ink-600 bg-ink-900 p-5 shadow-2xl transition-[left,top] duration-300",
          center ? "left-1/2 top-1/2 max-w-xl -translate-x-1/2 -translate-y-1/2" : "max-w-[400px]")}>
        <div className="mb-2 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-brand-300">
            <Presentation size={12} aria-hidden /> {step.kicker}</span>
          <span className="flex-1" />
          <span className="text-[11px] text-slate-500">{index + 1} / {STEPS.length}</span>
          <button className="rounded p-1 text-slate-400 hover:bg-ink-800 hover:text-white" onClick={stop} aria-label="Sair do modo apresentação"><X size={15} /></button>
        </div>
        <h2 id="tour-title" className={clsx("font-semibold text-white", center ? "text-2xl leading-tight" : "text-base")}>{step.title}</h2>
        <p className={clsx("mt-2 text-slate-300", center ? "text-base" : "text-sm")}>{step.text}</p>
        {!!step.bullets?.length && (
          <ul className={clsx("mt-3 space-y-1.5", center ? "text-sm" : "text-[13px]")}>
            {step.bullets.map((b) => <li key={b} className="flex gap-2 text-slate-200"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" />{b}</li>)}
          </ul>
        )}
        {step.live && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {live === null && <span className="col-span-full text-xs text-slate-500">Buscando números…</span>}
            {live?.length === 0 && <span className="col-span-full text-xs text-slate-500">Sem dados ainda — rode o pipeline ou a ação desta etapa.</span>}
            {live?.map((f) => (
              <div key={f.label} className="rounded-lg border border-ink-700 bg-ink-850 px-2.5 py-2">
                <div className="text-[10px] uppercase tracking-wide text-slate-500">{f.label}</div>
                <div className="text-lg font-semibold text-white">{f.value}</div>
                {f.hint && <div className="truncate text-[10px] text-slate-500">{f.hint}</div>}
              </div>
            ))}
            {!!live?.length && <span className="col-span-full text-[10px] text-slate-500">Dados sintéticos de demonstração · calculados agora</span>}
          </div>
        )}
        {step.action && (
          <div className="mt-3 rounded-lg border border-ink-700 bg-ink-850 p-3">
            <button className="btn-primary w-full justify-center" disabled={busy} onClick={runAction}>
              <Play size={14} aria-hidden /> {busy ? "Executando…" : step.action.label}</button>
            {step.action.hint && !result && <p className="mt-1.5 text-center text-[11px] text-slate-500">{step.action.hint}</p>}
            {result && <p role="status" className={clsx("mt-2 text-xs", result.ok ? "text-emerald-300" : "text-amber-300")}>{result.text}</p>}
          </div>
        )}
        {step.say && notes && (
          <p className="mt-3 flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            <Mic size={13} className="mt-0.5 shrink-0 text-amber-300" aria-hidden /><span><b className="text-amber-300">Fala sugerida:</b> {step.say}</span></p>
        )}
        {!center && step.target && !rect && path && <p className="mt-2 text-[11px] text-slate-500">{missing ? "Este trecho não está na tela agora (faltam dados ou permissão)." : "Carregando a tela…"}</p>}
        <div className="mt-4 flex items-center gap-2">
          <button className="btn-ghost" disabled={index === 0} onClick={() => go(index - 1)} aria-label="Etapa anterior"><ChevronLeft size={15} /></button>
          <div className="flex flex-1 justify-center gap-1" aria-hidden>
            {STEPS.map((s, i) => (
              <button key={s.id} tabIndex={-1} onClick={() => go(i)} title={s.title}
                className={clsx("h-1.5 rounded-full transition-all", i === index ? "w-5 bg-brand-400" : "w-1.5 bg-ink-600 hover:bg-slate-500")} />
            ))}
          </div>
          <button className={clsx("rounded p-1.5 hover:bg-ink-800", notes ? "text-amber-300" : "text-slate-500")} onClick={() => setNotes(!notes)}
            aria-pressed={notes} aria-label="Mostrar ou ocultar a fala sugerida" title={notes ? "Ocultar a fala sugerida" : "Mostrar a fala sugerida"}><Mic size={15} /></button>
          {last
            ? <button className="btn-primary" onClick={stop}>Encerrar</button>
            : <button className="btn-primary" onClick={() => go(index + 1)}>Próximo <ChevronRight size={15} aria-hidden /></button>}
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-600">← → navegam · Esc sai</p>
      </div>
    </>
  );
}
