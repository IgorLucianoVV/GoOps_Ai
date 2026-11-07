"use client";
import { useState } from "react";
import Link from "next/link";
import { Pencil, Plus } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, Empty, ErrorBox, Loading, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import AgentsPanel from "@/features/sectors/AgentsPanel";
import DashboardEditor from "@/features/sectors/DashboardEditor";
import MetricBuilder from "@/features/sectors/MetricBuilder";
import Widget, { type WidgetData } from "@/features/sectors/Widget";
import { useApi } from "@/hooks/useApi";

const ROLE: Record<string, string> = { key: "chave", time: "data", dimension: "dimensão", measure: "medida", text: "texto", attribute: "atributo" };

export default function SectorPage({ params }: { params: { key: string } }) {
  const d = useApi<any>(`/sectors/${params.key}`);
  const [period, setPeriod] = useState({ start: "", end: "" });
  const dash = useApi<any>(`/sectors/${params.key}/dashboard`, { start: period.start || undefined, end: period.end || undefined });
  const [tab, setTab] = useState("painel");
  const [editing, setEditing] = useState(false);
  const info = d.data;
  const reloadAll = () => { d.reload(); dash.reload(); };

  return (
    <>
      <PageHeader kicker="Setores" title={info?.domain?.name || params.key} subtitle={info?.domain?.description}
        actions={<>
          {info?.builtin_page && <Link className="btn-ghost" href={info.builtin_page}>Análise dedicada</Link>}
          {info?.can_edit && <Link className="btn-ghost" href={`/setores/novo?setor=${params.key}`}><Plus size={14} /> Conjunto de dados</Link>}
        </>} />
      <ErrorBox error={d.error || dash.error} onRetry={reloadAll} />
      {d.loading && !info && <Loading />}
      {info && (
        <>
          <Tabs active={tab} onChange={setTab} tabs={[
            { key: "painel", label: "Painel" }, { key: "agentes", label: `Agentes (${info.agents.length})` },
            { key: "metricas", label: `Métricas (${info.metrics.length})` }, { key: "dados", label: `Dados (${info.datasets.length})` }]} />
          <div className="mt-4">
            {tab === "painel" && (editing ? (
              <DashboardEditor domain={params.key} dashboard={info.dashboard} metrics={info.metrics}
                onSaved={() => { setEditing(false); reloadAll(); }} onCancel={() => setEditing(false)} />
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex flex-col"><span className="label">De</span><input type="date" className="input mt-1" value={period.start} onChange={(e) => setPeriod({ ...period, start: e.target.value })} /></label>
                  <label className="flex flex-col"><span className="label">Até</span><input type="date" className="input mt-1" value={period.end} onChange={(e) => setPeriod({ ...period, end: e.target.value })} /></label>
                  {(period.start || period.end) && <button className="btn-ghost" onClick={() => setPeriod({ start: "", end: "" })}>Limpar período</button>}
                  {info.can_edit && info.metrics.length > 0 && <button className="btn-ghost ml-auto" onClick={() => setEditing(true)}><Pencil size={14} /> Editar painel</button>}
                </div>
                {dash.loading && !dash.data && <Loading />}
                {dash.data && dash.data.widgets.length === 0 && (
                  <Empty title="Painel vazio" hint={info.metrics.length ? "Adicione widgets escolhendo métricas e gráficos." : "Crie métricas a partir de um conjunto de dados primeiro."}
                    action={info.can_edit && (info.metrics.length
                      ? <button className="btn-primary" onClick={() => setEditing(true)}>Montar painel</button>
                      : <Link className="btn-primary" href={`/setores/novo?setor=${params.key}`}>Adicionar conjunto de dados</Link>)} />
                )}
                {dash.data && (
                  <>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 [&>*]:min-w-0">
                      {dash.data.widgets.filter((w: WidgetData) => w.chart === "kpi").map((w: WidgetData) => <Widget key={w.id} w={w} />)}
                    </div>
                    <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
                      {dash.data.widgets.filter((w: WidgetData) => w.chart !== "kpi").map((w: WidgetData) => <Widget key={w.id} w={w} />)}
                    </div>
                  </>
                )}
              </div>
            ))}
            {tab === "agentes" && <AgentsPanel domain={params.key} agents={info.agents} metrics={info.metrics} canEdit={info.can_edit} onChange={reloadAll} />}
            {tab === "metricas" && info.can_edit && info.datasets.some((x: any) => x.built) && (
              <div className="mb-4"><MetricBuilder domain={params.key} datasets={info.datasets.filter((x: any) => x.built)} onCreated={reloadAll} /></div>
            )}
            {tab === "metricas" && (
              <Card title="Métricas do setor" subtitle="Novas métricas ficam aguardando aprovação de outra pessoa (segregação de funções). Até lá aparecem no painel como rascunho."
                actions={<Link className="btn-ghost" href="/semantic/approvals">Aprovações</Link>}>
                <DataTable rows={info.metrics} columns={[
                  { key: "name", label: "Métrica", render: (m: any) => <Link className="text-brand-500 underline-offset-2 hover:underline" href={`/semantic/metrics/${m.metric_key}`}>{m.name}</Link> },
                  { key: "metric_key", label: "Chave", render: (m: any) => <code className="text-xs">{m.metric_key}</code> },
                  { key: "formula_text", label: "Fórmula" }, { key: "unit", label: "Unidade" },
                  { key: "status", label: "Status", render: (m: any) => <StatusBadge status={m.status === "pending_approval" ? "pending_approval" : m.status} /> },
                ]} />
              </Card>
            )}
            {tab === "dados" && (
              <div className="space-y-4">
                {info.datasets.length === 0 && <Empty title="Nenhum conjunto de dados" hint="Conecte uma fonte e escolha os campos."
                  action={info.can_edit && <Link className="btn-primary" href={`/setores/novo?setor=${params.key}`}>Adicionar conjunto</Link>} />}
                {info.datasets.map((ds: any) => (
                  <Card key={ds.key} title={ds.name} subtitle={`${ds.description || ""} · versão ${ds.version}`}
                    actions={<span className="inline-flex flex-wrap gap-2">
                      {ds.built ? <Badge tone="green">{fmt.num(ds.rows)} registros</Badge> : <Badge tone="amber">execute o pipeline</Badge>}
                      <Link className="btn-ghost h-8" href={`/lakehouse/datasets/gold_${ds.key}`}>Gold</Link>
                      <Link className="btn-ghost h-8" href={`/lakehouse/lineage?node=dataset:gold_${ds.key}`}>Linhagem</Link>
                      {info.can_edit && <Link className="btn-ghost h-8" href={`/setores/novo?setor=${params.key}&conjunto=${ds.key}`}>Editar</Link>}</span>}>
                    <div className="mb-2 text-xs text-slate-500">Fontes: {ds.definition.source_keys.join(", ")} · chave <code>{ds.definition.key_field}</code>
                      {ds.definition.time_field && <> · data <code>{ds.definition.time_field}</code></>}</div>
                    <DataTable rows={ds.definition.fields} columns={[
                      { key: "name", label: "Campo", render: (f: any) => <code className="text-xs">{f.name}</code> }, { key: "label", label: "Rótulo" },
                      { key: "type", label: "Tipo" }, { key: "role", label: "Papel", render: (f: any) => ROLE[f.role] || f.role },
                      { key: "from", label: "Origem", render: (f: any) => f.derive ? `${f.derive}(${f.args.join(", ")})` : <code className="text-xs">{f.from}</code> },
                    ]} />
                  </Card>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
