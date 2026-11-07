"use client";
import { useState } from "react";
import { PlugZap, RefreshCw } from "lucide-react";
import { ENTITY_SOURCE_LABEL, fmt } from "@/components/labels";
import { Badge, Card, DataTable, DemoBadge, ErrorBox, JsonBlock, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";

const EXAMPLE = JSON.stringify({
  base_url: "https://SUA-API-INTERNA",
  endpoint: "/v1/orders",
  auth: { type: "bearer", token_env: "ORDERS_API_TOKEN" },
  pagination: { type: "page", page_param: "page", size_param: "per_page", page_size: 200, data_path: "data" },
  incremental: { param: "updated_since", cursor_field: "updated_at" },
  schema_version: "1.0",
}, null, 2);

export default function SourcesPage() {
  const { data, error, loading, reload } = useApi<any[]>("/sources");
  const { can } = useAuth();
  const action = useAction();
  const [result, setResult] = useState<any>(null);
  const [form, setForm] = useState({ key: "", name: "", entity: "orders", config: EXAMPLE });
  const [edit, setEdit] = useState<{ key: string; name: string; config: string } | null>(null);
  const saveEdit = async () => {
    if (!edit) return;
    let config: any;
    try { config = JSON.parse(edit.config); } catch { setResult({ error: "JSON de configuração inválido" }); return; }
    const r = await action.run(`/sources/${edit.key}`, { name: edit.name, config });
    if (r) { setEdit(null); setResult(r); reload(); }
  };
  const setStatus = async (key: string, status: string) => {
    if (status === "inactive" && !(await confirm({ title: "Desativar esta fonte?", description: "Ela deixará de ser sincronizada e seus dados não entrarão nos próximos processamentos.", confirmLabel: "Desativar", tone: "danger" }))) return;
    if (await action.run(`/sources/${key}`, { status }, undefined, { success: status === "active" ? "Fonte ativada" : "Fonte desativada" })) reload();
  };
  const confirm = useConfirm();
  const resetCursor = async (key: string) => {
    const ok = await confirm({ title: "Reiniciar o cursor incremental?", description: "A próxima sincronização buscará todos os registros da fonte novamente.", confirmLabel: "Reiniciar" });
    if (ok && await action.run(`/sources/${key}/cursor/reset`, undefined, undefined, { success: "Cursor reiniciado" })) reload();
  };

  const test = async (key: string) => setResult(await action.run(`/sources/${key}/test`));
  const sync = async (key: string) => { setResult(await action.run(`/sources/${key}/sync`, { full_refresh: false }, undefined, { success: "Sincronização concluída", successDescription: "Execute o pipeline para atualizar Silver/Gold." })); reload(); };
  const create = async () => {
    let config: any;
    try { config = JSON.parse(form.config); } catch { setResult({ error: "JSON de configuração inválido" }); return; }
    const r = await action.run("/sources", { key: form.key, name: form.name, entity: form.entity, connector: "http_json", config });
    if (r) { setResult(r); reload(); }
  };

  return (
    <>
      <PageHeader kicker="L0 · Fontes" title="Fontes de dados"
        subtitle="Cada integração é independente. Conectores padronizam autenticação, paginação, retentativas, rate limit e execução incremental. Credenciais vêm apenas de variáveis de ambiente." />
      <ErrorBox error={action.error || error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && (
        <Card title="Fontes registradas">
          <DataTable rows={data} columns={[
            { key: "name", label: "Fonte", render: (r: any) => <div><div className="text-slate-100">{r.name}</div><code className="text-xs text-slate-500">{r.key}</code></div> },
            { key: "entity", label: "Entidade", render: (r: any) => <Badge tone="blue">{ENTITY_SOURCE_LABEL[r.entity] || r.entity}</Badge> },
            { key: "connector", label: "Conector", render: (r: any) => <span>{r.connector} {r.is_demo && <DemoBadge />}</span> },
            { key: "last_run", label: "Última ingestão", render: (r: any) => r.last_run ? <div><StatusBadge status={r.last_run.status} /> <span className="text-xs text-slate-400">{fmt.num(r.last_run.records_ingested)} reg. · {fmt.date(r.last_run.started_at)}</span>{r.last_run.error && <div className="text-xs text-rose-300">{r.last_run.error}</div>}</div> : "—" },
            { key: "cursor", label: "Cursor incremental", render: (r: any) => <code className="text-xs">{r.cursor || "—"}</code> },
            { key: "status", label: "Status", render: (r: any) => <StatusBadge status={r.status} /> },
            { key: "actions", label: "", render: (r: any) => (
              <div className="flex flex-wrap gap-1">
                <button className="btn-ghost" disabled={action.busy} onClick={() => test(r.key)}><PlugZap size={13} /> Testar</button>
                {can("data:sync") && r.status === "active" && <button className="btn-ghost" disabled={action.busy} onClick={() => sync(r.key)}><RefreshCw size={13} /> Sincronizar</button>}
                {can("data:write") && <>
                  <button className="btn-ghost" onClick={() => setEdit({ key: r.key, name: r.name, config: JSON.stringify(Object.fromEntries(Object.entries(r.config).filter(([k]) => k !== "entity")), null, 2) })}>Editar</button>
                  <button className="btn-ghost" disabled={action.busy} onClick={() => setStatus(r.key, r.status === "active" ? "inactive" : "active")}>{r.status === "active" ? "Desativar" : "Ativar"}</button>
                  {r.cursor && <button className="btn-ghost" disabled={action.busy} onClick={() => resetCursor(r.key)}>Reiniciar cursor</button>}
                </>}
              </div>) },
          ]} />
        </Card>
      )}
      {edit && (
        <Card className="mt-4" title={`Editar fonte ${edit.key}`} subtitle="Credenciais nunca inline: use apenas o NOME da variável de ambiente (ex.: auth.token_env).">
          <input className="input mb-3 w-full" aria-label="Nome" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
          <textarea className="input h-56 w-full font-mono text-xs" aria-label="Configuração JSON" value={edit.config} onChange={(e) => setEdit({ ...edit, config: e.target.value })} />
          <div className="mt-3 flex gap-2"><button className="btn-primary" disabled={action.busy} onClick={saveEdit}>Salvar</button><button className="btn-ghost" onClick={() => setEdit(null)}>Cancelar</button></div>
        </Card>
      )}
      {result && <Card className="mt-4" title="Resultado"><JsonBlock value={result} /></Card>}
      {can("data:write") && (
        <Card className="mt-5" title="Registrar fonte REST/JSON" subtitle="Nenhum contrato é presumido: informe URL, endpoint, paginação e o NOME da variável de ambiente com a credencial.">
          <div className="grid gap-3 md:grid-cols-3">
            <input className="input" placeholder="chave (ex.: erp_orders)" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} />
            <input className="input" placeholder="Nome" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <select className="input" value={form.entity} onChange={(e) => setForm({ ...form, entity: e.target.value })}>
              <option value="orders">Pedidos</option><option value="nps">Avaliações/NPS</option><option value="deliveries">Entregas</option>
            </select>
          </div>
          <textarea className="input mt-3 h-56 w-full font-mono text-xs" value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })} />
          <button className="btn-primary mt-3" disabled={action.busy || !form.key || !form.name} onClick={create}>Registrar fonte</button>
        </Card>
      )}
    </>
  );
}
