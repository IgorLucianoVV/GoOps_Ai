"use client";
import Link from "next/link";
import { useState } from "react";
import { Bot, Check, Link2, MessagesSquare, X } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

const KIND: Record<string, { label: string; tone: string }> = {
  approval_request: { label: "pede aprovação", tone: "amber" }, approval_reminder: { label: "lembrete de aprovação", tone: "amber" },
  sla: { label: "SLA estourado", tone: "red" }, incident: { label: "incidente", tone: "red" }, digest: { label: "resumo do dia", tone: "blue" },
  info: { label: "aviso", tone: "gray" },
};
const PROVIDER: Record<string, string> = { app: "só no GoOps", telegram: "Telegram", slack: "Slack" };

/** Canal do time: o mural onde os agentes conversam com as pessoas (espelhado no Telegram/Slack quando configurado). */
export default function TeamChannelPage() {
  const { data, error, loading, reload } = useApi<any>("/team/feed", { limit: 150 });
  const { can } = useAuth();
  const act = useAction();
  const [code, setCode] = useState<any>(null);
  const decide = async (opId: string, approve: boolean) => {
    if (await act.run(`/operations/${opId}/${approve ? "approve" : "reject"}`, { note: "via Canal do time" }, undefined,
      { success: approve ? "Aprovado — o agente executa (simulado)" : "Rejeitado" })) reload();
  };
  const items = data?.items || [];
  return (
    <>
      <PageHeader kicker="Colaboração" title="Canal do time"
        subtitle="Os agentes avisam, pedem aprovação e mandam o resumo do dia onde o time conversa. Este mural registra tudo; com Telegram configurado, as mesmas mensagens chegam no grupo, com botões de aprovar."
        actions={<>
          {data && <Badge tone={data.provider === "app" ? "gray" : "green"}>canal: {PROVIDER[data.provider] || data.provider}</Badge>}
          {can("settings:write") && <Link className="btn-ghost" href="/settings">Configurar</Link>}
        </>} />
      <ErrorBox error={error || act.error} onRetry={reload} />
      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        <Card className="min-h-[400px]">
          {loading && !data && <Loading />}
          {data && items.length === 0 && <div className="grid place-items-center p-10 text-sm text-slate-500"><MessagesSquare size={22} className="mb-2" />Nada por aqui ainda. Rode o turno do Agente de Atendimento (Atendimento › Visão) ou proponha uma ação.</div>}
          <ul className="space-y-3">
            {items.map((m: any) => {
              const k = KIND[m.kind] || KIND.info;
              const op = m.operation;
              return (
                <li key={m.id} className="flex gap-3">
                  <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-teal-500/15 text-teal-300"><Bot size={16} aria-hidden /></span>
                  <div className="min-w-0 flex-1 rounded-lg border border-ink-700 bg-ink-850 p-3">
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span className="font-semibold text-slate-300">{m.operation_id || m.contact_id ? "Agente de Atendimento" : "GoOps"}</span>
                      <Badge tone={k.tone}>{k.label}</Badge>
                      <span>{fmt.date(m.created_at)}</span>
                      {m.provider !== "app" && <Badge tone={m.delivery === "delivered" ? "green" : m.delivery === "failed" ? "red" : "gray"}>
                        {m.delivery === "delivered" ? `enviado no ${PROVIDER[m.provider]}` : m.delivery === "failed" ? `falhou no ${PROVIDER[m.provider]}` : "só no app"}</Badge>}
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-slate-100">{m.text}</p>
                    {m.delivery_error && <p className="mt-1 text-[11px] text-rose-300">{m.delivery_error}</p>}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {m.contact_id && <Link className="text-xs text-brand-400 hover:underline" href={`/atendimento/${m.contact_id}`}>Abrir conversa</Link>}
                      {m.incident_id && <Link className="text-xs text-brand-400 hover:underline" href={`/incidents/${m.incident_id}`}>Abrir incidente</Link>}
                      {op && op.status === "pending_approval" && m.kind.startsWith("approval") && can("operations:approve") && <>
                        <button className="btn-primary !px-2.5 !py-1 text-xs" disabled={act.busy} onClick={() => decide(op.id, true)}><Check size={12} /> Aprovar</button>
                        <button className="btn-danger !px-2.5 !py-1 text-xs" disabled={act.busy} onClick={() => decide(op.id, false)}><X size={12} /> Rejeitar</button>
                      </>}
                      {op && op.status !== "pending_approval" && m.kind.startsWith("approval") && <Badge tone={op.status === "rejected" ? "red" : "green"}>{op.status === "rejected" ? "rejeitada" : op.status === "executed" ? "aprovada e executada (simulada)" : op.status}</Badge>}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
        <div className="space-y-4">
          <Card title="Aprovar pelo celular (Telegram)">
            <p className="text-xs text-slate-400">Vincule sua conta para aprovar ou rejeitar ações direto no grupo do time. A decisão usa as SUAS permissões no GoOps.</p>
            <div className="mt-2 text-xs">{data?.me?.linked ? <Badge tone="green">conta vinculada · {fmt.date(data.me.linked_at)}</Badge> : <Badge>não vinculada</Badge>}</div>
            <button className="btn-ghost mt-3" disabled={act.busy} onClick={async () => setCode(await act.run("/team/link-code", {}))}><Link2 size={14} /> Gerar código de vínculo</button>
            {code && <div className="mt-3 rounded-md border border-ink-700 bg-ink-850 p-3 text-sm">
              <div className="text-2xl font-semibold tracking-widest text-white">{code.code}</div>
              <p className="mt-1 text-xs text-slate-400">{code.instructions}</p>
            </div>}
            {data && !data.telegram_ready && <p className="mt-3 text-[11px] text-amber-300">O bot do Telegram ainda não está configurado (Configurações › Canal do time).</p>}
          </Card>
          <Card title="Comandos do bot">
            <ul className="space-y-1 text-xs text-slate-300">
              <li><code>/fila</code> — atendimentos aguardando e aprovações pendentes</li>
              <li><code>/resumo</code> — resumo do dia</li>
              <li><code>/caso &lt;id&gt;</code> — resumo de um atendimento</li>
              <li><code>/vincular &lt;código&gt;</code> — vincula sua conta</li>
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
