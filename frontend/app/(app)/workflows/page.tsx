"use client";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function WorkflowsPage() {
  const { data, meta, error, loading, reload } = useApi<any[]>("/workflows");
  const def = meta.definition;
  return (
    <>
      <PageHeader kicker="Orquestração" title="Fluxos de trabalho" subtitle="Execuções do grafo de estados do Supervisor. O fluxo é interrompido para aprovação humana e retomado após a decisão." />
      <ErrorBox error={error} onRetry={reload} />
      {def && (
        <Card className="mb-5" title={`Definição: ${def.name}`}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {def.nodes.map((n: string, i: number) => (
              <span key={n} className="flex items-center gap-2"><Badge tone={n === "await_approval" ? "amber" : "teal"}>{n}{n === "await_approval" ? " ⏸ humano" : ""}</Badge>{i < def.nodes.length - 1 && <ArrowRight size={13} className="text-slate-600" />}</span>
            ))}
          </div>
          <div className="mt-2 text-xs text-slate-500">Arestas condicionais: plan_resolution → (await_approval | execute | finalize); await_approval → (execute | finalize).</div>
        </Card>
      )}
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} empty="Nenhum fluxo de trabalho executado." columns={[
        { key: "id", label: "Execução", render: (r: any) => <code className="text-xs">{r.id}</code> },
        { key: "incident_id", label: "Incidente", render: (r: any) => r.incident_id ? <Link className="text-brand-400" href={`/incidents/${r.incident_id}`}>{r.incident_id}</Link> : "—" },
        { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
        { key: "current_node", label: "Nó atual", render: (r: any) => r.current_node ? <Badge tone="amber">{r.current_node}</Badge> : "—" },
        { key: "steps", label: "Passos", render: (r: any) => <div className="flex flex-wrap gap-1">{r.steps.map((s: any, i: number) => <Badge key={i} tone={s.status === "success" ? "green" : s.status === "interrupted" ? "amber" : "red"}>{s.node}</Badge>)}</div> },
        { key: "started_at", label: "Início", render: (r: any) => fmt.date(r.started_at) },
        { key: "error", label: "Erro" },
      ]} /></Card>}
    </>
  );
}
