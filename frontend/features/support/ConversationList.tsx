"use client";
import clsx from "clsx";
import { Repeat2, Search } from "lucide-react";
import { fmt } from "@/components/labels";
import { CHANNEL, URGENCY } from "./common";

function when(v?: string | null) {
  if (!v) return "";
  const d = new Date(v);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Lista de conversas (uma por cliente e canal), como a coluna de chats do WhatsApp. */
export default function ConversationList({ items, total, selected, onSelect, queue, setQueue, q, setQ, channel, setChannel, loading }:
  { items: any[]; total: number; selected?: string | null; onSelect: (id: string) => void; queue: string; setQueue: (v: string) => void;
    q: string; setQ: (v: string) => void; channel: string; setChannel: (v: string) => void; loading?: boolean }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-ink-700 p-3">
        <div role="tablist" aria-label="Fila" className="flex overflow-hidden rounded-md border border-ink-700 text-sm">
          {[["open", "Em aberto"], ["all", "Todas"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={queue === k} onClick={() => setQueue(k)}
              className={clsx("flex-1 px-3 py-1.5", queue === k ? "bg-brand-600 text-white" : "text-slate-300 hover:bg-ink-800")}>{l}</button>
          ))}
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" aria-hidden />
          <input aria-label="Buscar conversas" className="input w-full !pl-8" placeholder="Cliente, pedido ou texto…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-1">
          {[["", "Todos"], ...Object.entries(CHANNEL).map(([k, v]) => [k, v.label])].map(([k, l]) => (
            <button key={k} onClick={() => setChannel(k)} className={clsx("whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px]",
              channel === k ? "border-brand-500 bg-brand-500/15 text-brand-300" : "border-ink-600 text-slate-400 hover:text-slate-200")}>{l}</button>
          ))}
        </div>
        <div className="text-[11px] text-slate-500">{fmt.num(total)} conversa(s){loading ? " · atualizando…" : ""}</div>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto" aria-label="Conversas">
        {items.length === 0 && <li className="p-6 text-center text-sm text-slate-500">{queue === "open" ? "Nenhuma conversa aguardando. 🎉" : "Nenhuma conversa encontrada."}</li>}
        {items.map((c) => {
          const ch = CHANNEL[c.channel];
          const Icon = ch?.icon;
          const u = c.urgency ? URGENCY[c.urgency] : null;
          return (
            <li key={c.id}>
              <button onClick={() => onSelect(c.id)} aria-current={selected === c.id ? "true" : undefined}
                className={clsx("flex w-full gap-3 border-b border-ink-800 px-3 py-2.5 text-left hover:bg-ink-800/60", selected === c.id && "bg-ink-800")}>
                <span className={clsx("mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full",
                  c.channel === "whatsapp" ? "bg-emerald-500/15 text-emerald-300" : c.channel === "email" ? "bg-sky-500/15 text-sky-300" : "bg-rose-500/15 text-rose-300")}>
                  {Icon && <Icon size={16} aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-medium text-slate-100">{c.display_name}</span>
                    <span className="shrink-0 text-[10px] text-slate-500">{when(c.last_message_at)}</span>
                  </span>
                  <span className="block truncate text-[11px] text-slate-500">{c.handle_display}{c.intent_label ? ` · ${c.intent_label}` : ""}</span>
                  <span className="mt-0.5 flex items-center gap-2">
                    <span className={clsx("line-clamp-1 flex-1 text-xs", c.unread ? "text-slate-200" : "text-slate-400")}>
                      {c.last_author_type === "customer" ? "" : c.last_author_type === "bot" ? "🤖 " : c.last_author_type === "human" ? "Você: " : ""}{c.last_message_preview}
                    </span>
                    {!!c.is_repeat && <Repeat2 size={12} className="text-amber-300" aria-label="recontato" />}
                    {u && c.status === "open" && (c.urgency === "critica" || c.urgency === "alta") &&
                      <span className={clsx("h-2 w-2 rounded-full", c.urgency === "critica" ? "bg-rose-400" : "bg-amber-400")} title={`urgência ${u.label}`} />}
                    {c.unread > 0 && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-emerald-500 px-1.5 text-[10px] font-semibold text-ink-950">{c.unread}</span>}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
