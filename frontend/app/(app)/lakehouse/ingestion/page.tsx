"use client";
import { fmt } from "@/components/labels";
import { Card, DataTable, DemoBadge, ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function IngestionPage() {
  const { data, error, loading, reload } = useApi<any[]>("/data/ingestion-runs", { limit: 200 });
  return (
    <>
      <PageHeader kicker="L1 · Ingestão" title="Histórico de ingestão" subtitle="Cada execução grava um arquivo Bronze append-only, com identificador de execução, versão de schema e cursor incremental. Falhas são registradas, nunca silenciadas." />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} columns={[
        { key: "id", label: "Execução", render: (r: any) => <code className="text-xs">{r.id}</code> },
        { key: "source_key", label: "Fonte", render: (r: any) => <span>{r.source_key} {!!r.is_demo && <DemoBadge />}</span> },
        { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
        { key: "records_ingested", label: "Registros" }, { key: "records_failed", label: "Falhas" }, { key: "pages", label: "Páginas" },
        { key: "schema_version", label: "Esquema" },
        { key: "cursor_after", label: "Cursor", render: (r: any) => <code className="text-xs">{r.cursor_before || "∅"} → {r.cursor_after || "∅"}</code> },
        { key: "bronze_path", label: "Arquivo Bronze", render: (r: any) => <code className="text-[11px] text-slate-400">{r.bronze_path || "—"}</code> },
        { key: "started_at", label: "Início", render: (r: any) => fmt.date(r.started_at) },
        { key: "error", label: "Erro", render: (r: any) => r.error ? <span className="text-rose-300">{r.error}</span> : "—" },
      ]} /></Card>}
    </>
  );
}
