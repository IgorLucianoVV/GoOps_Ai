"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, FlaskConical, Pause, Pencil, Play, Sparkles, Trash2 } from "lucide-react";
import { CATEGORY_LABEL, DOMAIN_LABEL, SEVERITY_LABEL, fmt } from "@/components/labels";
import { Badge, Card, Empty, ErrorBox, JsonBlock, Kpi, Loading, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import { AgentRunResult, RunTrace } from "@/features/agents/parts";
import { useAction, useApi } from "@/hooks/useApi";
import { useConfirm } from "@/hooks/useConfirm";

const FREQ: Record<string, string> = { "60": "A cada hora", "1440": "Diário", "10080": "Semanal" };
const OUTPUT: Record<string, string> = { report: "Relatório no histórico", team_channel: "Relatório no canal do time",
  incident: "Incidente quando houver alerta", propose_action: "Incidente + proposta de ação (com aprovação)" };
const CHECK: Record<string, string> = { cites_metric: "Cita a métrica", uses_tool: "Consulta a ferramenta", contains: "Contém o texto",
  not_contains: "Não contém o texto", alert: "Alerta esperado", max_lines: "No máximo N linhas" };

function RunRow({ r }: { r: any }) {
  const [open, setOpen] = useState(false);
  const o = r.output || {};
  const failedChecks = (o.checks || []).filter((c: any) => c.ok === false).length;
  return (
    <li className="rounded-lg border border-ink-700">
      <button className="flex w-full flex-wrap items-center gap-2 p-3 text-left text-sm" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <span className="text-slate-300">{fmt.date(r.started_at)}</span>
        <StatusBadge status={r.status} />
        {o.status === "alert" && <Badge tone="red">alerta</Badge>}
        {o.generated_by && (o.generated_by === "deterministic" ? <Badge>sem IA</Badge> : <Badge tone="violet">{String(o.generated_by).replace("llm:", "")}</Badge>)}
        {failedChecks > 0 && <Badge tone="red">{failedChecks} critério(s) reprovado(s)</Badge>}
        <span className="text-xs text-slate-500">{r.input?.triggered_by === "scheduler" ? "agendador" : "manual"} · US$ {fmt.num(r.cost_usd, 4)}</span>
        <span className="ml-auto truncate text-xs text-slate-400">{o.message}</span>
      </button>
      {open && (
        <div className="grid gap-4 border-t border-ink-700 p-3 lg:grid-cols-2">
          <div><div className="mb-2 text-xs font-semibold text-slate-300">Resultado</div><AgentRunResult r={o} /></div>
          <div><div className="mb-2 text-xs font-semibold text-slate-300">Passo a passo</div>{r.trace ? <RunTrace steps={r.trace} /> : <JsonBlock value={o} maxHeight={260} />}</div>
        </div>
      )}
    </li>
  );
}

export default function CustomAgentPage({ params }: { params: { key: string } }) {
  const { data, error, loading, reload } = useApi<any>(`/agents/custom/${params.key}`);
  const action = useAction();
  const confirm = useConfirm();
  const router = useRouter();
  const [tab, setTab] = useState("overview");
  const [test, setTest] = useState<any>(null);
  const c = data?.config || {};
  const llm = data?.template === "llm_task";
  const h = data?.health || {};

  const runTest = async () => {
    setTab("test");
    const r = await action.run("/agents/custom/test", { key: data.key, domain: data.domain, name: data.name, config: data.config }, undefined,
      { success: "Teste concluído", successDescription: "Nada foi gravado: sem incidente, sem ação e sem mensagem no canal." });
    if (r) setTest(r);
  };
  const run = async () => {
    const effects = c.output === "incident" || c.output === "propose_action" || c.output === "team_channel";
    if (effects && !(await confirm({ title: "Executar para valer?", confirmLabel: "Executar",
      description: c.output === "team_channel" ? "O relatório será publicado no canal do time." : "Se a IA sinalizar alerta, um incidente será aberto" + (c.output === "propose_action" ? " e uma ação será proposta para aprovação." : ".") + " Para experimentar sem efeito, use “Testar”." }))) return;
    if (await action.run(`/agents/custom/${params.key}/run`, {}, undefined, { success: "Agente executado" })) { setTab("activity"); reload(); }
  };
  const toggle = async () => {
    if (await action.run(`/agents/custom/${params.key}/enabled`, { enabled: !data.enabled }, undefined, { success: data.enabled ? "Agente pausado" : "Agente retomado" })) reload();
  };
  const remove = async () => {
    if (await confirm({ title: `Excluir o agente "${data?.name}"?`, description: "O histórico de execuções, incidentes e auditoria é mantido.", confirmLabel: "Excluir", tone: "danger" })
      && await action.run(`/agents/custom/${params.key}/delete`, {}, undefined, { success: "Agente excluído" })) router.push("/agents");
  };

  return (
    <>
      <PageHeader kicker="Agente personalizado" title={data?.name || params.key}
        subtitle={data ? `${data.template_label} · ${DOMAIN_LABEL[data.domain] || data.domain} · ${data.interval_minutes ? FREQ[String(data.interval_minutes)] || `a cada ${data.interval_minutes} min` : "só manual"} · criado por ${String(data.owner || "").replace(/^(user|system):/, "")}` : undefined}
        actions={data?.can_edit && <>
          {llm && <button className="btn-primary" disabled={action.busy} onClick={runTest}><FlaskConical size={14} /> Testar</button>}
          <button className="btn-ghost" disabled={action.busy} onClick={run}><Play size={14} /> Executar agora</button>
          <button className="btn-ghost" disabled={action.busy} onClick={toggle}>{data.enabled ? <><Pause size={14} /> Pausar</> : <><Play size={14} /> Retomar</>}</button>
          {llm ? <Link className="btn-ghost" href={`/agents/custom/${params.key}/editar`}><Pencil size={14} /> Editar</Link>
            : <Link className="btn-ghost" href={`/setores/${data.domain}`}><Pencil size={14} /> Editar no setor</Link>}
          <button className="btn-danger px-2" aria-label="Excluir agente" disabled={action.busy} onClick={remove}><Trash2 size={14} /></button>
        </>} />
      <ErrorBox error={error || action.error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && !data.enabled && <div role="status" className="mb-4 rounded-lg border border-amber-500/40 bg-amber-950 p-3 text-sm text-amber-200">Agente pausado: o agendador não o executa. Testes e execuções manuais continuam disponíveis.</div>}
      {data && (
        <>
          <Tabs active={tab} onChange={setTab} tabs={[
            { key: "overview", label: "Visão geral" },
            ...(llm ? [{ key: "test", label: "Testar" }] : []),
            { key: "activity", label: `Atividade (${data.runs})` },
          ]} />

          {tab === "overview" && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <Kpi label="Execuções (7 dias)" value={fmt.num(h.runs)} hint={`${data.runs} no total · sucesso ${fmt.pct(data.success_rate)}`} />
                <Kpi label="Alertas (7 dias)" value={fmt.num(h.alerts ?? 0)} tone={h.alerts ? "warn" : "default"} hint="incidentes abertos pelo agente" />
                <Kpi label="Sem IA (contingência)" value={h.fallback_rate == null ? "—" : fmt.pct(h.fallback_rate)} tone={h.fallback_rate > 50 ? "warn" : "default"} hint="execuções em que o modelo não respondeu" />
                <Kpi label="Custo (7 dias)" value={`US$ ${fmt.num(h.cost_usd, 4)}`} hint={`US$ ${fmt.num(data.cost_usd, 4)} no total`} />
              </div>
              <div className="grid gap-4 lg:grid-cols-3">
                <Card className="lg:col-span-2" title={llm ? <span className="inline-flex items-center gap-2"><Sparkles size={15} aria-hidden /> Missão</span> : "Configuração"}>
                  {llm ? <p className="whitespace-pre-line text-sm text-slate-200">{c.instructions}</p> : <JsonBlock value={c} maxHeight={220} />}
                  {llm && (c.checks || []).length > 0 && (
                    <div className="mt-4"><div className="label mb-1">Critérios de aceite</div>
                      <ul className="list-disc pl-5 text-sm text-slate-300">{c.checks.map((x: any, i: number) => <li key={i}>{CHECK[x.type]}: <code>{x.value}</code></li>)}</ul></div>
                  )}
                </Card>
                <Card title="Como trabalha">
                  <dl className="space-y-2 text-sm">
                    {llm && <>
                      <div><dt className="label">Ferramentas</dt><dd className="mt-1 flex flex-wrap gap-1">{c.tools.map((t: string) => <Badge key={t}>{t}</Badge>)}</dd></div>
                      <div><dt className="label">Saída</dt><dd className="text-slate-200">{OUTPUT[c.output]}{c.severity && <> · {SEVERITY_LABEL[c.severity]} · {CATEGORY_LABEL[c.category]}</>}</dd></div>
                      <div><dt className="label">Modelo</dt><dd className="text-slate-200">{c.model_id === "default" ? "Padrão (níveis 3/2)" : c.model_id}</dd></div>
                    </>}
                    <div><dt className="label">Permissões</dt><dd className="mt-1 flex flex-wrap gap-1">{data.permissions.map((x: string) => <Badge key={x} tone="teal">{x}</Badge>)}</dd></div>
                  </dl>
                </Card>
              </div>
              <Card title="Último resultado" subtitle={data.last_run_at ? fmt.date(data.last_run_at) : undefined}>
                {data.last_result ? <AgentRunResult r={data.last_result} /> : <Empty title="Ainda não executado" hint="Use “Testar” para ver o resultado sem efeitos, ou “Executar agora”." />}
              </Card>
            </div>
          )}

          {tab === "test" && (
            <div className="space-y-4">
              <Card title="Teste sem efeito colateral" subtitle="Roda a configuração atual com dados reais e o mesmo modelo, mas não abre incidente, não propõe ação e não publica no canal. O custo de IA é registrado."
                actions={<button className="btn-primary" disabled={action.busy} onClick={runTest}><FlaskConical size={14} /> {action.busy ? "Executando…" : test ? "Testar de novo" : "Testar agora"}</button>}>
                {test ? <AgentRunResult r={test} showTrace /> : <p className="text-sm text-slate-500">Nenhum teste nesta sessão. O resultado mostra o relatório, os critérios de aceite e o passo a passo (instrução, chamadas ao modelo, ferramentas e decisão).</p>}
              </Card>
            </div>
          )}

          {tab === "activity" && (
            data.recent_runs.length === 0 ? <Empty title="Nenhuma execução ainda" /> : (
              <ul className="space-y-2" aria-label="Execuções">{data.recent_runs.map((r: any) => <RunRow key={r.id} r={r} />)}</ul>
            )
          )}
        </>
      )}
    </>
  );
}
