"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Play } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

const LINK: Record<string, string> = {
  sources: "/lakehouse/sources", bronze: "/lakehouse/layer/bronze", silver: "/lakehouse/layer/silver",
  gold_corporate: "/lakehouse/layer/gold_corporate", gold_domain: "/lakehouse/layer/gold_domain", semantic: "/semantic",
};

export default function LakehousePage() {
  const { data, error, loading, reload } = useApi<any>("/data/layers");
  const { can } = useAuth();
  const action = useAction();
  const [last, setLast] = useState<any>(null);
  const run = async (sync: boolean) => { const r = await action.run("/data/pipeline/run", { sync }, undefined, { success: sync ? "Pipeline completo executado" : "Reprocessamento concluído" }); if (r) { setLast(r); reload(); } };

  return (
    <>
      <PageHeader kicker="Lakehouse de dados" title="Camadas de dados"
        subtitle="L0 Fontes → L1 Bronze → L2 Silver → L3 Gold (corporativa + de domínio) → L4 Semântica e inteligência."
        actions={can("data:sync") && <>
          <button className="btn-ghost" disabled={action.busy} onClick={() => run(false)}>Reprocessar (sem ingestão)</button>
          <button className="btn-primary" disabled={action.busy} onClick={() => run(true)}><Play size={14} /> Executar pipeline completo</button>
        </>} />
      <ErrorBox error={action.error || error} onRetry={reload} />
      {last && <div className="mb-4 rounded-md border border-ink-600 p-3 text-sm">Pipeline {last.run_id}: <StatusBadge status={last.status} /> {last.error}</div>}
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="mb-6 flex flex-wrap items-stretch gap-2">
            {data.layers.map((l: any, i: number) => (
              <div key={l.key} className="flex items-center gap-2">
                <Link href={LINK[l.key]} className="card block w-48 p-4 transition hover:border-brand-600">
                  <div className="flex items-center justify-between"><Badge tone="teal">{l.level}</Badge><span className="text-xs text-slate-500">{l.count} itens</span></div>
                  <div className="mt-2 font-semibold text-white">{l.name}</div>
                  <div className="mt-1 text-xs text-slate-400">{l.description}</div>
                  {l.rows !== null && <div className="mt-2 text-xs text-slate-500">{fmt.num(l.rows)} linhas</div>}
                </Link>
                {i < data.layers.length - 1 && <ArrowRight size={16} className="text-slate-600" />}
              </div>
            ))}
          </div>
          <Card title="Execuções do pipeline">
            <DataTable rows={data.pipeline_runs} empty="Nenhuma execução ainda." columns={[
              { key: "id", label: "Execução", render: (r: any) => <code className="text-xs">{r.id}</code> },
              { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
              { key: "steps", label: "Etapas", render: (r: any) => <div className="flex flex-wrap gap-1">{r.steps.map((s: any) => <Badge key={s.step} tone={s.status === "success" ? "green" : "red"}>{s.step}</Badge>)}</div> },
              { key: "triggered_by", label: "Disparado por" },
              { key: "started_at", label: "Início", render: (r: any) => fmt.date(r.started_at) },
              { key: "error", label: "Erro" },
            ]} />
          </Card>
        </>
      )}
    </>
  );
}
