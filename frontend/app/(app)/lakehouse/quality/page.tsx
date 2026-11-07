"use client";
import { useState } from "react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Kpi, Loading, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function QualityPage() {
  const q = useApi<any>("/data/quality");
  const qr = useApi<any[]>("/data/quality/quarantine");
  const [tab, setTab] = useState("rules");
  const s = q.data?.summary || {};
  return (
    <>
      <PageHeader kicker="Governança" title="Qualidade de dados" subtitle="Regras declarativas e versionadas. Erros enviam registros para quarentena (com motivo e conteúdo original); alertas sinalizam sem descartar." />
      <ErrorBox error={q.error || qr.error} onRetry={q.reload} />
      {q.loading && !q.data && <Loading />}
      {q.data && (
        <>
          <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-5">
            <Kpi label="Regras avaliadas" value={s.rules_evaluated ?? "—"} />
            <Kpi label="Aprovadas" value={s.passed ?? "—"} tone="good" />
            <Kpi label="Alertas" value={s.warnings ?? "—"} tone="warn" />
            <Kpi label="Erros" value={s.errors ?? "—"} tone="bad" />
            <Kpi label="Em quarentena" value={s.quarantined_total ?? "—"} hint={Object.entries(s.quarantined_by_dataset || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")} />
          </div>
          <Tabs tabs={[{ key: "rules", label: "Resultados por regra" }, { key: "quarantine", label: "Quarentena" }]} active={tab} onChange={setTab} />
          {tab === "rules" && <Card subtitle={`Execução ${q.data.pipeline_run_id || "—"}`}><DataTable rows={q.data.results} columns={[
            { key: "rule_key", label: "Regra", render: (r: any) => <div><code className="text-xs">{r.rule_key}</code><div className="text-xs text-slate-500">{r.description}</div></div> },
            { key: "dataset", label: "Conjunto de dados" },
            { key: "severity", label: "Severidade", render: (r: any) => <Badge tone={r.severity === "error" ? "red" : r.severity === "warning" ? "amber" : "gray"}>{r.severity}</Badge> },
            { key: "rule_version", label: "Versão" }, { key: "checked", label: "Verificados", render: (r: any) => fmt.num(r.checked) },
            { key: "failed", label: "Falhas", render: (r: any) => fmt.num(r.failed) }, { key: "fail_rate", label: "% falha", render: (r: any) => fmt.pct(r.fail_rate, 2) },
            { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
            { key: "sample", label: "Amostra", render: (r: any) => <code className="text-[11px] text-slate-400">{(r.sample || []).join(", ")}</code> },
          ]} /></Card>}
          {tab === "quarantine" && <Card><DataTable rows={qr.data || []} maxHeight={600} empty="Nenhum registro em quarentena." columns={[
            { key: "dataset", label: "Conjunto de dados" }, { key: "record_key", label: "Chave" },
            { key: "reasons", label: "Motivos", render: (r: any) => <div className="flex flex-wrap gap-1">{r.reasons.map((x: string) => <Badge key={x} tone="red">{x}</Badge>)}</div> },
            { key: "payload", label: "Registro", render: (r: any) => <code className="text-[11px] text-slate-400">{JSON.stringify(r.payload).slice(0, 180)}</code> },
          ]} /></Card>}
        </>
      )}
    </>
  );
}
