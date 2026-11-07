"use client";
import { useState } from "react";
import { Badge, Card, DataTable, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function DictionaryPage() {
  const [q, setQ] = useState("");
  const [dataset, setDataset] = useState("");
  const ds = useApi<any[]>("/data/datasets");
  const { data, error, loading, reload } = useApi<any[]>("/data/dictionary", { q, dataset });
  return (
    <>
      <PageHeader kicker="Governança" title="Dicionário de dados" subtitle="Nome técnico, nome de negócio, descrição, tipo, origem, formato, obrigatoriedade, validação e relacionamentos de cada campo."
        actions={<>
          <select className="input" value={dataset} onChange={(e) => setDataset(e.target.value)}>
            <option value="">Todos os conjuntos de dados</option>
            {(ds.data || []).filter((d: any) => d.layer !== "bronze").map((d: any) => <option key={d.key} value={d.key}>{d.key}</option>)}
          </select>
          <input className="input" placeholder="Buscar campo…" value={q} onChange={(e) => setQ(e.target.value)} />
        </>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} maxHeight={700} columns={[
        { key: "dataset_key", label: "Conjunto de dados", render: (r: any) => <code className="text-xs">{r.dataset_key}</code> },
        { key: "field", label: "Campo", render: (r: any) => <code className="text-xs text-white">{r.field}</code> },
        { key: "business_name", label: "Nome de negócio" }, { key: "description", label: "Descrição" },
        { key: "data_type", label: "Tipo" }, { key: "origin", label: "Origem" }, { key: "format", label: "Formato" },
        { key: "required", label: "Obrig." }, { key: "validation", label: "Validação" }, { key: "relationships", label: "Relacionamentos" },
        { key: "sensitivity", label: "Sens.", render: (r: any) => <Badge tone={r.sensitivity === "pii" ? "amber" : "gray"}>{r.sensitivity}</Badge> },
      ]} /></Card>}
    </>
  );
}
