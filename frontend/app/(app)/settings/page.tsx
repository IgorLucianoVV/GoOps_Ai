"use client";
import Link from "next/link";
import { useState } from "react";
import { Badge, Card, DataTable, ErrorBox, JsonBlock, Loading, PageHeader, Tabs } from "@/components/ui";
import AutomationPanel from "@/features/settings/AutomationPanel";
import DomainsPanel from "@/features/settings/DomainsPanel";
import FeaturesPanel from "@/features/settings/FeaturesPanel";
import { Field } from "@/features/settings/common";
import ModelsPanel from "@/features/settings/ModelsPanel";
import PoliciesPanel from "@/features/settings/PoliciesPanel";
import SupportPanel from "@/features/settings/SupportPanel";
import TeamChannelPanel from "@/features/settings/TeamChannelPanel";
import UsersPanel from "@/features/settings/UsersPanel";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

export default function SettingsPage() {
  const s = useApi<any>("/settings");
  const cfg = useApi<any>("/settings/config");
  const sources = useApi<any[]>("/sources");
  const { can } = useAuth();
  const canWrite = can("settings:write");
  const [tab, setTab] = useState("models");
  const reload = () => { s.reload(); cfg.reload(); };
  const pwd = useAction();
  const [newPwd, setNewPwd] = useState("");
  const [pwdOk, setPwdOk] = useState(false);

  return (
    <>
      <PageHeader kicker="Configurações" title="Configurações"
        subtitle="Modelos, chaves de API, limites, monitoramento, agendamento, retenção, políticas, usuários, domínios e integrações — tudo configurado aqui. Valores salvos na interface têm precedência sobre o .env."
        actions={!canWrite && <Badge tone="amber">somente leitura para o seu papel</Badge>} />
      <ErrorBox error={s.error || cfg.error} onRetry={reload} />
      {(s.loading || cfg.loading) && !(s.data && cfg.data) && <Loading />}
      {s.data && cfg.data && (
        <>
          <Tabs active={tab} onChange={setTab} tabs={[
            { key: "models", label: "Modelos e chaves" }, { key: "features", label: "Recursos" }, { key: "support", label: "Atendimento" }, { key: "team", label: "Canal do time" }, { key: "automation", label: "Monitor, agendador e retenção" },
            { key: "policies", label: "Políticas" }, { key: "users", label: "Usuários" }, { key: "domains", label: "Domínios" },
            { key: "integrations", label: "Integrações" }, { key: "roles", label: "Permissões" }, { key: "account", label: "Minha conta" },
            { key: "env", label: "Ambiente" }]} />
          {tab === "models" && <ModelsPanel config={cfg.data} onSaved={reload} canWrite={canWrite} />}
          {tab === "features" && <FeaturesPanel config={cfg.data} onSaved={reload} canWrite={canWrite} />}
          {tab === "support" && <SupportPanel config={cfg.data} onSaved={reload} canWrite={canWrite} />}
          {tab === "team" && <TeamChannelPanel config={cfg.data} onSaved={reload} canWrite={canWrite} />}
          {tab === "automation" && <AutomationPanel config={cfg.data} onSaved={reload} canWrite={canWrite} />}
          {tab === "policies" && <PoliciesPanel config={cfg.data} settings={s.data} onSaved={reload} canWrite={canWrite} />}
          {tab === "users" && <UsersPanel domains={s.data.domains} canWrite={canWrite} />}
          {tab === "domains" && <DomainsPanel domains={s.data.domains} onSaved={reload} canWrite={canWrite} />}
          {tab === "integrations" && <Card title="Fontes de dados" actions={<Link className="btn-ghost" href="/lakehouse/sources">Gerenciar fontes →</Link>}>
            <DataTable rows={sources.data || []} columns={[{ key: "key", label: "Chave" }, { key: "name", label: "Nome" }, { key: "entity", label: "Entidade" },
              { key: "connector", label: "Conector" }, { key: "status", label: "Status", render: (r: any) => <Badge tone={r.status === "active" ? "green" : "gray"}>{({ active: "Ativa", inactive: "Inativa", disabled: "Desativada" } as Record<string, string>)[r.status] || r.status}</Badge> }]} />
          </Card>}
          {tab === "roles" && <div className="space-y-4">
            <Card title="Papéis de usuário" subtitle="Atribua papéis e domínios na aba Usuários."><DataTable rows={s.data.roles} columns={[{ key: "label", label: "Papel" }, { key: "permissions", label: "Permissões", render: (r: any) => <div className="flex flex-wrap gap-1">{r.permissions.map((p: string) => <Badge key={p}>{p}</Badge>)}</div> }]} /></Card>
            <Card title="Permissões dos agentes (explícitas e mínimas)"><JsonBlock value={s.data.agent_permissions} /></Card>
          </div>}
          {tab === "account" && <Card title="Alterar minha senha">
            <div className="flex max-w-md items-end gap-2">
              <Field label="Nova senha" hint="mín. 8 caracteres"><input className="input w-full" type="password" autoComplete="new-password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} /></Field>
              <button className="btn-primary" disabled={pwd.busy || newPwd.length < 8} onClick={async () => { if (await pwd.run("/auth/password", { password: newPwd })) { setNewPwd(""); setPwdOk(true); } }}>Salvar</button>
            </div>
            {pwdOk && <div role="status" className="mt-2 text-xs text-emerald-300">Senha alterada.</div>}
            <ErrorBox error={pwd.error} />
          </Card>}
          {tab === "env" && <Card title="Ambiente (infraestrutura — definido no servidor)"><JsonBlock value={s.data.environment} /></Card>}
        </>
      )}
    </>
  );
}
