"use client";
import Link from "next/link";
import { BellRing } from "lucide-react";
import { Bars } from "@/components/charts";
import { fmt } from "@/components/labels";
import { Badge, Card, DataTable, ErrorBox, Kpi, PageHeader, PageSkeleton } from "@/components/ui";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";

export default function PreventionPage() {
  const { data, error, loading, reload } = useApi<any>("/support/prevention");
  const { can } = useAuth();
  const act = useAction();
  const confirm = useConfirm();
  if (loading && !data) return <PageSkeleton />;
  const r = data?.recontact || {};
  const p = data?.proactive || {};
  const notify = async () => {
    const ok = await confirm({ title: `Avisar ${fmt.num(p.count)} clientes antes que entrem em contato?`, confirmLabel: "Propor aviso para aprovação",
      description: "Toca a área crítica “clientes”: fica aguardando a aprovação de um responsável em Operações. Envio simulado nesta versão." });
    if (!ok) return;
    if (await act.run("/support/prevention/notify", {}, undefined, { success: "Aviso proativo proposto", successDescription: "Aguardando aprovação em Operações." })) reload();
  };
  return (
    <>
      <PageHeader kicker="Atendimento ao cliente" title="Prevenção de recontato"
        subtitle="Contatos que se repetem ou que poderiam ter sido evitados: onde se concentram e o que fazer antes que o cliente precise chamar."
        actions={<Link className="btn-ghost" href="/operations">Ver aprovações em Operações</Link>} />
      <ErrorBox error={error || act.error} onRetry={reload} />
      {data && r.total > 0 && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Recontato" value={fmt.pct(r.repeat_rate)} hint={`${fmt.num(r.repeats)} de ${fmt.num(r.total)} contatos`} tone="warn"
              info="Cliente voltou pelo mesmo assunto (mesmo pedido) dentro da janela de recontato." />
            <Kpi label="Recontatos escalados ao Reclame Aqui" value={fmt.num(r.repeats_escalated_to_reclameaqui)} tone="bad" hint="reclamação pública após contato sem solução" />
            <Kpi label="Contatos evitáveis" value={fmt.pct(r.avoidable_rate)} hint={`${fmt.num(r.avoidable)} contatos`} tone="warn" />
            <Kpi label="Contatos evitados com aviso proativo" value={`≈ ${fmt.num(p.expected_contacts_avoided)}`} tone="good" hint={`avisando ${fmt.num(p.count)} pedidos em risco`} info={p.assumption} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Por que os contatos eram evitáveis">
              <Bars data={(r.avoidable_by_reason || []).map((x: any) => ({ ...x, label: x.avoidable_reason }))} x="label" y="contacts" name="Contatos" horizontal />
            </Card>
            <Card title="Recontato por assunto">
              <DataTable rows={r.by_intent || []} columns={[
                { key: "label", label: "Assunto" },
                { key: "contacts", label: "Contatos", className: "text-right tabular-nums" },
                { key: "repeats", label: "Recontatos", className: "text-right tabular-nums", render: (x: any) => fmt.num(x.repeats) },
                { key: "rate", label: "% recontato", className: "text-right tabular-nums", render: (x: any) => <span className={x.rate >= 20 ? "text-amber-300" : ""}>{fmt.pct(x.rate)}</span> },
              ]} />
            </Card>
          </div>

          <Card title="Onde os contatos se concentram" subtitle="Assunto × transportadora × linha de produto (contatos com pedido vinculado). Ponto de partida para atacar a causa, não o sintoma.">
            <DataTable rows={data.root_causes || []} columns={[
              { key: "intent_label", label: "Assunto" }, { key: "carrier", label: "Transportadora" }, { key: "product_line", label: "Linha" },
              { key: "contacts", label: "Contatos", className: "text-right tabular-nums" },
              { key: "share_pct", label: "% do total", className: "text-right tabular-nums", render: (x: any) => fmt.pct(x.share_pct) },
              { key: "repeats", label: "Recontatos", className: "text-right tabular-nums" },
            ]} />
          </Card>

          <Card title={<span className="inline-flex items-center gap-1.5"><BellRing size={15} /> Aviso proativo de atraso</span>}
            subtitle="Pedidos em aberto com risco médio/alto de atraso (Gold de Logística) que ainda não geraram contato."
            actions={can("support:write") && p.count > 0 && <button className="btn-primary" disabled={act.busy} onClick={notify}>Propor aviso a {fmt.num(p.count)} clientes</button>}>
            {p.count === 0 && <p className="text-sm text-slate-400">Nenhum pedido em risco sem contato no momento.</p>}
            {p.count > 0 && (
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(p.by_risk || {}).map(([k, v]: any) => <Badge key={k} tone={k === "high" ? "red" : "amber"}>risco {k === "high" ? "alto" : "médio"}: {v}</Badge>)}
                    {Object.entries(p.by_carrier || {}).map(([k, v]: any) => <Badge key={k}>{k}: {v}</Badge>)}
                  </div>
                  {p.message_preview && <><div className="mt-3 label">Prévia da mensagem</div><div className="mt-1 rounded-md border border-ink-700 bg-ink-850 p-3 text-sm text-slate-200">{p.message_preview}</div></>}
                  <p className="mt-2 text-xs text-slate-500">{p.assumption}</p>
                </div>
                <DataTable rows={p.orders || []} maxHeight={260} columns={[
                  { key: "order_id", label: "Pedido" }, { key: "carrier", label: "Transportadora" }, { key: "state", label: "UF" },
                  { key: "estimated_delivery_date", label: "Previsão", render: (x: any) => fmt.day(x.estimated_delivery_date) },
                  { key: "risk_level", label: "Risco", render: (x: any) => <Badge tone={x.risk_level === "high" ? "red" : "amber"}>{x.risk_level === "high" ? "alto" : "médio"}</Badge> },
                ]} />
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
