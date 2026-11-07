"use client";
import Link from "next/link";
import { fmt, SCOPE_LABEL } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, JsonBlock, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function ApprovalsPage() {
  const { data, error, loading, reload } = useApi<any[]>("/semantic/approvals");
  return (
    <>
      <PageHeader kicker="Governança semântica" title="Aprovações pendentes" subtitle="Versões de métricas aguardando revisão. Abra a métrica para aprovar ou rejeitar." />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} empty="Nenhuma versão pendente." columns={[
        { key: "metric_key", label: "Métrica", render: (r: any) => <Link className="text-brand-400" href={`/semantic/metrics/${r.metric_key}`}>{r.metric_key}</Link> },
        { key: "scope", label: "Escopo", render: (r: any) => <Badge tone={r.scope === "corporate" ? "teal" : "blue"}>{SCOPE_LABEL[r.scope] || r.scope}{r.domain && r.scope === "domain" ? `: ${r.domain}` : ""}</Badge> },
        { key: "version", label: "Versão proposta", render: (r: any) => <code>v{r.version}</code> },
        { key: "change_note", label: "Justificativa" }, { key: "proposed_by", label: "Proposto por" },
        { key: "proposed_at", label: "Data", render: (r: any) => fmt.date(r.proposed_at) },
        { key: "snapshot", label: "Definição proposta", render: (r: any) => <JsonBlock value={r.snapshot.formula_definition} maxHeight={120} /> },
      ]} /></Card>}
    </>
  );
}
