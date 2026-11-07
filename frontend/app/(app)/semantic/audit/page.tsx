"use client";
import { PageHeader } from "@/components/ui";
import AuditTable from "@/features/AuditTable";

export default function SemanticAuditPage() {
  return (<><PageHeader kicker="Governança semântica" title="Auditoria semântica" subtitle="Criação, propostas, aprovações e rejeições de métricas." /><AuditTable path="/semantic/audit" /></>);
}
