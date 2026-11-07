"use client";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { Field, Saved, SavedInfo } from "./common";

const URG = [["media", "Média ou maior"], ["alta", "Alta ou maior"], ["critica", "Só crítica"]];
const CHANNELS: Record<string, string> = { whatsapp: "WhatsApp", email: "E-mail", reclameaqui: "Reclame Aqui" };

/** Matriz "resolve sozinho × precisa de uma pessoa" e premissas de esforço do Atendimento (Desafio 1). */
export default function SupportPanel({ config, onSaved, canWrite }: { config: any; onSaved: () => void; canWrite: boolean }) {
  const sec = config.sections.support;
  const cat = useApi<any>("/support/catalog");
  const action = useAction();
  const [v, setV] = useState<any>(sec.value);
  const [saved, setSaved] = useState(false);
  useEffect(() => setV(sec.value), [config]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: string, val: any) => setV({ ...v, [k]: val });
  const toggleIn = (k: string, item: string) => set(k, (v[k] || []).includes(item) ? v[k].filter((x: string) => x !== item) : [...(v[k] || []), item]);
  const save = async () => {
    if (await action.run("/settings/config/support", { value: v }, undefined, { success: "Matriz de atendimento atualizada",
      successDescription: "Vale para os próximos contatos; use “Refazer triagem” num contato para reavaliá-lo." })) {
      setSaved(true); setTimeout(() => setSaved(false), 2500); onSaved();
    }
  };
  const intents: Record<string, { label: string; claim: boolean }> = cat.data?.intents || {};
  return (
    <div className="space-y-4">
      <Card title="Resolve sozinho × precisa de uma pessoa" actions={<SavedInfo section={sec} />}
        subtitle="O agente só responde sozinho assuntos informativos, com dados governados. Reclamações que pedem reparação (avaria, defeito, não recebido, produto errado) sempre passam por uma pessoa, e ações em pedidos/pagamentos/estoque/clientes sempre exigem aprovação.">
        <div className="label mb-2">Assuntos que podem ser resolvidos automaticamente</div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(intents).map(([k, it]) => {
            const locked = it.claim && k !== "atraso_entrega";
            return (
              <label key={k} className="flex items-start gap-2 rounded-md border border-ink-700 p-2 text-sm">
                <input type="checkbox" className="mt-1" disabled={!canWrite || locked} checked={(v.auto_intents || []).includes(k)} onChange={() => toggleIn("auto_intents", k)} />
                <span><span className="text-white">{it.label}</span>{locked && <span className="block text-[11px] text-slate-500">exige verificação humana</span>}</span>
              </label>
            );
          })}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div>
            <div className="label mb-2">Canais sempre revisados por pessoa</div>
            {Object.entries(CHANNELS).map(([k, l]) => (
              <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canWrite} checked={(v.human_channels || []).includes(k)} onChange={() => toggleIn("human_channels", k)} /> {l}</label>
            ))}
          </div>
          <Field label="Urgência que vai para pessoa">
            <select className="input w-full" disabled={!canWrite} value={v.human_from_urgency} onChange={(e) => set("human_from_urgency", e.target.value)}>
              {URG.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          </Field>
          <Field label="Confiança mínima da intenção" hint="abaixo disso, a intenção é incerta → pessoa">
            <input className="input w-full" type="number" step="0.05" min={0.3} max={0.99} disabled={!canWrite} value={v.min_confidence} onChange={(e) => set("min_confidence", Number(e.target.value))} />
          </Field>
          <Field label="Reclamação em pedido acima de (R$) → pessoa">
            <input className="input w-full" type="number" min={0} disabled={!canWrite} value={v.claim_value_human_brl} onChange={(e) => set("claim_value_human_brl", Number(e.target.value))} />
          </Field>
          <Field label="Janela de recontato (dias)" hint="mesmo assunto dentro da janela = recontato">
            <input className="input w-full" type="number" min={1} max={60} disabled={!canWrite} value={v.recontact_window_days} onChange={(e) => set("recontact_window_days", Number(e.target.value))} />
          </Field>
          <div className="space-y-2 pt-5 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" disabled={!canWrite} checked={!!v.repeat_to_human} onChange={(e) => set("repeat_to_human", e.target.checked)} /> Recontato vai para pessoa</label>
            <label className="flex items-center gap-2"><input type="checkbox" disabled={!canWrite} checked={!!v.auto_carrier_ticket} onChange={(e) => set("auto_carrier_ticket", e.target.checked)} /> Abrir chamado na transportadora automaticamente</label>
          </div>
        </div>
      </Card>
      <Card title="Conversa e atendimentos" subtitle="Chat contínuo por cliente e canal (como no WhatsApp), com atendimentos dentro dele — padrão de Zendesk, Intercom, Blip e Octadesk.">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="“Obrigado” após encerrar não reabre por (h)" hint="mensagens de cortesia nesta janela ficam no atendimento encerrado">
            <input className="input w-full" type="number" min={0} max={168} disabled={!canWrite} value={v.reopen_window_hours ?? 24} onChange={(e) => set("reopen_window_hours", Number(e.target.value))} /></Field>
          <Field label="Encerrar por inatividade do cliente após (h)" hint="atendimento aguardando o cliente">
            <input className="input w-full" type="number" min={1} max={720} disabled={!canWrite} value={v.inactivity_close_hours ?? 48} onChange={(e) => set("inactivity_close_hours", Number(e.target.value))} /></Field>
          <Field label="Continuidade no histórico da demo (h)" hint="mensagem até X h após a anterior continua o atendimento">
            <input className="input w-full" type="number" min={1} max={720} disabled={!canWrite} value={v.continue_window_hours ?? 72} onChange={(e) => set("continue_window_hours", Number(e.target.value))} /></Field>
        </div>
      </Card>
      <Card title="Veracidade da reclamação" subtitle="Faixas do score (0–100) calculado a partir de fatores explicáveis: entrega registrada, prazo, foto e data da foto, tempo desde a entrega, histórico de reclamações do cliente, transportadora e fragilidade do produto.">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Consistente a partir de"><input className="input w-full" type="number" min={50} max={95} disabled={!canWrite} value={v.veracity_consistent_min} onChange={(e) => set("veracity_consistent_min", Number(e.target.value))} /></Field>
          <Field label="Não sustentada até"><input className="input w-full" type="number" min={5} max={49} disabled={!canWrite} value={v.veracity_inconsistent_max} onChange={(e) => set("veracity_inconsistent_max", Number(e.target.value))} /></Field>
        </div>
      </Card>
      <Card title="Premissas de esforço manual" subtitle="Minutos que cada assunto leva no atendimento 100% manual (abrir pedido, portal da transportadora, chamado, ERP…). Base para estimar as horas poupadas — são premissas, ajuste com a realidade da operação.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(intents).map(([k, it]) => (
            <Field key={k} label={it.label}><input className="input w-full" type="number" min={0} max={600} disabled={!canWrite} value={v.manual_minutes?.[k] ?? 0}
              onChange={(e) => set("manual_minutes", { ...(v.manual_minutes || {}), [k]: Number(e.target.value) })} /></Field>
          ))}
          <Field label="Revisão de um contato automático (min)"><input className="input w-full" type="number" min={0} max={30} step="0.5" disabled={!canWrite} value={v.auto_minutes} onChange={(e) => set("auto_minutes", Number(e.target.value))} /></Field>
        </div>
      </Card>
      <Card title="IA (opcional)" subtitle="Sem modelo configurado, tudo funciona com regras determinísticas.">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canWrite} checked={!!v.llm_reply} onChange={(e) => set("llm_reply", e.target.checked)} /> Permitir “Reescrever com IA” nas respostas (o modelo não pode acrescentar fatos, datas ou valores)</label>
      </Card>
      {canWrite && <div className="flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={save}>Salvar matriz de atendimento</button><Saved show={saved} /></div>}
    </div>
  );
}
