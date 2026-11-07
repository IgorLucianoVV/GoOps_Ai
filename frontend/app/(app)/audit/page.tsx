"use client";
import { useState } from "react";
import { PageHeader } from "@/components/ui";
import AuditTable from "@/features/AuditTable";
import { ENTITY_LABEL } from "@/components/labels";

export default function AuditPage() {
  const [entity, setEntity] = useState("");
  return (
    <>
      <PageHeader kicker="Governança" title="Trilha de auditoria" subtitle="Registro imutável de ações de usuários, agentes e sistema (segredos são redigidos)."
        actions={<select className="input" value={entity} onChange={(e) => setEntity(e.target.value)}>
          <option value="">Todas as entidades</option>
          {["incident", "operation", "metric", "source", "pipeline", "user", "platform"].map((e) => <option key={e} value={e}>{ENTITY_LABEL[e] || e}</option>)}
        </select>} />
      <AuditTable path="/audit" query={{ entity_type: entity, limit: 500 }} />
    </>
  );
}
