"use client";
import Link from "next/link";
import { useState } from "react";
import { Card, ErrorBox, Loading, PageHeader, Tabs } from "@/components/ui";
import OperationCard from "@/features/incidents/OperationCard";
import { useApi } from "@/hooks/useApi";
import type { Operation } from "@/types/api";

export default function OperationsPage() {
  const [tab, setTab] = useState("pending_approval");
  const { data, error, loading, reload } = useApi<Operation[]>("/operations", tab === "all" ? {} : { status: tab });
  return (
    <>
      <PageHeader kicker="Operações" title="Ações e aprovações" subtitle="Ações recomendadas pelos agentes a partir do catálogo governado. Ações em pagamentos, pedidos, estoque ou clientes exigem aprovação explícita. Execução nesta versão: SIMULADA." />
      <Tabs tabs={[{ key: "pending_approval", label: "Aguardando aprovação" }, { key: "approved", label: "Aprovadas" }, { key: "executed", label: "Executadas" }, { key: "rejected", label: "Rejeitadas" }, { key: "all", label: "Todas" }]} active={tab} onChange={setTab} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && data.length === 0 && <Card><div className="text-sm text-slate-500">Nenhuma ação neste estado.</div></Card>}
      <div className="space-y-3">
        {(data || []).map((op) => (
          <div key={op.id}>
            {op.incident_id && <Link href={`/incidents/${op.incident_id}`} className="mb-1 inline-block text-xs text-brand-400">Incidente {op.incident_id} →</Link>}
            <OperationCard op={op} onChange={reload} />
          </div>
        ))}
      </div>
    </>
  );
}
