"use client";
import { useState } from "react";
import { Bot, Search, User, XCircle } from "lucide-react";
import { CATEGORY_LABEL, fmt, generatedByLabel } from "@/components/labels";
import { Badge, Card, DemoBadge, ErrorBox, JsonBlock, Loading, PageHeader, SeverityBadge, StatusBadge } from "@/components/ui";
import OperationCard from "@/features/incidents/OperationCard";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";
import type { Incident, IncidentEvent } from "@/types/api";

const EVENT_LABEL: Record<string, string> = {
  detected: "Incidente detectado", anomaly_detected: "Anomalia identificada", supervisor: "Supervisor", tool_call: "Consulta governada",
  data_validation: "Validação de dados", data_quality_check: "Qualidade de dados", lineage_check: "Linhagem", investigation_started: "Investigação iniciada",
  analysis: "Análise", hypothesis: "Hipótese", recommendation: "Recomendação", approval_requested: "Aprovação solicitada",
  human_decision: "Decisão humana", summary: "Resumo", execution: "Execução", validation: "Validação de resultado", status_changed: "Status", agent_error: "Erro de agente", tool_denied: "Acesso negado",
};

export default function IncidentPage({ params }: { params: { id: string } }) {
  const inc = useApi<Incident>(`/incidents/${params.id}`);
  const tl = useApi<IncidentEvent[]>(`/incidents/${params.id}/timeline`);
  const { can } = useAuth();
  const action = useAction();
  const [hideTools, setHideTools] = useState(true);
  const [note, setNote] = useState("");
  const reload = () => { inc.reload(); tl.reload(); };
  const investigate = async () => { if (await action.run(`/incidents/${params.id}/investigate`, undefined, undefined, { success: "Nova investigação concluída" })) reload(); };
  const confirm = useConfirm();
  const close = async () => {
    if (!(await confirm({ title: "Encerrar este incidente?", description: "Ele poderá ser reaberto depois. A justificativa ficará na linha do tempo.", confirmLabel: "Encerrar", tone: "danger" }))) return;
    if (await action.run(`/incidents/${params.id}/close`, { note: note || "Encerrado manualmente" }, undefined, { success: "Incidente encerrado" })) reload();
  };
  const d = inc.data;
  const events = (tl.data || []).filter((e) => !hideTools || e.event_type !== "tool_call");

  return (
    <>
      <PageHeader kicker={d ? `${CATEGORY_LABEL[d.category]} · domínio ${d.domain}` : "Incidente"} title={d?.title || params.id} subtitle={d?.description}
        actions={d && <>
          {d.is_demo && <DemoBadge />}<SeverityBadge severity={d.severity} /><StatusBadge status={d.status} />
          {can("agents:execute") && d.status !== "closed" && <button className="btn-ghost" disabled={action.busy} onClick={investigate}><Search size={14} /> Solicitar nova investigação</button>}
        </>} />
      <ErrorBox error={inc.error || action.error} onRetry={reload} />
      {inc.loading && !d && <Loading />}
      {d && (
        <div className="grid gap-5 xl:grid-cols-[1fr_440px]">
          <div className="space-y-5">
            {d.summary && (() => {
              const ev = [...(tl.data || [])].reverse().find((e) => e.event_type === "summary");
              const by = ev?.data?.generated_by;
              return <Card title="Resumo executivo" subtitle="Gerado pelo Supervisor ao final do fluxo"
                actions={by && <Badge tone={by === "deterministic" ? "gray" : "violet"}>{by === "deterministic" ? "determinístico" : `gerado por LLM · ${by.replace("llm:", "")}`}</Badge>}>
                <div className="whitespace-pre-line text-sm text-slate-100">{d.summary}</div></Card>;
            })()}
            <Card title="Causa provável" subtitle="Hipótese principal do Agente de Investigação (contribuição ≠ causalidade)">
              <div className="text-sm text-slate-100">{d.root_cause || "Ainda não investigado."}</div>
            </Card>
            <Card title="Hipóteses e evidências">
              {(d.hypotheses || []).length === 0 && <div className="text-sm text-slate-500">Sem hipóteses.</div>}
              <div className="space-y-3">
                {(d.hypotheses || []).map((h: any) => (
                  <div key={h.id} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-sm text-slate-100">{h.statement}</div>
                      <div className="text-right"><div className="text-lg font-semibold text-white">{(h.confidence * 100).toFixed(0)}%</div><Badge tone={h.confidence >= 0.7 ? "green" : h.confidence >= 0.4 ? "amber" : "gray"}>confiança {h.confidence_label}</Badge></div>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded bg-ink-700"><div className="h-full bg-brand-500" style={{ width: `${h.confidence * 100}%` }} /></div>
                    <details className="mt-2"><summary className="cursor-pointer text-xs text-slate-400">{h.evidence.length} evidência(s)</summary><JsonBlock value={h.evidence} maxHeight={300} /></details>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Recomendações e aprovações" subtitle={d.recommendation?.summary ? `${d.recommendation.summary} · gerado por: ${generatedByLabel(d.recommendation.generated_by)}` : undefined}>
              <div className="space-y-3">
                {(d.operations || []).length === 0 && <div className="text-sm text-slate-500">Nenhuma ação proposta.</div>}
                {(d.operations || []).map((op) => <OperationCard key={op.id} op={op} onChange={reload} />)}
              </div>
            </Card>
            {d.result && <Card title="Validação do resultado"><JsonBlock value={d.result} /></Card>}
            <Card title="Sinal original (Agente Monitor)"><JsonBlock value={d.signal} /></Card>
            {can("incidents:write") && d.status !== "closed" && (
              <Card title="Encerrar incidente">
                <div className="flex gap-2"><input className="input flex-1" placeholder="Justificativa" value={note} onChange={(e) => setNote(e.target.value)} />
                  <button className="btn-danger" disabled={action.busy} onClick={close}><XCircle size={14} /> Encerrar</button></div>
              </Card>
            )}
          </div>
          <Card title="Linha do tempo operacional" actions={<label className="flex items-center gap-1.5 text-xs text-slate-400"><input type="checkbox" checked={hideTools} onChange={(e) => setHideTools(e.target.checked)} /> ocultar consultas</label>}>
            <ol className="relative space-y-4 border-l border-ink-600 pl-5">
              {events.map((e) => (
                <li key={e.id} className="relative">
                  <span className="absolute -left-[27px] top-0.5 grid h-5 w-5 place-items-center rounded-full border border-ink-600 bg-ink-900">
                    {e.actor_type === "user" ? <User size={11} className="text-amber-300" /> : <Bot size={11} className="text-brand-400" />}
                  </span>
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
                    <span>#{e.seq}</span><span>{fmt.date(e.ts)}</span><Badge tone={e.actor_type === "user" ? "amber" : "teal"}>{e.actor}</Badge>
                    <span className="font-semibold text-slate-300">{EVENT_LABEL[e.event_type] || e.event_type}</span>
                    {e.data?.generated_by && <Badge tone={e.data.generated_by === "deterministic" ? "gray" : "violet"}>{generatedByLabel(e.data.generated_by)}</Badge>}
                    {e.is_demo && <Badge tone="violet">demo</Badge>}
                  </div>
                  <div className="mt-0.5 text-sm text-slate-200">{e.message}</div>
                  {e.data && e.event_type !== "status_changed" && <details><summary className="cursor-pointer text-[11px] text-slate-500">dados</summary><JsonBlock value={e.data} maxHeight={220} /></details>}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      )}
    </>
  );
}
