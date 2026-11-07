"use client";
import { Bars } from "@/components/charts";
import { fmt } from "@/components/labels";
import Link from "next/link";
import { Badge, Card, DataTable, DemoBadge, ErrorBox, Kpi, Loading, MetricTag, PageHeader, SyntheticBadge } from "@/components/ui";

const RISK_LABEL: Record<string, string> = { high: "Alto", medium: "Médio", low: "Baixo" };
import { useApi } from "@/hooks/useApi";

export default function LogisticsPage() {
  const { data, error, loading, reload } = useApi<any>("/analytics/logistics");
  return (
    <>
      <PageHeader kicker="Análises · Gold de logística" title="Logística" subtitle="Prazos, atrasos, transportadoras, fretes e risco de atraso. A métrica de domínio com tolerância é exibida separadamente da corporativa."
        actions={data?.scorecard?.meta?.is_demo && <DemoBadge />} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          {data.late_rate.metric.synthetic && (
            <div role="note" className="flex flex-wrap items-start gap-2 rounded-md border border-violet-500/40 bg-violet-950/20 p-3 text-sm text-slate-300">
              <SyntheticBadge fields={data.late_rate.metric.synthetic_fields} />
              <span className="min-w-0 flex-1">
                As planilhas do case não trazem datas de envio, previsão e entrega nem pedidos em aberto. Para a visão completa, esses campos
                vêm de um <strong>complemento sintético</strong> (produção e prazo prometido simulados; “Dias de entrega” real) e há
                120 pedidos fictícios em trânsito (ids DEMO-…). Indicadores marcados como <em>sintético</em> não são dados reais da Gocase.
                O <strong>prazo envio→entrega</strong> usa os dias reais da planilha.{" "}
                <Link href="/lakehouse/sources" className="text-brand-500 underline underline-offset-2">Desativar o complemento em Fontes</Link>.
              </span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Prazo médio envio→entrega" value={`${fmt.num(data.lead_time.result.value, 1)} dias`} hint={<MetricTag meta={data.lead_time.metric} />} />
            <Kpi label="Prazo médio pedido→entrega" value={`${fmt.num(data.delivery_days.result.value, 1)} dias`} hint={<MetricTag meta={data.delivery_days.metric} />} />
            <Kpi label="Entregas atrasadas (corporativa)" value={fmt.pct(data.late_rate.result.value)} hint={<MetricTag meta={data.late_rate.metric} />} />
            <Kpi label="No prazo c/ tolerância 1 dia (domínio)" value={fmt.pct(data.on_time_with_tolerance.result.value)} hint={<MetricTag meta={data.on_time_with_tolerance.metric} />} />
            <Kpi label="Entregas em aberto" value={fmt.num(data.delay_risk.rows.length)} hint={data.delay_risk.meta?.is_demo ? <SyntheticBadge demoRows /> : "exige datas de envio/previsão"} />
            <Kpi label="Risco alto de atraso" value={fmt.num(data.delay_risk.rows.filter((r: any) => r.risk_level === "high").length)} tone="bad" />
          </div>
          {data.late_rate.result.value === null && (
            <div role="note" className="rounded-md border border-amber-600/40 bg-amber-950/20 p-3 text-sm text-amber-200">
              As fontes atuais não informam datas de envio/previsão/entrega (apenas &quot;Dias de entrega&quot;). Taxa de atraso e risco de atraso
              ficam indisponíveis — nada é estimado. Use o prazo médio de entrega abaixo.
            </div>
          )}
          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Prazo médio envio→entrega por transportadora (dias)" actions={<MetricTag meta={data.lead_time_by_carrier.metric} />}><Bars data={data.lead_time_by_carrier.groups} x="carrier" y="value" name="dias" colorFn={() => "secondary"} /></Card>
            <Card title="Prazo médio envio→entrega por tipo de frete (dias)" actions={<MetricTag meta={data.lead_time_by_shipping_type.metric} />}><Bars data={data.lead_time_by_shipping_type.groups} x="shipping_type" y="value" name="dias" colorFn={() => "primary"} /></Card>
            <Card title="% atrasadas por transportadora" actions={<MetricTag meta={data.late_by_carrier.metric} />}><Bars data={data.late_by_carrier.groups} x="carrier" y="value" name="% atrasadas" unit="%" colorFn={(r) => (r.value > 20 ? "negative" : "primary")} /></Card>
            <Card title="Prazo médio pedido→entrega por transportadora (dias)" actions={<MetricTag meta={data.delivery_days_by_carrier.metric} />}><Bars data={data.delivery_days_by_carrier.groups} x="carrier" y="value" name="dias" colorFn={() => "secondary"} /></Card>
            <Card title="Prazo médio pedido→entrega por tipo de frete (dias)" actions={<MetricTag meta={data.delivery_days_by_shipping_type.metric} />}><Bars data={data.delivery_days_by_shipping_type.groups} x="shipping_type" y="value" name="dias" colorFn={() => "primary"} /></Card>
            <Card title="% atrasadas por tipo de frete" actions={<MetricTag meta={data.late_by_shipping_type.metric} />}><Bars data={data.late_by_shipping_type.groups} x="shipping_type" y="value" name="% atrasadas" unit="%" /></Card>
          </div>
          <Card title="Scorecard de transportadoras (mês)" subtitle="Gold de domínio · logistics_carrier_scorecard · % atraso e prazos dependem das datas sintéticas">
            <DataTable rows={data.scorecard.rows} maxHeight={360} columns={[
              { key: "carrier", label: "Transportadora" }, { key: "month", label: "Mês" }, { key: "deliveries", label: "Entregas" },
              { key: "late_rate", label: "% atraso", render: (r: any) => <span className={r.late_rate > 20 ? "text-rose-300" : ""}>{fmt.pct(r.late_rate)}</span> },
              { key: "avg_delay_days", label: "Atraso médio (d)" }, { key: "avg_lead_time_days", label: "Prazo médio (d)" },
              { key: "evaluations", label: "Avaliações" }, { key: "nps", label: "NPS" },
            ]} />
          </Card>
          <Card title="Pedidos com risco de atraso" actions={data.delay_risk.meta?.is_demo ? <SyntheticBadge demoRows /> : undefined} subtitle="Heurística determinística v1.0: atraso já ocorrido, tempo decorrido vs. previsto e taxa recente de atraso da transportadora.">
            <DataTable rows={data.delay_risk.rows} maxHeight={420} columns={[
              { key: "order_id", label: "Pedido", render: (r: any) => <code className="text-xs">{r.order_id}</code> }, { key: "carrier", label: "Transportadora" },
              { key: "state", label: "UF" }, { key: "estimated_delivery_date", label: "Previsão", render: (r: any) => fmt.day(r.estimated_delivery_date) },
              { key: "days_overdue", label: "Dias em atraso" }, { key: "risk_score", label: "Pontuação" },
              { key: "risk_level", label: "Risco", render: (r: any) => <Badge tone={r.risk_level === "high" ? "red" : r.risk_level === "medium" ? "amber" : "gray"}>{RISK_LABEL[r.risk_level] || r.risk_level}</Badge> },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
