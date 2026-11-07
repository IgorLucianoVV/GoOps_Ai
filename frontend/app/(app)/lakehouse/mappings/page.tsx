"use client";
import { useEffect, useMemo, useState } from "react";
import { Copy, Eye, Play, Save } from "lucide-react";
import { FIELD_TYPE_LABEL, fmt } from "@/components/labels";
import { Badge, Card, DataTable, Empty, ErrorBox, Kpi, PageHeader, PageSkeleton, Tabs } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";

type Mode = "from" | "compose" | "derive";
interface Row { field: string; mode: Mode; paths: string; type: string; source: string; required: boolean; help?: string }
const ENTITY_LABEL: Record<string, string> = { orders: "Pedidos", nps: "Avaliações (NPS)", deliveries: "Entregas" };

function toRows(schema: any, entity: string, def: any): Row[] {
  return schema.entities[entity].fields.map((f: any) => {
    const spec = def?.fields?.[f.field] || {};
    const mode: Mode = spec.compose ? "compose" : spec.derive ? "derive" : "from";
    const paths = (spec.compose || spec.from || []).join(", ");
    return { field: f.field, mode, paths, type: spec.type || f.type, source: spec.source || "", required: f.required, help: f.help };
  });
}

function toDefinition(rows: Row[], grain: string) {
  const fields: Record<string, any> = {};
  rows.forEach((r) => {
    const list = r.paths.split(",").map((p) => p.trim()).filter(Boolean);
    if (r.mode === "derive") fields[r.field] = { derive: "product_line_from_name", source: r.source.trim(), type: r.type };
    else if (r.mode === "compose") fields[r.field] = { compose: list, type: r.type };
    else fields[r.field] = { from: list, type: r.type };
  });
  return { fields, grain };
}

export default function MappingsPage() {
  const schema = useApi<any>("/mapping/schema");
  const profiles = useApi<any[]>("/mapping/profiles");
  const sources = useApi<any[]>("/sources");
  const { can } = useAuth();
  const canWrite = can("data:write");
  const confirm = useConfirm();
  const action = useAction();
  const prev = useAction();
  const [entity, setEntity] = useState("nps");
  const [selected, setSelected] = useState<any>(null);
  const [key, setKey] = useState("");
  const [grain, setGrain] = useState("evaluation");
  const [rows, setRows] = useState<Row[]>([]);
  const [focusField, setFocusField] = useState<string | null>(null);
  const [sourceKey, setSourceKey] = useState("");
  const [sample, setSample] = useState("");
  const [useSample, setUseSample] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [note, setNote] = useState("");
  const [applyTo, setApplyTo] = useState("");

  const list = (profiles.data || []).filter((p) => p.entity === entity);
  const entitySources = (sources.data || []).filter((s) => s.entity === entity);
  const versions = useApi<any[]>(selected && !selected.builtin ? `/mapping/profiles/${selected.profile_key}/${entity}/versions` : null);

  const open = (p: any, duplicate = false) => {
    setSelected(p);
    setKey(duplicate || p.builtin ? `${p.profile_key === "default" ? "meu_perfil" : p.profile_key}_${entity}_v2`.slice(0, 41) : p.profile_key);
    setGrain(p.definition.grain || schema.data.entities[entity].natural_key);
    setRows(toRows(schema.data, entity, p.definition));
    setResult(null);
    const used = entitySources.find((s) => (s.config.mapping_profile || "default") === p.profile_key);
    setSourceKey(used?.key || entitySources[0]?.key || "");
  };
  useEffect(() => { setSelected(null); setRows([]); setResult(null); }, [entity]);
  useEffect(() => {
    if (!selected && schema.data && profiles.data) {
      const first = profiles.data.find((p) => p.entity === entity && p.used_by?.length) || profiles.data.find((p) => p.entity === entity);
      if (first) open(first);
    }
  }, [schema.data, profiles.data, entity]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRow = (field: string, patch: Partial<Row>) => setRows(rows.map((r) => (r.field === field ? { ...r, ...patch } : r)));
  const definition = useMemo(() => toDefinition(rows, grain), [rows, grain]);
  const editable = canWrite && selected && (!selected.builtin || key !== selected.profile_key);

  const runPreview = async () => {
    let parsed: any = undefined;
    if (useSample) {
      try { parsed = JSON.parse(sample); if (!Array.isArray(parsed)) parsed = [parsed]; }
      catch { prev.clearError(); setResult({ error: "JSON da amostra inválido. Cole um objeto ou uma lista de objetos." }); return; }
    }
    const r = await prev.run("/mapping/preview", { entity, definition, source_key: useSample ? undefined : sourceKey, sample: parsed, limit: 300 });
    if (r) setResult(r);
  };
  const save = async (reprocess: boolean) => {
    if (reprocess && !(await confirm({ title: "Salvar e reprocessar?", confirmLabel: "Salvar e reprocessar",
      description: "O perfil será salvo como nova versão e a Silver/Gold serão reconstruídas a partir da Bronze (sem chamar as APIs)." }))) return;
    const saved = await action.run("/mapping/profiles", { profile_key: key, entity, definition, change_note: note,
      based_on: selected?.builtin ? selected.profile_key : undefined }, undefined, { success: `Perfil ${key} salvo` });
    if (!saved) return;
    setNote("");
    if (applyTo) {
      const src = entitySources.find((s) => s.key === applyTo);
      if (src) {
        const { entity: _e, ...cfg } = src.config;
        await action.run(`/sources/${applyTo}`, { config: { ...cfg, mapping_profile: key } }, undefined, { success: `Fonte ${applyTo} agora usa ${key}` });
      }
    }
    if (reprocess) await action.run("/data/pipeline/run", { sync: false }, undefined, { success: "Dados reprocessados com o novo mapeamento" });
    profiles.reload(); sources.reload(); versions.reload();
    setSelected({ ...saved });
  };
  const addPath = (path: string) => {
    if (!focusField) return;
    const r = rows.find((x) => x.field === focusField);
    if (!r) return;
    const list = r.paths.split(",").map((p) => p.trim()).filter(Boolean);
    if (!list.includes(path)) setRow(focusField, { paths: [...list, path].join(", "), mode: r.mode === "derive" ? "from" : r.mode });
  };

  if (schema.loading || profiles.loading) return <PageSkeleton />;
  return (
    <>
      <PageHeader kicker="Lakehouse de dados" title="Mapeamentos de fontes"
        subtitle="Diga de onde vem cada campo canônico quando uma API ou planilha muda. Pré-visualize com dados reais da Bronze, salve como nova versão e reprocesse — métricas e dashboards não precisam mudar." />
      <ErrorBox error={schema.error || profiles.error} onRetry={profiles.reload} />
      <Tabs active={entity} onChange={setEntity} tabs={Object.keys(ENTITY_LABEL).map((k) => ({ key: k, label: ENTITY_LABEL[k] }))} />
      <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
        <Card title="Perfis">
          <ul className="space-y-2">
            {list.map((p) => (
              <li key={p.profile_key}>
                <button onClick={() => open(p)} aria-pressed={selected?.profile_key === p.profile_key}
                  className={`w-full rounded-lg border p-3 text-left text-sm ${selected?.profile_key === p.profile_key ? "border-brand-500 bg-ink-800" : "border-ink-700 hover:bg-ink-800"}`}>
                  <div className="flex items-center justify-between gap-2"><code className="font-medium text-white">{p.profile_key}</code>
                    {p.builtin ? <Badge>embutido</Badge> : <Badge tone="teal">v{p.version}</Badge>}</div>
                  <div className="mt-1 text-xs text-slate-500">{p.used_by?.length ? `Usado por: ${p.used_by.join(", ")}` : "Não usado por fontes"}</div>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">Perfis embutidos são somente leitura: duplique para editar.</p>
        </Card>

        {!selected ? <Card><Empty title="Selecione um perfil" hint="Escolha um perfil à esquerda para ver e editar o mapeamento." /></Card> : (
          <div className="space-y-5">
            <Card title="Identificação" actions={selected.builtin && canWrite && <button className="btn-ghost" onClick={() => open(selected, true)}><Copy size={14} aria-hidden /> Duplicar para editar</button>}>
              <div className="grid gap-3 md:grid-cols-3">
                <label><span className="label">Chave do perfil</span>
                  <input className="input mt-1 w-full font-mono" value={key} disabled={!canWrite} onChange={(e) => setKey(e.target.value.toLowerCase())} aria-describedby="key-help" />
                  <span id="key-help" className="mt-0.5 block text-[11px] text-slate-500">minúsculas, números e _ (ex.: nps_api_v2)</span></label>
                {entity === "orders" && <label><span className="label">Grão da fonte</span>
                  <select className="input mt-1 w-full" value={grain} disabled={!editable} onChange={(e) => setGrain(e.target.value)}>
                    <option value="order">1 linha por pedido</option><option value="item">1 linha por item (agrega por pedido)</option></select></label>}
                <div><span className="label">Situação</span><div className="mt-2 text-sm text-slate-300">
                  {selected.builtin && key === selected.profile_key ? "Somente leitura (embutido)" : selected.builtin ? `Novo perfil baseado em ${selected.profile_key}` : `Versão atual v${selected.version} · ${fmt.date(selected.updated_at)}`}</div></div>
              </div>
            </Card>

            <Card title="Campos canônicos" subtitle="Informe um ou mais caminhos de origem (separados por vírgula): o primeiro encontrado é usado. Aceita campos aninhados com ponto, ex.: order.code ou items.0.sku.">
              <div className="overflow-auto">
                <table className="table w-full">
                  <thead><tr><th scope="col">Campo</th><th scope="col">Modo</th><th scope="col">Origem na API/planilha</th><th scope="col">Tipo</th><th scope="col">Prévia</th></tr></thead>
                  <tbody>
                    {rows.map((r) => {
                      const fr = result?.fields?.find((f: any) => f.field === r.field);
                      const missing = r.required && !r.paths.trim() && r.mode !== "derive";
                      return (
                        <tr key={r.field} className={focusField === r.field ? "bg-ink-800/60" : undefined}>
                          <td><code className="text-white">{r.field}</code>{r.required && <Badge tone="amber" className="ml-1.5">obrigatório</Badge>}
                            {r.help && <div className="mt-0.5 max-w-[220px] text-[11px] text-slate-500">{r.help}</div>}</td>
                          <td><select aria-label={`Modo de ${r.field}`} className="input" disabled={!editable} value={r.mode} onChange={(e) => setRow(r.field, { mode: e.target.value as Mode })}>
                            <option value="from">Campo</option><option value="compose">Chave composta</option>
                            {r.field === "product_line" && <option value="derive">Regra (nome do material)</option>}</select></td>
                          <td>{r.mode === "derive"
                            ? <input aria-label={`Campo base de ${r.field}`} className="input w-full font-mono text-xs" disabled={!editable} value={r.source} onChange={(e) => setRow(r.field, { source: e.target.value })} placeholder="ex.: material_name" />
                            : <input aria-label={`Origem de ${r.field}`} aria-invalid={missing} onFocus={() => setFocusField(r.field)}
                                className={`input w-full font-mono text-xs ${missing ? "border-rose-500" : ""}`} disabled={!editable} value={r.paths}
                                onChange={(e) => setRow(r.field, { paths: e.target.value })} placeholder={r.mode === "compose" ? "campo_a, campo_b" : "nome_do_campo"} />}
                            {missing && <div className="mt-0.5 text-[11px] text-rose-300">Campo obrigatório sem origem.</div>}</td>
                          <td><select aria-label={`Tipo de ${r.field}`} className="input" disabled={!editable} value={r.type} onChange={(e) => setRow(r.field, { type: e.target.value })}>
                            {schema.data.types.map((t: string) => <option key={t} value={t}>{FIELD_TYPE_LABEL[t] || t}</option>)}</select></td>
                          <td className="text-xs">{fr ? <>
                            <span className={fr.coverage_pct === 0 && fr.configured ? "text-rose-300" : fr.coverage_pct < 100 ? "text-amber-300" : "text-emerald-300"}>{fmt.pct(fr.coverage_pct, 0)} preenchido</span>
                            {fr.cast_errors > 0 && <div className="text-rose-300">{fr.cast_errors} erro(s) de tipo</div>}
                            {fr.examples.length > 0 && <div className="mt-0.5 max-w-[200px] truncate text-slate-500" title={fr.examples.join(" · ")}>ex.: {fr.examples.join(" · ")}</div>}
                          </> : <span className="text-slate-500">—</span>}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Pré-visualizar com dados reais" subtitle="Nada é gravado. Use os payloads mais recentes da Bronze de uma fonte, ou cole um exemplo da nova versão da API.">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex items-center gap-2 text-sm"><input type="radio" checked={!useSample} onChange={() => setUseSample(false)} /> Bronze da fonte</label>
                <select aria-label="Fonte para prévia" className="input" disabled={useSample} value={sourceKey} onChange={(e) => setSourceKey(e.target.value)}>
                  {entitySources.map((s) => <option key={s.key} value={s.key}>{s.key}</option>)}</select>
                <label className="flex items-center gap-2 text-sm"><input type="radio" checked={useSample} onChange={() => setUseSample(true)} /> Colar exemplo JSON</label>
                <button className="btn-primary" disabled={prev.busy || (!useSample && !sourceKey)} onClick={runPreview}><Eye size={14} aria-hidden /> Pré-visualizar</button>
              </div>
              {useSample && <textarea aria-label="Exemplo de registro (JSON)" className="input mt-3 h-36 w-full font-mono text-xs" value={sample} onChange={(e) => setSample(e.target.value)}
                placeholder='[{"id": "E1", "order": {"code": "0001"}, "rating": 9, "created_at": "2026-01-02T10:00:00Z"}]' />}
              {result?.error && <div role="alert" className="mt-3 text-sm text-rose-300">{result.error}</div>}
              {result && !result.error && (
                <div className="mt-4 space-y-4">
                  {result.message ? <Empty title="Sem dados para prévia" hint={result.message} /> : <>
                    <div className="grid grid-cols-3 gap-3">
                      <Kpi label="Registros analisados" value={fmt.num(result.records)} />
                      <Kpi label="Válidos" value={fmt.num(result.valid)} tone="good" />
                      <Kpi label="Iriam para quarentena" value={fmt.num(result.quarantined)} tone={result.quarantined ? "bad" : "default"} />
                    </div>
                    <div>
                      <div className="label mb-1">Campos encontrados no registro</div>
                      <p className="mb-2 text-xs text-slate-500">{focusField ? <>Clique para adicionar à origem de <code>{focusField}</code>.</> : "Clique no campo de origem de uma linha acima e depois em um campo abaixo para adicioná-lo."}
                        {" "}Campos ainda não usados aparecem destacados — geralmente são os renomeados.</p>
                      <div className="flex flex-wrap gap-1.5">
                        {result.payload_keys.map((k: any) => (
                          <button key={k.path} disabled={!editable || !focusField} onClick={() => addPath(k.path)}
                            className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] disabled:cursor-default ${k.used ? "border-ink-600 text-slate-500" : "border-coral-500/60 bg-coral-400/10 text-coral-300"}`}>
                            {k.path}</button>))}
                      </div>
                    </div>
                    <DataTable caption="Amostra mapeada" maxHeight={360} rows={result.rows.map((r: any) => ({ ...r.values, _q: r.quarantine_reasons }))}
                      columns={[{ key: "_q", label: "Situação", render: (r: any) => r._q.length ? <Badge tone="red">quarentena: {r._q.join(", ")}</Badge> : <Badge tone="green">válido</Badge> },
                        ...rows.filter((x) => x.paths || x.mode === "derive").map((x) => ({ key: x.field, label: x.field }))]} />
                  </>}
                </div>
              )}
              <ErrorBox error={prev.error} />
            </Card>

            {editable && (
              <Card title="Salvar como nova versão">
                <div className="grid gap-3 md:grid-cols-[1fr_220px]">
                  <label><span className="label">O que mudou</span><input className="input mt-1 w-full" value={note} onChange={(e) => setNote(e.target.value)} placeholder="ex.: API v2 renomeou nota → rating" /></label>
                  <label><span className="label">Aplicar à fonte (opcional)</span><select className="input mt-1 w-full" value={applyTo} onChange={(e) => setApplyTo(e.target.value)}>
                    <option value="">Não alterar fontes</option>{entitySources.map((s) => <option key={s.key} value={s.key}>{s.key}</option>)}</select></label>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className="btn-ghost" disabled={action.busy || note.length < 5} onClick={() => save(false)}><Save size={14} aria-hidden /> Salvar</button>
                  <button className="btn-primary" disabled={action.busy || note.length < 5} onClick={() => save(true)}><Play size={14} aria-hidden /> Salvar e reprocessar</button>
                </div>
                <p className="mt-2 text-xs text-slate-500">Dica: rode a prévia antes. Registros que falharem nas regras de qualidade vão para a quarentena com o motivo — nada é descartado em silêncio.</p>
                <ErrorBox error={action.error} />
              </Card>
            )}

            {!selected.builtin && (
              <Card title="Histórico de versões">
                <DataTable rows={versions.data || []} empty="Sem versões" columns={[
                  { key: "version", label: "Versão", render: (r: any) => <code>v{r.version}</code> }, { key: "change_note", label: "Alteração" },
                  { key: "created_by", label: "Por" }, { key: "created_at", label: "Quando", render: (r: any) => fmt.date(r.created_at) },
                  { key: "load", label: "", render: (r: any) => <button className="btn-ghost" onClick={() => { setRows(toRows(schema.data, entity, r.definition)); setGrain(r.definition.grain || grain); }}>Carregar no editor</button> },
                ]} />
              </Card>
            )}
          </div>
        )}
      </div>
    </>
  );
}
