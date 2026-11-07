"use client";
import { Bars, LineSeries } from "@/components/charts";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, Kpi, MetricTag } from "@/components/ui";

export interface WidgetData {
  id: string; title: string; metric_key: string; chart: "kpi" | "bar" | "line" | "table"; group_by: string | null;
  data: any; error: string | null;
}

export function fmtValue(v: any, unit?: string) {
  if (v === null || v === undefined) return "—";
  if (unit === "%") return fmt.pct(v);
  const n = fmt.num(v, Number.isInteger(v) ? 0 : 2);
  return unit && !/^(registros|reclamações|valor)$/.test(unit) ? `${n} ${unit}` : n;
}

const DIM_TITLE: Record<string, string> = { month: "mês" };

/** Desenha um widget calculado no backend (métrica governada). Nenhum cálculo de indicador acontece aqui. */
export default function Widget({ w, actions }: { w: WidgetData; actions?: React.ReactNode }) {
  const meta = w.data?.metric;
  const draft = meta?.draft && <Badge tone="amber">rascunho · aguardando aprovação</Badge>;
  if (w.error) {
    return <Card title={w.title} actions={actions}><p className="text-sm text-rose-300">{w.error}</p></Card>;
  }
  if (w.chart === "kpi") {
    const r = w.data?.result || {};
    return (
      <div className="relative min-w-0">
        <Kpi label={w.title} value={fmtValue(r.value, meta?.unit)}
          hint={<span className="inline-flex flex-wrap items-center gap-1">n = {fmt.num(r.n)} <MetricTag meta={meta} />{draft}</span>} />
        {actions && <div className="absolute right-2 top-2">{actions}</div>}
      </div>
    );
  }
  let groups: any[] = (w.data?.groups || []).filter((g: any) => g.value !== null && g.value !== undefined);
  const gb = w.group_by as string;
  const many = groups.length > 12;
  if (w.chart === "bar" && gb !== "month") groups = [...groups].sort((a, b) => b.value - a.value).slice(0, 20);
  const rows = groups.map((g) => ({ ...g, label: String(g[gb]) }));
  const summary = rows.slice(0, 8).map((g) => `${g.label}: ${fmtValue(g.value, meta?.unit)}`).join("; ");
  return (
    <Card title={w.title} subtitle={`por ${DIM_TITLE[gb] || gb}`} className={w.chart === "table" || many ? "lg:col-span-2" : ""}
      actions={<span className="inline-flex flex-wrap items-center gap-1"><MetricTag meta={meta} />{draft}{actions}</span>}>
      {rows.length === 0 ? <p className="text-sm text-slate-500">Sem dados para este recorte.</p>
        : w.chart === "line" ? (
          <LineSeries data={rows} x="label" lines={[{ key: "value", name: meta?.unit || "valor" }]} label={w.title} summary={summary} />
        ) : w.chart === "bar" ? (
          <Bars data={rows} x="label" y="value" name={meta?.unit || "valor"} unit={meta?.unit === "%" ? "%" : undefined}
            horizontal={many || rows.some((r) => r.label.length > 14)} label={w.title} summary={summary} />
        ) : (
          <DataTable rows={rows} maxHeight={360} columns={[
            { key: "label", label: DIM_TITLE[gb] || gb },
            { key: "value", label: "Valor", render: (r: any) => fmtValue(r.value, meta?.unit) },
            { key: "n", label: "n", render: (r: any) => fmt.num(r.n) },
          ]} />
        )}
    </Card>
  );
}
