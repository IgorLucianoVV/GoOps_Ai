"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowRight, FlaskConical, ShieldCheck } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, Empty, ErrorBox, Kpi, Loading, PageHeader } from "@/components/ui";
import { CaseItem } from "@/features/agents/validation";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

const FLOW = [
  { k: "data", t: "Gerar dados" }, { k: "monitor", t: "Monitor" }, { k: "validation", t: "Validação" },
  { k: "investigation", t: "Investigação" }, { k: "resolution", t: "Resolução" }, { k: "supervisor", t: "Aprovação humana" },
  { k: "support", t: "Atendimento" }, { k: "sector", t: "Setores" }, { k: "custom", t: "Com instruções" }, { k: "ai", t: "IA e custo" },
];

export default function ValidationPage() {
  const { data, error, loading, reload } = useApi<any>("/agents/validation");
  const { can } = useAuth();
  const action = useAction();
  const [withAi, setWithAi] = useState(false);
  const [report, setReport] = useState<any>(null);
  const r = report || data;
  const run = async () => {
    const out = await action.run("/agents/validation/run", { with_ai: withAi }, undefined,
      { success: "Validação concluída", successDescription: "Ambiente isolado: os dados da aplicação não foram alterados." });
    if (out) { setReport(out); reload(); }
  };
  const byKey: Record<string, any> = Object.fromEntries((r?.agents || []).map((a: any) => [a.key, a]));
  return (
    <>
      <PageHeader kicker="Agentes de IA" title="Validação ponta a ponta"
        subtitle="Gera dados sintéticos num ambiente isolado, executa cada agente como em produção e recalcula cada decisão de forma independente — fórmulas, limiares, quem pode aprovar e o que vai para uma pessoa."
        actions={can("agents:execute") && <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={withAi} onChange={(e) => setWithAi(e.target.checked)} />
            Usar o modelo de IA configurado (gera custo)</label>
          <button className="btn-primary" disabled={action.busy} onClick={run}><FlaskConical size={14} /> {action.busy ? "Validando… (cerca de 30 s)" : r ? "Rodar de novo" : "Rodar validação"}</button>
        </div>} />
      <ErrorBox error={error || action.error} onRetry={reload} />
      {loading && !r && <Loading />}
      {!loading && !r && !action.busy && <div data-tour="validation-kpis"><Empty title="Nenhuma validação ainda" hint="Rode a validação para gerar os dados de teste e conferir cada decisão dos agentes. Também dá para rodar pelo terminal: python manage.py validate-agents" /></div>}
      {action.busy && <Loading label="Gerando dados e executando os fluxos num ambiente isolado…" />}
      {r && !action.busy && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" data-tour="validation-kpis">
            <Kpi label="Verificações aprovadas" value={`${r.summary.passed}/${r.summary.cases}`} tone={r.summary.failed ? "bad" : "good"}
              hint={r.summary.failed ? `${r.summary.failed} reprovada(s)` : "todas aprovadas"} />
            <Kpi label="Casos com dados gerados" value={fmt.num(r.summary.generated_cases)} hint="cenários criados sob medida" />
            <Kpi label="Contatos e registros" value={fmt.num(r.data?.support_contacts)} hint={`${r.data?.datasets?.length || 0} conjuntos de dados processados`} />
            <Kpi label="Duração" value={`${fmt.num(r.duration_s)} s`} hint={`${new Date(r.generated_at).toLocaleString("pt-BR")} · ${r.with_ai ? "com" : "sem"} modelo de IA`} />
          </div>
          <Card title={<span className="inline-flex items-center gap-2"><ShieldCheck size={15} aria-hidden /> O que foi executado</span>}
            subtitle="Banco e Lakehouse temporários, apagados ao final: nada da aplicação é alterado. Dados sintéticos do cenário “full” (com a queda de NPS encenada em jun/2026) e casos gerados sob medida quando um fluxo não tinha dado.">
            <ol className="flex flex-wrap items-center gap-2 text-sm" aria-label="Sequência da validação">
              {FLOW.filter((f) => byKey[f.k]).map((f, i, arr) => (
                <li key={f.k} className="inline-flex items-center gap-2">
                  <a href={`#v-${f.k}`} className={`rounded-full border px-3 py-1 ${byKey[f.k].failed ? "border-rose-500/50 text-rose-300" : "border-emerald-500/40 text-emerald-300"}`}>
                    {f.t} · {byKey[f.k].passed}/{byKey[f.k].passed + byKey[f.k].failed}</a>
                  {i < arr.length - 1 && <ArrowRight size={13} className="text-slate-500" aria-hidden />}
                </li>
              ))}
            </ol>
          </Card>
          {r.agents.map((a: any) => (
            <section key={a.key} id={`v-${a.key}`} aria-labelledby={`h-${a.key}`} className="scroll-mt-20">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h2 id={`h-${a.key}`} className="text-base font-semibold text-white">{a.name}</h2>
                <Badge tone={a.failed ? "red" : "green"}>{a.passed}/{a.passed + a.failed}</Badge>
                {a.catalog && <Link className="text-xs text-brand-500 underline underline-offset-2" href={`/agents/${a.key}`}>ver como decide</Link>}
              </div>
              <p className="mb-2 text-sm text-slate-400">{a.description}</p>
              <ul className="space-y-2">{a.cases.map((c: any, i: number) => <CaseItem key={i} c={c} />)}</ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
