"use client";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, Moon, Search, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { flatNav } from "./nav";

type Entry = { id: string; label: string; hint?: string; section: string; run: () => void };

/** Paleta de comandos (Ctrl/⌘ + K): atalho para usuários experientes sem esconder a navegação (Heurística 7). */
export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { theme, toggle } = useTheme();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const entries: Entry[] = useMemo(() => [
    ...flatNav().map((n) => ({ id: n.href, label: n.label, hint: n.hint, section: n.section === n.label ? "Páginas" : n.section,
      run: () => router.push(n.href) })),
    { id: "theme", label: theme === "dark" ? "Usar tema claro" : "Usar tema escuro", section: "Preferências", run: toggle },
  ], [router, theme, toggle]);
  const norm = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const filtered = entries.filter((e) => !q || norm(`${e.label} ${e.hint || ""} ${e.section}`).includes(norm(q)));

  useEffect(() => { if (open) { setQ(""); setIdx(0); setTimeout(() => inputRef.current?.focus(), 0); } }, [open]);
  useEffect(() => { setIdx(0); }, [q]);
  if (!open) return null;

  const choose = (e?: Entry) => { if (!e) return; onClose(); e.run(); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(filtered[idx]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  return (
    <div className="fixed inset-0 z-[75] bg-black/50 p-4 pt-[12vh]" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label="Paleta de comandos" className="mx-auto w-full max-w-xl overflow-hidden rounded-xl border border-ink-600 bg-ink-900 shadow-2xl">
        <div className="flex items-center gap-2 border-b border-ink-700 px-4">
          <Search size={16} className="text-slate-500" aria-hidden />
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            role="combobox" aria-expanded="true" aria-controls="cmd-list" aria-activedescendant={filtered[idx] ? `cmd-${idx}` : undefined}
            placeholder="Ir para página ou ação…" className="h-12 flex-1 bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500" aria-label="Buscar páginas e ações" />
          <kbd className="rounded border border-ink-600 px-1.5 text-[11px] text-slate-500">Esc</kbd>
        </div>
        <ul id="cmd-list" role="listbox" className="max-h-80 overflow-y-auto p-2">
          {filtered.length === 0 && <li className="p-4 text-center text-sm text-slate-500">Nada encontrado para “{q}”.</li>}
          {filtered.map((e, i) => (
            <li key={e.id} id={`cmd-${i}`} role="option" aria-selected={i === idx} onMouseEnter={() => setIdx(i)} onClick={() => choose(e)}
              className={clsx("flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm", i === idx ? "bg-ink-800 text-white" : "text-slate-300")}>
              {e.id === "theme" ? (theme === "dark" ? <Sun size={15} aria-hidden /> : <Moon size={15} aria-hidden />) : <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-coral-500" />}
              <span className="flex-1"><span className="font-medium">{e.label}</span>{e.hint && <span className="ml-2 text-xs text-slate-500">{e.hint}</span>}</span>
              <span className="text-[11px] text-slate-500">{e.section}</span>
              {i === idx && <CornerDownLeft size={13} className="text-slate-500" aria-hidden />}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
