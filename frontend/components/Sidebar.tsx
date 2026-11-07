"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { NAV } from "./nav";

/** Barra lateral neutra (segue o tema), grupos recolhíveis (divulgação progressiva) e item ativo sinalizado
 *  por cor, peso e marcador — não apenas por cor (WCAG 1.4.1). */
export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const isActive = (href: string) => {
    const base = href.split("?")[0];
    return base === "/" ? pathname === "/" : pathname === base || pathname.startsWith(base + "/");
  };
  const activeGroup = NAV.find((s) => s.items?.some((i) => isActive(i.href)))?.label;
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => { if (activeGroup) setOpen((o) => ({ ...o, [activeGroup]: true })); }, [activeGroup]);

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-ink-700 bg-ink-900 text-slate-400">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span aria-hidden className="relative h-9 w-9 overflow-hidden rounded-xl bg-accent-400">
          <span className="absolute -right-2.5 -top-2.5 h-6 w-6 rounded-full bg-coral-400" />
          <span className="absolute bottom-1.5 left-1.5 h-3.5 w-3.5 rotate-45 rounded-[3px] bg-navy-900" />
        </span>
        <div>
          <div className="text-[15px] font-semibold text-white">GoOps AI</div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Operational Intelligence</div>
        </div>
      </div>
      <nav aria-label="Navegação principal" className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        {NAV.map((s) => {
          const Icon = s.icon;
          if (s.href) {
            const active = isActive(s.href);
            return (
              <Link key={s.label} href={s.href} aria-current={active ? "page" : undefined}
                className={clsx("relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm",
                  active ? "bg-ink-800 font-semibold text-white" : "hover:bg-ink-800 hover:text-white")}>
                {active && <span aria-hidden className="absolute left-0 top-1.5 h-6 w-1 rounded-r bg-coral-500" />}
                <Icon size={17} aria-hidden />{s.label}
              </Link>
            );
          }
          const isOpen = !!open[s.label];
          const groupActive = activeGroup === s.label;
          return (
            <div key={s.label}>
              <button type="button" aria-expanded={isOpen} onClick={() => setOpen({ ...open, [s.label]: !isOpen })}
                className={clsx("flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm hover:bg-ink-800 hover:text-white",
                  groupActive && "text-white")}>
                <Icon size={17} aria-hidden /><span className="flex-1">{s.label}</span>
                <ChevronDown size={15} aria-hidden className={clsx("transition-transform", isOpen && "rotate-180")} />
              </button>
              {isOpen && (
                <div className="mb-1 ml-[22px] border-l border-ink-700 pl-2">
                  {s.items!.map((it, _i, all) => {
                    // só o item mais específico do grupo fica ativo (ex.: /atendimento × /atendimento/caixa)
                    const best = all.filter((x) => !x.href.includes("?") && isActive(x.href)).sort((a, b) => b.href.length - a.href.length)[0];
                    const active = best?.href === it.href;
                    return (
                      <Link key={it.href} href={it.href} aria-current={active ? "page" : undefined}
                        className={clsx("block rounded-md px-2.5 py-1.5 text-[13px]",
                          active ? "bg-ink-800 font-semibold text-white" : "hover:bg-ink-800 hover:text-white")}>
                        {it.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      {user && (
        <div className="border-t border-ink-700 p-4">
          <div className="truncate text-sm font-medium text-white">{user.name}</div>
          <div className="text-xs text-slate-500">{user.role_label} · {user.domains.join(", ")}</div>
          <button onClick={() => logout()} className="mt-2 inline-flex items-center gap-1.5 rounded text-xs text-slate-400 hover:text-white"><LogOut size={13} aria-hidden /> Sair</button>
        </div>
      )}
    </aside>
  );
}
