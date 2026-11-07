"use client";
import { DIM_LABEL } from "@/components/labels";
import { useApi } from "@/hooks/useApi";

export interface NpsFilters { start?: string; end?: string; state?: string; product_line?: string; carrier?: string; shipping_type?: string; }

export default function Filters({ value, onChange }: { value: NpsFilters; onChange: (v: NpsFilters) => void }) {
  const { data } = useApi<any>("/analytics/nps/filters");
  const opts = data?.options || {};
  const set = (k: keyof NpsFilters, v: string) => onChange({ ...value, [k]: v || undefined });
  return (
    <div role="search" aria-label="Filtros do NPS" className="card mb-5 flex flex-wrap items-end gap-3 p-4">
      <label><div className="label mb-1">De</div><input type="date" className="input" value={value.start || ""} min={data?.date_range?.min?.slice(0, 10)} onChange={(e) => set("start", e.target.value)} /></label>
      <label><div className="label mb-1">Até</div><input type="date" className="input" value={value.end || ""} max={data?.date_range?.max?.slice(0, 10)} onChange={(e) => set("end", e.target.value)} /></label>
      {(["state", "product_line", "carrier", "shipping_type"] as const).map((d) => (
        <label key={d}><div className="label mb-1">{DIM_LABEL[d]}</div>
          <select className="input min-w-36" value={(value[d] as string) || ""} onChange={(e) => set(d, e.target.value)}>
            <option value="">Todos</option>
            {(opts[d] || []).map((o: string) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
      ))}
      <button className="btn-ghost" onClick={() => onChange({})} disabled={!Object.values(value).some(Boolean)}>Limpar filtros</button>
      <div className="flex w-full flex-wrap items-center gap-1.5" aria-live="polite">
        {Object.entries(value).filter(([, v]) => v).length === 0
          ? <span className="text-xs text-slate-500">Sem filtros: exibindo toda a base.</span>
          : Object.entries(value).filter(([, v]) => v).map(([k, v]) => (
            <button key={k} onClick={() => set(k as keyof NpsFilters, "")} className="inline-flex items-center gap-1 rounded-full border border-ink-600 bg-ink-800 px-2.5 py-0.5 text-xs text-slate-200 hover:border-slate-500"
              aria-label={`Remover filtro ${DIM_LABEL[k] || k}: ${v}`}>
              {(DIM_LABEL[k] || (k === "start" ? "De" : "Até"))}: <strong>{v as string}</strong> <span aria-hidden>×</span>
            </button>))}
      </div>
    </div>
  );
}
