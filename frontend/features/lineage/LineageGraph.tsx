"use client";
import clsx from "clsx";
import { useMemo } from "react";
import { useTheme } from "@/hooks/useTheme";

const COLS = ["L0 Fontes", "L1 Bronze", "L2 Silver", "L3 Gold corporativa", "L3 Gold de domínio", "L4 Semântica"];
/** Rótulos antigos (em inglês) vindos de APIs anteriores → coluna correta, para nenhum nó cair na coluna errada. */
const LAYER_ALIAS: Record<string, string> = {
  "L0 Sources": "L0 Fontes", "L3 Corporate Gold": "L3 Gold corporativa", "L3 Domain Gold": "L3 Gold de domínio", "L4 Semantic": "L4 Semântica",
};
const layerOf = (l: string) => LAYER_ALIAS[l] || l;
const COLOR: Record<string, string> = {
  "L0 Fontes": "border-l-slate-500", "L1 Bronze": "border-l-amber-600", "L2 Silver": "border-l-slate-400",
  "L3 Gold corporativa": "border-l-amber-500", "L3 Gold de domínio": "border-l-sky-500", "L4 Semântica": "border-l-brand-600",
};
const W = 200, H = 46, GAP_X = 36, GAP_Y = 10, TOP = 28;

export default function LineageGraph({ nodes, edges, selected, onSelect }: { nodes: any[]; edges: any[]; selected?: string | null; onSelect: (id: string) => void }) {
  const { chart } = useTheme();
  const layout = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {};
    const counts: number[] = COLS.map(() => 0);
    nodes.forEach((n) => {
      const col = Math.max(0, COLS.indexOf(layerOf(n.layer)));
      pos[n.id] = { x: col * (W + GAP_X), y: TOP + counts[col] * (H + GAP_Y) };
      counts[col] += 1;
    });
    const height = TOP + Math.max(1, ...counts) * (H + GAP_Y);
    return { pos, height, width: COLS.length * (W + GAP_X) };
  }, [nodes]);

  const related = useMemo(() => {
    if (!selected) return new Set<string>();
    return new Set(edges.filter((e) => e.upstream === selected || e.downstream === selected).flatMap((e) => [e.upstream, e.downstream]));
  }, [edges, selected]);

  return (
    <div className="overflow-auto rounded-lg border border-ink-700 bg-ink-950 p-4">
      <div className="relative" style={{ width: layout.width, height: layout.height }}>
        {COLS.map((c, i) => <div key={c} className="label absolute" style={{ left: i * (W + GAP_X), top: 0 }}>{c}</div>)}
        <svg className="absolute inset-0" width={layout.width} height={layout.height}>
          {edges.map((e, i) => {
            const a = layout.pos[e.upstream], b = layout.pos[e.downstream];
            if (!a || !b) return null;
            const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
            const hot = selected && (e.upstream === selected || e.downstream === selected);
            return <path key={i} d={`M${x1},${y1} C${x1 + 30},${y1} ${x2 - 30},${y2} ${x2},${y2}`} fill="none"
              stroke={hot ? chart.primary : chart.axisLine} strokeWidth={hot ? 2 : 1.2} />;
          })}
        </svg>
        {nodes.map((n) => {
          const p = layout.pos[n.id];
          return (
            <button key={n.id} onClick={() => onSelect(n.id)} title={n.id}
              className={clsx("absolute rounded-md border-l-4 border border-ink-600 bg-ink-850 px-2.5 py-1 text-left transition hover:bg-ink-800",
                COLOR[layerOf(n.layer)], selected === n.id && "ring-2 ring-brand-500", selected && !related.has(n.id) && selected !== n.id && "opacity-40")}
              style={{ left: p.x, top: p.y, width: W, height: H }}>
              <div className="truncate text-xs font-medium text-slate-100">{n.label}</div>
              <div className="truncate font-mono text-[10px] text-slate-500">{n.key}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
