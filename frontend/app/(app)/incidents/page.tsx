"use client";
import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";
import { CATEGORY_LABEL, DOMAIN_LABEL, fmt, SEVERITY_LABEL, STATUS_LABEL } from "@/components/labels";
import { Card, DataTable, DemoBadge, ErrorBox, Loading, PageHeader, SeverityBadge, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

export default function IncidentsPage() {
  const [f, setF] = useState<Record<string, string>>({});
  const { data, error, loading, reload } = useApi<any[]>("/incidents", f);
  const { can } = useAuth();
  const action = useAction();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", category: "orders", domain: "corporate", severity: "medium" });
  const create = async () => { if (await action.run("/incidents", form, undefined, { success: "Incidente registrado" })) { setOpen(false); reload(); } };
  const sel = (k: string, opts: Record<string, string>, label: string) => (
    <select className="input" value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })}>
      <option value="">{label}</option>{Object.entries(opts).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
  return (
    <>
      <PageHeader kicker="Operações" title="Incidentes" subtitle="Detectados automaticamente pelo Agente Monitor ou registrados manualmente. Cada incidente mantém evidências, investigação, recomendações, aprovações, execuções e histórico."
        actions={<>{sel("status", STATUS_LABEL as any, "Status")}{sel("severity", SEVERITY_LABEL, "Severidade")}{sel("category", CATEGORY_LABEL, "Categoria")}
          {can("incidents:write") && <button className="btn-primary" onClick={() => setOpen(!open)}><Plus size={14} /> Novo incidente</button>}</>} />
      <ErrorBox error={error || action.error} onRetry={reload} />
      {open && (
        <Card className="mb-5" title="Registrar incidente manual">
          <div className="grid gap-3 md:grid-cols-4">
            <input className="input md:col-span-2" placeholder="Título" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{Object.entries(CATEGORY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <select className="input" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>{Object.entries(SEVERITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <textarea className="input md:col-span-3" placeholder="Descrição" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <select className="input" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })}>{["corporate", "cx", "logistics", "products"].map((d) => <option key={d} value={d}>{DOMAIN_LABEL[d] || d}</option>)}</select>
          </div>
          <button className="btn-primary mt-3" disabled={action.busy || form.title.length < 5 || form.description.length < 5} onClick={create}>Registrar</button>
        </Card>
      )}
      {loading && !data && <Loading />}
      {data && <Card><DataTable rows={data} empty="Nenhum incidente encontrado" emptyHint="Ajuste os filtros ou execute um ciclo de monitoramento para que o Agente Monitor avalie os indicadores."
        emptyAction={<Link className="btn-ghost" href="/agents">Ir para Agentes de IA</Link>} columns={[
        { key: "severity", label: "Sev.", render: (r: any) => <SeverityBadge severity={r.severity} /> },
        { key: "title", label: "Incidente", render: (r: any) => <Link href={`/incidents/${r.id}`} className="hover:text-brand-400"><div className="text-slate-100">{r.title}</div><code className="text-xs text-slate-500">{r.id}</code></Link> },
        { key: "category", label: "Categoria", render: (r: any) => CATEGORY_LABEL[r.category] },
        { key: "domain", label: "Domínio" },
        { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
        { key: "source", label: "Origem", render: (r: any) => <span>{r.source} {r.is_demo && <DemoBadge />}</span> },
        { key: "detected_at", label: "Detectado", render: (r: any) => fmt.date(r.detected_at) },
      ]} /></Card>}
    </>
  );
}
