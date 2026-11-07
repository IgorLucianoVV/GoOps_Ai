"use client";
import Link from "next/link";
import { Database, Play, RefreshCw } from "lucide-react";
import { Bars, LineSeries, npsColor } from "@/components/charts";
import { fmt, CATEGORY_LABEL } from "@/components/labels";
import { Badge, Card, DataTable, DemoBadge, Empty, ErrorBox, Kpi, MetricTag, PageHeader, PageSkeleton, SyntheticBadge, SeverityBadge, StatusBadge } from "@/components/ui";
import { useConfirm } from "@/hooks/useConfirm";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<any>("/overview");
  const { can } = useAuth();
  const action = useAction();
  const confirm = useConfirm();

  const runCycle = async () => {
    const res = await action.run("/agents/supervisor/execute", {}, undefined, { success: "Ciclo de monitoramento concluído" });
    if (res) reload();
  };
  const loadDemo = async () => {
    const ok = await confirm({ title: "Recarregar os dados da Gocase?", tone: "danger", confirmLabel: "Recarregar",
      description: "Os dados processados, incidentes e operações atuais serão substituídos pelo processamento das planilhas do case. Métricas e usuários são mantidos." });
    if (!ok) return;
    const res = await action.run("/demo/load", { scenario: "gocase", reset: true }, undefined, { success: "Dados da Gocase recarregados" });
    if (res) reload();
  };
  const evo = (data?.nps?.trend || []) as any[];
  const npsDelta = evo.length >= 2 ? evo[evo.length - 1].delta : null;

  return (
    <>
      <PageHeader kicker="Visão executiva" title="Central de Operações"
        subtitle="Estado da operação a partir de indicadores governados, incidentes e atividade dos agentes."
        actions={<>
          {data?.nps?.meta?.is_demo && <DemoBadge />}
          {can("settings:write") && <button className="btn-ghost" onClick={loadDemo} disabled={action.busy}><Database size={14} /> Recarregar dados da Gocase</button>}
          {can("agents:execute") && <button className="btn-primary" onClick={runCycle} disabled={action.busy || !data?.ready}><Play size={14} /> Executar ciclo de monitoramento</button>}
          <button className="btn-ghost" onClick={reload}><RefreshCw size={14} /></button>
        </>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <PageSkeleton />}
      {data && !data.ready && (
        <Card className="mb-5"><Empty title="Nenhum dado processado ainda" hint={data.message}
          action={<>{can("settings:write") && <button className="btn-primary" onClick={loadDemo} disabled={action.busy}><Database size={14} aria-hidden /> Carregar dados da Gocase</button>}
            <Link className="btn-ghost" href="/lakehouse">Abrir Lakehouse de dados</Link></>} /></Card>
      )}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Kpi label="Incidentes ativos" value={data.incidents.open} hint={`${data.incidents.awaiting_approval} aguardando aprovação`} tone={data.incidents.open ? "warn" : "good"} />
            <Kpi label="Incidentes críticos" value={data.incidents.critical} hint={`${data.incidents.high} de severidade alta`} tone={data.incidents.critical ? "bad" : "default"} />
            <Kpi label="NPS global" value={data.nps ? fmt.num(data.nps.current.value, 1) : "—"} hint={data.nps ? `${fmt.num(data.nps.current.n)} avaliações válidas` : "sem dados"}
              delta={npsDelta} deltaLabel="no último mês" info={data.nps ? data.nps.metric.formula_text : undefined} />
            {data.logistics && data.logistics.late_rate.value === null
              ? <Kpi label="Prazo médio de entrega" value={`${fmt.num(data.logistics.delivery_days.value, 1)} dias`} hint="fonte sem datas de previsão: atraso não mensurável" />
              : <Kpi label="Entregas atrasadas" value={data.logistics ? fmt.pct(data.logistics.late_rate.value) : "—"} hint={data.logistics ? <span className="inline-flex flex-wrap items-center gap-1">{fmt.num(data.logistics.late_rate.n)} entregas concluídas{data.logistics.metric?.synthetic && <SyntheticBadge fields={data.logistics.metric.synthetic_fields} />}</span> : ""} />}
            <Kpi label="Aprovações pendentes" value={data.operations_pending} hint="ações aguardando humano" tone={data.operations_pending ? "warn" : "default"} />
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2" title="Evolução do NPS" subtitle="Métrica corporativa oficial" actions={<MetricTag meta={data.nps?.metric} />}>
              {data.nps ? <LineSeries data={data.nps.trend} x="month" lines={[{ key: "nps", name: "NPS", color: "primary" }]} label="Evolução do NPS"
                summary={evo.map((r: any) => `${r.month}: ${fmt.num(r.nps, 1)}`).join("; ")} /> : <div className="text-sm text-slate-500">Sem dados.</div>}
            </Card>
            {data.logistics && data.logistics.late_rate.value === null ? (
              <Card title="Prazo médio de entrega por transportadora" actions={<MetricTag meta={data.logistics.days_metric} />}>
                <Bars data={data.logistics.days_by_carrier} x="carrier" y="value" name="dias" horizontal colorFn={() => "secondary"} />
              </Card>
            ) : (
              <Card title="Taxa de atraso por transportadora" actions={<MetricTag meta={data.logistics?.metric} />}>
                {data.logistics ? <Bars data={data.logistics.by_carrier} x="carrier" y="value" name="% atrasadas" horizontal unit="%" colorFn={(r) => (r.value > 20 ? "negative" : "primary")} /> : null}
              </Card>
            )}
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2" title="Incidentes recentes" actions={<Link href="/incidents" className="text-xs text-brand-400">ver todos →</Link>}>
              <DataTable rows={data.incidents.recent} empty="Nenhum incidente aberto" emptyHint="O Agente Monitor cria incidentes quando um indicador governado ultrapassa os limiares configurados."
                emptyAction={can("agents:execute") && data.ready ? <button className="btn-ghost" onClick={runCycle} disabled={action.busy}><Play size={14} aria-hidden /> Executar ciclo agora</button> : undefined} columns={[
                { key: "severity", label: "Sev.", render: (r: any) => <SeverityBadge severity={r.severity} /> },
                { key: "title", label: "Incidente", render: (r: any) => <Link href={`/incidents/${r.id}`} className="text-slate-100 hover:text-brand-400">{r.title}</Link> },
                { key: "category", label: "Categoria", render: (r: any) => CATEGORY_LABEL[r.category] || r.category },
                { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
              ]} />
            </Card>
            <Card title="Qualidade de dados" subtitle="Última execução do pipeline">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><div className="label">Regras</div><div className="text-xl text-white">{data.data_quality.rules_evaluated ?? "—"}</div></div>
                <div><div className="label">Em quarentena</div><div className="text-xl text-amber-300">{data.data_quality.quarantined_total ?? "—"}</div></div>
                <div><div className="label">Alertas</div><div className="text-xl text-white">{data.data_quality.warnings ?? "—"}</div></div>
                <div><div className="label">Erros</div><div className="text-xl text-rose-300">{data.data_quality.errors ?? "—"}</div></div>
              </div>
              <Link href="/lakehouse/quality" className="mt-3 inline-block text-xs text-brand-400">detalhes →</Link>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2" title="Atividade dos agentes">
              <DataTable rows={data.agent_activity} empty="Nenhuma execução de agente ainda" emptyHint="As execuções aparecem aqui após o primeiro ciclo de monitoramento." columns={[
                { key: "agent_key", label: "Agente", render: (r: any) => <Badge tone="teal">{r.agent_key}</Badge> },
                { key: "task", label: "Tarefa" },
                { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
                { key: "started_at", label: "Início", render: (r: any) => fmt.date(r.started_at) },
                { key: "incident_id", label: "Incidente", render: (r: any) => r.incident_id ? <Link className="text-brand-400" href={`/incidents/${r.incident_id}`}>{r.incident_id}</Link> : "—" },
              ]} />
            </Card>
            <Card title="Roteamento inteligente de custo">
              <div className="space-y-2 text-sm">
                <Row k="Decisões de roteamento" v={fmt.num(data.routing.routing_decisions)} />
                <Row k="Resolvido sem LLM" v={fmt.pct(data.routing.pct_without_llm)} />
                <Row k="Chamadas a LLM" v={fmt.num(data.routing.llm_calls)} />
                <Row k="Custo acumulado" v={`US$ ${fmt.num(data.routing.cost_usd, 4)}`} />
                <Row k="Fallbacks determinísticos" v={fmt.num(data.routing.fallbacks_to_deterministic)} />
              </div>
            </Card>
          </div>
          {data.pipeline && (
            <Card title="Último pipeline" actions={<StatusBadge status={data.pipeline.status} />}>
              <div className="flex flex-wrap gap-2">
                {data.pipeline.steps.map((s: any) => <Badge key={s.step} tone={s.status === "success" ? "green" : "red"}>{s.step} · {s.ms} ms</Badge>)}
              </div>
              <div className="mt-2 text-xs text-slate-500">{data.pipeline.id} · {fmt.date(data.pipeline.started_at)} · por {data.pipeline.triggered_by}</div>
            </Card>
          )}
        </div>
      )}
    </>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between border-b border-ink-700/60 pb-1.5"><span className="text-slate-400">{k}</span><span className="tabular-nums text-slate-100">{v}</span></div>;
}
