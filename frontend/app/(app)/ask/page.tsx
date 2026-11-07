"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Bot, ChevronDown, Database, Loader2, RotateCcw, Sparkles, User } from "lucide-react";
import { Badge, PageHeader, SyntheticBadge } from "@/components/ui";
import Markdown from "@/features/ask/Markdown";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/services/api";

interface Msg { role: "user" | "assistant"; content: string; meta?: any; error?: boolean }

const SUGGESTIONS = [
  "Por que o NPS de Copos é menor?",
  "Qual o NPS por transportadora?",
  "Como evoluiu o NPS mês a mês?",
  "Qual o prazo médio de entrega no frete Expresso?",
  "Quais UFs têm mais detratores?",
  "Tem algum incidente aberto?",
];

function filtersText(f: Record<string, any>) {
  const e = Object.entries(f || {}).filter(([, v]) => v && (!Array.isArray(v) || v.length));
  return e.length ? e.map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : v}`).join(" · ") : "base completa";
}

function Citations({ meta }: { meta: any }) {
  const [open, setOpen] = useState(false);
  const cits: any[] = meta.citations || [];
  return (
    <div className="mt-3 border-t border-ink-700 pt-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={meta.generated_by === "deterministic" ? "gray" : "violet"}>
          {meta.generated_by === "deterministic" ? "Resposta determinística (sem LLM)" : `Gerado por LLM · ${meta.provider ? meta.provider + " · " : ""}${meta.model}`}
        </Badge>
        {cits.filter((c) => c.type === "metric").slice(0, 4).map((c, i) => (
          <Link key={i} href={`/semantic/metrics/${c.metric_key}`} className="inline-flex items-center gap-1 rounded-full border border-ink-600 px-2 py-0.5 font-mono text-[11px] text-slate-300 hover:border-slate-500">
            <Database size={11} aria-hidden /> {c.metric_key} v{c.version}
          </Link>
        ))}
        {cits.some((c) => c.synthetic) && <SyntheticBadge fields={["métricas com dados sintéticos de demonstração"]} />}
        {meta.engine && meta.engine !== "deterministic" && <Badge tone="teal">{meta.engine === "langgraph" ? "LangGraph" : "loop nativo"}</Badge>}
        <span className="text-[11px] text-slate-500">{meta.latency_ms ? `${(meta.latency_ms / 1000).toFixed(1)} s` : ""}{meta.cost_usd ? ` · US$ ${meta.cost_usd.toFixed(4)}` : ""}</span>
      </div>
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-slate-400 hover:text-white">
        <ChevronDown size={13} className={open ? "rotate-180 transition" : "transition"} aria-hidden /> Fontes e como cheguei aqui ({cits.length} fonte(s), {(meta.tools_used || []).length} consulta(s))
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-xs">
          {cits.map((c, i) => (
            <div key={i} className="rounded-lg border border-ink-700 bg-ink-850 p-2.5">
              {c.type === "metric" ? <>
                <div className="font-medium text-slate-100">{c.name} <span className="font-mono text-slate-500">{c.metric_key} v{c.version}</span></div>
                <div className="text-slate-400">Valor: <strong className="text-slate-100">{typeof c.value === "number" ? c.value.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) : c.value}</strong> {c.unit} · n={c.n?.toLocaleString?.("pt-BR") ?? c.n}
                  {c.group_by && <> · agrupado por {c.group_by}</>} · recorte: {filtersText(c.filters)} · dataset {c.dataset}</div>
              </> : c.type === "comments" ? (
                <div className="text-slate-400">Comentários ({c.category}) — {c.n} processados · {c.method} · recorte: {filtersText(c.filters)}</div>
              ) : <div className="text-slate-400">Fonte: {c.dataset}</div>}
            </div>
          ))}
          {meta.fallback_reason && <div className="text-slate-500">Observação: {meta.fallback_reason}.</div>}
          <details><summary className="cursor-pointer text-slate-500">Consultas executadas</summary>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5 font-mono text-[11px] text-slate-400">
              {(meta.tools_used || []).map((t: any, i: number) => <li key={i}>{t.tool}({JSON.stringify(t.args)}) {t.ok ? "✓" : `✗ ${t.error || ""}`}</li>)}
            </ol></details>
        </div>
      )}
    </div>
  );
}

export default function AskPage() {
  const status = useApi<any>("/assistant/status");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [modelId, setModelId] = useState<string>("default");
  const options: any[] = status.data?.options || [];
  useEffect(() => {
    if (!status.data) return;
    let saved: string | null = null;
    try { saved = window.localStorage.getItem("goops_chat_model"); } catch { /* indisponível */ }
    const pick = options.find((o) => o.id === saved && o.available) || options.find((o) => o.available);
    if (pick) setModelId(pick.id);
  }, [status.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const chooseModel = (id: string) => {
    setModelId(id);
    try { window.localStorage.setItem("goops_chat_model", id); } catch { /* indisponível */ }
  };
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  const send = async (text?: string) => {
    const question = (text ?? q).trim();
    if (question.length < 3 || busy) return;
    const history = msgs.filter((m) => !m.error).slice(-8).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api.post<any>("/assistant/ask", { question, history, model_id: options.length ? modelId : undefined });
      setMsgs((m) => [...m, { role: "assistant", content: r.data.answer, meta: r.data }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: (e as ApiError).message || "Não foi possível responder.", error: true }]);
    } finally {
      setBusy(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  return (
    <div className="flex h-[calc(100vh-8.5rem)] flex-col">
      <PageHeader kicker="Assistente" title="Pergunte ao GoOps"
        subtitle="Pergunte em linguagem natural. As respostas usam apenas métricas oficiais do catálogo, com o número, o recorte e a fonte — e respeitam as suas permissões."
        actions={<>
          {status.data && options.length > 0 && (
            <label className="flex items-center gap-2 text-sm"><span className="text-slate-500">Modelo</span>
              <select className="input" value={modelId} onChange={(e) => chooseModel(e.target.value)} aria-label="Provedor e modelo das respostas">
                {options.map((o) => <option key={o.id} value={o.id} disabled={!o.available}>
                  {o.label}{!o.available ? (o.credential ? " (pacote não instalado)" : " (sem credencial)") : ""}</option>)}
              </select></label>)}
          {status.data && <Badge tone="teal">motor: {status.data.engine === "langgraph" ? "LangGraph" : "nativo"}</Badge>}
          {status.data && !status.data.llm_enabled && <Link href="/settings" className="btn-ghost"><Sparkles size={14} aria-hidden /> Conectar modelo</Link>}
          {msgs.length > 0 && <button className="btn-ghost" onClick={() => setMsgs([])}><RotateCcw size={14} aria-hidden /> Nova conversa</button>}
        </>} />
      {status.data && !status.data.llm_enabled && (
        <div role="note" className="mb-3 rounded-lg border border-ink-600 bg-ink-900 p-3 text-xs text-slate-400">
          Modo determinístico: as respostas já usam as métricas oficiais, mas em formato padronizado. Conecte um modelo em
          <Link href="/settings" className="mx-1 font-medium text-brand-500 underline underline-offset-2">Configurações › Modelos e chaves</Link>para respostas em linguagem natural.
        </div>
      )}
      <div className="card flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-5 overflow-y-auto p-5" aria-live="polite" aria-busy={busy}>
          {msgs.length === 0 && (
            <div className="mx-auto max-w-2xl py-6 text-center">
              <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-accent-400 text-navy-900"><Sparkles size={22} aria-hidden /></span>
              <h2 className="mt-3 text-lg font-semibold text-white">O que você quer saber sobre a operação?</h2>
              <p className="mt-1 text-sm text-slate-400">Exemplos:</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="rounded-full border border-ink-600 bg-ink-850 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500">{s}</button>)}
              </div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : ""}`}>
              {m.role === "assistant" && <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-400 text-navy-900"><Bot size={16} aria-hidden /></span>}
              <div className={m.role === "user" ? "max-w-[75%] rounded-2xl rounded-br-sm bg-ink-800 px-4 py-2.5 text-sm text-white"
                : `max-w-[85%] rounded-2xl rounded-tl-sm border px-4 py-3 ${m.error ? "border-rose-500/40 bg-rose-950" : "border-ink-700 bg-ink-900"}`}>
                <span className="sr-only">{m.role === "user" ? "Você:" : "GoOps:"}</span>
                {m.role === "user" ? m.content : <Markdown text={m.content} />}
                {m.meta && <Citations meta={m.meta} />}
              </div>
              {m.role === "user" && <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ink-800 text-slate-400"><User size={16} aria-hidden /></span>}
            </div>
          ))}
          {busy && <div className="flex items-center gap-2 text-sm text-slate-400" role="status"><Loader2 size={15} className="animate-spin" aria-hidden /> Consultando métricas oficiais…</div>}
          <div ref={endRef} />
        </div>
        <form className="flex items-end gap-2 border-t border-ink-700 p-3" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <label htmlFor="ask-input" className="sr-only">Sua pergunta</label>
          <textarea id="ask-input" ref={inputRef} rows={1} value={q} onChange={(e) => setQ(e.target.value)} maxLength={1000}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Ex.: Qual linha de produto tem mais detratores?" className="input max-h-40 min-h-[44px] flex-1 resize-y py-2.5" />
          <button className="btn-primary h-11 w-11 p-0" disabled={busy || q.trim().length < 3} aria-label="Enviar pergunta"><ArrowUp size={18} aria-hidden /></button>
        </form>
      </div>
      <p className="mt-2 text-center text-[11px] text-slate-500">Enter envia · Shift+Enter quebra linha · Respostas sobre correlação não provam causalidade.</p>
    </div>
  );
}
