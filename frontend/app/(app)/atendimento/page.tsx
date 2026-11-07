"use client";
import Link from "next/link";
import { Bot, FastForward, Inbox, Play, Radio, ShieldCheck, Sparkles, Split, Repeat2, Timer } from "lucide-react";
import { Bars, StackedBars } from "@/components/charts";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, DemoBadge, Empty, ErrorBox, InfoTip, Kpi, PageHeader, PageSkeleton } from "@/components/ui";
import { CHANNEL, hours, minutesLabel, URGENCY, VERACITY } from "@/features/support/common";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

const CHALLENGES = [
  { icon: Timer, title: "Volume e tempo por contato", text: "Assuntos informativos (onde está, prazo, estorno, dúvidas) são respondidos na hora com dados do pedido; os demais chegam triados e priorizados." },
  { icon: Split, title: "Trabalho espalhado entre sistemas", text: "Visão 360 do contato (pedido, entrega, transportadora, histórico, NPS) numa tela; chamado, troca, reenvio e reembolso viram ações de um clique." },
  { icon: ShieldCheck, title: "A reclamação é verdadeira?", text: "Score de veracidade explicável: entrega registrada, prazo, foto e data da foto, tempo desde a entrega, reclamações em série. Nunca nega sozinho." },
  { icon: Sparkles, title: "Sozinho × pessoa", text: "Matriz configurável: canal público, urgência, recontato, valor, intenção incerta ou dados que não sustentam a reclamação vão para uma pessoa." },
  { icon: Repeat2, title: "Contatos que se repetem", text: "Detecta recontato e contatos evitáveis, mostra as causas e propõe aviso proativo aos pedidos em risco de atraso." },
];

export default function SupportOverviewPage() {
  const { data, error, loading, reload } = useApi<any>("/support/overview");
  const { can } = useAuth();
  const sim = useAction();
  const simulate = async () => { if (await sim.run("/support/simulate", { count: 12 }, undefined, { success: "Novos contatos recebidos", successDescription: "O Agente de Atendimento fez a triagem — veja a caixa unificada." })) reload(); };
  if (loading && !data) return <PageSkeleton />;
  return (
    <>
      <PageHeader kicker="Atendimento ao cliente" title="Visão do atendimento"
        subtitle="Contatos de WhatsApp, e-mail e Reclame Aqui triados pelo Agente de Atendimento: o que se resolve sozinho, o que precisa de uma pessoa, se a reclamação procede e o que poderia ter sido evitado."
        actions={<>
          {data?.is_demo && <DemoBadge />}
          {can("support:write") && <button className="btn-ghost" disabled={sim.busy} onClick={simulate}><Radio size={14} /> Simular chegada de contatos</button>}
          {can("support:read") && <Link className="btn-primary" href="/atendimento/caixa"><Inbox size={14} /> Abrir caixa unificada</Link>}
        </>} />
      <ErrorBox error={error || sim.error} onRetry={reload} />
      {data && !data.ready && <Empty title="Ainda não há contatos" hint="Carregue a demonstração e execute o pipeline (Lakehouse › Camadas) — a etapa “support” gera e tria os contatos." />}
      {data?.ready && <ShiftCard onDone={reload} canRun={can("support:write")} />}
      {data?.ready && <SupportOverview d={data} />}
    </>
  );
}

function ShiftCard({ onDone, canRun }: { onDone: () => void; canRun: boolean }) {
  const s = useApi<any>("/support/shift");
  const act = useAction();
  const run = async (advance: number) => {
    if (await act.run("/support/shift", { advance_hours: advance }, undefined, { success: "Turno do agente concluído", successDescription: "Veja o que ele fez abaixo e no Canal do time." })) { s.reload(); onDone(); }
  };
  const o = s.data?.last_run?.output;
  const items = o ? [
    ["Mensagens processadas", o.processed], ["Lembretes de inatividade", o.reminders], ["Encerrados por inatividade", o.closed_inactive],
    ["Alertas de SLA ao time", o.sla_alerts], ["Cobranças de aprovação", o.approval_reminders], ["Incidentes abertos (equipe de agentes)", (o.incidents || []).length],
  ] : [];
  return (
    <Card className="mb-5" tour="shift" title={<span className="inline-flex items-center gap-1.5"><Bot size={15} /> Turno do Agente de Atendimento</span>}
      subtitle="O que o agente faz sozinho a cada rodada: processa a caixa, lembra e encerra por inatividade, avisa o time quando o SLA estoura, cobra aprovações, abre incidente e chama os agentes de Investigação e Resolução quando uma transportadora concentra reclamações, e manda o resumo do dia no Canal do time."
      actions={canRun && <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled={act.busy} onClick={() => run(0)}><Play size={14} /> Rodar turno agora</button>
        <button className="btn-ghost" disabled={act.busy} onClick={() => run(12)} title="Simula o passar de 12 horas no relógio da demonstração"><FastForward size={14} /> Avançar 12 h (demo)</button>
      </div>}>
      {!o && <p className="text-sm text-slate-400">O agente ainda não rodou um turno. Ligue o agendamento em Configurações › Monitor, agendador e retenção ou rode agora.</p>}
      {o && <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
          {items.map(([l, v]) => <div key={l as string} className="rounded-md border border-ink-700 p-2.5"><div className="text-[11px] text-slate-500">{l}</div><div className="text-xl font-semibold tabular-nums text-white">{fmt.num(v)}</div></div>)}
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
          <span>Último turno: {fmt.date(s.data.last_run.finished_at || s.data.last_run.started_at)}</span>
          <span>Relógio da demo: {fmt.date(s.data.clock)}{s.data.offset_hours ? ` (+${fmt.num(s.data.offset_hours)} h simuladas)` : ""}</span>
          {(o.incidents || []).map((i: any) => <Link key={i.incident_id} className="text-brand-400 hover:underline" href={`/incidents/${i.incident_id}`}>Incidente {i.carrier} ({i.contacts} reclamações)</Link>)}
          <Link className="text-brand-400 hover:underline" href="/canal">Ver no Canal do time →</Link>
        </div>
      </>}
    </Card>
  );
}

function SupportOverview({ d }: { d: any }) {
  const months = (d.per_month || []).map((m: any) => ({ ...m, human: m.contacts - m.auto }));
  const claims = d.claims.by_veracity || {};
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6" data-tour="support-kpis">
        <Kpi label="Atendimentos" value={fmt.num(d.total)} hint={`${fmt.num(d.conversations)} conversas · ${fmt.num(d.inbound_messages)} mensagens de clientes`}
          info="Cada conversa (cliente + canal) reúne vários atendimentos; mensagens do cliente com o atendimento aberto continuam o mesmo atendimento." />
        <Kpi label="Resolvidos sem pessoa" value={fmt.pct(d.automation.auto_rate)} tone="good" hint={`${fmt.num(d.automation.auto)} contatos`}
          info="Assuntos informativos respondidos na hora com dados do pedido, conforme a matriz em Configurações › Atendimento." />
        <Kpi label="Horas poupadas" value={hours(d.effort.saved_hours)} tone="good" hint={`${fmt.pct(d.effort.saved_pct)} do esforço manual (${hours(d.effort.manual_hours)})`}
          info={d.effort.assumption} />
        <Kpi label="Recontato" value={fmt.pct(d.recontact.rate)} tone={d.recontact.rate > 15 ? "warn" : "default"} hint={`${fmt.num(d.recontact.repeats)} reaberturas · ${fmt.num(d.chases)} cobranças`}
          info="Recontato = cliente voltou pelo mesmo pedido DEPOIS de o atendimento ser encerrado. Cobranças = mensagens enquanto o atendimento ainda estava aberto." />
        <Kpi label="Evitáveis" value={fmt.pct(d.recontact.avoidable_rate)} tone="warn" hint="aviso proativo teria dispensado"
          info="Atraso não comunicado, status de entrega, prazo de estorno e recontatos." />
        <Kpi label="1ª resposta" value={minutesLabel(d.response.first_response_auto_min)} hint={`automático · pessoa: ${minutesLabel(d.response.first_response_human_min)}`}
          info="Mediana do tempo até a primeira resposta. Tempos de contatos antigos da demo são simulados." />
      </div>

      <Card tour="support-challenges" title="Como o GoOps responde aos desafios do atendimento" subtitle="Cada ponto do desafio e onde ele aparece na plataforma.">
        <div className="grid gap-3 md:grid-cols-5">
          {CHALLENGES.map((c) => (
            <div key={c.title} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
              <c.icon size={18} className="text-brand-400" aria-hidden />
              <div className="mt-2 text-sm font-medium text-white">{c.title}</div>
              <p className="mt-1 text-xs text-slate-400">{c.text}</p>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Contatos por mês" subtitle="Automático × pessoa" className="lg:col-span-2">
          <StackedBars data={months} x="month" label="Contatos por mês, automáticos e humanos"
            series={[{ key: "auto", name: "Resolvidos sem pessoa", color: "tertiary" }, { key: "human", name: "Com pessoa", color: "primary" }]} />
        </Card>
        <Card title="Por canal">
          <Bars data={d.by_channel.map((c: any) => ({ ...c, label: CHANNEL[c.channel]?.label || c.channel }))} x="label" y="contacts" name="Contatos" />
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Assuntos e automação" subtitle="Quanto de cada assunto o agente resolveu sozinho">
          <DataTable rows={d.by_intent} columns={[
            { key: "label", label: "Assunto" },
            { key: "contacts", label: "Contatos", className: "text-right tabular-nums", render: (r: any) => fmt.num(r.contacts) },
            { key: "auto", label: "Sem pessoa", className: "text-right tabular-nums", render: (r: any) => (
              <span className="inline-flex items-center gap-2">
                <span className="h-1.5 w-16 overflow-hidden rounded bg-ink-700"><span className="block h-full bg-emerald-400" style={{ width: `${(r.auto / r.contacts) * 100}%` }} /></span>
                {fmt.pct((r.auto / r.contacts) * 100, 0)}
              </span>) },
          ]} />
        </Card>
        <div className="space-y-5">
          <Card title={<span className="inline-flex items-center gap-1.5">A reclamação procede? <InfoTip text="Reclamações que pedem reparação (atraso, avaria, defeito, não recebido, produto errado), classificadas pelos dados antes de qualquer ação." /></span>}
            subtitle={`${fmt.num(d.claims.total)} reclamações de reparação`}>
            <div className="grid grid-cols-3 gap-2">
              {["consistente", "inconclusiva", "inconsistente"].map((k) => (
                <div key={k} className="rounded-md border border-ink-700 p-3">
                  <Badge tone={VERACITY[k].tone}>{VERACITY[k].label}</Badge>
                  <div className="mt-2 text-2xl font-semibold tabular-nums text-white">{fmt.num(claims[k] || 0)}</div>
                  <p className="mt-1 text-[11px] text-slate-500">{VERACITY[k].hint}</p>
                </div>
              ))}
            </div>
            {d.accuracy && (
              <div className="mt-3 rounded-md border border-violet-500/30 bg-violet-500/5 p-3 text-xs text-slate-300">
                <div className="mb-1 font-medium text-violet-200">Coerência na base sintética</div>
                Intenção correta em <b>{fmt.pct(d.accuracy.intent_accuracy_pct)}</b> · das {fmt.num(d.accuracy.fake_claims)} reclamações falsas plantadas,
                <b> {fmt.pct(d.accuracy.fake_flagged_pct)}</b> não foram liberadas automaticamente · precisão do “não sustentada”: <b>{fmt.pct(d.accuracy.flag_precision_pct)}</b>.
                <div className="mt-1 text-slate-500">{d.accuracy.note}</div>
              </div>
            )}
          </Card>
          <Card title="Fila humana agora" subtitle="Contatos aguardando uma pessoa ou aprovação" actions={<Link className="btn-ghost" href="/atendimento/caixa">Ver fila →</Link>}>
            <div className="flex flex-wrap gap-2">
              {["critica", "alta", "media", "baixa"].map((u) => (
                <Badge key={u} tone={URGENCY[u].tone}>{URGENCY[u].label}: {fmt.num(d.queue.by_urgency?.[u] || 0)}</Badge>
              ))}
              <span className="ml-auto text-sm text-slate-300">{fmt.num(d.queue.open)} em aberto</span>
            </div>
          </Card>
        </div>
      </div>

      <Card title="Trabalho espalhado entre sistemas" subtitle={`No atendimento manual, cada contato exigiria em média ${fmt.num(d.effort.avg_systems_per_contact, 1)} sistemas/portais. No GoOps, a visão 360 e as ações reúnem tudo numa tela.`}>
        <Bars data={d.effort.systems} x="label" y="contacts" name="Contatos que exigiriam o sistema" horizontal />
      </Card>
      {d.history_simulated > 0 && <p className="text-xs text-slate-500">{fmt.num(d.history_simulated)} contatos antigos da carga inicial têm desfecho histórico simulado (tempos de resposta/resolução), sinalizado como sintético.</p>}
    </div>
  );
}
