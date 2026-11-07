"use client";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTheme, type ChartPalette } from "@/hooks/useTheme";

/** Tokens semânticos aceitos em colorFn/color: resolvidos pela paleta do tema (claro/escuro). Hex também é aceito. */
export type ChartColor = keyof Omit<ChartPalette, "series"> | string;

const resolve = (p: ChartPalette, c: ChartColor) => ((p as any)[c] as string) || c;

function useChartStyles() {
  const { chart: p } = useTheme();
  return {
    p,
    axis: { stroke: p.axis, fontSize: 12, fill: p.axis },
    tooltip: {
      contentStyle: { background: p.tooltipBg, border: `1px solid ${p.tooltipBorder}`, borderRadius: 10, fontSize: 12, color: p.text },
      labelStyle: { color: p.text, fontWeight: 600 }, itemStyle: { color: p.text },
    },
  };
}

/** Gráficos são "imagens" com descrição textual (WCAG 1.1.1); o resumo deve trazer a leitura principal. */
function Figure({ label, summary, height, children }: { label: string; summary?: string; height: number; children: React.ReactNode }) {
  return (
    <figure role="img" aria-label={summary ? `${label}. ${summary}` : label} style={{ height }} className="w-full">
      {children}
    </figure>
  );
}

export function LineSeries({ data, x, lines, height = 240, refY, label = "Gráfico de linhas", summary }:
  { data: any[]; x: string; lines: { key: string; name: string; color?: ChartColor }[]; height?: number; refY?: number; label?: string; summary?: string }) {
  const { p, axis, tooltip } = useChartStyles();
  return (
    <Figure label={label} summary={summary} height={height}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
          <CartesianGrid stroke={p.grid} vertical={false} />
          <XAxis dataKey={x} tick={axis} stroke={p.axisLine} tickLine={false} />
          <YAxis tick={axis} stroke={p.axisLine} tickLine={false} axisLine={false} />
          <Tooltip {...tooltip} />
          {refY !== undefined && <ReferenceLine y={refY} stroke={p.muted} strokeDasharray="4 4" />}
          {lines.map((l, i) => (
            <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={resolve(p, l.color || p.series[i % p.series.length])}
              strokeWidth={2.5} dot={{ r: 3.5, strokeWidth: 0, fill: resolve(p, l.color || p.series[i % p.series.length]) }} activeDot={{ r: 5 }} connectNulls={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Figure>
  );
}

export function Bars({ data, x, y, name, height = 240, horizontal = false, colorFn, unit, label, summary }:
  { data: any[]; x: string; y: string; name: string; height?: number; horizontal?: boolean; colorFn?: (row: any) => ChartColor; unit?: string; label?: string; summary?: string }) {
  const { p, axis, tooltip } = useChartStyles();
  const h = horizontal ? Math.max(height, data.length * 30 + 40) : height;   // uma linha legível por categoria
  return (
    <Figure label={label || `${name} por ${x}`} summary={summary} height={h}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 20, left: horizontal ? 24 : -8, bottom: 0 }}>
          <CartesianGrid stroke={p.grid} horizontal={!horizontal} vertical={horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={axis} stroke={p.axisLine} unit={unit} tickLine={false} />
              <YAxis type="category" dataKey={x} tick={axis} stroke={p.axisLine} width={120} tickLine={false} interval={0} />
            </>
          ) : (
            <>
              {/* muitas categorias: mostra todos os rótulos, inclinados, em vez de ocultar alternados */}
              <XAxis dataKey={x} tick={axis} stroke={p.axisLine} tickLine={false} interval={0}
                {...(data.length > 5 ? { angle: -35, textAnchor: "end", height: 70 } : {})} />
              <YAxis tick={axis} stroke={p.axisLine} unit={unit} tickLine={false} axisLine={false} />
            </>
          )}
          <Tooltip {...tooltip} cursor={{ fill: p.cursor }} />
          <Bar dataKey={y} name={name} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} maxBarSize={44}>
            {data.map((row, i) => <Cell key={i} fill={resolve(p, colorFn ? colorFn(row) : "primary")} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Figure>
  );
}

export function StackedBars({ data, x, series, height = 240, label = "Gráfico de barras empilhadas", summary }:
  { data: any[]; x: string; series: { key: string; name: string; color?: ChartColor }[]; height?: number; label?: string; summary?: string }) {
  const { p, axis, tooltip } = useChartStyles();
  return (
    <Figure label={label} summary={summary} height={height}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
          <CartesianGrid stroke={p.grid} vertical={false} />
          <XAxis dataKey={x} tick={axis} stroke={p.axisLine} tickLine={false} />
          <YAxis tick={axis} stroke={p.axisLine} tickLine={false} axisLine={false} />
          <Tooltip {...tooltip} cursor={{ fill: p.cursor }} />
          <Legend wrapperStyle={{ fontSize: 12, color: p.axis }} />
          {series.map((s, i) => <Bar key={s.key} dataKey={s.key} name={s.name} stackId="a" fill={resolve(p, s.color || p.series[i % p.series.length])} />)}
        </BarChart>
      </ResponsiveContainer>
    </Figure>
  );
}

/** Escala NPS divergente (azul = bom, laranja = ruim), segura para daltonismo. Retorna token semântico. */
export function npsColor(v: number | null | undefined): ChartColor {
  if (v === null || v === undefined) return "muted";
  if (v >= 75) return "nps_high";
  if (v >= 50) return "nps_mid";
  if (v >= 0) return "nps_low";
  return "nps_neg";
}

export function useChartPalette() {
  return useTheme().chart;
}

export function npsHex(p: ChartPalette, v: number | null | undefined): string {
  return resolve(p, npsColor(v));
}
