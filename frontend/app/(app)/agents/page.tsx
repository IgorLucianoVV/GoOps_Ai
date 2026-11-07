"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Pause, Play, Plus, Search, Sparkles } from "lucide-react";
import { DOMAIN_LABEL, fmt } from "@/components/labels";
import { Badge, Card, Empty, ErrorBox, JsonBlock, Kpi, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { HealthChips } from "@/features/agents/parts";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

const RUN_TONE: Record<string, string> = { ok: "green", alert: "red", skipped: "amber", no_data: "gray", error: "red" };
const RUN_LABEL: Record<string, string> = { ok: "OK", alert: "Alerta", skipped: "Ignorado", no_data: "Sem dados", error: "Erro" };
const FREQ: Record<string, string> = { "60": "a cada hora", "1440": "diário", "10080": "semanal" };
const norm = (t: string) => (t || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

export default function AgentsPage() {
  const { data, meta, error, loading, reload } = useApi<any[]>("/agents");
  const custom = useApi<any[]>("/agents/custom");
  const { can } = useAuth();
  const action = useAction();
  const [out, setOut] = useState<any>(null);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [domain, setDomain] = useState("");
  const [status, setStatus] = useState("");
  const cycle = async (auto: boolean) => { const r = await action.run("/agents/supervisor/execute", { auto_investigate: auto }, undefined, { success: "Ciclo executado", successDescription: "Veja os incidentes criados em Incidentes." }); if (r) { setOut(r); reload(); } };
  const toggle = async (e: React.MouseEvent, a: any) => {
    e.preventDefault(); e.stopPropagation();
    if (await action.run(`/agents/custom/${a.key}/enabled`, { enabled: !a.enabled }, undefined, { success: a.enabled ? "Agente pausado" : "Agente retomado" })) custom.reload();
  };
  const r = meta.routing;

  const native = useMemo(() => (data || []).filter((a) => kind !== "custom" && (!q || norm(`${a.name} ${a.role}`).includes(norm(q)))
    && (!status || (status === "attention" && (a.health?.failed > 0 || a.health?.fallback_rate > 50)))), [data, kind, q, status]);
  const mine = useMemo(() => (custom.data || []).filter((a) => kind !== "native"
    && (!q || norm(`${a.name} ${a.config?.instructions || ""}`).includes(norm(q)))
    && (!domain || a.domain === domain)
    && (!status || (status === "paused" && !a.enabled) || (status === "active" && a.enabled) || (status === "alert" && a.last_status === "alert")
      || (status === "attention" && (a.health?.failed > 0 || a.health?.fallback_rate > 50 || a.last_status === "error")))), [custom.data, kind, q, domain, status]);
  const domains = Array.from(new Set((custom.data || []).map((a) => a.domain)));
  const drafts = (data || []).reduce((n, a) => n + (a.drafts || 0), 0);

  return (
    <>
      <PageHeader kicker="Agentes de IA" title="Sistema multiagente" subtitle="Veja o que cada agente faz, ajuste e teste as instruções de IA antes de publicar e crie agentes para funções específicas. Agentes usam somente ferramentas governadas com permissões mínimas."
        actions={<>
          {can("agents:execute") && <>
            <button className="btn-ghost" disabled={action.busy} onClick={() => cycle(false)}>Somente monitorar</button>
            <button className="btn-ghost" disabled={action.busy} onClick={() => cycle(true)}><Play size={14} /> Ciclo completo</button>
            <Link className="btn-primary" href="/agents/novo"><Plus size={14} /> Novo agente</Link>
          </>}
        </>} />
      <ErrorBox error={error || action.error} onRetry={reload} />
      {out && <Card className="mb-5" title="Resultado do ciclo"><JsonBlock value={out} maxHeight={200} /></Card>}
      {loading && !data && <Loading />}
      {r && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Kpi label="Agentes" value={fmt.num((data?.length || 0) + (custom.data?.length || 0))} hint={`${data?.length || 0} nativos · ${custom.data?.length || 0} personalizados${drafts ? ` · ${drafts} rascunho(s)` : ""}`} />
          <Kpi label="Resolvido sem LLM" value={fmt.pct(r.pct_without_llm)} hint="nível 0 — regras e estatística" tone="good" />
          <Kpi label="Com IA (níveis 1–3)" value={fmt.pct((r.pct_small_model || 0) + (r.pct_economy_model || 0) + (r.pct_advanced_model || 0))} hint={`${r.fallbacks_to_deterministic} contingências sem IA`} />
          <Kpi label="Tokens (entrada/saída)" value={`${fmt.num(r.input_tokens)} / ${fmt.num(r.output_tokens)}`} hint={`${r.llm_calls} chamadas · lat. ${fmt.num(r.avg_latency_ms)} ms`} />
          <Kpi label="Custo" value={`US$ ${fmt.num(r.cost_usd, 4)}`} hint={`limites: ${r.limits.per_run_usd}/execução · ${r.limits.daily_usd}/dia`} />
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-end gap-3" role="search">
        <label className="relative min-w-[220px] flex-1"><span className="sr-only">Buscar agente</span>
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" aria-hidden />
          <input className="input w-full" style={{ paddingLeft: 32 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nome ou missão…" /></label>
        <div className="inline-flex rounded-lg border border-ink-700 p-0.5" role="group" aria-label="Tipo de agente">
          {[["all", "Todos"], ["native", "Nativos"], ["custom", "Personalizados"]].map(([k, l]) => (
            <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)} className={`rounded-md px-3 py-1 text-sm ${kind === k ? "bg-brand-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>{l}</button>))}
        </div>
        <label><span className="sr-only">Setor</span>
          <select className="input" value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="">Todos os setores</option>{domains.map((d) => <option key={d} value={d}>{DOMAIN_LABEL[d] || d}</option>)}</select></label>
        <label><span className="sr-only">Situação</span>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Qualquer situação</option><option value="attention">Precisa de atenção</option><option value="alert">Com alerta</option>
            <option value="active">Ativos</option><option value="paused">Pausados</option></select></label>
      </div>

      {kind !== "custom" && data && (
        <section aria-labelledby="native-title" className="mb-8">
          <h2 id="native-title" className="mb-1 text-base font-semibold text-white">Agentes nativos <span className="text-sm font-normal text-slate-500">({native.length})</span></h2>
          <p className="mb-3 text-sm text-slate-400">Fazem parte do produto. Abra um agente para ver o que ele faz e ajustar as instruções de IA (editar → testar → publicar).</p>
          {native.length === 0 ? <Empty title="Nenhum agente nativo com esses filtros" /> : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {native.map((a) => (
                <Link key={a.key} href={`/agents/${a.key}`} className="card block p-4 transition hover:border-brand-600">
                  <div className="flex items-start justify-between gap-2"><div className="font-semibold text-white">{a.name}</div><StatusBadge status={a.state} /></div>
                  <div className="mt-1 line-clamp-3 text-sm text-slate-400">{a.role}</div>
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
                    {a.ai_tasks?.length ? <Badge tone="violet">IA em {a.ai_tasks.length} {a.ai_tasks.length === 1 ? "tarefa" : "tarefas"}</Badge> : <Badge>100% regras</Badge>}
                    {a.drafts > 0 && <Badge tone="amber">{a.drafts} rascunho(s)</Badge>}
                    <HealthChips h={a.health} />
                  </div>
                  <div className="mt-2 text-xs text-slate-500">{a.runs} execuções · US$ {fmt.num(a.cost_usd, 4)} · última: {fmt.date(a.last_run?.started_at)}</div>
                </Link>
              ))}
            </div>
          )}
        </section>
      )}

      {kind !== "native" && (
        <section aria-labelledby="custom-title">
          <h2 id="custom-title" className="mb-1 text-base font-semibold text-white">Agentes personalizados <span className="text-sm font-normal text-slate-500">({mine.length})</span></h2>
          <p className="mb-3 text-sm text-slate-400">Criados pela equipe para funções específicas — por instruções (IA com ferramentas governadas) ou por modelos de setor. Rodam com permissões restritas ao setor e nunca aprovam nem executam ações.</p>
          <ErrorBox error={custom.error} onRetry={custom.reload} />
          {custom.loading && !custom.data && <Loading />}
          {custom.data && custom.data.length === 0 && (
            <Empty title="Nenhum agente personalizado" hint="Descreva uma missão (ex.: “toda segunda, resumir o NPS por transportadora e avisar o time se cair”), escolha as ferramentas e teste antes de salvar."
              action={can("agents:execute") ? <Link className="btn-primary" href="/agents/novo"><Plus size={14} /> Criar o primeiro</Link> : undefined} />
          )}
          {custom.data && custom.data.length > 0 && mine.length === 0 && <Empty title="Nenhum agente com esses filtros" />}
          {mine.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {mine.map((a) => (
                <div key={a.key} className={`card relative p-4 transition focus-within:border-brand-600 hover:border-brand-600 ${a.enabled ? "" : "opacity-75"}`}>
                  <div className="flex items-start justify-between gap-2">
                    <Link href={`/agents/custom/${a.key}`} className="font-semibold text-white after:absolute after:inset-0 after:content-[''] focus:outline-none">{a.name}</Link>
                    {a.last_status ? <Badge tone={RUN_TONE[a.last_status] || "gray"}>{RUN_LABEL[a.last_status] || a.last_status}</Badge> : <Badge>nunca executado</Badge>}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                    {a.template === "llm_task" ? <Badge tone="violet"><Sparkles size={11} aria-hidden />{a.template_label}</Badge> : <Badge>{a.template_label}</Badge>}
                    <Badge tone="teal">{DOMAIN_LABEL[a.domain] || a.domain}</Badge>
                    {!a.enabled && <Badge tone="amber">pausado</Badge>}
                  </div>
                  {a.template === "llm_task" && <p className="mt-2 line-clamp-2 text-sm text-slate-400">{a.config.instructions}</p>}
                  <div className="mt-3 flex flex-wrap items-center gap-1.5"><HealthChips h={a.health} /></div>
                  <div className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-500">
                    <span>{a.interval_minutes ? FREQ[String(a.interval_minutes)] || `${a.interval_minutes} min` : "manual"} · última: {fmt.date(a.last_run_at)}</span>
                    {can("agents:execute") && <button className="btn-ghost relative z-10 h-7 px-2 text-xs" disabled={action.busy} onClick={(e) => toggle(e, a)} aria-label={a.enabled ? `Pausar ${a.name}` : `Retomar ${a.name}`}>
                      {a.enabled ? <><Pause size={12} /> Pausar</> : <><Play size={12} /> Retomar</>}</button>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
}
