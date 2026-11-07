"use client";
import Link from "next/link";
import { useState } from "react";
import { fmt, generatedByLabel } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, JsonBlock, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";

export default function MetricPage({ params }: { params: { key: string } }) {
  const { data, error, loading, reload } = useApi<any>(`/semantic/metrics/${params.key}`);
  const value = useApi<any>(`/semantic/metrics/${params.key}/value`);
  const { can } = useAuth();
  const action = useAction();
  const [description, setDescription] = useState("");
  const [definition, setDefinition] = useState("");
  const [note, setNote] = useState("");
  const [explain, setExplain] = useState<any>(null);
  const [explaining, setExplaining] = useState(false);
  const doExplain = async () => {
    setExplaining(true);
    try { const r = await api.get(`/semantic/metrics/${params.key}/explain`); setExplain(r.data); }
    catch (e: any) { setExplain({ explanation: e.message, generated_by: "erro" }); }
    finally { setExplaining(false); }
  };

  const propose = async () => {
    const changes: any = {};
    if (description) changes.description = description;
    if (definition) {
      try { changes.formula_definition = JSON.parse(definition); } catch { alert("JSON da definição inválido"); return; }
    }
    if (await action.run(`/semantic/metrics/${params.key}/versions`, { changes, change_note: note })) { setNote(""); reload(); }
  };
  const review = async (version: string, approve: boolean) => {
    if (await action.run(`/semantic/metrics/${params.key}/approve`, { version, approve, note: approve ? "aprovado" : "rejeitado" })) { reload(); value.reload(); }
  };

  return (
    <>
      <PageHeader kicker={data ? (data.scope === "corporate" ? "Registro semântico corporativo" : `Registro semântico de domínio · ${data.domain}`) : "Métrica"}
        title={data?.name || params.key} subtitle={data?.description}
        actions={<><Badge tone="teal" className="font-mono">{params.key} v{data?.version}</Badge><Link className="btn-ghost" href={`/lakehouse/lineage?node=metric:${params.key}`}>Linhagem</Link></>} />
      <ErrorBox error={error || action.error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Definição oficial" className="lg:col-span-2">
              <div className="space-y-3 text-sm">
                <div className="rounded-md bg-ink-950 p-3 font-mono text-[13px] text-brand-400">{data.formula_text}</div>
                <div className="grid grid-cols-2 gap-3">
                  <div><span className="label">Unidade</span><div>{data.unit}</div></div>
                  <div><span className="label">Status</span><div><StatusBadge status={data.status} /></div></div>
                  <div><span className="label">Responsável</span><div>{data.owner}</div></div>
                  <div><span className="label">Fontes</span><div>{data.source_datasets.join(", ")}</div></div>
                  <div><span className="label">Dimensões</span><div>{data.dimensions.join(", ") || "—"}</div></div>
                  <div><span className="label">Relação</span><div className="text-slate-300">{data.relationship}</div></div>
                </div>
                <div>
                  <button className="btn-ghost" disabled={explaining} onClick={doExplain}>{explaining ? "Gerando…" : "Explicar métrica"}</button>
                  {explain && <div className="mt-2 rounded-md border border-ink-600 p-3 text-sm text-slate-200">{explain.explanation}
                    <div className="mt-1"><Badge tone={explain.generated_by === "deterministic" ? "gray" : "violet"}>{generatedByLabel(explain.generated_by)}</Badge>{explain.fallback_reason && <span className="ml-2 text-xs text-slate-500">{explain.fallback_reason}</span>}</div></div>}
                </div>
                <div><span className="label">Definição declarativa (executada por funções controladas)</span><JsonBlock value={{ formula_definition: data.formula_definition, filters: data.filters }} /></div>
              </div>
            </Card>
            <Card title="Valor atual" subtitle="Calculado pelo backend governado">
              {value.error ? <ErrorBox error={value.error} /> : value.data ? (
                <>
                  <div className="text-4xl font-semibold text-white">{fmt.num(value.data.result?.value, 2)}</div>
                  <div className="text-xs text-slate-500">{data.unit} · n = {fmt.num(value.data.result?.n)}</div>
                  <JsonBlock value={value.data.result} maxHeight={180} />
                </>
              ) : <Loading />}
            </Card>
          </div>
          <Card title="Versões e aprovações" subtitle="Toda alteração gera nova versão pendente; quem propõe não aprova (segregação de funções).">
            <DataTable rows={data.versions} columns={[
              { key: "version", label: "Versão", render: (r: any) => <span><code>v{r.version}</code> {r.is_current && <Badge tone="green">vigente</Badge>}</span> },
              { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status === "approved" ? "approved" : r.status} /> },
              { key: "change_note", label: "Justificativa" }, { key: "proposed_by", label: "Proposto por" },
              { key: "reviewed_by", label: "Revisado por" }, { key: "proposed_at", label: "Data", render: (r: any) => fmt.date(r.proposed_at) },
              { key: "a", label: "", render: (r: any) => r.status === "pending" && can("semantic:read") ? (
                <div className="flex gap-1"><button className="btn-primary" onClick={() => review(r.version, true)} disabled={action.busy}>Aprovar</button>
                  <button className="btn-danger" onClick={() => review(r.version, false)} disabled={action.busy}>Rejeitar</button></div>) : null },
            ]} />
          </Card>
          {(can("semantic:write") || can("semantic:write_corporate")) && (
            <Card title="Propor alteração" subtitle="Alterações de fórmula/filtros geram versão MAJOR. Definições são validadas (tipos e operadores permitidos).">
              <div className="grid gap-3 md:grid-cols-2">
                <textarea className="input h-28" placeholder="Nova descrição (opcional)" value={description} onChange={(e) => setDescription(e.target.value)} />
                <textarea className="input h-28 font-mono text-xs" placeholder='Nova formula_definition em JSON (opcional)' value={definition} onChange={(e) => setDefinition(e.target.value)} />
              </div>
              <input className="input mt-3 w-full" placeholder="Justificativa (obrigatória)" value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn-primary mt-3" disabled={action.busy || note.length < 5 || (!description && !definition)} onClick={propose}>Enviar para aprovação</button>
            </Card>
          )}
          <Card title="Auditoria da métrica">
            <DataTable rows={data.audit} columns={[
              { key: "ts", label: "Data", render: (r: any) => fmt.date(r.ts) }, { key: "actor_id", label: "Ator" },
              { key: "action", label: "Ação" }, { key: "details", label: "Detalhes" },
            ]} />
          </Card>
        </div>
      )}
    </>
  );
}
