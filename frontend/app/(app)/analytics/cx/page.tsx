"use client";
import Link from "next/link";
import { fmt, DIM_LABEL } from "@/components/labels";
import { Card, DataTable, ErrorBox, Kpi, Loading, MetricTag, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function CxPage() {
  const { data, error, loading, reload } = useApi<any>("/analytics/cx");
  return (
    <>
      <PageHeader kicker="Análises · Gold de CX" title="Experiência do cliente" subtitle="Satisfação, comentários e comportamento dos clientes. A métrica CX de NPS com comentário é de domínio e NÃO equivale ao NPS corporativo."
        actions={<Link href="/analytics/nps" className="btn-ghost">Painel de NPS completo →</Link>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="NPS corporativo" value={fmt.num(data.nps_corporate.result.value, 1)} hint={<MetricTag meta={data.nps_corporate.metric} />} />
            <Kpi label="NPS c/ comentário (domínio CX)" value={fmt.num(data.nps_commented_domain.result.value, 1)} hint={<MetricTag meta={data.nps_commented_domain.metric} />} />
            <Kpi label="Clientes avaliadores" value={fmt.num(data.customers.summary.customers_with_evaluation)} hint={`${fmt.num(data.customers.summary.customers)} clientes`} />
            <Kpi label="Última avaliação = detrator" value={fmt.num(data.customers.summary.customers_last_detractor)} tone="bad" />
          </div>
          <Card title="Fatores de detração (maiores taxas por mês × dimensão)" subtitle="Gold de domínio · cx_detractor_drivers">
            <DataTable rows={data.drivers.rows.filter((r: any) => r.evaluations >= 20)} maxHeight={480} columns={[
              { key: "eval_month", label: "Mês" }, { key: "dimension", label: "Dimensão", render: (r: any) => DIM_LABEL[r.dimension] || r.dimension },
              { key: "value", label: "Valor" }, { key: "evaluations", label: "n" },
              { key: "detractor_rate", label: "% detratores", render: (r: any) => fmt.pct(r.detractor_rate) }, { key: "nps", label: "NPS" },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
