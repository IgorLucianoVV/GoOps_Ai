"use client";
import Link from "next/link";
import { ArrowRight, Plus } from "lucide-react";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

export default function SectorsPage() {
  const { data, error, loading, reload } = useApi<any[]>("/sectors");
  const { can } = useAuth();
  return (
    <>
      <PageHeader kicker="Setores" title="Setores"
        subtitle="Cada setor reúne seus conjuntos de dados, métricas, painel e agentes — tudo configurado na interface, sem código."
        actions={can("data:write") && <Link href="/setores/novo" className="btn-primary"><Plus size={14} /> Novo setor / conjunto</Link>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && data.length === 0 && <Empty title="Nenhum setor" hint="Crie o primeiro setor conectando uma fonte de dados." />}
      {data && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((s) => (
            <Card key={s.key} title={s.name} subtitle={s.description || undefined}
              actions={s.status !== "active" && <Badge tone="amber">{s.status === "planned" ? "planejado" : "inativo"}</Badge>}>
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge>{s.datasets} conjunto(s)</Badge><Badge>{s.metrics} métrica(s)</Badge><Badge>{s.agents} agente(s)</Badge>
                {s.has_dashboard && <Badge tone="teal">painel</Badge>}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href={`/setores/${s.key}`} className="btn-ghost">Abrir setor <ArrowRight size={14} /></Link>
                {s.builtin_page && <Link href={s.builtin_page} className="btn-ghost">Análise dedicada</Link>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
