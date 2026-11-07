"use client";
import Link from "next/link";
import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, CircleDashed, Database, XCircle } from "lucide-react";
import { Badge } from "@/components/ui";

const KEY_LABEL: Record<string, string> = {
  status: "status", mes: "mês", nps: "NPS", mes_anterior: "mês anterior", media_base: "média base", queda_recalculada: "queda recalculada",
  queda_do_agente: "queda do agente", n: "n", severidade: "severidade", severidade_esperada: "severidade esperada", novos: "novos",
  ja_abertos: "já abertos", limiar_testado: "limiar testado", sinais_de_nps: "sinais de NPS", delta_total: "Δ NPS total",
  hipotese_principal: "hipótese principal", confianca: "confiança", causa_registrada: "causa registrada", origem: "origem",
  destino: "destino", fatia: "fatia (%)", impacto_estimado_pts: "impacto estimado (pts)", efeito_desempenho: "efeito de desempenho",
  premissa: "premissa", intencao: "intenção", urgencia: "urgência", veracidade: "veracidade", rotulo: "rótulo", rota: "rota",
  motivos: "motivos", fatores: "fatores", resposta_sugerida: "resposta sugerida", divergencias: "divergências", exemplos: "exemplos",
  automaticos: "automáticos", violacoes: "violações", exige_aprovacao: "exige aprovação", status_operacao: "status da operação",
  status_atendimento: "status do atendimento", atendente_aprovando: "atendente tentando aprovar", incidente: "incidente",
  agentes_acionados: "agentes acionados", hipotese: "hipótese", turno: "turno", gerado_por: "gerado por", alerta: "alerta",
  incidentes_criados: "incidentes criados", criterios: "critérios", passos: "passos", relatorio: "relatório", tarefas: "tarefas",
  chamadas_ao_modelo: "chamadas ao modelo", custo_usd: "custo (US$)", modo: "modo", status_workflow: "status do fluxo",
  decisoes: "decisões", operacoes: "operações", status_incidente: "status do incidente", policies_ok: "políticas respeitadas",
  intent_accuracy_pct: "acerto de intenção (%)", fake_flagged_pct: "falsas sinalizadas (%)", flag_precision_pct: "precisão da sinalização (%)",
  genuine_consistent_pct: "verdadeiras consistentes (%)", claims_evaluated: "reclamações avaliadas", fake_claims: "reclamações falsas",
  reclame_aqui_fora: "Reclame Aqui sem pessoa", concentracao: "concentração", corroboracoes: "corroborações",
  confianca_agente: "confiança do agente", confianca_recalculada: "confiança recalculada", significativa: "significativa",
  segmento: "segmento", acao: "ação", titulo: "título", risco: "risco", politica: "política exige",
  aprovado_por: "aprovado por", agente: "agente", modelo: "modelo", resultado: "resultado", incidentes: "incidentes",
  pedidos: "pedidos de IA", com_ia: "com IA", contingencia: "sem IA (plano B)", motivo: "motivo", soma_carrier: "soma · transportadora",
  soma_state: "soma · UF", soma_product_line: "soma · linha", soma_shipping_type: "soma · frete", passos_do_fluxo: "passos", inconsistentes_fora: "inconsistentes sem pessoa", contatos_atendimento: "contatos de atendimento",
};
const label = (k: string) => KEY_LABEL[k] || k.replace(/_/g, " ");

function fmtVal(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "sim" : "não";
  if (typeof v === "number") return v.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  return String(v);
}

/** Mostra o "observado" de forma legível: tabela para listas de objetos, pares chave/valor para objetos. */
export function ObservedView({ value, depth = 0 }: { value: any; depth?: number }) {
  if (value === null || value === undefined || typeof value !== "object") return <span className="text-slate-200">{fmtVal(value)}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-slate-500">nenhum</span>;
    if (value.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
      const cols = Array.from(new Set(value.flatMap((x) => Object.keys(x)))).slice(0, 9);
      return (
        <div className="max-w-full overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead><tr>{cols.map((c) => <th key={c} className="border-b border-ink-700 px-2 py-1 text-left font-semibold text-slate-400">{label(c)}</th>)}</tr></thead>
            <tbody>{value.slice(0, 20).map((row, i) => (
              <tr key={i}>{cols.map((c) => <td key={c} className="border-b border-ink-800 px-2 py-1 align-top text-slate-200">
                {row[c] !== null && typeof row[c] === "object" ? <ObservedView value={row[c]} depth={depth + 1} /> : fmtVal(row[c])}</td>)}</tr>))}</tbody>
          </table>
        </div>
      );
    }
    return <ul className="list-disc pl-5">{value.slice(0, 20).map((x, i) => <li key={i}><ObservedView value={x} depth={depth + 1} /></li>)}</ul>;
  }
  return (
    <dl className={`grid gap-x-4 gap-y-1 ${depth ? "" : "sm:grid-cols-[minmax(160px,auto)_1fr]"}`}>
      {Object.entries(value).map(([k, v]) => (
        <div key={k} className={depth ? "flex flex-wrap gap-1" : "contents"}>
          <dt className="text-xs text-slate-500">{label(k)}</dt>
          <dd className="text-xs">{<ObservedView value={v} depth={depth + 1} />}</dd>
        </div>
      ))}
    </dl>
  );
}

export function CaseItem({ c }: { c: any }) {
  const [open, setOpen] = useState(false);
  const Icon = c.ok === true ? CheckCircle2 : c.ok === false ? XCircle : CircleDashed;
  return (
    <li className={`rounded-lg border ${c.ok === false ? "border-rose-500/40" : "border-ink-700"}`}>
      <button className="flex w-full items-start gap-2 p-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <Icon size={16} className={`mt-0.5 shrink-0 ${c.ok === true ? "text-emerald-400" : c.ok === false ? "text-rose-400" : "text-slate-500"}`}
          aria-label={c.ok === true ? "aprovado" : c.ok === false ? "reprovado" : "não avaliado"} />
        <span className="flex-1">
          <span className="text-sm font-medium text-slate-100">{c.title}</span>
          {c.generated_data && <Badge tone="blue" className="ml-2"><Database size={10} aria-hidden /> dado gerado</Badge>}
          <span className="mt-0.5 block text-xs text-slate-400">{c.what}</span>
        </span>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
      </button>
      {open && (
        <div className="space-y-3 border-t border-ink-700 p-3 text-sm">
          <div><div className="label">Como decide (regra)</div><p className="mt-0.5 font-mono text-xs text-slate-300">{c.rule}</p></div>
          <div><div className="label">Esperado</div><p className="mt-0.5 text-slate-300">{c.expected}</p></div>
          <div><div className="label">Observado</div><div className="mt-1 rounded-md bg-ink-950 p-2"><ObservedView value={c.observed} /></div></div>
        </div>
      )}
    </li>
  );
}

export function AgentValidationSummary({ report, agentKey }: { report: any; agentKey: string }) {
  const map: Record<string, string[]> = { supervisor: ["supervisor"], monitor: ["monitor"], investigation: ["investigation"],
    resolution: ["resolution"], validation: ["validation"], support: ["support"], assistant: ["ai"] };
  const groups = (report?.agents || []).filter((a: any) => (map[agentKey] || []).includes(a.key));
  if (!groups.length) return null;
  const cases = groups.flatMap((g: any) => g.cases);
  const passed = cases.filter((c: any) => c.ok).length;
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <Badge tone={passed === cases.length ? "green" : "red"}>{passed}/{cases.length} verificações aprovadas</Badge>
        <span className="text-xs text-slate-500">última validação ponta a ponta: {new Date(report.generated_at).toLocaleString("pt-BR")}</span>
        <Link href="/agents/validacao" className="text-xs text-brand-500 underline underline-offset-2">ver relatório completo</Link>
      </div>
      <ul className="space-y-2">{cases.map((c: any, i: number) => <CaseItem key={i} c={c} />)}</ul>
    </div>
  );
}
