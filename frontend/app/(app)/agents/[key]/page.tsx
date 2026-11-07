"use client";
import Link from "next/link";
import { useState } from "react";
import { useTourTab } from "@/features/presentation/events";
import { Cpu, Hand, Scale, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, JsonBlock, Kpi, Loading, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import InstructionEditor from "@/features/agents/InstructionEditor";
import { AgentValidationSummary } from "@/features/agents/validation";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

function List({ items }: { items?: string[] }) {
  return <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">{(items || []).map((t) => <li key={t}>{t}</li>)}</ul>;
}

export default function AgentPage({ params }: { params: { key: string } }) {
  const { data, error, loading, reload } = useApi<any>(`/agents/${params.key}`);
  const validation = useApi<any>("/agents/validation");
  const { can } = useAuth();
  const [tab, setTab] = useState("overview");
  useTourTab(setTab, ["overview", "decides", "instructions", "activity"]);
  const canEdit = can("agents:configure");
  const p = data?.profile || {};
  const h = data?.health || {};
  const drafts = (data?.instructions || []).filter((i: any) => i.draft).length;
  return (
    <>
      <PageHeader kicker="Agente nativo" title={data?.name || params.key} subtitle={data?.role}
        actions={data && <span className="inline-flex items-center gap-2">{data.ai_tasks?.length ? <Badge tone="violet">usa IA em {data.ai_tasks.length} tarefa(s)</Badge> : <Badge>100% regras</Badge>}<StatusBadge status={data.state} /></span>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <div data-tour="agent-tabs"><Tabs active={tab} onChange={setTab} tabs={[
            { key: "overview", label: "Visão geral" },
            { key: "decides", label: "Como decide" },
            { key: "instructions", label: `Instruções de IA (${data.instructions.length})${drafts ? ` · ${drafts} rascunho(s)` : ""}` },
            { key: "activity", label: `Atividade (${data.runs})` },
          ]} /></div>

          {tab === "overview" && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <Kpi label="Execuções (7 dias)" value={fmt.num(h.runs)} hint={`${data.runs} no total`} />
                <Kpi label="Falhas (7 dias)" value={fmt.num(h.failed)} tone={h.failed ? "bad" : "good"} hint="execuções com erro" />
                <Kpi label="Sem IA (contingência)" value={h.fallback_rate == null ? "—" : fmt.pct(h.fallback_rate)} hint={h.ai_tasks ? `${h.fallbacks} de ${h.ai_tasks} tarefas de IA` : "nenhuma tarefa de IA no período"} />
                <Kpi label="Custo (7 dias)" value={`US$ ${fmt.num(h.cost_usd, 4)}`} hint={`US$ ${fmt.num(data.cost_usd, 4)} no total`} />
              </div>
              <div className="grid gap-4 lg:grid-cols-3">
                <Card title={<span className="inline-flex items-center gap-2"><Cpu size={15} aria-hidden /> O que faz</span>} className="lg:col-span-2">
                  <List items={p.does} />
                  <div className="mt-3 text-xs text-slate-500">Nível de roteamento: {data.level}</div>
                </Card>
                <div className="space-y-4">
                  <Card title={<span className="inline-flex items-center gap-2"><Zap size={15} aria-hidden /> Quando roda</span>}><List items={p.triggers} /></Card>
                  <Card title={<span className="inline-flex items-center gap-2"><ShieldCheck size={15} aria-hidden /> Limites</span>}><List items={p.guardrails} /></Card>
                </div>
              </div>
              <Card title="Permissões explícitas (menor privilégio)"><div className="flex flex-wrap gap-1">{data.permissions.map((x: string) => <Badge key={x} tone="teal">{x}</Badge>)}</div></Card>
              {data.instructions.length > 0 && (
                <Card title="Tarefas de IA" actions={<button className="btn-ghost h-8" onClick={() => setTab("instructions")}>Abrir instruções</button>}>
                  <ul className="space-y-1 text-sm">{data.instructions.map((i: any) => (
                    <li key={i.slot} className="flex flex-wrap items-center gap-2"><span className="text-slate-200">{i.label}</span>
                      {i.is_default ? <Badge>padrão</Badge> : <Badge tone="teal">v{i.version}</Badge>}{i.draft && <Badge tone="amber">rascunho</Badge>}</li>))}</ul>
                </Card>
              )}
            </div>
          )}

          {tab === "decides" && data.decision_logic && (
            <div className="space-y-5">
              <Card tour="agent-decides" title={<span className="inline-flex items-center gap-2"><Scale size={15} aria-hidden /> Como este agente decide</span>}
                subtitle="Regras e fórmulas implementadas no código. Os parâmetros abaixo são os que estão valendo agora.">
                <p className="text-sm text-slate-200">{data.decision_logic.summary}</p>
                <ol className="mt-4 space-y-3">
                  {(data.decision_logic.steps || []).map((st: any, i: number) => (
                    <li key={i} className="flex gap-3">
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">{i + 1}</span>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-slate-100">{st.title}</div>
                        <code className="mt-1 block whitespace-pre-wrap break-words rounded bg-ink-950 px-2 py-1 text-xs text-slate-300">{st.rule}</code>
                        <p className="mt-1 text-sm text-slate-400">{st.decides}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </Card>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Parâmetros em vigor">
                  <table className="w-full text-sm">
                    <tbody>{(data.decision_logic.params || []).map((x: any) => (
                      <tr key={x.label} className="border-b border-ink-800 last:border-0">
                        <td className="py-1.5 pr-3 text-slate-400">{x.label}</td>
                        <td className="py-1.5 pr-3 font-medium text-slate-100">{String(x.value ?? "—")}</td>
                        <td className="py-1.5 text-xs text-slate-500">{x.where}</td></tr>))}</tbody>
                  </table>
                </Card>
                <div className="space-y-4">
                  <Card title={<span className="inline-flex items-center gap-2"><Hand size={15} aria-hidden /> Quando passa para uma pessoa</span>}>
                    <List items={data.decision_logic.human} /></Card>
                  <Card title={<span className="inline-flex items-center gap-2"><Sparkles size={15} aria-hidden /> Uso de IA</span>}>
                    <p className="text-sm text-slate-300">{data.decision_logic.ai}</p></Card>
                </div>
              </div>
              {data.decision_logic.actions && (
                <Card title="Ações que pode propor (catálogo)">
                  <DataTable rows={data.decision_logic.actions} columns={[
                    { key: "title", label: "Ação" }, { key: "risk", label: "Risco", render: (r: any) => <Badge tone={r.risk === "high" ? "red" : r.risk === "medium" ? "amber" : "green"}>{({ high: "alto", medium: "médio", low: "baixo" } as any)[r.risk]}</Badge> },
                    { key: "areas", label: "Áreas", render: (r: any) => r.areas.join(", ") }, { key: "approval", label: "Aprovação humana" },
                  ]} />
                </Card>
              )}
              <Card title="Decisões recentes" subtitle="Exemplos reais registrados por este agente, com os números e motivos usados.">
                {data.recent_decisions?.length ? (
                  <ul className="space-y-2 text-sm">{data.recent_decisions.map((d: any, i: number) => (
                    <li key={i} className="rounded-lg border border-ink-700 p-2">
                      <div className="flex flex-wrap items-center gap-2"><span className="font-medium text-slate-100">{d.title}</span>
                        <span className="text-xs text-slate-500">{fmt.date(d.at)}</span>
                        {d.link && <Link className="text-xs text-brand-500 underline underline-offset-2" href={d.link}>abrir</Link>}</div>
                      <p className="mt-0.5 text-slate-300">{d.decision}</p></li>))}</ul>
                ) : <p className="text-sm text-slate-500">Nenhuma decisão registrada ainda. Rode o ciclo de monitoramento ou a validação ponta a ponta.</p>}
              </Card>
              <Card title="Validação ponta a ponta" subtitle="Cada regra recalculada de forma independente sobre dados sintéticos gerados num ambiente isolado.">
                {validation.data ? <AgentValidationSummary report={validation.data} agentKey={params.key} />
                  : <p className="text-sm text-slate-500">Ainda não há validação. <Link className="text-brand-500 underline" href="/agents/validacao">Rodar agora</Link></p>}
              </Card>
            </div>
          )}

          {tab === "instructions" && (
            <section aria-label="Instruções de IA" className="space-y-3" data-tour="agent-instructions">
              <p className="text-sm text-slate-400">
                {data.instructions.length
                  ? "Ajuste como a IA escreve em cada tarefa. O fluxo é Editar → Testar → Publicar: o rascunho não afeta os agentes, o teste usa dados de exemplo sem gravar nada, e só a versão publicada vale. Regras, números, ações do catálogo e aprovações continuam no núcleo determinístico."
                  : "Este agente não usa IA: funciona 100% por regras e estatística. Os parâmetros ficam em Configurações."}
                {data.instructions.length > 0 && !canEdit && " Você pode ver, mas só administradores e responsáveis pelos dados editam."}
              </p>
              {data.instructions.map((i: any) => <InstructionEditor key={`${i.slot}-${i.version}`} item={i} canEdit={canEdit} onSaved={reload} />)}
            </section>
          )}

          {tab === "activity" && (
            <Card title="Histórico de execuções">
              <DataTable rows={data.recent_runs} columns={[
                { key: "started_at", label: "Início", render: (r: any) => fmt.date(r.started_at) },
                { key: "task", label: "Tarefa" },
                { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
                { key: "incident_id", label: "Incidente", render: (r: any) => r.incident_id ? <Link className="text-brand-400" href={`/incidents/${r.incident_id}`}>{r.incident_id}</Link> : "—" },
                { key: "cost_usd", label: "Custo (US$)", render: (r: any) => fmt.num(r.cost_usd, 4) },
                { key: "output", label: "Saída", render: (r: any) => r.error ? <span className="text-rose-300">{r.error}</span> : <details><summary className="cursor-pointer text-xs text-slate-400">ver</summary><JsonBlock value={r.output} maxHeight={200} /></details> },
              ]} />
            </Card>
          )}
        </>
      )}
    </>
  );
}
