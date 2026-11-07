"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Send } from "lucide-react";
import { Badge, Card } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { Field, Saved, SavedInfo } from "./common";

/** Onde os agentes conversam com o time: mural do app (sempre), Telegram (bot com aprovação por botão) ou Slack (avisos). */
export default function TeamChannelPanel({ config, onSaved, canWrite }: { config: any; onSaved: () => void; canWrite: boolean }) {
  const sec = config.sections.team_channel;
  const secrets = config.secrets || {};
  const action = useAction();
  const [v, setV] = useState<any>(sec.value);
  const [tok, setTok] = useState("");
  const [hook, setHook] = useState("");
  const [saved, setSaved] = useState(false);
  const [testOut, setTestOut] = useState<any>(null);
  useEffect(() => setV(sec.value), [config]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: string, val: any) => setV({ ...v, [k]: val });
  const save = async () => {
    if (tok && !(await action.run("/settings/secrets/telegram_bot_token", { value: tok }))) return;
    if (hook && !(await action.run("/settings/secrets/slack_webhook_url", { value: hook }))) return;
    if (await action.run("/settings/config/team_channel", { value: v }, undefined, { success: "Canal do time atualizado" })) {
      setTok(""); setHook(""); setSaved(true); setTimeout(() => setSaved(false), 2500); onSaved();
    }
  };
  const sec_ = (n: string) => secrets[n]?.configured ? <Badge tone="green">configurado · {secrets[n].hint}</Badge> : <Badge>não configurado</Badge>;
  return (
    <div className="space-y-4">
      <Card title="Canal do time" actions={<SavedInfo section={sec} />}
        subtitle="O Agente de Atendimento avisa, pede aprovação e recebe pedidos onde o time já conversa. O mural do GoOps (Canal do time) registra tudo sempre.">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Onde o agente conversa">
            <select className="input w-full" disabled={!canWrite} value={v.provider} onChange={(e) => set("provider", e.target.value)}>
              <option value="app">Só no GoOps (mural Canal do time)</option>
              <option value="telegram">Telegram (avisos + aprovação por botão + comandos)</option>
              <option value="slack">Slack (avisos por webhook)</option>
            </select>
          </Field>
          <Field label="Endereço do GoOps (links nas mensagens)"><input className="input w-full" disabled={!canWrite} value={v.app_base_url} onChange={(e) => set("app_base_url", e.target.value)} /></Field>
          <div className="space-y-1 pt-5 text-sm">
            {[["notify_approvals", "Pedidos de aprovação"], ["notify_sla", "SLA estourado"], ["notify_incidents", "Incidentes"], ["notify_digest", "Resumo do dia"]].map(([k, l]) => (
              <label key={k} className="flex items-center gap-2"><input type="checkbox" disabled={!canWrite} checked={!!v[k]} onChange={(e) => set(k, e.target.checked)} /> {l}</label>
            ))}
          </div>
        </div>
      </Card>
      <Card title="Telegram" actions={sec_("telegram_bot_token")}
        subtitle="1) No Telegram, fale com @BotFather → /newbot e copie o token. 2) Crie um grupo do time e adicione o bot. 3) Descubra o ID do grupo (ex.: adicione @RawDataBot) e cole abaixo. Cada pessoa vincula a própria conta em Canal do time para aprovar pelo celular.">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Token do bot" hint="guardado cifrado; nunca exibido de novo"><input className="input w-full" type="password" autoComplete="off" disabled={!canWrite} value={tok} onChange={(e) => setTok(e.target.value)} placeholder="123456:ABC-…" /></Field>
          <Field label="ID do grupo/canal" hint="ex.: -1001234567890"><input className="input w-full" disabled={!canWrite} value={v.telegram_chat_id} onChange={(e) => set("telegram_chat_id", e.target.value)} /></Field>
        </div>
      </Card>
      <Card title="Slack" actions={sec_("slack_webhook_url")} subtitle="Incoming Webhook do canal (https://hooks.slack.com/…). Só avisos: para aprovar, a mensagem traz o link do GoOps.">
        <Field label="URL do webhook"><input className="input w-full" type="password" autoComplete="off" disabled={!canWrite} value={hook} onChange={(e) => setHook(e.target.value)} placeholder="https://hooks.slack.com/services/…" /></Field>
      </Card>
      {canWrite && <div className="flex flex-wrap items-center gap-3">
        <button className="btn-primary" disabled={action.busy} onClick={save}>Salvar canal do time</button>
        <button className="btn-ghost" disabled={action.busy} onClick={async () => setTestOut(await action.run("/team/test", {}, undefined, { success: "Mensagem de teste publicada" })) }><Send size={14} /> Enviar teste</button>
        <Link className="btn-ghost" href="/canal">Abrir Canal do time</Link>
        <Saved show={saved} />
        {testOut && <Badge tone={testOut.delivery === "failed" ? "red" : "green"}>{testOut.delivery === "failed" ? `falhou: ${testOut.error}` : testOut.delivery === "delivered" ? "entregue no canal externo" : "publicado no mural do app"}</Badge>}
      </div>}
    </div>
  );
}
