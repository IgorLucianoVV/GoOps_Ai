"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { Saved, SavedInfo } from "./common";

function Toggle({ label, hint, checked, onChange, disabled }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-start gap-3 rounded-md border border-ink-700 p-3">
      <input type="checkbox" className="mt-1" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span><span className="block text-sm font-medium text-white">{label}</span><span className="block text-xs text-slate-500">{hint}</span></span>
    </label>
  );
}

const FREQ = [["60", "A cada hora"], ["360", "A cada 6 horas"], ["1440", "Diário"], ["10080", "Semanal"]];

/** Recursos opcionais da demonstração: cada um pode ser ligado ou desligado sem perder dados. */
export default function FeaturesPanel({ config, onSaved, canWrite }: { config: any; onSaved: () => void; canWrite: boolean }) {
  const sec = config.sections.features;
  const action = useAction();
  const [v, setV] = useState<any>(sec.value);
  const [saved, setSaved] = useState(false);
  useEffect(() => setV(sec.value), [config]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: string, val: any) => setV({ ...v, [k]: val });
  const save = async () => {
    const body = { ...v, briefing_email_to: typeof v.briefing_email_to === "string" ? v.briefing_email_to : (v.briefing_email_to || []).join(", ") };
    if (await action.run("/settings/config/features", { value: body }, undefined, { success: "Recursos atualizados" })) { setSaved(true); setTimeout(() => setSaved(false), 2500); onSaved(); }
  };
  return (
    <div className="space-y-4">
      <Card title="Recursos da demonstração" subtitle="Ligue ou desligue cada recurso. Desligar não apaga dados nem histórico." actions={<SavedInfo section={sec} />}>
        <div className="grid gap-3 md:grid-cols-2">
          <Toggle label="Atendimento ao cliente" disabled={!canWrite} checked={v.support !== false} onChange={(x) => set("support", x)}
            hint="Desafio 1: caixa unificada (WhatsApp, e-mail, Reclame Aqui), triagem, veracidade, automação e prevenção de recontato. Desligado, o domínio, as fontes de contatos e os agentes ficam inativos." />
          <Toggle label="Setor Estoque · Pedidos travados" disabled={!canWrite} checked={!!v.sector_stock} onChange={(x) => set("sector_stock", x)}
            hint="Desafio 2: estoque × pedidos com FIFO; agente propõe avisar clientes (sempre com aprovação). Desligado, o setor, as fontes e os agentes ficam inativos." />
          <Toggle label="Simulação “e se…” nas ações" disabled={!canWrite} checked={!!v.whatif} onChange={(x) => set("whatif", x)}
            hint="Antes de aprovar, projeta o efeito (atraso, NPS, alcance do contato). Estimativa — não altera nada." />
        </div>
      </Card>
      <Card title="Briefing diário" subtitle="Resumo do que mudou, incidentes e decisões pendentes. Entrega em Slack/e-mail sempre SIMULADA (registrada, nada é enviado)."
        actions={<Link className="btn-ghost" href="/briefing">Ver briefings</Link>}>
        <div className="grid gap-3 md:grid-cols-2">
          <Toggle label="Gerar automaticamente" disabled={!canWrite} checked={!!v.briefing_enabled} onChange={(x) => set("briefing_enabled", x)}
            hint="Usa o agendador da API (precisa estar ativo). Sempre é possível gerar manualmente." />
          <label className="block"><span className="label">Frequência</span>
            <select className="input mt-1 w-full" disabled={!canWrite} value={String(v.briefing_interval_minutes)} onChange={(e) => set("briefing_interval_minutes", Number(e.target.value))}>
              {FREQ.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <Toggle label="Narrativa por IA" disabled={!canWrite} checked={!!v.briefing_ai} onChange={(x) => set("briefing_ai", x)}
            hint="Reescreve o resumo para gestores usando o modelo configurado (nível 2). Sem modelo, fica só o texto determinístico." />
          <div className="space-y-2 rounded-md border border-ink-700 p-3">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canWrite} checked={!!v.briefing_slack} onChange={(e) => set("briefing_slack", e.target.checked)} /> Slack (simulado)</label>
            <input className="input w-full" disabled={!canWrite || !v.briefing_slack} value={v.briefing_slack_channel || ""} onChange={(e) => set("briefing_slack_channel", e.target.value)} placeholder="#operacoes" />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!canWrite} checked={!!v.briefing_email} onChange={(e) => set("briefing_email", e.target.checked)} /> E-mail (simulado)</label>
            <input className="input w-full" disabled={!canWrite || !v.briefing_email}
              value={typeof v.briefing_email_to === "string" ? v.briefing_email_to : (v.briefing_email_to || []).join(", ")}
              onChange={(e) => set("briefing_email_to", e.target.value)} placeholder="gestor@empresa.com, outra@empresa.com" />
          </div>
        </div>
      </Card>
      {canWrite && <div className="flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={save}>Salvar recursos</button><Saved show={saved} /></div>}
    </div>
  );
}
