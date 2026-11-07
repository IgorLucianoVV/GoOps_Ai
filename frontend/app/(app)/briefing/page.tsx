"use client";
import { useState } from "react";
import Link from "next/link";
import { Newspaper, Sparkles } from "lucide-react";
import { fmt } from "@/components/labels";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader } from "@/components/ui";
import Markdown from "@/features/ask/Markdown";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";

export default function BriefingPage() {
  const list = useApi<any[]>("/briefings");
  const feats = useApi<any>("/features");
  const action = useAction();
  const { can } = useAuth();
  const [sel, setSel] = useState<string | null>(null);
  const items = list.data || [];
  const cur = items.find((b) => b.id === sel) || items[0];
  const run = async () => { const r: any = await action.run("/briefings/run", {}, undefined, { success: "Briefing gerado" }); if (r) { setSel(r.id); list.reload(); } };
  return (
    <>
      <PageHeader kicker="Visão geral" title="Briefing diário"
        subtitle="O que mudou, onde olhar e o que espera decisão — calculado pelas métricas governadas. Entregas em canais são simuladas."
        actions={<>
          <Badge tone={feats.data?.briefing_enabled ? "green" : "gray"}>{feats.data?.briefing_enabled ? "automático ligado" : "automático desligado"}</Badge>
          {can("settings:write") && <Link className="btn-ghost" href="/settings">Configurar</Link>}
          <button className="btn-primary" disabled={action.busy} onClick={run}><Newspaper size={14} /> Gerar agora</button>
        </>} />
      <ErrorBox error={list.error || action.error} onRetry={list.reload} />
      {list.loading && !list.data && <Loading />}
      {list.data && items.length === 0 && <Empty title="Nenhum briefing ainda" hint="Gere agora ou ligue o briefing automático em Configurações › Recursos." />}
      {cur && (
        <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
          <Card title={`Briefing de ${fmt.date(cur.created_at)}`} subtitle={cur.triggered_by === "scheduler" ? "gerado automaticamente" : `gerado por ${cur.triggered_by}`}
            actions={<span className="inline-flex flex-wrap gap-1">{(cur.deliveries || []).map((d: any) => <Badge key={d.channel} tone="violet">{d.channel} {d.target} · {d.status}</Badge>)}</span>}>
            {cur.narrative_md && <div className="mb-4 rounded-md border border-violet-500/40 p-3 text-sm">
              <Badge tone="violet"><Sparkles size={11} aria-hidden /> Narrativa por IA · {String(cur.generated_by).replace("llm:", "")}</Badge>
              <div className="mt-2"><Markdown text={cur.narrative_md} /></div></div>}
            <div className="text-sm"><Markdown text={cur.content_md} /></div>
          </Card>
          <Card title="Histórico">
            <ul className="space-y-1 text-sm">{items.map((b) => (
              <li key={b.id}><button className={`w-full rounded px-2 py-1 text-left ${b.id === cur.id ? "bg-ink-800 text-white" : "text-slate-400 hover:text-white"}`} onClick={() => setSel(b.id)}>
                {fmt.date(b.created_at)} <span className="text-xs text-slate-500">{b.triggered_by === "scheduler" ? "auto" : "manual"}</span></button></li>))}</ul>
          </Card>
        </div>
      )}
    </>
  );
}
