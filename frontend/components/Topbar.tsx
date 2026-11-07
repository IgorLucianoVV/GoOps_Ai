"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { ChevronRight, Menu, Moon, Search, Sparkles, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { breadcrumbFor } from "./nav";

/** Barra superior: onde estou (breadcrumb — H1/H6), busca rápida (H7) e preferência de tema. */
export default function Topbar({ onMenu, onSearch }: { onMenu: () => void; onSearch: () => void }) {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const crumb = breadcrumbFor(pathname);
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-ink-700 bg-ink-900/90 px-4 backdrop-blur sm:px-8">
      <button aria-label="Abrir menu" className="btn-ghost lg:hidden" onClick={onMenu}><Menu size={16} aria-hidden /></button>
      <nav aria-label="Você está em" className="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
        <span className="text-slate-500">GoOps AI</span>
        {crumb.section && <><ChevronRight size={14} className="text-slate-600" aria-hidden /><span className={crumb.page ? "text-slate-500" : "font-medium text-white"}>{crumb.section}</span></>}
        {crumb.page && <><ChevronRight size={14} className="text-slate-600" aria-hidden /><span className="truncate font-medium text-white" aria-current="page">{crumb.page}</span></>}
      </nav>
      <button onClick={onSearch} className="btn-ghost hidden h-9 w-60 justify-start text-slate-500 md:inline-flex" aria-keyshortcuts="Control+K Meta+K">
        <Search size={15} aria-hidden /><span className="flex-1 text-left">Buscar…</span>
        <kbd className="rounded border border-ink-600 px-1.5 text-[11px]">Ctrl K</kbd>
      </button>
      <button onClick={onSearch} className="btn-ghost md:hidden" aria-label="Buscar"><Search size={16} aria-hidden /></button>
      {pathname !== "/ask" && <Link href="/ask" className="btn-accent hidden sm:inline-flex"><Sparkles size={15} aria-hidden /> Perguntar</Link>}
      <button onClick={toggle} className="btn-ghost" aria-label={theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"} title="Alternar tema">
        {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
      </button>
    </header>
  );
}
