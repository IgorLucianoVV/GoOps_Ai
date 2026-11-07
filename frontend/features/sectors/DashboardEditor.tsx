"use client";
import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Card } from "@/components/ui";
import { useAction } from "@/hooks/useApi";

const CHARTS = [
  { key: "kpi", label: "Indicador (KPI)" }, { key: "line", label: "Linha (evolução)" },
  { key: "bar", label: "Barras (comparação)" }, { key: "table", label: "Tabela" },
];

/** Monta o painel do setor escolhendo métrica, tipo de gráfico e agrupamento — sem código. */
export default function DashboardEditor({ domain, dashboard, metrics, onSaved, onCancel }:
  { domain: string; dashboard: any; metrics: any[]; onSaved: () => void; onCancel: () => void }) {
  const action = useAction();
  const [name, setName] = useState(dashboard?.name || "Painel do setor");
  const [widgets, setWidgets] = useState<any[]>(dashboard?.widgets || []);
  const [draft, setDraft] = useState<any>({ metric_key: metrics[0]?.metric_key || "", chart: "kpi", group_by: "", title: "" });
  useEffect(() => { setWidgets(dashboard?.widgets || []); setName(dashboard?.name || "Painel do setor"); }, [dashboard]);
  const metric = metrics.find((m) => m.metric_key === draft.metric_key);
  const dims: string[] = metric?.dimensions || [];
  const move = (i: number, d: number) => {
    const j = i + d; if (j < 0 || j >= widgets.length) return;
    const next = [...widgets]; [next[i], next[j]] = [next[j], next[i]]; setWidgets(next);
  };
  const add = () => {
    if (!metric) return;
    const gb = draft.chart === "kpi" ? null : (draft.group_by || dims[0] || null);
    setWidgets([...widgets, { id: `w${Date.now()}`, metric_key: metric.metric_key, chart: draft.chart, group_by: gb,
      title: draft.title || (gb ? `${metric.name} por ${gb === "month" ? "mês" : gb}` : metric.name) }]);
    setDraft({ ...draft, title: "" });
  };
  const save = async () => { if (await action.run(`/sectors/${domain}/dashboard`, { name, widgets }, undefined, { success: "Painel salvo" })) onSaved(); };

  return (
    <Card title="Editar painel" subtitle="Cada widget usa uma métrica governada do setor; os números são calculados no servidor.">
      <label className="mb-3 block max-w-md"><span className="label">Nome do painel</span>
        <input className="input mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <ul className="mb-4 space-y-1.5">
        {widgets.map((w, i) => (
          <li key={w.id} className="flex flex-wrap items-center gap-2 rounded-md border border-ink-700 px-3 py-2 text-sm">
            <span className="min-w-0 flex-1 truncate text-white">{w.title}</span>
            <span className="text-xs text-slate-500">{CHARTS.find((c) => c.key === w.chart)?.label}{w.group_by ? ` · por ${w.group_by}` : ""} · <code>{w.metric_key}</code></span>
            <button className="btn-ghost h-8 px-2" aria-label="Mover para cima" onClick={() => move(i, -1)}><ArrowUp size={13} /></button>
            <button className="btn-ghost h-8 px-2" aria-label="Mover para baixo" onClick={() => move(i, 1)}><ArrowDown size={13} /></button>
            <button className="btn-danger h-8 px-2" aria-label={`Remover ${w.title}`} onClick={() => setWidgets(widgets.filter((_, j) => j !== i))}><Trash2 size={13} /></button>
          </li>
        ))}
        {widgets.length === 0 && <li className="text-sm text-slate-500">Nenhum widget. Adicione abaixo.</li>}
      </ul>
      <div className="grid gap-2 rounded-md border border-dashed border-ink-600 p-3 md:grid-cols-5">
        <label className="md:col-span-2"><span className="label">Métrica</span>
          <select className="input mt-1 w-full" value={draft.metric_key} onChange={(e) => setDraft({ ...draft, metric_key: e.target.value, group_by: "" })}>
            {metrics.map((m) => <option key={m.metric_key} value={m.metric_key}>{m.name}{m.status !== "active" ? " (rascunho)" : ""}</option>)}
          </select></label>
        <label><span className="label">Gráfico</span>
          <select className="input mt-1 w-full" value={draft.chart} onChange={(e) => setDraft({ ...draft, chart: e.target.value })}>
            {CHARTS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
        <label><span className="label">Agrupar por</span>
          <select className="input mt-1 w-full" disabled={draft.chart === "kpi"} value={draft.group_by} onChange={(e) => setDraft({ ...draft, group_by: e.target.value })}>
            {dims.map((d) => <option key={d} value={d}>{d === "month" ? "mês" : d}</option>)}</select></label>
        <label><span className="label">Título (opcional)</span>
          <input className="input mt-1 w-full" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
        <div className="md:col-span-5"><button className="btn-ghost" onClick={add} disabled={!metric}><Plus size={14} /> Adicionar widget</button></div>
      </div>
      <div className="mt-4 flex gap-2">
        <button className="btn-primary" disabled={action.busy} onClick={save}>Salvar painel</button>
        <button className="btn-ghost" onClick={onCancel}>Cancelar</button>
      </div>
    </Card>
  );
}
