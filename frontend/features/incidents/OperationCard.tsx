"use client";
import { useState } from "react";
import { Check, X } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, ErrorBox, JsonBlock, StatusBadge } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";
import type { Operation } from "@/types/api";
import WhatIf from "./WhatIf";

export default function OperationCard({ op, onChange, compact = false }: { op: Operation; onChange: () => void; compact?: boolean }) {
  const { can } = useAuth();
  const action = useAction();
  const [note, setNote] = useState("");
  const confirm = useConfirm();
  const decide = async (approve: boolean) => {
    const ok = await confirm(approve
      ? { title: `Aprovar "${op.title}"?`, confirmLabel: "Aprovar e executar (simulado)",
          description: `Impacta: ${op.impacted_areas.join(", ")}. Risco ${op.risk}. A execução nesta versão é SIMULADA e ficará registrada na auditoria.` }
      : { title: `Rejeitar "${op.title}"?`, confirmLabel: "Rejeitar", tone: "danger",
          description: "A ação não será executada. Se todas as ações do incidente forem rejeitadas, ele volta para investigação." });
    if (!ok) return;
    const r = await action.run(`/operations/${op.id}/${approve ? "approve" : "reject"}`, { note }, undefined,
      { success: approve ? "Ação aprovada" : "Ação rejeitada", successDescription: approve ? "O fluxo do incidente foi retomado." : undefined });
    if (r) onChange();
  };
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium text-white">{op.title}</div>
          <div className="mt-0.5 text-sm text-slate-400">{op.description}</div>
        </div>
        <div className="flex flex-wrap gap-1">
          <StatusBadge status={op.status} />
          <Badge tone={op.risk === "high" ? "red" : op.risk === "medium" ? "amber" : "gray"}>risco {op.risk}</Badge>
          {op.requires_approval && <Badge tone="amber">requer aprovação humana</Badge>}
        </div>
      </div>
      <div className={`mt-3 grid gap-3 text-xs ${compact ? "grid-cols-1" : "md:grid-cols-3"}`}>
        <div><div className="label mb-1">Áreas impactadas</div>{op.impacted_areas.map((a) => <Badge key={a} className="mr-1">{a}</Badge>)}</div>
        <div><div className="label mb-1">Aprovadores autorizados</div><div className="text-slate-300">{op.approver_roles.join(", ")}</div></div>
        <div><div className="label mb-1">Proposto por</div><code>{op.proposed_by}</code> · {fmt.date(op.created_at)}</div>
      </div>
      {compact ? (
        <details className="mt-2 text-xs"><summary className="cursor-pointer text-slate-400">Detalhes técnicos</summary>
          <div className="mt-2 space-y-2"><JsonBlock value={op.expected_impact} maxHeight={120} /><JsonBlock value={op.params} maxHeight={120} /></div>
        </details>
      ) : (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div><div className="label mb-1">Impacto esperado (estimativa)</div><JsonBlock value={op.expected_impact} maxHeight={140} /></div>
          <div><div className="label mb-1">Parâmetros</div><JsonBlock value={op.params} maxHeight={140} /></div>
        </div>
      )}
      {op.approved_by && <div className="mt-2 text-xs text-slate-400">Decisão: <code>{op.approved_by}</code> em {fmt.date(op.approved_at)} {op.decision_note && `— "${op.decision_note}"`}</div>}
      {op.result && !compact && <div className="mt-3"><div className="label mb-1">Resultado da execução <Badge tone="violet">{op.execution_mode}</Badge></div><JsonBlock value={op.result} maxHeight={160} /></div>}
      {op.status === "pending_approval" && <WhatIf op={op} />}
      <ErrorBox error={action.error} />
      {op.status === "pending_approval" && can("operations:approve") && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input className="input flex-1" placeholder="Observação da decisão (opcional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn-primary" disabled={action.busy} onClick={() => decide(true)}><Check size={14} /> Aprovar</button>
          <button className="btn-danger" disabled={action.busy} onClick={() => decide(false)}><X size={14} /> Rejeitar</button>
        </div>
      )}
    </div>
  );
}
