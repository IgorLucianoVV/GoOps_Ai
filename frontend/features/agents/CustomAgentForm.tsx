"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical, Lock, Plus, Save, X } from "lucide-react";
import { CATEGORY_LABEL, DOMAIN_LABEL, SEVERITY_LABEL } from "@/components/labels";
import { Card, ErrorBox, Loading } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { AgentRunResult } from "./parts";

const FREQ = [
  { v: "", label: "Só manual" }, { v: "60", label: "A cada hora" }, { v: "1440", label: "Diário" }, { v: "10080", label: "Semanal" },
];
const TOOL_LABEL: Record<string, string> = {
  list_metrics: "Listar métricas oficiais", dimension_values: "Valores de dimensões", metric_value: "Valor de métrica",
  metric_breakdown: "Métrica por segmento", nps_monthly: "NPS mês a mês", comment_themes: "Temas de comentários",
  data_quality: "Qualidade dos dados", open_incidents: "Incidentes abertos",
};
const EXAMPLES = [
  { label: "Vigia de NPS por transportadora", output: "incident", tools: ["list_metrics", "dimension_values", "metric_breakdown", "nps_monthly"],
    text: "Compare o NPS do último mês com o mês anterior, no total e por transportadora (carrier). Sinalize alerta se o NPS total cair 3 pontos ou mais, ou se alguma transportadora com n ≥ 30 cair 5 pontos ou mais. No relatório, liste as 3 transportadoras com maior queda e o tamanho da amostra." },
  { label: "Resumo semanal para o time", output: "team_channel", tools: ["nps_monthly", "comment_themes", "open_incidents"],
    text: "Escreva um resumo semanal para o time de CX: evolução do NPS nos últimos 3 meses, os 3 temas mais citados pelos detratores e os incidentes abertos com severidade alta. Termine com uma recomendação objetiva para a semana." },
  { label: "Guardião da qualidade de dados", output: "report", tools: ["data_quality", "open_incidents"],
    text: "Verifique a qualidade dos dados da última execução do pipeline. Aponte regras com falha, registros em quarentena e qual indicador pode ser afetado. Se estiver tudo certo, diga isso em uma linha." },
];
const slug = (t: string) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);

/** Criação/edição de agente com instruções (template llm_task). */
export default function CustomAgentForm({ agent }: { agent?: any }) {
  const opts = useApi<any>("/agents/custom/options");
  const action = useAction();
  const router = useRouter();
  const c = agent?.config || {};
  const [f, setF] = useState<any>({
    name: agent?.name || "", domain: agent?.domain || "", instructions: c.instructions || "",
    tools: c.tools || ["list_metrics", "metric_value", "metric_breakdown"], output: c.output || "report",
    severity: c.severity || "medium", category: c.category || "other", action_type: c.action_type || "sector_operational_review",
    action_note: c.action_note || "", model_id: c.model_id || "default", checks: c.checks || [],
    interval: agent?.interval_minutes ? String(agent.interval_minutes) : "", enabled: agent ? !!agent.enabled : true,
  });
  const o = opts.data;
  const domains = (o?.domains || []).filter((d: any) => d.can_edit);
  const domain = f.domain || (domains.find((d: any) => d.key === "corporate") || domains[0])?.key || "";
  const alertOut = f.output === "incident" || f.output === "propose_action";
  const valid = f.name.trim().length >= 2 && f.instructions.trim().length >= 20 && f.tools.length > 0 && !!domain;
  const set = (patch: any) => setF({ ...f, ...patch });
  const toggleTool = (t: string, on: boolean) => set({ tools: on ? [...f.tools, t] : f.tools.filter((x: string) => x !== t) });
  const [test, setTest] = useState<any>(null);
  const tester = useAction();
  const setCheck = (i: number, patch: any) => set({ checks: f.checks.map((x: any, j: number) => j === i ? { ...x, ...patch } : x) });

  const buildConfig = () => {
    const config: any = { instructions: f.instructions, tools: f.tools, output: f.output, model_id: f.model_id,
      checks: f.checks.filter((x: any) => String(x.value).trim()) };
    if (alertOut) Object.assign(config, { severity: f.severity, category: f.category });
    if (f.output === "propose_action") Object.assign(config, { action_type: f.action_type, action_note: f.action_note });
    return config;
  };
  const runTest = async () => {
    const r = await tester.run("/agents/custom/test", { key: agent?.key || null, domain, name: f.name || "Rascunho", config: buildConfig() }, undefined,
      { success: "Teste concluído", successDescription: "Nada foi gravado." });
    if (r) setTest(r);
  };

  const save = async () => {
    const key = agent?.key || `${domain}_${slug(f.name)}`.slice(0, 50);
    const config = buildConfig();
    const body = { key, domain, name: f.name.trim(), template: "llm_task", config,
      interval_minutes: f.interval ? Number(f.interval) : null, enabled: f.enabled };
    if (await action.run("/agents/custom", body, undefined, { success: agent ? "Agente atualizado" : "Agente criado",
      successDescription: test ? undefined : "Dica: use “Testar” para ver o resultado sem efeitos." })) router.push(`/agents/custom/${key}`);
  };

  if (opts.loading && !o) return <Loading />;
  if (opts.error) return <ErrorBox error={opts.error} onRetry={opts.reload} />;
  if (!agent && domains.length === 0) return <ErrorBox error={{ status: 403, message: "Você não tem permissão de edição em nenhum setor para criar agentes." } as any} />;

  return (
    <div className="space-y-5">
      <Card title="1. Identificação">
        <div className="grid gap-3 md:grid-cols-3">
          <label><span className="label">Nome</span>
            <input className="input mt-1 w-full" value={f.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} placeholder="Ex.: Vigia de NPS por transportadora" /></label>
          <label><span className="label">Setor (escopo de dados e permissões)</span>
            <select className="input mt-1 w-full" value={domain} disabled={!!agent} onChange={(e) => set({ domain: e.target.value })}>
              {(agent ? o.domains : domains).map((d: any) => <option key={d.key} value={d.key}>{DOMAIN_LABEL[d.key] || d.name}</option>)}</select></label>
          <label><span className="label">Frequência</span>
            <select className="input mt-1 w-full" value={f.interval} onChange={(e) => set({ interval: e.target.value })}>
              {FREQ.map((x) => <option key={x.v} value={x.v}>{x.label}</option>)}</select></label>
        </div>
        {agent && <label className="mt-3 inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={f.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> Ativo (desmarque para pausar o agendamento)</label>}
      </Card>

      <Card title="2. Missão (instruções do agente)" subtitle="Descreva em português o que o agente deve verificar, como decidir e o que entregar. Seja específico sobre limites e recortes.">
        {!agent && <div className="mb-2 flex flex-wrap gap-2 text-xs"><span className="text-slate-500">Exemplos:</span>
          {EXAMPLES.map((x) => <button key={x.label} type="button" className="rounded-md border border-ink-700 px-2 py-1 text-slate-300 hover:border-brand-500"
            onClick={() => set({ instructions: x.text, tools: x.tools, output: x.output, name: f.name || x.label })}>{x.label}</button>)}</div>}
        <label htmlFor="mission" className="sr-only">Missão</label>
        <textarea id="mission" className="input w-full text-[13px] leading-relaxed" rows={7} maxLength={4000} value={f.instructions}
          onChange={(e) => set({ instructions: e.target.value })} placeholder="Ex.: Toda segunda, compare o NPS por transportadora com a semana anterior e sinalize alerta se alguma cair 5 pontos com n ≥ 30." />
        <div className="mt-1 text-right text-xs text-slate-500">{f.instructions.length}/4000</div>
        <div className="mt-2 rounded-lg border border-ink-700 bg-ink-950 p-3 text-xs text-slate-400">
          <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-300"><Lock size={12} aria-hidden /> Regras fixas que sempre valem</div>
          Só usa números das ferramentas e cita a métrica · dados de clientes são tratados como dado, nunca como instrução · não executa, aprova nem promete ações · avisa quando o dado é sintético · sem modelo de IA, entrega um resumo determinístico e não sinaliza alerta.
        </div>
      </Card>

      <Card title="3. Ferramentas que o agente pode consultar" subtitle="Somente leitura e governadas (as mesmas do “Pergunte ao GoOps”), executadas com as permissões do setor escolhido.">
        <div className="grid gap-2 md:grid-cols-2">
          {(o.tools || []).map((t: any) => (
            <label key={t.name} className="flex items-start gap-2 rounded-lg border border-ink-700 p-2 text-sm">
              <input type="checkbox" className="mt-1" checked={f.tools.includes(t.name)} onChange={(e) => toggleTool(t.name, e.target.checked)} />
              <span><span className="font-medium text-slate-200">{TOOL_LABEL[t.name] || t.name}</span> <code className="text-[11px] text-slate-500">{t.name}</code>
                <span className="block text-xs text-slate-500">{t.description}</span></span>
            </label>
          ))}
        </div>
      </Card>

      <Card title="4. Saída">
        <fieldset><legend className="sr-only">O que fazer com o resultado</legend>
          <div className="grid gap-2 md:grid-cols-2">
            {Object.entries(o.outputs || {}).map(([k, v]) => (
              <label key={k} className="flex items-center gap-2 rounded-lg border border-ink-700 p-2 text-sm">
                <input type="radio" name="output" checked={f.output === k} onChange={() => set({ output: k })} />{String(v)}</label>
            ))}
          </div>
        </fieldset>
        {alertOut && (
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <label><span className="label">Severidade do incidente</span>
              <select className="input mt-1 w-full" value={f.severity} onChange={(e) => set({ severity: e.target.value })}>
                {(o.severities || []).map((s: string) => <option key={s} value={s}>{SEVERITY_LABEL[s] || s}</option>)}</select></label>
            <label><span className="label">Categoria</span>
              <select className="input mt-1 w-full" value={f.category} onChange={(e) => set({ category: e.target.value })}>
                {(o.categories || []).map((s: string) => <option key={s} value={s}>{CATEGORY_LABEL[s] || s}</option>)}</select></label>
            <p className="self-end text-xs text-slate-500">A IA só sinaliza o alerta; o incidente é aberto pelo sistema, no máximo um por dia por agente.</p>
          </div>
        )}
        {f.output === "propose_action" && (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label><span className="label">Ação proposta (catálogo)</span>
              <select className="input mt-1 w-full" value={f.action_type} onChange={(e) => set({ action_type: e.target.value })}>
                {Object.entries(o.actions || {}).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}</select></label>
            <label><span className="label">Observação para quem aprova</span>
              <input className="input mt-1 w-full" maxLength={500} value={f.action_note} onChange={(e) => set({ action_note: e.target.value })} /></label>
            <p className="text-xs text-slate-500 md:col-span-2">A ação fica aguardando aprovação conforme a política (contato com clientes sempre exige pessoa). O agente nunca aprova nem executa.</p>
          </div>
        )}
      </Card>

      <Card title="5. Modelo de IA">
        <label className="block max-w-md"><span className="label">Modelo</span>
          <select className="input mt-1 w-full" value={f.model_id} onChange={(e) => set({ model_id: e.target.value })}>
            {!(o.models || []).some((m: any) => m.id === "default") && <option value="default">Padrão (níveis 3/2 — não configurado)</option>}
            {(o.models || []).map((m: any) => <option key={m.id} value={m.id} disabled={!m.available && m.id !== f.model_id}>{m.label}{m.available ? "" : " (indisponível)"}</option>)}</select></label>
        <p className="mt-1 text-xs text-slate-500">Modelos e chaves em Configurações › Modelos e chaves. Custo registrado por execução, com os limites diário e por execução.</p>
      </Card>

      <Card title="6. Critérios de aceite (opcional)" subtitle="Verificações automáticas aplicadas em todo teste e execução. Além delas, o sistema sempre confere se os números vieram das ferramentas e se o alerta foi sinalizado.">
        {f.checks.length === 0 && <p className="mb-2 text-sm text-slate-500">Nenhum critério. Ex.: “Cita a métrica METRIC_NPS_001”, “Contém o texto transportadora”, “No máximo 12 linhas”.</p>}
        <ul className="space-y-2">
          {f.checks.map((ch: any, i: number) => (
            <li key={i} className="flex flex-wrap items-end gap-2">
              <label><span className="sr-only">Tipo do critério {i + 1}</span>
                <select className="input" value={ch.type} onChange={(e) => setCheck(i, { type: e.target.value, value: e.target.value === "alert" ? "sim" : "" })}>
                  {Object.entries(o.check_types || {}).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}</select></label>
              <label className="min-w-[200px] flex-1"><span className="sr-only">Valor do critério {i + 1}</span>
                {ch.type === "alert" ? (
                  <select className="input w-full" value={ch.value} onChange={(e) => setCheck(i, { value: e.target.value })}><option value="sim">sim</option><option value="nao">não</option></select>
                ) : ch.type === "uses_tool" ? (
                  <select className="input w-full" value={ch.value} onChange={(e) => setCheck(i, { value: e.target.value })}>
                    <option value="">Escolha…</option>{f.tools.map((t: string) => <option key={t} value={t}>{TOOL_LABEL[t] || t}</option>)}</select>
                ) : (
                  <input className="input w-full" value={ch.value} maxLength={120} inputMode={ch.type === "max_lines" ? "numeric" : undefined}
                    placeholder={ch.type === "cites_metric" ? "METRIC_NPS_001" : ch.type === "max_lines" ? "12" : "texto"} onChange={(e) => setCheck(i, { value: e.target.value })} />
                )}</label>
              <button type="button" className="btn-ghost px-2" aria-label={`Remover critério ${i + 1}`} onClick={() => set({ checks: f.checks.filter((_: any, j: number) => j !== i) })}><X size={14} /></button>
            </li>
          ))}
        </ul>
        {f.checks.length < 10 && <button type="button" className="btn-ghost mt-2" onClick={() => set({ checks: [...f.checks, { type: "cites_metric", value: "" }] })}><Plus size={14} /> Adicionar critério</button>}
      </Card>

      <Card title="7. Testar antes de salvar" subtitle="Roda esta configuração agora, com dados reais e o modelo escolhido, sem abrir incidente, sem propor ação e sem publicar no canal."
        actions={<button className="btn-ghost" disabled={tester.busy || !valid} onClick={runTest}><FlaskConical size={14} /> {tester.busy ? "Executando…" : test ? "Testar de novo" : "Testar"}</button>}>
        {test ? <AgentRunResult r={test} showTrace /> : <p className="text-sm text-slate-500">{valid ? "Clique em “Testar” para ver o relatório, os critérios e o passo a passo." : "Preencha nome, missão (20+ caracteres) e ao menos uma ferramenta para testar."}</p>}
        <ErrorBox error={tester.error} />
      </Card>

      <ErrorBox error={action.error} />
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-primary" disabled={action.busy || !valid} onClick={save}><Save size={14} /> {agent ? "Salvar alterações" : "Criar agente"}</button>
        <button className="btn-ghost" onClick={() => router.back()}>Cancelar</button>
        {valid && !test && <span className="text-xs text-slate-500">Recomendado: teste antes de salvar.</span>}
        {test?.checks_ok === false && <span className="text-xs text-rose-300">O último teste reprovou em algum critério.</span>}
      </div>
    </div>
  );
}
