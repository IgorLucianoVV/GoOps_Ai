"use client";
import { Bars, npsColor, npsHex, useChartPalette } from "@/components/charts";
import { fmt } from "@/components/labels";
import { Card, DataTable, ErrorBox, Loading, MetricTag, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function RegionalPage() {
  const { data, error, loading, reload } = useApi<any>("/analytics/regional");
  const palette = useChartPalette();
  return (
    <>
      <PageHeader kicker="Análises" title="Desempenho regional" subtitle="NPS, detratores, atrasos e prazos por UF (Gold corporativa · gold_regional_performance)."
        actions={data?.regions?.meta?.synthetic_fields?.length > 0 && <SyntheticBadge fields={data.regions.meta.synthetic_fields} />} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          <Card title="NPS por UF" actions={<MetricTag meta={data.nps_by_state.metric} />}>
            <Bars data={data.nps_by_state.groups} x="state" y="value" name="NPS" colorFn={(r) => npsColor(r.value)} height={280} />
          </Card>
          <Card title="Indicadores por UF">
            <DataTable rows={data.regions.rows} columns={[
              { key: "state", label: "UF" }, { key: "orders", label: "Pedidos" }, { key: "evaluations", label: "Avaliações" },
              { key: "nps", label: "NPS", render: (r: any) => <span className="font-medium tabular-nums" style={{ color: npsHex(palette, r.nps) }}>{fmt.num(r.nps, 1)}</span> },
              { key: "detractor_rate", label: "% detratores", render: (r: any) => fmt.pct(r.detractor_rate) },
              { key: "late_rate", label: "% atraso", render: (r: any) => fmt.pct(r.late_rate) },
              { key: "avg_lead_time_days", label: "Prazo médio (d)" },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
