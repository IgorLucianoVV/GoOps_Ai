"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card, DataTable, ErrorBox, Loading, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function SemanticPage({ searchParams }: { searchParams: { scope?: string } }) {
  const [scope, setScope] = useState(searchParams?.scope || "all");
  useEffect(() => { setScope(searchParams?.scope || "all"); }, [searchParams?.scope]);
  const { data, error, loading, reload } = useApi<any[]>("/semantic/metrics", scope === "all" ? {} : { scope });
  return (
    <>
      <PageHeader kicker="Governança semântica" title="Catálogo de métricas"
        subtitle="Registro semântico corporativo (definições oficiais compartilhadas) + Registro semântico de domínio (métricas próprias, versionadas). Métricas de domínio nunca são apresentadas como equivalentes às corporativas quando usam critérios diferentes." />
      <Tabs tabs={[{ key: "all", label: "Todas" }, { key: "corporate", label: "Métricas corporativas" }, { key: "domain", label: "Métricas de domínio" }]} active={scope} onChange={setScope} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} columns={[
        { key: "metric_key", label: "Métrica", render: (r: any) => <Link href={`/semantic/metrics/${r.metric_key}`} className="hover:text-brand-400"><div className="text-slate-100">{r.name}</div><code className="text-xs text-slate-500">{r.metric_key}</code></Link> },
        { key: "scope", label: "Escopo", render: (r: any) => <Badge tone={r.scope === "corporate" ? "teal" : "blue"}>{r.scope === "corporate" ? "Corporativa" : `Domínio: ${r.domain}`}</Badge> },
        { key: "formula_text", label: "Definição", render: (r: any) => <span className="text-xs text-slate-300">{r.formula_text}</span> },
        { key: "relationship", label: "Relação", render: (r: any) => <span className="text-xs text-slate-400">{r.relationship}</span> },
        { key: "unit", label: "Unidade" }, { key: "version", label: "Versão", render: (r: any) => <code>v{r.version}</code> },
        { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> }, { key: "owner", label: "Responsável" },
      ]} /></Card>}
    </>
  );
}
