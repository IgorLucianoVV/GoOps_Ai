"use client";
import clsx from "clsx";
import { Fragment, useEffect, useRef, useState } from "react";
import { Bot, CheckCircle2, Clock, Image as ImageIcon, Lock, Send, StickyNote, Wand2 } from "lucide-react";
import { Badge } from "@/components/ui";
import { ChannelBadge, SupportStatusBadge } from "./common";

const hhmm = (v: string) => new Date(v).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const day = (v: string) => new Date(v).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });

/** Conversa no formato WhatsApp: cliente à esquerda; robô e atendente à direita; sistema e notas ao centro;
 *  um divisor marca o início de cada atendimento dentro da mesma conversa. */
export default function ChatThread({ conv, selectedCase, onSelectCase, canWrite, suggestion, busy, onSend, onNote, onAi, onClose }:
  { conv: any; selectedCase?: string | null; onSelectCase: (id: string) => void; canWrite: boolean; suggestion?: string;
    busy?: boolean; onSend: (text: string) => void; onNote: (text: string) => void; onAi: () => Promise<string | null>;
    onClose: () => void }) {
  const end = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [note, setNote] = useState(false);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [conv?.id, conv?.messages?.length]);
  useEffect(() => { setText(suggestion || ""); setNote(false); }, [conv?.id, suggestion]);
  const caseById: Record<string, any> = Object.fromEntries((conv.cases || []).map((k: any) => [k.id, k]));
  const openCase = (conv.cases || []).find((k: any) => k.id === conv.current_case_id && ["pending_human", "pending_approval", "awaiting_customer"].includes(k.status));
  const win = conv.whatsapp_window;
  const submit = () => {
    const t = text.trim();
    if (busy) return;
    if (note) { if (t.length >= 2) { onNote(t); setText(""); setNote(false); } return; }
    if (openCase && t.length >= 5) onSend(t);
  };
  let lastDay = "";
  let lastCase = "";
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-ink-700 px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-white">{conv.display_name}</div>
          <div className="truncate text-xs text-slate-500">{conv.handle_display} · {(conv.cases || []).length} atendimento(s)</div>
        </div>
        <ChannelBadge channel={conv.channel} />
        {conv.channel === "reclameaqui" && <Badge tone="red">resposta pública</Badge>}
        {canWrite && openCase && (
          <button className="btn-ghost !px-2.5 !py-1 text-xs" disabled={busy} onClick={onClose}
            title={`Encerrar o atendimento #${openCase.case_number}`}><CheckCircle2 size={13} /> Encerrar atendimento</button>
        )}
      </header>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto bg-ink-950/40 px-3 py-4 sm:px-6" aria-live="polite">
        {conv.messages.map((m: any) => {
          const d = day(m.sent_at);
          const showDay = d !== lastDay;
          lastDay = d;
          const k = m.contact_id ? caseById[m.contact_id] : null;
          const showCase = k && k.id !== lastCase;
          if (k) lastCase = k.id;
          return (
            <Fragment key={m.id}>
              {showDay && <div className="py-2 text-center"><span className="rounded-full bg-ink-800 px-3 py-0.5 text-[11px] text-slate-400">{d}</span></div>}
              {showCase && (
                <button onClick={() => onSelectCase(k.id)} className={clsx("my-2 flex w-full items-center gap-2 text-left", selectedCase === k.id ? "text-brand-300" : "text-slate-500 hover:text-slate-300")}>
                  <span className="h-px flex-1 bg-ink-600" />
                  <span className="text-[11px] font-medium">Atendimento #{k.case_number} · {k.intent_label}{k.order_id ? ` · pedido #${k.order_id}` : ""}</span>
                  <SupportStatusBadge status={k.status} />
                  {k.is_repeat && <Badge tone="amber">recontato</Badge>}
                  <span className="h-px flex-1 bg-ink-600" />
                </button>
              )}
              <Message m={m} />
            </Fragment>
          );
        })}
        <div ref={end} />
      </div>

      <footer className="border-t border-ink-700 p-3">
        {!openCase && <p className="mb-2 text-xs text-slate-500">Nenhum atendimento em aberto nesta conversa. Uma nova mensagem do cliente abre um novo atendimento.</p>}
        {openCase && win && (
          <p className={clsx("mb-2 flex items-center gap-1.5 text-[11px]", win.open ? "text-slate-500" : "text-amber-300")}>
            <Clock size={12} aria-hidden /> {win.open ? `Janela do WhatsApp aberta · ${win.hours_left} h restantes` : "Janela de 24 h do WhatsApp encerrada: no canal real, só modelo de mensagem aprovado."}
          </p>
        )}
        {canWrite && (
          <>
            <div className={clsx("rounded-lg border", note ? "border-amber-500/50 bg-amber-500/5" : "border-ink-600 bg-ink-850")}>
              <textarea aria-label={note ? "Nota interna" : "Resposta ao cliente"} rows={3} className="w-full resize-none bg-transparent px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600"
                placeholder={note ? "Nota interna (o cliente não vê)…" : openCase ? "Escreva a resposta…" : "Selecione um atendimento em aberto"}
                disabled={!note && !openCase} value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); } }} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button className={clsx("btn-ghost", note && "border-amber-500/50 text-amber-300")} onClick={() => { setNote(!note); setText(note ? suggestion || "" : ""); }}>
                <StickyNote size={14} /> {note ? "Cancelar nota" : "Nota interna"}</button>
              {!note && openCase && <button className="btn-ghost" disabled={busy} onClick={async () => { const t = await onAi(); if (t) setText(t); }}><Wand2 size={14} /> Reescrever com IA</button>}
              <span className="flex-1" />
              <span className="hidden text-[11px] text-slate-500 sm:inline">Ctrl + Enter</span>
              {note
                ? <button className="btn-primary" disabled={busy || text.trim().length < 2} onClick={submit}><Lock size={14} /> Salvar nota</button>
                : <button className="btn-primary" disabled={busy || !openCase || text.trim().length < 5} onClick={submit}><Send size={14} /> Enviar</button>}
            </div>
          </>
        )}
      </footer>
    </div>
  );
}

function Message({ m }: { m: any }) {
  if (m.author_type === "system") {
    return <div className="py-1 text-center"><span className="inline-block max-w-[85%] rounded-md bg-ink-800/80 px-3 py-1 text-[11px] text-slate-400">{m.text} · {hhmm(m.sent_at)}</span></div>;
  }
  if (m.author_type === "note") {
    return (
      <div className="mx-auto max-w-[80%] rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
        <div className="mb-0.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-amber-300"><Lock size={10} /> Nota interna · {m.author}</div>
        {m.text}
      </div>
    );
  }
  const inbound = m.direction === "in";
  const bot = m.author_type === "bot";
  return (
    <div className={clsx("flex", inbound ? "justify-start" : "justify-end")}>
      <div className={clsx("max-w-[78%] rounded-2xl px-3 py-2 shadow-sm",
        inbound ? "rounded-tl-sm bg-ink-800 text-slate-100"
          : bot ? "rounded-tr-sm border border-teal-500/30 bg-teal-500/15 text-slate-100"
            : "rounded-tr-sm bg-brand-600 text-white")}>
        <div className={clsx("mb-0.5 flex items-center gap-1 text-[10px] font-semibold", inbound ? "text-slate-400" : bot ? "text-teal-300" : "text-white/80")}>
          {inbound ? "Cliente" : bot ? <><Bot size={11} aria-hidden /> Agente de Atendimento · automático</> : m.author || "Atendente"}
        </div>
        <div className="whitespace-pre-wrap text-sm leading-snug">{m.text}</div>
        {(m.attachments || []).map((a: any, i: number) => (
          <div key={i} className={clsx("mt-1.5 inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px]", inbound ? "border-ink-600 text-slate-300" : "border-white/30")}>
            <ImageIcon size={11} aria-hidden /> foto · tirada em {new Date(a.taken_at).toLocaleDateString("pt-BR")}
          </div>
        ))}
        <div className={clsx("mt-0.5 text-right text-[10px]", inbound ? "text-slate-500" : bot ? "text-slate-400" : "text-white/70")}>{hhmm(m.sent_at)}</div>
      </div>
    </div>
  );
}
