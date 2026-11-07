"use client";
import { useMemo, useState } from "react";
import { Eye, Plus } from "lucide-react";
import { fmt } from "@/components/labels";
import { Card, DataTable } from "@/components/ui";
import { useAction } from "@/hooks/useApi";
import { fmtValue } from "./Widget";

const TYPES = [
  { k: "count", label: "Contagem de registros", field: false }, { k: "mean", label: "Média", field: "num" },
  { k: "sum", label: "Soma", field: "num" }, { k: "median", label: "Mediana", field: "num" },
  { k: "percentile", label: "Percentil", field: "num" }, { k: "count_distinct", label: "Contagem distinta", field: "any" },
  { k: "rate", label: "Taxa (%)", field: false },
];
const OPS = [["is_true", "é sim"], ["is_false", "é não"], ["eq", "igual a"], ["ne", "diferente de"], ["le", "≤"], ["lt", "<"],
  ["ge", "≥"], ["gt", ">"], ["not_null", "preenchido"], ["is_null", "vazio"]];
const NO_VALUE = new Set(["is_true", "is_false", "not_null", "is_null"]);
const slugKey = (t: string) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");

function condValue(op: string, v: string) {
  if (NO_VALUE.has(op)) return undefined;
  const n = Number(String(v).replace(",", "."));
  return v !== "" && !Number.isNaN(n) ? n : v;
}

/** Cria métricas do setor sem código: escolhe conjunto, tipo de cálculo, campo e condição — com prévia do resultado. */
export default function MetricBuilder({ domain, datasets, onCreated }: { domain: string; datasets: any[]; onCreated: () => void }) {
  const action = useAction();
  const [dsKey, setDsKey] = useState(datasets[0]?.key || "");
  const ds = datasets.find((d) => d.key === dsKey);
  const fields: any[] = useMemo(() => {
    if (!ds) return [];
    const own = ds.definition.fields;
    const rel = (ds.definition.relationships || []).flatMap((r: any) => r.bring.map((b: string) => ({ name: b, label: b, type: "string", role: "dimension" })));
    return [...own, ...rel];
  }, [ds]);
  const numeric = fields.filter((f) => ["int", "float"].includes(f.type));
  const [f, setF] = useState<any>({ type: "mean", field: "", q: "90", num_field: "", num_op: "is_true", num_value: "", base_field: "", name: "", unit: "", description: "" });
  const [preview, setPreview] = useState<any>(null);
  const t = TYPES.find((x) => x.k === f.type)!;

  const payload = () => {
    const defn: any = { type: f.type };
    if (ds?.definition.time_field) defn.time_field = ds.definition.time_field;
    if (t.field) defn.field = f.field || (t.field === "num" ? numeric[0]?.name : fields[0]?.name);
    if (f.type === "percentile") defn.q = Number(f.q);
    if (f.type === "rate") {
      defn.numerator = { field: f.num_field || fields[0]?.name, op: f.num_op, ...(NO_VALUE.has(f.num_op) ? {} : { value: condValue(f.num_op, f.num_value) }) };
      if (f.base_field) defn.base_filter = { field: f.base_field, op: "not_null" };
    }
    const label = TYPES.find((x) => x.k === f.type)?.label || f.type;
    const fieldLabel = defn.field || defn.numerator?.field || "registros";
    return {
      metric_key: slugKey(`${domain}_${dsKey}_${f.name || `${f.type}_${fieldLabel}`}`).slice(0, 60),
      scope: "domain", domain, name: f.name || `${label} de ${fieldLabel}`,
      description: f.description || `${label} de ${fieldLabel} em ${ds?.name}.`,
      formula_text: f.type === "rate" ? `${defn.numerator.field} ${OPS.find((o) => o[0] === f.num_op)?.[1]} ${f.num_value || ""} / ${f.base_field ? `${f.base_field} preenchido` : "total"} × 100`.replace(/\s+/g, " ")
        : `${label.toLowerCase()}(${fieldLabel})${f.type === "percentile" ? ` p${f.q}` : ""}`,
      formula_definition: defn, unit: f.unit || (f.type === "rate" ? "%" : f.type === "count" ? "registros" : "valor"),
      dimensions: ds?.dimensions || [], source_datasets: [`gold_${dsKey}`], owner: `Responsável do setor ${domain}`, filters: [],
    };
  };
  const doPreview = async () => { const r = await action.run(`/sectors/${domain}/metrics/preview`, { payload: payload() }); if (r) setPreview({ ...(r as any), unit: payload().unit }); };
  const create = async () => {
    const r: any = await action.run(`/sectors/${domain}/metrics`, { metrics: [payload()], create_dashboard: false }, undefined, { success: "Métrica criada (aguardando aprovação)" });
    if (r && r.created.length) { setPreview(null); onCreated(); }
  };

  if (!datasets.length) return null;
  return (
    <Card title="Nova métrica" subtitle="Escolha o cálculo e veja a prévia antes de criar. Métricas novas aguardam aprovação de outra pessoa.">
      <div className="grid gap-3 md:grid-cols-4">
        <label><span className="label">Conjunto de dados</span>
          <select className="input mt-1 w-full" value={dsKey} onChange={(e) => { setDsKey(e.target.value); setPreview(null); }}>
            {datasets.map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}</select></label>
        <label><span className="label">Cálculo</span>
          <select className="input mt-1 w-full" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value, field: "" })}>
            {TYPES.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}</select></label>
        {t.field && <label><span className="label">Campo</span>
          <select className="input mt-1 w-full" value={f.field} onChange={(e) => setF({ ...f, field: e.target.value })}>
            {(t.field === "num" ? numeric : fields).map((x) => <option key={x.name} value={x.name}>{x.label || x.name}</option>)}</select></label>}
        {f.type === "percentile" && <label><span className="label">Percentil (1–99)</span>
          <input className="input mt-1 w-full" type="number" min={1} max={99} value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></label>}
        {f.type === "rate" && <>
          <label><span className="label">Conta quando o campo…</span>
            <select className="input mt-1 w-full" value={f.num_field} onChange={(e) => setF({ ...f, num_field: e.target.value })}>
              {fields.map((x) => <option key={x.name} value={x.name}>{x.label || x.name}</option>)}</select></label>
          <label><span className="label">Condição</span>
            <span className="mt-1 flex gap-1">
              <select className="input" value={f.num_op} onChange={(e) => setF({ ...f, num_op: e.target.value })}>{OPS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              {!NO_VALUE.has(f.num_op) && <input className="input w-24" value={f.num_value} onChange={(e) => setF({ ...f, num_value: e.target.value })} placeholder="valor" />}
            </span></label>
          <label><span className="label">Base (opcional)</span>
            <select className="input mt-1 w-full" value={f.base_field} onChange={(e) => setF({ ...f, base_field: e.target.value })}>
              <option value="">Todos os registros</option>{fields.map((x) => <option key={x.name} value={x.name}>só com {x.label || x.name} preenchido</option>)}</select></label>
        </>}
        <label><span className="label">Nome</span><input className="input mt-1 w-full" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="automático" /></label>
        <label><span className="label">Unidade</span><input className="input mt-1 w-full" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} placeholder="%, dias, R$…" /></label>
        <label className="md:col-span-2"><span className="label">Descrição</span><input className="input mt-1 w-full" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="automática" /></label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn-ghost" disabled={action.busy} onClick={doPreview}><Eye size={14} /> Prévia</button>
        <button className="btn-primary" disabled={action.busy || !preview} onClick={create}><Plus size={14} /> Criar métrica</button>
        <code className="self-center text-xs text-slate-500">{payload().metric_key}</code>
      </div>
      {preview && (
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="rounded-md bg-ink-950 p-3"><div className="label">Resultado</div>
            <div className="text-2xl font-semibold text-white">{fmtValue(preview.result.value, preview.unit)}</div>
            <div className="text-xs text-slate-500">n = {fmt.num(preview.result.n)} · {fmt.num(preview.rows_considered)} registros</div></div>
          {preview.groups && <div className="md:col-span-2"><DataTable rows={preview.groups} maxHeight={200} columns={[
            { key: preview.group_by, label: preview.group_by === "month" ? "mês" : preview.group_by, render: (g: any) => String(g[preview.group_by]) },
            { key: "value", label: "Valor", render: (g: any) => fmtValue(g.value, preview.unit) }, { key: "n", label: "n" }]} /></div>}
        </div>
      )}
    </Card>
  );
}
