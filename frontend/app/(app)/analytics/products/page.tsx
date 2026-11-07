"use client";
import { Bars } from "@/components/charts";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Loading, MetricTag, PageHeader, SyntheticBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function ProductsPage() {
  const { data, error, loading, reload } = useApi<any>("/analytics/products");
  return (
    <>
      <PageHeader kicker="Análises · Gold de produtos" title="Produtos" subtitle="Qualidade, avaliações e frequência de reclamações por produto e linha."
        actions={data?.performance?.meta?.synthetic_fields?.length > 0 && <SyntheticBadge fields={data.performance.meta.synthetic_fields} demoRows={data.performance.meta.is_demo} />} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          <Card title="Taxa de reclamação por linha" subtitle={data.complaint_rate_by_line.metric.relationship} actions={<MetricTag meta={data.complaint_rate_by_line.metric} />}>
            <Bars data={data.complaint_rate_by_line.groups} x="product_line" y="value" name="% com tema negativo" unit="%" colorFn={(r) => (r.value > 25 ? "negative" : "secondary")} />
          </Card>
          <Card title="Desempenho por produto" subtitle="Gold corporativa · gold_product_performance">
            <DataTable rows={data.performance.rows} columns={[
              { key: "product_name", label: "Produto" }, { key: "product_line", label: "Linha" }, { key: "orders", label: "Pedidos" },
              { key: "evaluations", label: "Avaliações" }, { key: "avg_score", label: "Nota média" },
              { key: "detractor_rate", label: "% detratores", render: (r: any) => fmt.pct(r.detractor_rate) }, { key: "nps", label: "NPS" },
              { key: "late_rate", label: "% atraso", render: (r: any) => fmt.pct(r.late_rate) },
            ]} />
          </Card>
          <Card title="Temas de reclamação por linha" subtitle="Gold de domínio · products_complaint_frequency">
            <DataTable rows={data.complaints.rows} columns={[
              { key: "product_line", label: "Linha" }, { key: "theme_label", label: "Tema" },
              { key: "polarity", label: "Polaridade", render: (r: any) => <Badge tone={r.polarity === "negative" ? "red" : "green"}>{r.polarity}</Badge> },
              { key: "mentions", label: "Menções" }, { key: "detractor_mentions", label: "Entre detratores" },
              { key: "mention_rate", label: "% avaliações", render: (r: any) => fmt.pct(r.mention_rate) },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
