"use client";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Loading } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function AuditTable({ path, query }: { path: string; query?: Record<string, any> }) {
  const { data, error, loading, reload } = useApi<any[]>(path, query);
  return (
    <>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} maxHeight={720} columns={[
        { key: "ts", label: "Data", render: (r: any) => fmt.date(r.ts) },
        { key: "actor", label: "Ator", render: (r: any) => <span><Badge tone={r.actor_type === "agent" ? "violet" : r.actor_type === "system" ? "gray" : "teal"}>{r.actor_type}</Badge> <code className="text-xs">{r.actor_id}</code></span> },
        { key: "action", label: "Ação", render: (r: any) => <code className="text-xs text-white">{r.action}</code> },
        { key: "entity", label: "Entidade", render: (r: any) => <span className="text-xs">{r.entity_type} · <code>{r.entity_id || "—"}</code></span> },
        { key: "details", label: "Detalhes", render: (r: any) => <code className="text-[11px] text-slate-400">{JSON.stringify(r.details).slice(0, 200)}</code> },
      ]} /></Card>}
    </>
  );
}
