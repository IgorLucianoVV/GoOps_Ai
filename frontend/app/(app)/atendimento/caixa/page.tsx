"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { MessagesSquare, Radio } from "lucide-react";
import { DemoBadge, ErrorBox, Loading, PageHeader } from "@/components/ui";
import CasePanel from "@/features/support/CasePanel";
import ChatThread from "@/features/support/ChatThread";
import ConversationList from "@/features/support/ConversationList";
import { useAction, useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";

export default function Page() {
  return <Suspense fallback={<Loading />}><SupportInbox /></Suspense>;
}

/** Caixa unificada estilo WhatsApp: conversas (uma por cliente e canal) · chat · painel do atendimento. */
function SupportInbox() {
  const router = useRouter();
  const params = useSearchParams();
  const { can } = useAuth();
  const write = can("support:write");
  const [queue, setQueue] = useState("open");
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const convId = params.get("c");
  const list = useApi<any>("/support/conversations", { queue, q, channel, limit: 100 });
  const conv = useApi<any>(convId ? `/support/conversations/${convId}` : null);
  const caseId = params.get("k") || conv.data?.current_case_id || conv.data?.cases?.[conv.data.cases.length - 1]?.id || null;
  const kase = useApi<any>(caseId ? `/support/contacts/${caseId}` : null);
  const cat = useApi<any>("/support/catalog");
  const act = useAction();
  const confirm = useConfirm();

  const select = (c: string, k?: string) => router.replace(`/atendimento/caixa?c=${c}${k ? `&k=${k}` : ""}`, { scroll: false });
  useEffect(() => { if (!convId && list.data?.items?.length) select(list.data.items[0].id); }, [convId, list.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const reloadAll = () => { list.reload(); conv.reload(); kase.reload(); };

  const send = async (text: string) => {
    const open = conv.data?.cases?.find((k: any) => k.id === conv.data.current_case_id);
    if (!open) return;
    if (await act.run(`/support/contacts/${open.id}/reply`, { text, resolve: false }, undefined,
      { success: "Resposta enviada", successDescription: "Envio simulado pelo canal de origem. O atendimento segue aberto aguardando o cliente." })) reloadAll();
  };
  const closeCase = async () => {
    const open = conv.data?.cases?.find((k: any) => k.id === conv.data.current_case_id);
    if (!open) return;
    const ok = await confirm({ title: `Encerrar o atendimento #${open.case_number}?`, confirmLabel: "Encerrar atendimento",
      description: "O atendimento sai da fila. Se o cliente escrever de novo, um novo atendimento é aberto na mesma conversa." });
    if (ok && await act.run(`/support/contacts/${open.id}/update`, { status: "resolved", note: "Encerrado pelo atendente" }, undefined,
      { success: "Atendimento encerrado" })) reloadAll();
  };
  const note = async (text: string) => { if (await act.run(`/support/conversations/${convId}/note`, { text, contact_id: caseId }, undefined, { success: "Nota interna salva" })) conv.reload(); };
  const ai = async () => {
    const open = conv.data?.current_case_id;
    if (!open) return null;
    const r: any = await act.run(`/support/contacts/${open}/draft-ai`, {});
    return r ? r.text : null;
  };
  const propose = async (a: any) => {
    const ok = await confirm({ title: `Propor "${a.title}"?`, confirmLabel: a.requires_approval ? "Propor para aprovação" : "Executar (simulado)",
      description: a.requires_approval ? "Ação em área crítica: aguarda a aprovação de um responsável. Aprovada, o Agente de Atendimento executa (simulado)."
        : "A política dispensa aprovação; a ação é registrada e executada em modo simulado." });
    if (ok && await act.run(`/support/contacts/${caseId}/actions`, { action_type: a.action_type, note: "" }, undefined, { success: "Ação proposta" })) reloadAll();
  };
  const update = async (body: any, success: string) => { if (await act.run(`/support/contacts/${caseId}/update`, body, undefined, { success })) reloadAll(); };
  const retriage = async () => { if (await act.run(`/support/contacts/${caseId}/retriage`, {}, undefined, { success: "Triagem refeita" })) reloadAll(); };
  const simulate = async () => { if (await act.run("/support/simulate", { count: 8 }, undefined, { success: "Novas mensagens recebidas", successDescription: "O agente fez a triagem; veja as conversas no topo." })) { setQueue("open"); reloadAll(); } };

  const openCase = conv.data?.cases?.find((k: any) => k.id === conv.data?.current_case_id && ["pending_human", "pending_approval", "awaiting_customer"].includes(k.status));
  const suggestion = openCase && kase.data?.id === openCase.id && kase.data?.status !== "auto_resolved" ? kase.data?.suggested_reply : "";

  return (
    <>
      <PageHeader kicker="Atendimento ao cliente" title="Caixa unificada"
        subtitle="Uma conversa por cliente e canal, como no WhatsApp: o cliente à esquerda; o agente automático e os atendentes à direita. Cada atendimento aparece separado dentro da conversa."
        actions={<>{conv.data?.is_demo && <DemoBadge />}
          {write && <button className="btn-ghost" disabled={act.busy} onClick={simulate}><Radio size={14} /> Simular novas mensagens</button>}</>} />
      <ErrorBox error={list.error || conv.error || act.error} onRetry={reloadAll} />
      <div className="card grid h-[calc(100vh-15rem)] min-h-[560px] grid-cols-1 overflow-hidden p-0 md:grid-cols-[300px_1fr] xl:grid-cols-[300px_1fr_360px]">
        <aside className="hidden min-h-0 border-r border-ink-700 md:block">
          <ConversationList items={list.data?.items || []} total={list.data?.total || 0} selected={convId} onSelect={(id) => select(id)}
            queue={queue} setQueue={setQueue} q={q} setQ={setQ} channel={channel} setChannel={setChannel} loading={list.loading} />
        </aside>
        <section className="min-h-0 min-w-0" data-tour="chat">
          {!convId && <div className="grid h-full place-items-center text-sm text-slate-500"><span className="flex items-center gap-2"><MessagesSquare size={18} /> Selecione uma conversa</span></div>}
          {convId && conv.loading && !conv.data && <Loading />}
          {conv.data && <ChatThread conv={conv.data} selectedCase={caseId} onSelectCase={(k) => select(convId!, k)} canWrite={write}
            suggestion={suggestion} busy={act.busy} onSend={send} onNote={note} onAi={ai} onClose={closeCase} />}
        </section>
        <aside className="hidden min-h-0 border-l border-ink-700 xl:block" data-tour="case-panel">
          {kase.data && <CasePanel c={kase.data} intents={cat.data?.intents || {}} canWrite={write} busy={act.busy}
            onPropose={propose} onUpdate={update} onRetriage={retriage} onReload={reloadAll} />}
          {!kase.data && <div className="p-6 text-sm text-slate-500">Selecione um atendimento para ver triagem, veracidade, pedido e ações.</div>}
        </aside>
      </div>
      {kase.data && <div className="mt-4 xl:hidden"><div className="card p-0" data-tour="case-panel">
        <CasePanel c={kase.data} intents={cat.data?.intents || {}} canWrite={write} busy={act.busy} onPropose={propose} onUpdate={update} onRetriage={retriage} onReload={reloadAll} />
      </div></div>}
    </>
  );
}
