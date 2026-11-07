"use client";
import Link from "next/link";
import { useState } from "react";
import { Bars, LineSeries, npsColor, npsHex, StackedBars, useChartPalette } from "@/components/charts";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, DemoBadge, SyntheticBadge, ErrorBox, Kpi, Loading, MetricTag, PageHeader } from "@/components/ui";
import Filters, { type NpsFilters } from "@/features/nps/Filters";
import { useApi } from "@/hooks/useApi";

const CAT_COLOR: Record<string, string> = { promoter: "positive", neutral: "neutral", detractor: "negative" };

/** Segmentos reais da dimensão. O grupo "sem vínculo" (avaliações órfãs / sem o atributo) não é um estado,
 *  produto ou transportadora: fica fora dos rankings e é informado à parte (UnlinkedNote). */
const linked = (d: any): any[] => (d?.rows || []).filter((r: any) => !r.unlinked);

function UnlinkedNote({ d }: { d: any }) {
  const u = d?.meta?.unlinked;
  if (!u || !u.total) return null;
  return (
    <p className="mt-2 text-xs text-slate-400" title={u.note}>
      Fora do gráfico: {fmt.num(u.total)} avaliações sem pedido vinculado ou sem este atributo — não representam um segmento.
      {" "}<Link href="/lakehouse/quality" className="underline decoration-dotted hover:text-slate-200">Ver Qualidade de dados</Link>
    </p>
  );
}

export default function NpsPage() {
  const [f, setF] = useState<NpsFilters>({});
  const q = f as Record<string, string>;
  const ov = useApi<any>("/analytics/nps/overview", q);
  const evo = useApi<any>("/analytics/nps/evolution", q);
  const dist = useApi<any>("/analytics/nps/distribution", q);
  const st = useApi<any>("/analytics/nps/by-state", q);
  const pr = useApi<any>("/analytics/nps/by-product", q);
  const ca = useApi<any>("/analytics/nps/by-carrier", q);
  const co = useApi<any>("/analytics/nps/correlation", q);
  const cm = useApi<any>("/analytics/nps/comments", q);
  const n = ov.data?.nps;
  const palette = useChartPalette();
  const evoRows = (evo.data?.rows || []).filter((r: any) => r.has_data);
  const lastDelta = evoRows.length >= 2 ? evoRows[evoRows.length - 1].delta : null;

  return (
    <>
      <PageHeader kicker="Análises · Experiência do cliente" title="NPS"
        subtitle="Todos os indicadores usam a definição oficial METRIC_NPS_001 calculada no backend: ((Promotores − Detratores) / avaliações válidas) × 100."
        actions={<>{ov.data?.meta?.is_demo && <DemoBadge />}<MetricTag meta={ov.data?.metric} /></>} />
      <Filters value={f} onChange={setF} />
      <ErrorBox error={ov.error} onRetry={ov.reload} />
      {ov.loading && !ov.data && <Loading />}
      {n && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Kpi label="NPS" value={n.value === null ? "—" : fmt.num(n.value, 1)} hint={n.value === null ? "sem avaliações válidas (nulo)" : "pontos (−100 a +100)"}
              tone={n.value === null ? "default" : n.value >= 50 ? "good" : n.value >= 0 ? "warn" : "bad"} delta={lastDelta} deltaLabel="vs. mês anterior"
              info={<>{ov.data.metric.formula_text}<br /><span className="text-slate-500">{ov.data.metric.metric_key} v{ov.data.metric.version}</span></>} />
            <Kpi label="Avaliações válidas" value={fmt.num(n.n)} hint={`${ov.data.invalid_scores_quarantined ?? 0} notas inválidas em quarentena`}
              info="Somente notas inteiras de 0 a 10 entram no cálculo. Notas fora do intervalo ficam em quarentena (Qualidade de dados)." />
            <Kpi label="Promotores" value={fmt.pct(n.promoter_pct)} hint={`${fmt.num(n.promoters)} (notas 9–10)`} tone="good" />
            <Kpi label="Neutros" value={fmt.pct(n.neutral_pct)} hint={`${fmt.num(n.neutrals)} (notas 7–8)`} />
            <Kpi label="Detratores" value={fmt.pct(n.detractor_pct)} hint={`${fmt.num(n.detractors)} (notas 0–6)`} tone="bad" />
          </div>
          <div className="grid gap-5 xl:grid-cols-3">
            <Card className="xl:col-span-2" title="Evolução mensal" subtitle="Por data da avaliação. Meses sem avaliações aparecem como nulos, nunca como zero.">
              {evo.data && <>
                <LineSeries data={evo.data.rows} x="month" lines={[{ key: "nps", name: "NPS", color: "primary" }]} refY={0}
                  label="Evolução mensal do NPS" summary={evoRows.map((r: any) => `${r.month}: ${fmt.num(r.nps, 1)}`).join("; ")} />
                <details className="mt-3"><summary className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white">Ver dados em tabela</summary>
                <DataTable caption="Evolução mensal do NPS" rows={evo.data.rows} columns={[
                  { key: "month", label: "Mês" }, { key: "total", label: "Avaliações" }, { key: "promoters", label: "Prom." },
                  { key: "neutrals", label: "Neutros" }, { key: "detractors", label: "Detr." },
                  { key: "nps", label: "NPS", render: (r: any) => <span className="font-medium tabular-nums" style={{ color: npsHex(palette, r.nps) }}>{fmt.num(r.nps, 1)}</span> },
                  { key: "delta", label: "Δ mês ant.", render: (r: any) => r.delta === null ? "—" : <span className={r.delta < 0 ? "text-rose-300" : "text-emerald-300"}>{r.delta > 0 ? "▲ +" : "▼ "}{fmt.num(r.delta, 1)}</span> },
                ]} /></details>
              </>}
            </Card>
            <Card title="Distribuição das notas">
              {dist.data && <>
                <Bars data={dist.data.scores} x="score" y="count" name="Avaliações" colorFn={(r) => CAT_COLOR[r.category]} height={280}
                  label="Distribuição das notas de 0 a 10" summary={`Promotores ${fmt.pct(dist.data.categories.promoter_pct)}, neutros ${fmt.pct(dist.data.categories.neutral_pct)}, detratores ${fmt.pct(dist.data.categories.detractor_pct)}`} />
                <ul className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400" aria-label="Legenda">
                  {[["positive", "Promotores (9–10)"], ["neutral", "Neutros (7–8)"], ["negative", "Detratores (0–6)"]].map(([k, l]) => (
                    <li key={k} className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: (palette as any)[k] }} />{l}</li>))}
                </ul></>}
            </Card>
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <Card title="NPS por estado" subtitle="Amostras pequenas (< 30) sinalizadas">
              {st.data && <Bars data={linked(st.data)} x="value" y="nps" name="NPS" horizontal height={Math.max(260, linked(st.data).length * 22)} colorFn={(r) => npsColor(r.nps)} />}
              {st.data && <div className="mt-2 flex flex-wrap gap-1">{linked(st.data).filter((r: any) => r.low_sample).map((r: any) => <Badge key={r.value} tone="amber">{r.value}: n={r.total}</Badge>)}</div>}
              <UnlinkedNote d={st.data} />
            </Card>
            <Card title="Taxa de detratores por estado e por linha de produto">
              {st.data && <DataTable maxHeight={200} rows={[...linked(st.data)].sort((a: any, b: any) => (b.detractor_rate ?? 0) - (a.detractor_rate ?? 0))} columns={[
                { key: "value", label: "UF" }, { key: "total", label: "n" }, { key: "detractor_rate", label: "% detratores", render: (r: any) => fmt.pct(r.detractor_rate) }, { key: "nps", label: "NPS", render: (r: any) => fmt.num(r.nps, 1) },
              ]} />}
              {pr.data && <Bars data={[...linked(pr.data)].sort((a: any, b: any) => (b.detractor_rate ?? 0) - (a.detractor_rate ?? 0))} x="value" y="detractor_rate" name="% detratores" unit="%" height={200} colorFn={(r) => (r.detractor_rate > 20 ? "negative" : "secondary")} />}
              <UnlinkedNote d={pr.data} />
            </Card>
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <Card title="Nota média por transportadora">
              {ca.data && <Bars data={linked(ca.data.carrier)} x="value" y="avg_score" name="Nota média" horizontal height={220} colorFn={(r) => npsColor(r.nps)} />}
              {ca.data && <DataTable rows={linked(ca.data.carrier)} columns={[{ key: "value", label: "Transportadora" }, { key: "total", label: "n" }, { key: "avg_score", label: "Nota média" }, { key: "nps", label: "NPS" }]} />}
              <UnlinkedNote d={ca.data?.carrier} />
            </Card>
            <Card title="Nota média por tipo de frete">
              {ca.data && <Bars data={linked(ca.data.shipping_type)} x="value" y="avg_score" name="Nota média" height={220} colorFn={() => "secondary"} />}
              {ca.data && <DataTable rows={linked(ca.data.shipping_type)} columns={[{ key: "value", label: "Frete" }, { key: "total", label: "n" }, { key: "avg_score", label: "Nota média" }, { key: "nps", label: "NPS" }]} />}
              <UnlinkedNote d={ca.data?.shipping_type} />
            </Card>
          </div>
          {co.data && (
            <Card title="Prazo de entrega × NPS" subtitle="Correlação de Pearson e Spearman. Correlação não implica causalidade.">
              <div className="grid gap-5 lg:grid-cols-2">
                {Object.entries(co.data.correlations).map(([k, v]: any) => (
                  <div key={k}>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-200">{v.label}{v.synthetic && <SyntheticBadge fields={["datas de envio/entrega"]} />}</div>
                    <div className="mb-2 grid grid-cols-3 gap-2 text-xs">
                      <div className="rounded bg-ink-950 p-2"><div className="label">Pearson r</div><div className="text-lg text-white">{fmt.num(v.pearson.r, 3)}</div><div className="text-slate-500">IC95 {v.pearson.ci95 ? v.pearson.ci95.join(" a ") : "—"}</div></div>
                      <div className="rounded bg-ink-950 p-2"><div className="label">Spearman ρ</div><div className="text-lg text-white">{fmt.num(v.spearman.r, 3)}</div><div className="text-slate-500">força: {v.strength}</div></div>
                      <div className="rounded bg-ink-950 p-2"><div className="label">Observações</div><div className="text-lg text-white">{fmt.num(v.pearson.n)}</div><div className="text-slate-500">excluídas: {fmt.num(v.observations_excluded)}</div></div>
                    </div>
                    <Bars data={v.buckets} x="bucket" y="nps" name="NPS na faixa" height={200} colorFn={(r) => npsColor(r.nps)} />
                  </div>
                ))}
              </div>
              <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-slate-400">{co.data.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul>
            </Card>
          )}
          {cm.data && (
            <Card title="Comentários (NLP determinístico)" subtitle={`${fmt.num(cm.data.comments_available)} comentários processados de ${fmt.num(cm.data.evaluations_in_scope)} avaliações · ${cm.data.injection_suspected} com suspeita de prompt injection (tratados apenas como dados)`}>
              <div className="grid gap-5 lg:grid-cols-2">
                {(["promoters", "detractors"] as const).map((g) => (
                  <div key={g}>
                    <div className="mb-2 text-sm font-medium" style={{ color: g === "promoters" ? palette.positive : palette.negative }}>{g === "promoters" ? "Promotores" : "Detratores"} · {cm.data[g].comments_processed} comentários</div>
                    <div className="mb-2 flex flex-wrap gap-1.5">{cm.data[g].unigrams.slice(0, 18).map((w: any) => <span key={w.term} className="rounded bg-ink-800 px-2 py-0.5 text-xs" style={{ fontSize: 10 + Math.min(8, w.count / 15) }}>{w.term} <span className="text-slate-500">{w.count}</span></span>)}</div>
                    <div className="label mb-1 mt-2">Bigramas</div>
                    <div className="flex flex-wrap gap-1.5">{cm.data[g].bigrams.slice(0, 10).map((w: any) => <Badge key={w.term}>{w.term} · {w.count}</Badge>)}</div>
                  </div>
                ))}
              </div>
              <div className="mt-5">
                <div className="label mb-2">Temas recorrentes — promotores × detratores</div>
                <StackedBars data={cm.data.theme_comparison} x="label" series={[{ key: "promoter_count", name: "Promotores", color: "positive" }, { key: "detractor_count", name: "Detratores", color: "negative" }]} height={240} />
              </div>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
