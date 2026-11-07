"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, Link2, Loader2, Plus, Search, Sparkles, Trash2 } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { api } from "@/services/api";
import { useAction, useApi } from "@/hooks/useApi";

const TYPES = [["id", "Identificador"], ["string", "Texto"], ["int", "Inteiro"], ["float", "Decimal"], ["datetime", "Data/hora"], ["bool", "Sim/Não"]];
const ROLES = [["key", "Chave"], ["time", "Data"], ["dimension", "Dimensão (agrupar/filtrar)"], ["measure", "Medida (calcular)"], ["text", "Texto livre"], ["attribute", "Atributo"]];
const STEPS = ["Setor", "Fonte", "Campos", "Processar", "Métricas e painel"];
const slug = (t: string) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");

function Steps({ step }: { step: number }) {
  return (
    <ol className="mb-5 flex flex-wrap gap-2" aria-label="Etapas">
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === step ? "step" : undefined}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${i === step ? "border-brand-600 text-white" : i < step ? "border-emerald-700 text-emerald-300" : "border-ink-700 text-slate-500"}`}>
          {i < step ? <Check size={12} aria-hidden /> : <span className="tabular-nums">{i + 1}</span>} {s}
        </li>
      ))}
    </ol>
  );
}

function Wizard() {
  const qs = useSearchParams();
  const action = useAction();
  const sectors = useApi<any[]>("/sectors");
  const [step, setStep] = useState(0);
  const editKey = qs.get("conjunto");
  const [domain, setDomain] = useState<string>(qs.get("setor") || "");
  const [newSector, setNewSector] = useState({ name: "", description: "" });
  const detail = useApi<any>(domain ? `/sectors/${domain}` : null);
  const allSources = useApi<any[]>("/sources");
  const [sourceKey, setSourceKey] = useState("");
  const [src, setSrc] = useState<any>({ name: "", connector: "file", path: "", format: "xlsx", base_url: "", endpoint: "", data_path: "", token_env: "" });
  const [fields, setFields] = useState<any[]>([]);
  const [keyField, setKeyField] = useState("");
  const [timeField, setTimeField] = useState("");
  const [derived, setDerived] = useState({ name: "", label: "", a: "", b: "" });
  const [discovery, setDiscovery] = useState<any>(null);
  const [rels, setRels] = useState<any[]>([]);
  const [relDraft, setRelDraft] = useState<any>({ field: "", dataset: "", on: "", bring: [] as string[] });
  const joinable = useApi<any[]>(step === 2 ? "/sectors/joinable/datasets" : null, editKey ? { exclude: `gold_${editKey}` } : undefined);
  const [ds, setDs] = useState({ key: "", name: "", description: "" });
  const [built, setBuilt] = useState<any>(null);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [result, setResult] = useState<any>(null);

  useEffect(() => { if (qs.get("setor")) setStep(1); }, [qs]);
  // edição de conjunto existente: carrega a definição atual
  useEffect(() => {
    if (!editKey || !detail.data) return;
    const cur = detail.data.datasets.find((x: any) => x.key === editKey);
    if (!cur) return;
    setDs({ key: cur.key, name: cur.name, description: cur.description || "" });
    setSourceKey(cur.definition.source_keys[0]);
    setFields(cur.definition.fields.map((f: any) => ({ ...f, path: f.from, include: true, examples: [], fill_pct: null })));
    setKeyField(cur.definition.key_field); setTimeField(cur.definition.time_field || "");
    setRels(cur.definition.relationships || []);
  }, [editKey, detail.data]);

  const sectorSources = useMemo(() => (allSources.data || []).filter((s: any) => s.entity === "custom" &&
    (!s.config?.domain || s.config.domain === domain)), [allSources.data, domain]);
  const included = fields.filter((f) => f.include);
  const dateFields = included.filter((f) => f.type === "datetime" && !f.derive);

  const createSector = async () => {
    const key = slug(newSector.name).slice(0, 30);
    const r = await action.run("/sectors", { key, name: newSector.name, description: newSector.description }, undefined, { success: "Setor criado" });
    if (r) { setDomain(key); sectors.reload(); setStep(1); }
  };
  const createSource = async () => {
    const key = slug(`${domain}_${src.name}`).slice(0, 60);
    const config = src.connector === "file" ? { path: src.path, format: src.format }
      : { base_url: src.base_url, endpoint: src.endpoint, pagination: { type: "none", data_path: src.data_path || undefined },
          ...(src.token_env ? { auth: { type: "bearer", token_env: src.token_env } } : {}) };
    const r = await action.run(`/sectors/${domain}/sources`, { key, name: src.name, connector: src.connector, config }, undefined, { success: "Fonte registrada" });
    if (r) { allSources.reload(); setSourceKey(key); }
  };
  const discover = async (useAi = false) => {
    const sectorName = (sectors.data || []).find((s: any) => s.key === domain)?.name || domain;
    const r: any = await action.run("/sectors/discover", { source_key: sourceKey, use_ai: useAi, sector: sectorName },
      undefined, useAi ? { success: "Sugestão refinada" } : undefined);
    if (!r) return;
    setDiscovery(r);
    setFields(r.fields.map((f: any) => ({ ...f, from: f.path })));
    setKeyField(r.suggested_key || ""); setTimeField(r.suggested_time_field || "");
    if (!ds.name) setDs({ ...ds, key: slug(sourceKey.replace(`${domain}_`, "")).slice(0, 40) || "conjunto", name: sourceKey });
  };
  const upd = (i: number, patch: any) => setFields(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const addDerived = () => {
    if (!derived.name || !derived.a || !derived.b) return;
    setFields([...fields, { name: slug(derived.name), label: derived.label || derived.name, type: "float", role: "measure", include: true,
      derive: "days_between", args: [derived.a, derived.b], examples: [], fill_pct: null, path: `dias(${derived.a} → ${derived.b})` }]);
    setDerived({ name: "", label: "", a: "", b: "" });
  };
  const saveAndBuild = async () => {
    const definition = {
      source_keys: [sourceKey], key_field: keyField, time_field: timeField || null, relationships: rels,
      fields: included.map((f) => f.derive
        ? { name: f.name, label: f.label, type: "float", role: f.role, derive: f.derive, args: f.args }
        : { name: f.name, label: f.label, type: f.type, role: f.role, from: f.from || f.path, pii: !!f.pii }),
    };
    const saved = await action.run(`/sectors/${domain}/datasets`, { ...ds, definition }, undefined, { success: "Conjunto salvo" });
    if (!saved) return;
    setStep(3);
    const run: any = await action.run("/data/pipeline/run", { sync: true }, undefined, { success: "Dados processados" });
    const prev = await api.get<any>(`/sectors/datasets/${ds.key}/preview`).catch(() => null);
    setBuilt({ run, preview: prev?.data });
    const sug = await api.get<any[]>(`/sectors/datasets/${ds.key}/suggest-metrics`).catch(() => null);
    const base: any[] = sug?.data || [];
    // métricas propostas pela IA (se houve refino): mesmas dimensões/fonte das heurísticas, sempre revisáveis
    const tmpl = base[0];
    const aiList = tmpl ? (discovery?.ai_metrics || []).map((m: any) => ({
      ...tmpl, metric_key: `${domain}_${ds.key}_${m.key_suffix}`.toUpperCase().replace(/[^A-Z0-9_]/g, "_").slice(0, 60),
      name: m.name, description: m.description, unit: m.unit, formula_text: `${m.formula.type}(${m.formula.field || m.formula.numerator?.field || "registros"})`,
      formula_definition: { ...m.formula, ...(tmpl.formula_definition.time_field ? { time_field: tmpl.formula_definition.time_field } : {}) },
      exists: false, ai: true })) : [];
    const list = [...base, ...aiList.filter((a: any) => !base.some((b) => b.metric_key === a.metric_key))];
    setSuggestions(list); setChosen(list.filter((m: any) => !m.exists).map((m: any) => m.metric_key));
  };
  const createMetrics = async () => {
    const metrics = suggestions.filter((m) => chosen.includes(m.metric_key) && !m.exists).map(({ exists, ...m }) => m);
    const r = await action.run(`/sectors/${domain}/metrics`, { metrics, create_dashboard: true }, undefined, { success: "Métricas e painel criados" });
    if (r) setResult(r);
  };

  return (
    <>
      <PageHeader kicker="Setores" title={editKey ? "Editar conjunto de dados" : "Novo setor / conjunto de dados"}
        subtitle="Conecte uma fonte, escolha os campos e o GoOps cria o conjunto governado, métricas sugeridas e um painel. Depois, crie agentes no setor." />
      <Steps step={step} />
      <ErrorBox error={action.error} />

      {step === 0 && (
        <Card title="1. Em qual setor?">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="label mb-1">Setor existente</div>
              {sectors.loading && <Loading />}
              <div className="flex flex-wrap gap-2">{(sectors.data || []).map((s) => (
                <button key={s.key} className={domain === s.key ? "btn-primary" : "btn-ghost"} onClick={() => { setDomain(s.key); setStep(1); }}>{s.name}</button>))}</div>
            </div>
            <div className="rounded-md border border-dashed border-ink-600 p-3">
              <div className="label mb-1">Ou crie um novo setor</div>
              <input className="input mb-2 w-full" placeholder="Nome (ex.: Atendimento)" value={newSector.name} onChange={(e) => setNewSector({ ...newSector, name: e.target.value })} />
              <input className="input mb-2 w-full" placeholder="Descrição (opcional)" value={newSector.description} onChange={(e) => setNewSector({ ...newSector, description: e.target.value })} />
              <div className="mb-2 text-xs text-slate-500">Chave: <code>{slug(newSector.name).slice(0, 30) || "—"}</code></div>
              <button className="btn-primary" disabled={!newSector.name.trim() || action.busy} onClick={createSector}><Plus size={14} /> Criar setor</button>
            </div>
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card title={`2. De onde vêm os dados? (setor: ${detail.data?.domain?.name || domain})`}
          subtitle="Credenciais nunca são digitadas aqui: informe só o NOME da variável de ambiente que guarda o token.">
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="label mb-1">Fontes do setor</div>
              {sectorSources.length === 0 && <p className="text-sm text-slate-500">Nenhuma fonte ainda — registre ao lado.</p>}
              <div className="space-y-1.5">{sectorSources.map((s: any) => (
                <label key={s.key} className="flex items-center gap-2 rounded-md border border-ink-700 px-3 py-2 text-sm">
                  <input type="radio" name="src" checked={sourceKey === s.key} onChange={() => setSourceKey(s.key)} />
                  <span className="min-w-0 flex-1 truncate text-white">{s.name}</span><code className="text-xs text-slate-500">{s.connector}</code></label>))}</div>
            </div>
            <div className="rounded-md border border-dashed border-ink-600 p-3">
              <div className="label mb-1">Registrar nova fonte</div>
              <input className="input mb-2 w-full" placeholder="Nome da fonte (ex.: API de tickets)" value={src.name} onChange={(e) => setSrc({ ...src, name: e.target.value })} />
              <div className="mb-2 flex gap-3 text-sm">
                <label className="inline-flex items-center gap-1.5"><input type="radio" checked={src.connector === "file"} onChange={() => setSrc({ ...src, connector: "file" })} /> Planilha (XLSX/CSV)</label>
                <label className="inline-flex items-center gap-1.5"><input type="radio" checked={src.connector === "http_json"} onChange={() => setSrc({ ...src, connector: "http_json" })} /> API REST (JSON)</label>
              </div>
              {src.connector === "file" ? (
                <div className="grid gap-2 sm:grid-cols-3">
                  <input className="input sm:col-span-2" placeholder="Caminho dentro de data/ (ex.: seed/minha_base.xlsx)" value={src.path} onChange={(e) => setSrc({ ...src, path: e.target.value })} />
                  <select className="input" value={src.format} onChange={(e) => setSrc({ ...src, format: e.target.value })}><option value="xlsx">xlsx</option><option value="csv">csv</option></select>
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  <input className="input" placeholder="Base URL (https://…)" value={src.base_url} onChange={(e) => setSrc({ ...src, base_url: e.target.value })} />
                  <input className="input" placeholder="Endpoint (ex.: /v1/tickets)" value={src.endpoint} onChange={(e) => setSrc({ ...src, endpoint: e.target.value })} />
                  <input className="input" placeholder="Caminho da lista no JSON (ex.: data)" value={src.data_path} onChange={(e) => setSrc({ ...src, data_path: e.target.value })} />
                  <input className="input" placeholder="Variável de ambiente do token (opcional)" value={src.token_env} onChange={(e) => setSrc({ ...src, token_env: e.target.value })} />
                </div>
              )}
              <button className="btn-ghost mt-2" disabled={!src.name.trim() || action.busy} onClick={createSource}><Plus size={14} /> Registrar fonte</button>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button className="btn-ghost" onClick={() => setStep(0)}>Voltar</button>
            <button className="btn-primary" disabled={!sourceKey} onClick={() => setStep(2)}>Continuar</button>
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card title="3. Quais dados e variáveis?" subtitle="O GoOps lê uma amostra, sugere tipo e papel de cada campo e marca possíveis dados pessoais (excluídos por padrão)."
          actions={<span className="inline-flex flex-wrap gap-2">
            <button className="btn-primary" disabled={action.busy} onClick={() => discover(false)}>{action.busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} Analisar fonte</button>
            {discovery && <button className="btn-accent" disabled={action.busy} onClick={() => discover(true)}><Sparkles size={14} /> Refinar com IA</button>}</span>}>
          {discovery && <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">{fmt.num(discovery.records_sampled)} registros analisados (origem: {discovery.origin}).
            <Badge tone={discovery.generated_by === "deterministic" ? "gray" : "violet"}>{discovery.generated_by === "deterministic" ? "sugestão por regras" : `sugestão por IA · ${String(discovery.generated_by).replace("llm:", "")}`}</Badge>
            {discovery.fallback_reason && <span className="text-amber-300">{discovery.fallback_reason}</span>}</p>}
          {fields.length > 0 && (
            <>
              <DataTable rows={fields.map((f, i) => ({ ...f, _i: i }))} maxHeight={460} columns={[
                { key: "include", label: "Usar", render: (f: any) => <input type="checkbox" aria-label={`Usar ${f.path}`} checked={f.include} disabled={f.pii} onChange={(e) => upd(f._i, { include: e.target.checked })} /> },
                { key: "path", label: "Campo na fonte", render: (f: any) => <span><code className="text-xs">{f.path}</code>
                  {f.pii && <button type="button" className="ml-1 align-middle" title="Marcado como dado pessoal (não será ingerido). Clique se não for."
                    onClick={() => upd(f._i, { pii: false })}><Badge tone="red">dado pessoal · desmarcar</Badge></button>}</span> },
                { key: "name", label: "Nome", render: (f: any) => <input className="input h-8 w-36" value={f.name} onChange={(e) => upd(f._i, { name: slug(e.target.value) })} /> },
                { key: "label", label: "Rótulo", render: (f: any) => <input className="input h-8 w-40" value={f.label} onChange={(e) => upd(f._i, { label: e.target.value })} /> },
                { key: "type", label: "Tipo", render: (f: any) => f.derive ? "Decimal" : <select className="input h-8" value={f.type} onChange={(e) => upd(f._i, { type: e.target.value })}>{TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select> },
                { key: "role", label: "Papel", render: (f: any) => <select className="input h-8" value={f.role} onChange={(e) => upd(f._i, { role: e.target.value })}>{ROLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select> },
                { key: "fill_pct", label: "Preench.", render: (f: any) => f.fill_pct === null ? "—" : fmt.pct(f.fill_pct, 0) },
                { key: "examples", label: "Exemplos", render: (f: any) => <span className="text-xs text-slate-400">{(f.examples || []).join(" · ")}</span> },
                { key: "_x", label: "", render: (f: any) => f.derive && <button className="btn-danger h-8 px-2" aria-label="Remover campo calculado" onClick={() => setFields(fields.filter((_, j) => j !== f._i))}><Trash2 size={13} /></button> },
              ]} />
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label><span className="label">Campo-chave (único por registro)</span>
                  <select className="input mt-1 w-full" value={keyField} onChange={(e) => setKeyField(e.target.value)}>
                    <option value="">Escolha…</option>{included.filter((f) => !f.derive).map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}</select></label>
                <label><span className="label">Data principal (gera a dimensão mês)</span>
                  <select className="input mt-1 w-full" value={timeField} onChange={(e) => setTimeField(e.target.value)}>
                    <option value="">Sem data</option>{dateFields.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}</select></label>
              </div>
              {dateFields.length >= 2 && (
                <div className="mt-4 rounded-md border border-dashed border-ink-600 p-3">
                  <div className="label mb-2">Campo calculado: dias entre duas datas</div>
                  <div className="grid gap-2 md:grid-cols-5">
                    <input className="input" placeholder="nome (ex.: dias_resposta)" value={derived.name} onChange={(e) => setDerived({ ...derived, name: e.target.value })} />
                    <input className="input" placeholder="rótulo" value={derived.label} onChange={(e) => setDerived({ ...derived, label: e.target.value })} />
                    <select className="input" value={derived.a} onChange={(e) => setDerived({ ...derived, a: e.target.value })}><option value="">de…</option>{dateFields.map((f) => <option key={f.name}>{f.name}</option>)}</select>
                    <select className="input" value={derived.b} onChange={(e) => setDerived({ ...derived, b: e.target.value })}><option value="">até…</option>{dateFields.map((f) => <option key={f.name}>{f.name}</option>)}</select>
                    <button className="btn-ghost" onClick={addDerived}><Plus size={14} /> Adicionar</button>
                  </div>
                </div>
              )}
              <div className="mt-4 rounded-md border border-dashed border-ink-600 p-3">
                <div className="label mb-2 inline-flex items-center gap-1"><Link2 size={13} aria-hidden /> Relacionar com outro conjunto (traz colunas para usar como dimensão)</div>
                {rels.map((r, i) => (
                  <div key={i} className="mb-1 flex flex-wrap items-center gap-2 text-sm">
                    <code>{r.field}</code> → <code>{r.dataset}.{r.on}</code> · traz {r.bring.join(", ")}
                    <button className="btn-danger h-7 px-2" aria-label="Remover relacionamento" onClick={() => setRels(rels.filter((_, j) => j !== i))}><Trash2 size={12} /></button>
                  </div>))}
                {(() => {
                  const t = (joinable.data || []).find((x: any) => x.key === relDraft.dataset);
                  return (
                    <div className="grid gap-2 md:grid-cols-4">
                      <select className="input" aria-label="Campo deste conjunto" value={relDraft.field} onChange={(e) => setRelDraft({ ...relDraft, field: e.target.value })}>
                        <option value="">Campo deste conjunto…</option>{included.filter((f) => !f.derive).map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}</select>
                      <select className="input" aria-label="Conjunto relacionado" value={relDraft.dataset}
                        onChange={(e) => { const x = (joinable.data || []).find((d: any) => d.key === e.target.value); setRelDraft({ ...relDraft, dataset: e.target.value, on: x?.suggested_on || "", bring: [] }); }}>
                        <option value="">Conjunto (Gold)…</option>{(joinable.data || []).map((d: any) => <option key={d.key} value={d.key}>{d.name} ({d.key})</option>)}</select>
                      <select className="input" aria-label="Coluna de ligação" value={relDraft.on} disabled={!t} onChange={(e) => setRelDraft({ ...relDraft, on: e.target.value })}>
                        <option value="">Coluna de ligação…</option>{(t?.columns || []).map((c: string) => <option key={c} value={c}>{c}</option>)}</select>
                      <button className="btn-ghost" disabled={!relDraft.field || !relDraft.dataset || !relDraft.on || relDraft.bring.length === 0}
                        onClick={() => { setRels([...rels, relDraft]); setRelDraft({ field: "", dataset: "", on: "", bring: [] }); }}><Plus size={14} /> Adicionar</button>
                      {t && <div className="flex flex-wrap gap-1.5 md:col-span-4">{t.bringable.filter((c: string) => c !== relDraft.on).slice(0, 40).map((c: string) => (
                        <label key={c} className="inline-flex items-center gap-1 rounded border border-ink-700 px-2 py-0.5 text-xs">
                          <input type="checkbox" checked={relDraft.bring.includes(c)} onChange={(e) => setRelDraft({ ...relDraft, bring: e.target.checked ? [...relDraft.bring, c] : relDraft.bring.filter((x: string) => x !== c) })} />{c}</label>))}
                        <span className="w-full text-[11px] text-slate-500">Identificadores de cliente e campos pessoais não podem ser trazidos.</span></div>}
                    </div>
                  );
                })()}
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <label><span className="label">Chave do conjunto</span><input className="input mt-1 w-full" value={ds.key} disabled={!!editKey} onChange={(e) => setDs({ ...ds, key: slug(e.target.value).slice(0, 40) })} /></label>
                <label><span className="label">Nome</span><input className="input mt-1 w-full" value={ds.name} onChange={(e) => setDs({ ...ds, name: e.target.value })} /></label>
                <label><span className="label">Descrição</span><input className="input mt-1 w-full" value={ds.description} onChange={(e) => setDs({ ...ds, description: e.target.value })} /></label>
              </div>
            </>
          )}
          <div className="mt-4 flex gap-2">
            <button className="btn-ghost" onClick={() => setStep(1)}>Voltar</button>
            <button className="btn-primary" disabled={!keyField || !ds.key || !ds.name || included.length === 0 || action.busy} onClick={saveAndBuild}>Salvar e processar</button>
          </div>
        </Card>
      )}

      {step >= 3 && (
        <Card title="4. Processamento" subtitle="Fonte → Bronze → Silver (tipado, deduplicado, quarentena) → Gold do setor.">
          {!built ? <p className="inline-flex items-center gap-2 text-sm text-slate-300"><Loader2 size={14} className="animate-spin" /> Executando o pipeline…</p> : (
            <div className="space-y-2 text-sm">
              <div>Pipeline: <Badge tone={built.run?.status === "success" ? "green" : "red"}>{built.run?.status || "falhou"}</Badge> {built.run?.error}</div>
              {built.preview?.built && <div>{fmt.num(built.preview.total)} registros na Gold do setor. Prévia:</div>}
              {built.preview?.built && <DataTable rows={built.preview.rows.slice(0, 8)} maxHeight={260}
                columns={built.preview.columns.slice(0, 8).map((c: string) => ({ key: c, label: c, render: (r: any) => String(r[c] ?? "—").slice(0, 40) }))} />}
              {step === 3 && <button className="btn-primary" disabled={!built.preview?.built} onClick={() => setStep(4)}>Continuar para métricas</button>}
            </div>
          )}
        </Card>
      )}

      {step === 4 && (
        <Card title="5. Métricas sugeridas e painel" subtitle="Escolha as métricas; elas entram como 'aguardando aprovação' (governança) e já aparecem no painel como rascunho.">
          {!result ? (
            <>
              <div className="space-y-1.5">{suggestions.map((m) => (
                <label key={m.metric_key} className="flex items-start gap-2 rounded-md border border-ink-700 px-3 py-2 text-sm">
                  <input type="checkbox" className="mt-1" disabled={m.exists} checked={m.exists || chosen.includes(m.metric_key)}
                    onChange={(e) => setChosen(e.target.checked ? [...chosen, m.metric_key] : chosen.filter((k) => k !== m.metric_key))} />
                  <span className="min-w-0 flex-1"><span className="text-white">{m.name}</span>{m.exists && <Badge className="ml-2">já existe</Badge>}{m.ai && <Badge tone="violet" className="ml-2">sugerida por IA</Badge>}
                    <span className="block text-xs text-slate-500">{m.formula_text} · <code>{m.metric_key}</code> · {m.unit}</span></span></label>))}</div>
              <button className="btn-primary mt-4" disabled={action.busy || chosen.length === 0} onClick={createMetrics}>Criar métricas e painel</button>
            </>
          ) : (
            <div className="space-y-2 text-sm">
              <p>{result.created.length} métrica(s) criada(s){result.dashboard ? " e painel montado" : ""}.</p>
              {result.errors.length > 0 && <ul className="list-disc pl-5 text-rose-300">{result.errors.map((e: any) => <li key={e.metric_key}>{e.metric_key}: {e.error}</li>)}</ul>}
              <div className="flex flex-wrap gap-2">
                <Link className="btn-primary" href={`/setores/${domain}`}>Abrir o setor</Link>
                <Link className="btn-ghost" href="/semantic/approvals">Enviar para aprovação</Link>
              </div>
            </div>
          )}
        </Card>
      )}
    </>
  );
}

export default function NewSectorPage() {
  return <Suspense fallback={<Loading />}><Wizard /></Suspense>;
}
