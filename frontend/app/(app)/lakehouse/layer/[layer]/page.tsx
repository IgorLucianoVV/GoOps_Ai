"use client";
import Link from "next/link";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, DemoBadge, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

const META: Record<string, { level: string; title: string; text: string }> = {
  bronze: { level: "L1", title: "Bronze", text: "Payloads originais preservados com origem, data de ingestão, execução e versão do schema. Nunca alterados; permitem reprocessamento." },
  silver: { level: "L2", title: "Silver", text: "Normalização, tipagem, deduplicação controlada, integração por order_id e controle de qualidade. Inválidos vão para quarentena com rastreabilidade." },
  gold_corporate: { level: "L3", title: "Gold corporativa", text: "Base analítica corporativa compartilhada, com grão explícito por dataset." },
  gold_domain: { level: "L3", title: "Gold de domínio", text: "Conjuntos especializados por domínio (CX, Logística, Produtos). Reutilizam a Gold corporativa sem alterar definições oficiais. Finance preparado para o futuro." },
};

export default function LayerPage({ params }: { params: { layer: string } }) {
  const m = META[params.layer] || { level: "", title: params.layer, text: "" };
  const { data, error, loading, reload } = useApi<any[]>("/data/datasets", { layer: params.layer });
  return (
    <>
      <PageHeader kicker={`${m.level} · Lakehouse de dados`} title={m.title} subtitle={m.text} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} empty="Nenhum conjunto de dados nesta camada. Execute o pipeline." columns={[
        { key: "name", label: "Conjunto de dados", render: (r: any) => params.layer === "bronze" ? <div><div>{r.name}</div><code className="text-xs text-slate-500">{r.key}</code></div> : <Link href={`/lakehouse/datasets/${r.key}`} className="hover:text-brand-400"><div className="text-slate-100">{r.name}</div><code className="text-xs text-slate-500">{r.key}</code></Link> },
        { key: "domain", label: "Domínio", render: (r: any) => r.domain ? <Badge tone="blue">{r.domain}</Badge> : <Badge tone="teal">corporate</Badge> },
        { key: "grain", label: "Grão" },
        { key: "row_count", label: "Linhas", render: (r: any) => fmt.num(r.row_count) },
        { key: "format", label: "Formato" }, { key: "schema_version", label: "Esquema v." },
        { key: "sensitivity", label: "Sensibilidade", render: (r: any) => <Badge tone={r.sensitivity === "pii" ? "amber" : "gray"}>{r.sensitivity}</Badge> },
        { key: "last_built_at", label: "Atualizado", render: (r: any) => <span>{fmt.date(r.last_built_at)} {r.is_demo && <DemoBadge />}</span> },
      ]} /></Card>}
    </>
  );
}
