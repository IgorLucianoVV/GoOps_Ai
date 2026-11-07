"use client";
import { useEffect, useState } from "react";
import { KeyRound, PlugZap, Plus, RefreshCw, Trash2 } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, ErrorBox } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { Field, Saved, SavedInfo, num } from "./common";
import ModelPicker, { ModelOption } from "./ModelPicker";

const LEVELS = [
  { key: "1", title: "Nível 1 — Modelo pequeno", text: "Classificação, roteamento e extração simples (ex.: classificação de comentários sem tema)." },
  { key: "2", title: "Nível 2 — LLM econômico", text: "Resumos de incidentes e explicações de métricas." },
  { key: "3", title: "Nível 3 — LLM avançado", text: "Narrativas de investigação e planos de resolução." },
];


export default function ModelsPanel({ config, onSaved, canWrite }: { config: any; onSaved: () => void; canWrite: boolean }) {
  const llm = config.sections.llm;
  const cost = config.sections.cost;
  const action = useAction();
  const [levels, setLevels] = useState<any>(llm.value.levels);
  const [baseUrl, setBaseUrl] = useState<string>(llm.value.openai_base_url || "");
  const [ollamaUrl, setOllamaUrl] = useState<string>(llm.value.ollama_base_url || "");
  const [chatModels, setChatModels] = useState<{ provider: string; model: string; label: string }[]>(llm.value.chat_models || []);
  const [pricing, setPricing] = useState<{ model: string; input: string; output: string }[]>([]);
  const [limits, setLimits] = useState({ run: String(cost.value.limit_per_run_usd), day: String(cost.value.limit_daily_usd) });
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [test, setTest] = useState<Record<string, any>>({});
  const [discovered, setDiscovered] = useState<Record<string, ModelOption[]>>({});
  const [discoverInfo, setDiscoverInfo] = useState<Record<string, string>>({});
  const providerStatus = (p: string) => (config.providers_status || []).find((x: any) => x.provider === p);
  const modelsFor = (p: string): ModelOption[] => discovered[p] || providerStatus(p)?.models || [];
  const providerLabel = (p: string) => providerStatus(p)?.label || p;
  const discover = async (p: string) => {
    const r: any = await action.run("/settings/models/discover", { provider: p }, undefined, { silentError: true });
    if (!r) return;
    if (r.source === "provider" && r.models.length) setDiscovered({ ...discovered, [p]: r.models });
    setDiscoverInfo({ ...discoverInfo, [p]: r.error ? `${r.error} Mostrando catálogo de referência.` : `${r.models.length} modelos encontrados no provedor.` });
  };
  const changeProvider = (provider: string) => ({ provider, model: modelsFor(provider)[0]?.id || "" });

  useEffect(() => {
    setLevels(llm.value.levels);
    setBaseUrl(llm.value.openai_base_url || "");
    setOllamaUrl(llm.value.ollama_base_url || "");
    setChatModels(llm.value.chat_models || []);
    setPricing(Object.entries(llm.value.pricing || {}).map(([model, p]: any) => ({ model, input: String(p.input_per_mtok), output: String(p.output_per_mtok) })));
    setLimits({ run: String(cost.value.limit_per_run_usd), day: String(cost.value.limit_daily_usd) });
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  const flash = (k: string) => { setSaved(k); setTimeout(() => setSaved(null), 2500); };
  const setLevel = (lvl: string, field: string, value: string) => setLevels({ ...levels, [lvl]: { ...levels[lvl], [field]: value } });

  const saveModels = async () => {
    const price: any = {};
    pricing.filter((p) => p.model.trim()).forEach((p) => { price[p.model.trim()] = { input_per_mtok: num(p.input) ?? 0, output_per_mtok: num(p.output) ?? 0 }; });
    const chat = chatModels.filter((m) => m.provider && m.model.trim()).map((m) => ({ ...m, model: m.model.trim() }));
    if (await action.run("/settings/config/llm", { value: { levels, openai_base_url: baseUrl, ollama_base_url: ollamaUrl, pricing: price, chat_models: chat } })) { flash("models"); onSaved(); }
  };
  const saveLimits = async () => {
    if (await action.run("/settings/config/cost", { value: { limit_per_run_usd: num(limits.run), limit_daily_usd: num(limits.day) } })) { flash("cost"); onSaved(); }
  };
  const saveKey = async (name: string, value: string | null) => {
    if (await action.run(`/settings/secrets/${name}`, { value })) { setKeys({ ...keys, [name]: "" }); flash(name); onSaved(); }
  };
  const useClaude = () => {
    // IDs de modelo da família Claude atual; preços NÃO são preenchidos (consulte a tabela oficial da Anthropic)
    setLevels({
      "1": { provider: "anthropic", model: "claude-haiku-5-5", alias: "JEF" },
      "2": { provider: "anthropic", model: "claude-haiku-5-5", alias: "" },
      "3": { provider: "anthropic", model: "claude-sonnet-5-5", alias: "" },
    });
  };
  const useGogroup = () => {
    // AI Proxy do Gogroup (evento): formato OpenAI; DeepSeek bloqueado. Custo: o proxy informa só tokens no chat.
    setLevels({
      "1": { provider: "gogroup", model: "gpt-6-luna", alias: "JEF" },
      "2": { provider: "gogroup", model: "gpt-6-luna", alias: "" },
      "3": { provider: "gogroup", model: "latest", alias: "" },
    });
  };
  const runTest = async (lvl: string) => {
    const r = await action.run("/settings/models/test", { level: Number(lvl) });
    setTest({ ...test, [lvl]: r || { ok: false, error: action.error?.message } });
  };

  return (
    <div className="space-y-5">
      {config.warnings.map((w: string) => <div key={w} role="alert" className="rounded-md border border-amber-600/40 bg-amber-950/20 p-3 text-sm text-amber-200">{w}</div>)}
      <ErrorBox error={action.error} />
      <Card title="Chaves de API" subtitle="Armazenadas cifradas no banco. Nunca são exibidas novamente — apenas o sufixo. Deixe em branco para manter a atual.">
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(config.secrets).map(([name, s]: any) => (
            <div key={name} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-white"><KeyRound size={14} /> {s.label}</div>
                {s.configured ? <Badge tone="green">configurada · {s.hint} · {s.source === "ui" ? "interface" : "ambiente"}</Badge> : <Badge>não configurada</Badge>}
              </div>
              {!s.readable && <div className="mt-1 text-xs text-rose-300">Chave salva não pôde ser lida (SECRET_KEY mudou). Cadastre novamente.</div>}
              {s.updated_at && <div className="mt-1 text-[11px] text-slate-500">Atualizada {fmt.date(s.updated_at)} por {s.updated_by}</div>}
              {canWrite && (
                <div className="mt-2 flex gap-2">
                  <input type="password" autoComplete="off" className="input flex-1" placeholder="Nova chave" aria-label={`Nova ${s.label}`}
                    value={keys[name] || ""} onChange={(e) => setKeys({ ...keys, [name]: e.target.value })} />
                  <button className="btn-primary" disabled={action.busy || !keys[name]} onClick={() => saveKey(name, keys[name])}>Salvar</button>
                  {s.source === "ui" && <button className="btn-danger" aria-label="Remover chave" disabled={action.busy} onClick={() => saveKey(name, null)}><Trash2 size={13} /></button>}
                </div>
              )}
              <Saved show={saved === name} />
            </div>
          ))}
        </div>
        <div className="mt-4 grid max-w-3xl gap-3 md:grid-cols-2">
          <Field label="URL do Ollama (modelos locais, sem custo)" hint="Padrão http://localhost:11434 — rode `ollama serve` e `ollama pull llama3.1`.">
            <input className="input w-full" value={ollamaUrl} disabled={!canWrite} onChange={(e) => setOllamaUrl(e.target.value)} placeholder="http://localhost:11434" />
          </Field>
          <Field label="Base URL OpenAI-compatível" hint="Ex.: endpoint de um gateway/provedor compatível com /chat/completions. Necessário para o provedor openai_compatible.">
            <input className="input w-full" value={baseUrl} disabled={!canWrite} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://..." />
          </Field>
        </div>
      </Card>

      <Card title="Modelos por nível (roteamento inteligente de custo)" subtitle="Nível 0 é sempre determinístico. Sem modelo configurado, o nível usa resposta determinística de contingência (identificado na interface)."
        actions={<div className="flex items-center gap-2">{canWrite && <button className="btn-accent" onClick={useGogroup}>Usar AI Proxy Gogroup</button>}{canWrite && <button className="btn-ghost" onClick={useClaude}>Usar Claude (Anthropic)</button>}<SavedInfo section={llm} /></div>}>
        {canWrite && <p className="mb-3 text-xs text-slate-500">Atalho para a demo: preenche Haiku nos níveis 1–2 e Sonnet no nível 3 (narrativas, investigação e “Pergunte ao GoOps”).
          Depois cole a chave Anthropic acima, clique em <strong>Salvar modelos</strong> e em <strong>Testar conexão</strong>. Para ver o custo, informe os preços por milhão de tokens conforme a tabela oficial da Anthropic.</p>}
        <div className="grid gap-4 lg:grid-cols-3">
          {LEVELS.map((l) => {
            const v = levels[l.key] || { provider: "none", model: "", alias: "" };
            const t = test[l.key];
            return (
              <div key={l.key} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
                <div className="text-sm font-medium text-white">{l.title}</div>
                <div className="mb-3 text-xs text-slate-500">{l.text}</div>
                <div className="space-y-2">
                  <Field label="Provedor">
                    <select className="input w-full" disabled={!canWrite} value={v.provider} onChange={(e) => setLevels({ ...levels, [l.key]: { ...v, ...(e.target.value === "none" ? { provider: "none", model: "" } : changeProvider(e.target.value)) } })}>
                      {config.providers.map((p: string) => <option key={p} value={p}>{p === "none" ? "Nenhum (determinístico)" : providerLabel(p)}</option>)}
                    </select>
                  </Field>
                  {v.provider !== "none" && <Field label="Modelo" hint="Lista do provedor escolhido; use “Outro…” para um id que não aparece.">
                    <ModelPicker value={v.model || ""} options={modelsFor(v.provider)} disabled={!canWrite} onChange={(id) => setLevel(l.key, "model", id)} />
                  </Field>}
                  <Field label="Apelido interno"><input className="input w-full" disabled={!canWrite} value={v.alias || ""} onChange={(e) => setLevel(l.key, "alias", e.target.value)} placeholder={l.key === "1" ? "JEF" : ""} /></Field>
                  {canWrite && <button className="btn-ghost" disabled={action.busy || v.provider === "none"} onClick={() => runTest(l.key)}><PlugZap size={13} /> Testar conexão</button>}
                  {t && <div className={t.ok ? "text-xs text-emerald-300" : "text-xs text-rose-300"}>{t.ok ? `OK · ${t.model} · ${t.latency_ms} ms` : `Falhou: ${t.error}`}</div>}
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-5">
          <div className="label mb-2">Preços por modelo (USD por milhão de tokens) — usados para calcular custo</div>
          <div className="space-y-2">
            {pricing.map((p, i) => (
              <div key={i} className="flex flex-wrap gap-2">
                <input className="input flex-1" aria-label="Modelo" placeholder="modelo" disabled={!canWrite} value={p.model} onChange={(e) => setPricing(pricing.map((x, j) => (j === i ? { ...x, model: e.target.value } : x)))} />
                <input className="input w-36" aria-label="Entrada" type="number" step="0.01" min="0" placeholder="entrada" disabled={!canWrite} value={p.input} onChange={(e) => setPricing(pricing.map((x, j) => (j === i ? { ...x, input: e.target.value } : x)))} />
                <input className="input w-36" aria-label="Saída" type="number" step="0.01" min="0" placeholder="saída" disabled={!canWrite} value={p.output} onChange={(e) => setPricing(pricing.map((x, j) => (j === i ? { ...x, output: e.target.value } : x)))} />
                {canWrite && <button className="btn-danger" aria-label="Remover preço" onClick={() => setPricing(pricing.filter((_, j) => j !== i))}><Trash2 size={13} /></button>}
              </div>
            ))}
            {canWrite && <button className="btn-ghost" onClick={() => setPricing([...pricing, { model: "", input: "0", output: "0" }])}><Plus size={13} /> Adicionar preço</button>}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">Modelos sem preço têm custo registrado como desconhecido.</div>
        </div>
        {canWrite && <div className="mt-4 flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={saveModels}>Salvar modelos</button><Saved show={saved === "models"} /></div>}
      </Card>

      <Card title="Provedores e modelos do “Pergunte ao GoOps”"
        subtitle={`Quem usa o chat escolhe entre estes modelos. Orquestração: ${config.langgraph ? "LangGraph (ativo)" : "loop nativo — instale as dependências para habilitar o LangGraph e todos os provedores"}.`}>
        <div className="mb-4 overflow-auto">
          <table className="table w-full">
            <thead><tr><th scope="col">Provedor</th><th scope="col">Pacote</th><th scope="col">Credencial</th><th scope="col">Modelos</th></tr></thead>
            <tbody>{(config.providers_status || []).map((p: any) => (
              <tr key={p.provider}><td>{p.label}</td>
                <td>{p.installed ? <Badge tone="green">instalado</Badge> : <Badge tone="amber">{p.package} ausente</Badge>}</td>
                <td>{p.credential ? <Badge tone="green">ok</Badge> : <Badge>{p.needs_key ? "falta chave" : "falta URL"}</Badge>}</td>
                <td><div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-500">{discovered[p.provider] ? `${discovered[p.provider].length} do provedor` : `${(p.models || []).length} no catálogo`}</span>
                  {canWrite && p.credential && <button className="btn-ghost h-7 text-xs" disabled={action.busy} onClick={() => discover(p.provider)}><RefreshCw size={12} aria-hidden /> Atualizar do provedor</button>}
                  {discoverInfo[p.provider] && <span className="text-[11px] text-slate-500">{discoverInfo[p.provider]}</span>}
                </div></td></tr>))}</tbody>
          </table>
        </div>
        <div className="space-y-2">
          {chatModels.map((m, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              <select aria-label="Provedor" className="input w-56" disabled={!canWrite} value={m.provider} onChange={(e) => {
                const next = changeProvider(e.target.value);
                const opt = modelsFor(e.target.value)[0];
                setChatModels(chatModels.map((x, j) => (j === i ? { ...x, ...next, label: opt ? opt.label : "" } : x)));
              }}>
                {config.providers.filter((p: string) => p !== "none").map((p: string) => <option key={p} value={p}>{providerLabel(p)}</option>)}</select>
              <ModelPicker className="flex-1" value={m.model} options={modelsFor(m.provider)} disabled={!canWrite}
                onChange={(id, label) => setChatModels(chatModels.map((x, j) => (j === i ? { ...x, model: id, label: label || x.label } : x)))} />
              <input aria-label="Rótulo" className="input w-48" placeholder="rótulo no chat" disabled={!canWrite} value={m.label} onChange={(e) => setChatModels(chatModels.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
              {canWrite && <button className="btn-danger" aria-label="Remover modelo" onClick={() => setChatModels(chatModels.filter((_, j) => j !== i))}><Trash2 size={13} /></button>}
            </div>
          ))}
          {canWrite && <div className="flex flex-wrap items-center gap-2 pt-1">
            <button className="btn-ghost h-8 text-xs" onClick={() => {
              const prov = (config.providers_status || []).find((x: any) => x.credential && x.installed)?.provider || "anthropic";
              const opt = modelsFor(prov)[0];
              setChatModels([...chatModels, { provider: prov, model: opt?.id || "", label: opt?.label || "" }]);
            }}><Plus size={12} /> Adicionar modelo</button>
          </div>}
          <p className="text-[11px] text-slate-500">A lista vem de um catálogo de referência e pode ficar desatualizada — use “Atualizar do provedor” para ver os modelos que a sua chave enxerga, ou “Outro…” para digitar um id.</p>
        </div>
        {canWrite && <div className="mt-4 flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={saveModels}>Salvar modelos</button><Saved show={saved === "models"} /></div>}
      </Card>

      <Card title="Limites de custo" actions={<SavedInfo section={cost} />} subtitle="Ao atingir o limite, o roteador usa a resposta determinística de contingência e registra o motivo.">
        <div className="grid max-w-xl gap-3 md:grid-cols-2">
          <Field label="Por execução de agente (USD)"><input className="input w-full" type="number" step="0.01" min="0" disabled={!canWrite} value={limits.run} onChange={(e) => setLimits({ ...limits, run: e.target.value })} /></Field>
          <Field label="Diário (USD)"><input className="input w-full" type="number" step="0.01" min="0" disabled={!canWrite} value={limits.day} onChange={(e) => setLimits({ ...limits, day: e.target.value })} /></Field>
        </div>
        {canWrite && <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={action.busy} onClick={saveLimits}>Salvar limites</button><Saved show={saved === "cost"} /></div>}
      </Card>
    </div>
  );
}
