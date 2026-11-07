"use client";
import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import { useTourTab } from "@/features/presentation/events";
import { RefreshCw, ShieldAlert, User as UserIcon } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, InfoTip } from "@/components/ui";
import OperationCard from "@/features/incidents/OperationCard";
import { minutesLabel, RoutingBadge, SENTIMENT, SupportStatusBadge, UrgencyBadge, VERACITY, VeracityBadge } from "./common";

const OTHER_ACTIONS = [["support_carrier_ticket", "Chamado na transportadora"], ["support_exchange", "Gerar troca"], ["support_reshipment", "Reenviar pedido"],
  ["support_refund", "Reembolsar"], ["support_cancel_order", "Cancelar pedido"]];

/** Painel do atendimento selecionado, em abas para não amontoar informação: Resumo · Veracidade · Pedido · Ações. */
export default function CasePanel({ c, intents, canWrite, busy, onPropose, onUpdate, onRetriage, onReload }:
  { c: any; intents: Record<string, any>; canWrite: boolean; busy?: boolean; onPropose: (a: any) => void;
    onUpdate: (body: any, msg: string) => Promise<void>; onRetriage: () => Promise<void>; onReload: () => void }) {
  const [tab, setTab] = useState("resumo");
  const [fix, setFix] = useState("");
  const [oid, setOid] = useState("");
  const vf = c.veracity_factors || { factors: [], checks: [] };
  const rr = c.routing_reasons || { reasons: [], urgency_factors: [] };
  const open = ["pending_human", "pending_approval", "awaiting_customer"].includes(c.status);
  const hasVer = c.veracity_label && c.veracity_label !== "nao_aplicavel";
  const pendingOps = (c.operations || []).filter((o: any) => o.status === "pending_approval").length;
  useTourTab(setTab, ["resumo", "veracidade", "pedido", "acoes"]);
  const tabs = [["resumo", "Resumo"], ...(hasVer ? [["veracidade", "Veracidade"]] : []), ["pedido", "Pedido"], ["acoes", `Ações${pendingOps ? ` (${pendingOps})` : ""}`]];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-ink-700 p-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-500">Atendimento #{c.case_number} · {c.external_id}</div>
            <div className="text-sm font-semibold text-white">{c.intent_label}</div>
          </div>
          <RoutingBadge routing={c.routing} />
        </div>
        <div className="mt-2 flex flex-wrap gap-1"><SupportStatusBadge status={c.status} /><UrgencyBadge urgency={c.urgency} />{hasVer && <VeracityBadge label={c.veracity_label} score={c.veracity_score} />}</div>
        {canWrite && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {open && !c.assigned_to && <button className="btn-ghost !px-2 !py-1 text-xs" disabled={busy} onClick={() => onUpdate({ assign_to_me: true }, "Atendimento assumido")}><UserIcon size={12} /> Assumir</button>}
            <button className="btn-ghost !px-2 !py-1 text-xs" disabled={busy} onClick={onRetriage}><RefreshCw size={12} /> Refazer triagem</button>
          </div>
        )}
      </div>
      <div role="tablist" aria-label="Detalhes do atendimento" className="flex border-b border-ink-700 text-xs">
        {tabs.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={clsx("flex-1 border-b-2 px-2 py-2", tab === k ? "border-brand-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200")}>{l}</button>
        ))}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 text-sm">
        {tab === "resumo" && <>
          {c.case_summary && (
            <section className="rounded-md border border-brand-500/30 bg-brand-500/5 p-2.5">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="label">Resumo para quem assume</span>
                <Badge tone={c.summary_generated_by && c.summary_generated_by !== "deterministic" ? "violet" : "gray"}>
                  {c.summary_generated_by && c.summary_generated_by !== "deterministic" ? `IA · ${c.summary_generated_by.replace("llm:", "")}` : "regras"}</Badge>
              </div>
              <p className="text-xs text-slate-200">{c.case_summary}</p>
            </section>
          )}
          <section>
            <div className="label">Assunto</div>
            <div className="mt-1 text-slate-100">{c.intent_label} <span className="text-xs text-slate-500">· {fmt.pct((c.intent_confidence || 0) * 100, 0)} · {c.intent_source === "humano" ? "corrigido por pessoa" : c.intent_source === "historico" ? "do contato anterior" : c.intent_source === "ia" ? "IA (Jev · AI Proxy)" : "regras"}</span></div>
            {canWrite && (
              <div className="mt-1.5 flex gap-1.5">
                <select aria-label="Corrigir assunto" className="input min-w-0 flex-1 !py-1 text-xs" value={fix} onChange={(e) => setFix(e.target.value)}>
                  <option value="">Corrigir assunto…</option>{Object.entries(intents).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <button className="btn-ghost !px-2 !py-1 text-xs" disabled={!fix || busy} onClick={async () => { await onUpdate({ intent: fix }, "Assunto corrigido"); await onRetriage(); setFix(""); }}>Aplicar</button>
              </div>
            )}
          </section>
          <section>
            <div className="label">{c.routing === "auto" ? "Por que o agente resolveu sozinho" : "Por que precisa de uma pessoa"}</div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-300">{(rr.reasons || []).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
          </section>
          {(rr.urgency_factors || []).length > 0 && <section>
            <div className="label">Urgência {c.urgency} · prioridade {c.priority_score}</div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-400">{rr.urgency_factors.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
          </section>}
          <section className="grid grid-cols-2 gap-2 text-xs">
            <Info k="Sentimento" v={SENTIMENT[c.sentiment] || c.sentiment} /><Info k="Mensagens" v={`${c.message_count}${c.chase_count ? ` · ${c.chase_count} cobrança(s)` : ""}`} />
            <Info k="Tempo manual (premissa)" v={minutesLabel(c.manual_minutes)} /><Info k="Poupado" v={minutesLabel(c.saved_minutes)} />
          </section>
          {c.injection_suspected && <div className="flex items-center gap-1.5 rounded-md border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-200"><ShieldAlert size={13} /> Tentativa de manipulação detectada — tratada como dado.</div>}
          {c.avoidable && <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-200">Evitável: {c.avoidable_reason}. <Link className="underline" href="/atendimento/prevencao">Prevenção</Link></div>}
          {(c.systems || []).length > 0 && <section>
            <div className="label">No atendimento manual, exigiria</div>
            <div className="mt-1 flex flex-wrap gap-1">{c.systems.map((s: any) => <Badge key={s.key}>{s.label}</Badge>)}</div>
          </section>}
        </>}

        {tab === "veracidade" && hasVer && <>
          <div className="flex items-center gap-2"><span className="text-slate-300">A reclamação procede?</span><InfoTip text={VERACITY[c.veracity_label]?.hint} /></div>
          <div className="h-2 overflow-hidden rounded bg-ink-700" role="meter" aria-valuenow={c.veracity_score} aria-valuemin={0} aria-valuemax={100} aria-label="Score de veracidade">
            <div className={clsx("h-full", c.veracity_label === "consistente" ? "bg-emerald-400" : c.veracity_label === "inconsistente" ? "bg-rose-400" : "bg-amber-400")} style={{ width: `${c.veracity_score}%` }} />
          </div>
          <p className="text-[11px] text-slate-500">Começa em 50; cada evidência soma ou subtrai pontos. Atualiza a cada nova mensagem do cliente (ex.: foto enviada).</p>
          <ul className="space-y-2">
            {vf.factors.map((f: any, i: number) => (
              <li key={i} className="flex gap-2 text-xs">
                <span className={clsx("w-9 shrink-0 text-right font-semibold tabular-nums", f.points > 0 ? "text-emerald-300" : f.points < 0 ? "text-rose-300" : "text-slate-400")}>{f.points > 0 ? "+" : ""}{f.points}</span>
                <span><span className="text-slate-100">{f.factor}</span><div className="text-slate-400">{f.evidence}</div></span>
              </li>
            ))}
          </ul>
          {vf.checks.length > 0 && <section><div className="label">Verificação recomendada</div><ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-300">{vf.checks.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></section>}
        </>}

        {tab === "pedido" && <>
          {!c.order && <>
            <p className="text-slate-400">Nenhum pedido vinculado.</p>
            {canWrite && <div className="flex gap-1.5">
              <input aria-label="Número do pedido" className="input min-w-0 flex-1 !py-1 text-xs" placeholder="Número do pedido" value={oid} onChange={(e) => setOid(e.target.value.replace(/[^0-9A-Za-z-]/g, ""))} />
              <button className="btn-ghost !px-2 !py-1 text-xs" disabled={busy || oid.length < 3} onClick={async () => { await onUpdate({ order_id: oid }, "Pedido vinculado"); await onRetriage(); }}>Vincular</button>
            </div>}
          </>}
          {c.order && <>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <Info k="Pedido" v={`#${c.order.order_id}`} /><Info k="Valor" v={c.order.order_total != null ? `R$ ${fmt.num(c.order.order_total, 2)}` : "—"} />
              <Info k="Produto" v={c.order.product_name} /><Info k="Linha" v={c.order.product_line} />
              <Info k="Transportadora" v={`${c.order.carrier || "—"} · ${c.order.shipping_type || ""}`} /><Info k="Situação no contato" v={c.order.status_at_contact} />
            </div>
            <ol className="border-l border-ink-600 pl-3">
              {c.order.timeline.map((t: any, i: number) => <li key={i} className="mb-1 text-xs"><span className={t.planned ? "text-slate-500" : "text-slate-200"}>{t.step}</span> <span className="text-slate-500">· {fmt.day(t.at)}</span></li>)}
            </ol>
          </>}
          {c.customer && <div className="grid grid-cols-2 gap-2 border-t border-ink-700 pt-3 text-xs">
            <Info k="Cliente" v={c.customer.customer_id} /><Info k="Pedidos" v={fmt.num(c.customer.orders)} />
            <Info k="Atendimentos" v={fmt.num(c.customer.contacts)} /><Info k="Reclamações" v={fmt.num(c.customer.claims)} />
            <Info k="Valor em compras" v={`R$ ${fmt.num(c.customer.lifetime_value, 2)}`} /><Info k="Último NPS" v={c.customer.nps_last ?? "—"} />
          </div>}
        </>}

        {tab === "acoes" && <>
          <p className="text-[11px] text-slate-500">Cada ação substitui um passo em outro sistema (portal da transportadora, ERP, financeiro). Execução simulada.</p>
          {(c.suggested_actions || []).length === 0 && <p className="text-xs text-slate-400">Nenhuma ação de reparação recomendada.</p>}
          {(c.suggested_actions || []).map((a: any) => {
            const exists = (c.operations || []).some((o: any) => o.action_type === a.action_type && o.status !== "rejected");
            return (
              <div key={a.action_type} className="rounded-md border border-ink-700 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-white">{a.title}</span>
                  {a.requires_approval ? <Badge tone="amber">aprovação</Badge> : <Badge tone="teal">sem aprovação</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-slate-400">{a.why}</div>
                {canWrite && !exists && <button className="btn-ghost mt-2 !px-2 !py-1 text-xs" disabled={busy} onClick={() => onPropose(a)}>Propor</button>}
                {exists && <div className="mt-1"><Badge tone="green">já proposta</Badge></div>}
              </div>
            );
          })}
          {canWrite && c.order && <details className="text-xs"><summary className="cursor-pointer text-slate-400">Outras ações</summary>
            <div className="mt-2 flex flex-wrap gap-1.5">{OTHER_ACTIONS.map(([k, l]) => <button key={k} className="btn-ghost !px-2 !py-1 text-xs" disabled={busy}
              onClick={() => onPropose({ action_type: k, title: l, requires_approval: k !== "support_carrier_ticket" })}>{l}</button>)}</div></details>}
          {(c.operations || []).length > 0 && <div className="space-y-3">{c.operations.map((op: any) => <OperationCard key={op.id} op={op} onChange={onReload} compact />)}</div>}
        </>}
      </div>
    </div>
  );
}

function Info({ k, v }: { k: string; v: any }) {
  return <div><div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div><div className="text-slate-200">{v ?? "—"}</div></div>;
}
