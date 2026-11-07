"use client";
import { useMemo, useState } from "react";
import { Card, DemoBadge, ErrorBox, JsonBlock, Loading, PageHeader } from "@/components/ui";
import LineageGraph from "@/features/lineage/LineageGraph";
import { useApi } from "@/hooks/useApi";

export default function LineagePage({ searchParams }: { searchParams: { node?: string } }) {
  const [focus, setFocus] = useState<string>(searchParams?.node || "");
  const [direction, setDirection] = useState("upstream");
  const full = useApi<any>("/data/lineage");
  const focused = useApi<any>(focus ? "/data/lineage" : null, { node: focus, direction });
  const g = focus ? focused.data : full.data;
  const [selected, setSelected] = useState<string | null>(null);
  const sel = useMemo(() => g?.nodes.find((n: any) => n.id === selected), [g, selected]);
  const options = (full.data?.nodes || []).map((n: any) => n.id).sort();

  return (
    <>
      <PageHeader kicker="Governança" title="Linhagem de dados"
        subtitle="Navegue de um indicador até sua origem: fonte → Bronze → Silver → Gold → métrica semântica. Selecione um nó para ver dependências, versões e execuções."
        actions={<>
          <select className="input" value={focus} onChange={(e) => { setFocus(e.target.value); setSelected(e.target.value || null); }}>
            <option value="">Grafo completo</option>
            {options.map((o: string) => <option key={o} value={o}>{o}</option>)}
          </select>
          <select className="input" value={direction} onChange={(e) => setDirection(e.target.value)} disabled={!focus}>
            <option value="upstream">Origem (upstream)</option><option value="downstream">Impacto (downstream)</option><option value="both">Ambos</option>
          </select>
        </>} />
      <ErrorBox error={full.error || focused.error} onRetry={full.reload} />
      {(full.loading || focused.loading) && !g && <Loading />}
      {g && g.nodes.length === 0 && <Card><div className="text-sm text-slate-400">Sem linhagem registrada. Execute o pipeline.</div></Card>}
      {g && g.nodes.length > 0 && (
        <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
          <LineageGraph nodes={g.nodes} edges={g.edges} selected={selected} onSelect={setSelected} />
          <Card title={sel ? sel.label : "Detalhes do nó"} subtitle={sel?.id}>
            {sel ? (
              <div className="space-y-3 text-sm">
                <div>Camada: <span className="text-white">{sel.layer}</span> {sel.is_demo && <DemoBadge />}</div>
                <div>
                  <div className="label mb-1">Dependências diretas</div>
                  <ul className="space-y-1 text-xs">
                    {g.edges.filter((e: any) => e.downstream === sel.id).map((e: any) => <li key={e.upstream}>⬅ <code>{e.upstream}</code> <span className="text-slate-500">({e.transform})</span></li>)}
                    {g.edges.filter((e: any) => e.upstream === sel.id).map((e: any) => <li key={e.downstream}>➡ <code>{e.downstream}</code> <span className="text-slate-500">({e.transform})</span></li>)}
                  </ul>
                </div>
                <div><div className="label mb-1">Metadados / última execução</div><JsonBlock value={sel.details || {}} maxHeight={320} /></div>
              </div>
            ) : <div className="text-sm text-slate-500">Clique em um nó do grafo.</div>}
          </Card>
        </div>
      )}
    </>
  );
}
