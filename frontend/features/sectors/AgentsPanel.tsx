"use client";
import { useState } from "react";
import Link from "next/link";
import { Bot, Play, Plus, Trash2 } from "lucide-react";
import { CATEGORY_LABEL, SEVERITY_LABEL, fmt } from "@/components/labels";
import { Badge, Card, Empty } from "@/components/ui";
import Markdown from "@/features/ask/Markdown";
import { useAction } from "@/hooks/useApi";
import { useConfirm } from "@/hooks/useConfirm";

const FREQ = [
  { v: "", label: "Só manual" }, { v: "60", label: "A cada hora" }, { v: "1440", label: "Diário" }, { v: "10080", label: "Semanal" },
];
const RULES: Record<string, string> = { drop: "Queda de pelo menos", rise: "Alta de pelo menos", above: "Acima de", below: "Abaixo de" };
const TEMPLATES: Record<string, string> = { metric_monitor: "Monitor de métrica", action_task: "Tarefa com ação",
  driver_analysis: "Investigação de causas", summary: "Resumo do período", llm_task: "Agente com instruções (IA)" };
const ACTIONS: Record<string, string> = { sector_operational_review: "Revisão operacional do setor",
  sector_customer_contact: "Contato com clientes do segmento (exige aprovação)" };
const STATUS_TONE: Record<string, any> = { ok: "green", alert: "red", skipped: "amber", no_data: "gray", error: "red" };
const STATUS_LABEL: Record<string, string> = { ok: "OK", alert: "Alerta", skipped: "Ignorado", no_data: "Sem dados", error: "Erro" };

const slug = (t: string) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);

/** Agentes do setor criados a partir de modelos (monitor de métrica, resumo), com permissões restritas ao setor. */
export default function AgentsPanel({ domain, agents, metrics, canEdit, onChange }:
  { domain: string; agents: any[]; metrics: any[]; canEdit: boolean; onChange: () => void }) {
  const action = useAction();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const active = metrics.filter((m) => m.status === "active");
  const [f, setF] = useState<any>({ name: "", template: "metric_monitor", metric_key: active[0]?.metric_key || "", rule: "drop",
    threshold: "1", segment_by: "", min_n: "20", severity: "medium", category: "other", metric_keys: [] as string[], interval: "1440",
    use_ai: false, dimensions: [] as string[], action_type: "sector_operational_review", action_note: "" });
  const metric = metrics.find((m) => m.metric_key === f.metric_key);

  const run = async (key: string) => { if (await action.run(`/sectors/agents/${key}/run`, {}, undefined, { success: "Agente executado" })) onChange(); };
  const remove = async (a: any) => {
    if (await confirm({ title: `Excluir o agente "${a.name}"?`, description: "O histórico de execuções e incidentes é mantido.", confirmLabel: "Excluir", tone: "danger" })
      && await action.run(`/sectors/agents/${a.key}/delete`, {}, undefined, { success: "Agente excluído" })) onChange();
  };
  const save = async () => {
    const monitor = { metric_key: f.metric_key, rule: f.rule, threshold: Number(f.threshold), segment_by: f.segment_by || null,
      min_n: Number(f.min_n), severity: f.severity, category: f.category };
    const config = f.template === "metric_monitor" ? monitor
      : f.template === "action_task" ? { ...monitor, action_type: f.action_type, action_note: f.action_note }
      : f.template === "driver_analysis" ? { metric_key: f.metric_key, dimensions: f.dimensions, min_n: Number(f.min_n) }
      : { metric_keys: f.metric_keys, use_ai: f.use_ai };
    const body = { key: `${domain}_${slug(f.name)}`.slice(0, 50), name: f.name, template: f.template, config,
      interval_minutes: f.interval ? Number(f.interval) : null, enabled: true };
    if (await action.run(`/sectors/${domain}/agents`, body, undefined, { success: "Agente criado" })) { setOpen(false); onChange(); }
  };

  return (
    <div className="space-y-4">
      {canEdit && !open && <button className="btn-primary" onClick={() => setOpen(true)}><Plus size={14} /> Novo agente</button>}
      {open && (
        <Card title="Novo agente do setor" subtitle="Escolha um modelo e preencha os parâmetros. O agente só lê métricas aprovadas do setor e pode abrir incidentes — nunca executa ações sozinho.">
          <div className="grid gap-3 md:grid-cols-3">
            <label><span className="label">Nome</span><input className="input mt-1 w-full" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Ex.: Monitor da nota" /></label>
            <label><span className="label">Modelo</span>
              <select className="input mt-1 w-full" value={f.template} onChange={(e) => setF({ ...f, template: e.target.value })}>
                {Object.entries(TEMPLATES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label><span className="label">Frequência</span>
              <select className="input mt-1 w-full" value={f.interval} onChange={(e) => setF({ ...f, interval: e.target.value })}>
                {FREQ.map((x) => <option key={x.v} value={x.v}>{x.label}</option>)}</select></label>
          </div>
          {f.template === "driver_analysis" && (
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <label><span className="label">Métrica investigada</span>
                <select className="input mt-1 w-full" value={f.metric_key} onChange={(e) => setF({ ...f, metric_key: e.target.value, dimensions: [] })}>
                  {active.map((m) => <option key={m.metric_key} value={m.metric_key}>{m.name}</option>)}</select></label>
              <fieldset className="md:col-span-2"><legend className="label mb-1">Explicar por (dimensões)</legend>
                <div className="flex flex-wrap gap-2">{(metric?.dimensions || []).filter((d: string) => d !== "month").map((d: string) => (
                  <label key={d} className="inline-flex items-center gap-1.5 rounded-md border border-ink-700 px-2 py-1 text-sm">
                    <input type="checkbox" checked={f.dimensions.includes(d)} onChange={(e) => setF({ ...f, dimensions: e.target.checked ? [...f.dimensions, d] : f.dimensions.filter((x: string) => x !== d) })} />{d}</label>))}</div></fieldset>
              <label><span className="label">Amostra mínima por segmento</span>
                <input className="input mt-1 w-full" type="number" min={1} value={f.min_n} onChange={(e) => setF({ ...f, min_n: e.target.value })} /></label>
            </div>
          )}
          {f.template === "driver_analysis" ? null : f.template === "metric_monitor" || f.template === "action_task" ? (
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <label className="md:col-span-2"><span className="label">Métrica observada</span>
                <select className="input mt-1 w-full" value={f.metric_key} onChange={(e) => setF({ ...f, metric_key: e.target.value, segment_by: "" })}>
                  {active.map((m) => <option key={m.metric_key} value={m.metric_key}>{m.name}</option>)}</select></label>
              <label><span className="label">Regra (mês a mês)</span>
                <select className="input mt-1 w-full" value={f.rule} onChange={(e) => setF({ ...f, rule: e.target.value })}>
                  {Object.entries(RULES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
              <label><span className="label">Limite {metric?.unit ? `(${metric.unit})` : ""}</span>
                <input className="input mt-1 w-full" type="number" step="any" value={f.threshold} onChange={(e) => setF({ ...f, threshold: e.target.value })} /></label>
              <label><span className="label">Também por segmento (opcional)</span>
                <select className="input mt-1 w-full" value={f.segment_by} onChange={(e) => setF({ ...f, segment_by: e.target.value })}>
                  <option value="">Só o total</option>
                  {(metric?.dimensions || []).filter((d: string) => d !== "month").map((d: string) => <option key={d} value={d}>{d}</option>)}</select></label>
              <label><span className="label">Amostra mínima (n)</span>
                <input className="input mt-1 w-full" type="number" min={1} value={f.min_n} onChange={(e) => setF({ ...f, min_n: e.target.value })} /></label>
              <label><span className="label">Severidade do incidente</span>
                <select className="input mt-1 w-full" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>
                  {Object.entries(SEVERITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
              <label><span className="label">Categoria</span>
                <select className="input mt-1 w-full" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
              {f.template === "action_task" && <>
                <label className="md:col-span-2"><span className="label">Ação proposta (vai para aprovação conforme a política)</span>
                  <select className="input mt-1 w-full" value={f.action_type} onChange={(e) => setF({ ...f, action_type: e.target.value })}>
                    {Object.entries(ACTIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
                <label className="md:col-span-2"><span className="label">{f.action_type === "sector_customer_contact" ? "Mensagem" : "Orientação"}</span>
                  <input className="input mt-1 w-full" value={f.action_note} onChange={(e) => setF({ ...f, action_note: e.target.value })} /></label>
              </>}
              {active.length === 0 && <p className="text-xs text-amber-300 md:col-span-4">Nenhuma métrica aprovada neste setor ainda — aprove as métricas em Governança semântica › Aprovações.</p>}
            </div>
          ) : (
            <fieldset className="mt-3"><legend className="label mb-1">Métricas do resumo</legend>
              <div className="flex flex-wrap gap-2">{active.map((m) => (
                <label key={m.metric_key} className="inline-flex items-center gap-1.5 rounded-md border border-ink-700 px-2 py-1 text-sm">
                  <input type="checkbox" checked={f.metric_keys.includes(m.metric_key)}
                    onChange={(e) => setF({ ...f, metric_keys: e.target.checked ? [...f.metric_keys, m.metric_key] : f.metric_keys.filter((k: string) => k !== m.metric_key) })} />
                  {m.name}</label>))}</div>
              <label className="mt-2 inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={f.use_ai} onChange={(e) => setF({ ...f, use_ai: e.target.checked })} />
                Acrescentar narrativa executiva por IA (usa o modelo configurado; sem modelo, fica só o resumo determinístico)</label></fieldset>
          )}
          <div className="mt-4 flex gap-2">
            <button className="btn-primary" disabled={action.busy || !f.name.trim()} onClick={save}>Criar agente</button>
            <button className="btn-ghost" onClick={() => setOpen(false)}>Cancelar</button>
          </div>
        </Card>
      )}
      {agents.length === 0 && !open ? (
        <Empty title="Nenhum agente neste setor" hint="Crie um monitor para ser avisado quando uma métrica piorar, ou um resumo periódico." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {agents.map((a) => (
            <Card key={a.key} title={<span className="inline-flex items-center gap-2"><Bot size={15} aria-hidden /> {a.name}</span>}
              subtitle={`${TEMPLATES[a.template] || a.template} · ${a.interval_minutes ? FREQ.find((x) => x.v === String(a.interval_minutes))?.label || `a cada ${a.interval_minutes} min` : "só manual"}`}
              actions={canEdit && <span className="inline-flex gap-1">
                <button className="btn-ghost h-8" disabled={action.busy} onClick={() => run(a.key)}><Play size={13} /> Executar</button>
                <button className="btn-danger h-8 px-2" aria-label={`Excluir ${a.name}`} onClick={() => remove(a)}><Trash2 size={13} /></button></span>}>
              <div className="text-xs text-slate-500">
                {a.template === "llm_task"
                  ? <>{a.config.instructions.slice(0, 160)}{a.config.instructions.length > 160 ? "…" : ""} <Link className="text-brand-500 underline underline-offset-2" href={`/agents/custom/${a.key}`}>Abrir em Agentes de IA</Link></>
                  : a.template === "driver_analysis"
                  ? <>Investiga <code>{a.config.metric_key}</code> por {a.config.dimensions.join(", ")} (n ≥ {a.config.min_n}).</>
                  : a.template === "metric_monitor" || a.template === "action_task"
                  ? <>Observa <code>{a.config.metric_key}</code>: {RULES[a.config.rule]?.toLowerCase()} {a.config.threshold}{a.config.segment_by ? `, também por ${a.config.segment_by}` : ""} (n ≥ {a.config.min_n}).{a.template === "action_task" && <> Propõe: {ACTIONS[a.config.action_type]}.</>}</>
                  : <>Métricas: {a.config.metric_keys.map((k: string) => <code key={k} className="mr-1">{k}</code>)}</>}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                {a.last_status ? <Badge tone={STATUS_TONE[a.last_status] || "gray"}>{STATUS_LABEL[a.last_status] || a.last_status}</Badge> : <Badge>nunca executado</Badge>}
                {a.last_run_at && <span className="text-xs text-slate-500">{fmt.date(a.last_run_at)}</span>}
                {a.last_result?.message && <span className="text-slate-300">{a.last_result.message}</span>}
              </div>
              {a.last_result?.incidents?.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm">{a.last_result.incidents.map((i: any) => (
                  <li key={i.id}><Link className="text-brand-500 underline underline-offset-2" href={`/incidents/${i.id}`}>{i.title}</Link>{!i.created && <span className="text-xs text-slate-500"> (já aberto)</span>}
                    {i.operation && <> · <Link className="text-brand-500 underline underline-offset-2" href="/operations">ação {i.operation.status === "pending_approval" ? "aguardando aprovação" : "aprovada pela política"}</Link></>}</li>))}</ul>
              )}
              {a.last_result?.narrative_md && <div className="mt-3 rounded-md border border-violet-500/40 p-3 text-sm">
                <Badge tone="violet">Narrativa por IA · {String(a.last_result.narrative_generated_by).replace("llm:", "")}</Badge>
                <div className="mt-2"><Markdown text={a.last_result.narrative_md} /></div></div>}
              {(a.last_result?.summary_md || a.last_result?.report_md) && <div className="mt-3 rounded-md bg-ink-950 p-3 text-sm"><Markdown text={a.last_result.summary_md || a.last_result.report_md} /></div>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
