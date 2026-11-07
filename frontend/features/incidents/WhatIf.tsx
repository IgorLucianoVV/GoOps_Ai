"use client";
import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";

/** "E se…": projeção determinística do efeito da ação ANTES da aprovação (não altera nada). */
export default function WhatIf({ op }: { op: any }) {
  const feats = useApi<any>("/features");
  const action = useAction();
  const [res, setRes] = useState<any>(null);
  const [share, setShare] = useState<number>(Number(op.params?.share_pct ?? 30));
  if (!feats.data?.whatif) return null;
  const supported = ["carrier_reallocation", "proactive_customer_contact", "sector_customer_contact"].includes(op.action_type);
  if (!supported) return null;
  const run = async (overrides: any = {}) => { const r = await action.run(`/operations/${op.id}/whatif`, { overrides }, undefined, { silentError: true }); if (r) setRes(r); };
  const carrier = op.action_type === "carrier_reallocation";
  return (
    <div className="mt-3 rounded-md border border-violet-500/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-sm font-medium text-white"><FlaskConical size={14} aria-hidden /> Simulação “e se…”</span>
        <Badge tone="violet">estimativa · não altera nada</Badge>
        {!res && <button className="btn-ghost h-8 ml-auto" disabled={action.busy} onClick={() => run(carrier ? { share_pct: share } : {})}>Simular</button>}
      </div>
      {carrier && res && (
        <label className="mt-3 block text-sm"><span className="label">Volume realocado: {share}%</span>
          <input type="range" min={0} max={100} step={5} value={share} className="mt-1 w-full"
            onChange={(e) => setShare(Number(e.target.value))} onMouseUp={() => run({ share_pct: share })} onKeyUp={() => run({ share_pct: share })} onTouchEnd={() => run({ share_pct: share })} />
        </label>
      )}
      {res && !res.available && <p className="mt-2 text-sm text-slate-400">{res.message}</p>}
      {res?.available && carrier && (
        <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
          <div><div className="label">Taxa de atraso no recorte</div><div className="text-white">{fmt.pct(res.late_rate_current)} → <strong>{fmt.pct(res.late_rate_projected)}</strong></div>
            <div className="text-xs text-slate-500">{res.carrier_late_rate}% ({op.params.carrier}) vs {res.target_late_rate}% ({op.params.target_carrier})</div></div>
          <div><div className="label">NPS no recorte</div><div className="text-white">{fmt.num(res.nps_current, 1)} → <strong>{fmt.num(res.nps_projected, 1)}</strong></div>
            <div className="text-xs text-slate-500">NPS no prazo {fmt.num(res.nps_on_time, 1)} · atrasadas {fmt.num(res.nps_late, 1)}</div></div>
          <div><div className="label">Entregas realocadas (histórico)</div><div className="text-white">{fmt.num(res.volume_moved)} de {fmt.num(res.scope_deliveries)}</div></div>
        </div>
      )}
      {res?.available && !carrier && (
        <div className="mt-3 space-y-2 text-sm">
          <div>Pedidos a contatar: <strong className="text-white">{fmt.num(res.orders_to_contact)}</strong> · canal {res.channel}
            {res.by_reason && <span className="text-xs text-slate-500"> · {Object.entries(res.by_reason).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span>}</div>
          {res.message_preview && <blockquote className="rounded bg-ink-950 p-2 text-xs text-slate-300">{res.message_preview}</blockquote>}
        </div>
      )}
      {res?.assumptions && <ul className="mt-2 list-disc pl-5 text-[11px] text-slate-500">{res.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>}
    </div>
  );
}
