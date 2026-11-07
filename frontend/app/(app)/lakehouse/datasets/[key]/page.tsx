"use client";
import Link from "next/link";
import { fmt, SCOPE_LABEL } from "@/components/labels";
import { Badge, Card, DataTable, DemoBadge, SyntheticBadge, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function DatasetPage({ params }: { params: { key: string } }) {
  const { data, error, loading, reload } = useApi<any>(`/data/datasets/${params.key}`, { preview: 25 });
  return (
    <>
      <PageHeader kicker={data ? `${data.layer} · ${SCOPE_LABEL[data.scope] || data.scope}${data.domain ? " · " + data.domain : ""}` : "Conjunto de dados"} title={data?.name || params.key}
        subtitle={data?.description} actions={<>{data?.is_demo && <DemoBadge />}{data?.synthetic_fields?.length > 0 && <SyntheticBadge fields={data.synthetic_fields} />}<Link className="btn-ghost" href={`/lakehouse/lineage?node=dataset:${params.key}`}>Ver linhagem</Link></>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          <div className="grid gap-4 md:grid-cols-4">
            <Card title="Grão"><div className="text-sm">{data.grain}</div></Card>
            <Card title="Linhas"><div className="text-xl text-white">{fmt.num(data.row_count)}</div></Card>
            <Card title="Esquema"><div className="text-sm">v{data.schema_version} · {data.format}</div></Card>
            <Card title="Atualizado"><div className="text-sm">{fmt.date(data.last_built_at)}</div><div className="text-xs text-slate-500">{data.last_pipeline_run_id}</div></Card>
          </div>
          <Card title="Transformações aplicadas">
            <DataTable rows={data.transformations} columns={[
              { key: "transform", label: "Transformação" }, { key: "inputs", label: "Entradas", render: (r: any) => r.inputs.join(", ") },
              { key: "rule_version", label: "Versão regra" }, { key: "rows_out", label: "Linhas saída" },
              { key: "executed_at", label: "Executado", render: (r: any) => fmt.date(r.executed_at) }, { key: "actor", label: "Responsável" },
            ]} />
          </Card>
          <Card title="Prévia" subtitle={data.masked_columns.length ? `Colunas mascaradas para seu papel: ${data.masked_columns.join(", ")}` : undefined}>
            {data.preview.length ? (
              <DataTable rows={data.preview} maxHeight={420} columns={Object.keys(data.preview[0]).map((k) => ({ key: k, label: k }))} />
            ) : <div className="text-sm text-slate-500">Sem prévia.</div>}
          </Card>
          <Card title="Dicionário de dados">
            <DataTable rows={data.dictionary} columns={[
              { key: "field", label: "Campo", render: (r: any) => <code className="text-xs">{r.field}</code> }, { key: "business_name", label: "Nome de negócio" },
              { key: "description", label: "Descrição" }, { key: "data_type", label: "Tipo" }, { key: "validation", label: "Validação" },
              { key: "sensitivity", label: "Sens.", render: (r: any) => <Badge tone={r.sensitivity === "pii" ? "amber" : "gray"}>{r.sensitivity}</Badge> },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
