"use client";
import Link from "next/link";
import { useState } from "react";
import { Cpu, ShieldCheck, Zap } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, JsonBlock, Kpi, Loading, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import InstructionEditor from "@/features/agents/InstructionEditor";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

function List({ items }: { items?: string[] }) {
  return <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">{(items || []).map((t) => <li key={t}>{t}</li>)}</ul>;
}

export default function AgentPage({ params }: { params: { key: string } }) {
  const { data, error, loading, reload } = useApi<any>(`/agents/${params.key}`);
  const { can } = useAuth();
  const [tab, setTab] = useState("overview");
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
          <Tabs active={tab} onChange={setTab} tabs={[
            { key: "overview", label: "Visão geral" },
            { key: "instructions", label: `Instruções de IA (${data.instructions.length})${drafts ? ` · ${drafts} rascunho(s)` : ""}` },
            { key: "activity", label: `Atividade (${data.runs})` },
          ]} />

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

          {tab === "instructions" && (
            <section aria-label="Instruções de IA" className="space-y-3">
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
