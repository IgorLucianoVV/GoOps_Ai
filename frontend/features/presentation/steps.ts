"use client";
import { fmt } from "@/components/labels";
import { hours, minutesLabel } from "@/features/support/common";
import { api } from "@/services/api";

/** Roteiro do modo apresentação (pitch). Segue docs/pitch/ROTEIRO_DEMO.md e acrescenta a área Agentes de IA.
 *
 * Cada etapa: abre uma página, destaca um elemento marcado com `data-tour="..."` e mostra o valor da funcionalidade.
 * Números exibidos vêm da API no momento (`live`), nunca escritos à mão. Ações (`action`) só rodam quando a pessoa
 * clica — nunca automaticamente — e usam as mesmas rotas e a mesma política de aprovação da interface.
 */
export interface LiveFigure { label: string; value: string; hint?: string }
export interface TourAction { label: string; hint?: string; run: (ctx: TourCtx) => Promise<string> }
export interface TourCtx { cache: Record<string, any> }
export interface TourStep {
  id: string;
  /** rota fixa ou resolvida na hora (ex.: abrir uma conversa de avaria existente) */
  path: string | ((ctx: TourCtx) => Promise<string>);
  kicker: string;          // critério da banca que a etapa prova
  title: string;
  text: string;
  bullets?: string[];
  say?: string;            // fala sugerida para quem apresenta
  target?: string;         // data-tour do elemento destacado
  tab?: string;            // aba que a página deve abrir (evento goops:tour)
  placement?: "center";    // abertura/fechamento: cartão central, sem destaque
  live?: (ctx: TourCtx) => Promise<LiveFigure[]>;
  action?: TourAction;
}

const data = async <T = any>(path: string, q?: Record<string, any>) => (await api.get<T>(path, q)).data;

async function demoCase(ctx: TourCtx): Promise<any | null> {
  if (ctx.cache.case !== undefined) return ctx.cache.case;
  const tries: Record<string, any>[] = [
    { intent: "avaria", queue: "open", veracity: "consistente", limit: 1 },
    { intent: "avaria", queue: "open", limit: 1 },
    { intent: "defeito", queue: "open", limit: 1 },
    { queue: "open", limit: 1 },
  ];
  for (const q of tries) {
    try {
      const r: any = await data("/support/contacts", q);
      const item = r?.items?.find((i: any) => i.order_id) || r?.items?.[0];
      if (item) {
        const full: any = await data(`/support/contacts/${item.id}`);
        ctx.cache.case = full;
        return full;
      }
    } catch { /* tenta o próximo filtro */ }
  }
  ctx.cache.case = null;
  return null;
}

async function casePath(ctx: TourCtx) {
  const c = await demoCase(ctx);
  return c?.conversation_id ? `/atendimento/caixa?c=${c.conversation_id}&k=${c.id}` : "/atendimento/caixa";
}

async function overviewFigures(): Promise<LiveFigure[]> {
  const d: any = await data("/support/overview");
  if (!d?.ready) return [];
  return [
    { label: "Resolvidos sem pessoa", value: fmt.pct(d.automation?.auto_rate), hint: `${fmt.num(d.total)} atendimentos` },
    { label: "Esforço poupado", value: hours(d.effort?.saved_hours), hint: `${fmt.pct(d.effort?.saved_pct)} do manual` },
    { label: "1ª resposta automática", value: minutesLabel(d.response?.first_response_auto_min),
      hint: `pessoa: ${minutesLabel(d.response?.first_response_human_min)}` },
  ];
}

export const STEPS: TourStep[] = [
  {
    id: "abertura", path: "/atendimento", placement: "center",
    kicker: "Conceito", title: "Um colega de trabalho para o atendimento — não um chatbot",
    text: "Milhares de contatos por WhatsApp, e-mail e Reclame Aqui. Cada um exige pular entre pedidos, transportadora, ERP e financeiro; nem toda reclamação procede; e o cliente volta quando ninguém avisa.",
    bullets: [
      "Faz sozinho o que é simples, com dados do pedido",
      "Levanta a mão quando não deve decidir",
      "Chama outros agentes quando o problema é maior que um caso",
      "Mora onde o time já conversa",
    ],
    say: "Vou mostrar o colega digital funcionando de ponta a ponta, com a pessoa no controle das decisões críticas.",
  },
  {
    id: "visao", path: "/atendimento", target: "support-kpis",
    kicker: "Modelagem · funciona ponta a ponta", title: "O resultado, medido na própria plataforma",
    text: "Todos os contatos passam pelo Agente de Atendimento: triagem, visão 360 do pedido, veracidade e decisão entre resolver sozinho ou passar para uma pessoa.",
    live: overviewFigures,
    say: "Estes números são calculados agora, sobre os dados da demonstração (sintéticos), com premissas de tempo editáveis.",
  },
  {
    id: "desafios", path: "/atendimento", target: "support-challenges",
    kicker: "Conceito · aderência ao desafio", title: "Cada dor do desafio tem uma resposta na tela",
    text: "Volume, sistemas espalhados, reclamações falsas, o que automatizar e recontato: cada ponto do Desafio 1 aparece como funcionalidade, não como promessa.",
  },
  {
    id: "turno", path: "/atendimento", target: "shift",
    kicker: "Modelagem · autonomia", title: "Ninguém precisa mandar: ele trabalha em turnos",
    text: "A cada rodada o agente processa a caixa, lembra o cliente antes de encerrar, fecha por inatividade, avisa o time quando o SLA estoura, cobra aprovações paradas e, se uma transportadora concentra reclamações, abre incidente e chama Investigação e Resolução.",
    action: {
      label: "Avançar 12 h e rodar o turno", hint: "Simula 12 horas no relógio da demonstração",
      run: async () => {
        const o: any = (await api.post("/support/shift", { advance_hours: 12 })).data || {};
        const inc = (o.incidents || []).length;
        const parts = [
          [o.processed, "mensagens processadas"], [o.reminders, "lembretes enviados"], [o.closed_inactive, "encerrados por inatividade"],
          [o.sla_alerts, "alertas de SLA ao time"], [o.approval_reminders, "cobranças de aprovação"], [inc, "incidente(s) com a equipe de agentes"],
        ].filter(([n]) => Number(n) > 0).map(([n, l]) => `${fmt.num(n)} ${l}`);
        return parts.length ? `Em 12 h simuladas: ${parts.join(" · ")}. Detalhes no Canal do time.`
          : "Turno concluído: nada pendente nesta rodada — a fila está em dia.";
      },
    },
    say: "Agora sim alguém olhando a fila de madrugada: o próprio agente.",
  },
  {
    id: "chat", path: casePath, target: "chat",
    kicker: "Aderência cultural", title: "Uma conversa por cliente, como no WhatsApp",
    text: "Cliente à esquerda; agente automático e atendentes à direita; ações e notas internas no meio. Cada atendimento aparece separado dentro da mesma conversa, com o histórico do cliente.",
    bullets: ["Pediu a foto, o cliente mandou e a triagem foi refeita na hora", "Janela de 24 h do WhatsApp sinalizada no campo de resposta"],
  },
  {
    id: "veracidade", path: casePath, target: "case-panel", tab: "veracidade",
    kicker: "Modelagem · reclamações falsas", title: "A reclamação procede? Com evidências",
    text: "Score de veracidade explicável: entrega registrada, prazo, data da foto versus data da entrega, tempo desde a entrega e reclamações em série. Cada ponto mostra a fonte.",
    bullets: ["Quando os dados não sustentam, vai para uma pessoa com as evidências", "O agente nunca nega uma reclamação sozinho"],
  },
  {
    id: "acoes", path: casePath, target: "case-panel", tab: "acoes",
    kicker: "Agente colega · levanta a mão", title: "Reenvio mexe em pedido e estoque: ele pede aprovação",
    text: "Chamado na transportadora o agente abre sozinho. Troca, reenvio, reembolso e cancelamento seguem a política: ele propõe com as evidências e uma pessoa com o papel certo aprova.",
    action: {
      label: "Propor reenvio deste pedido", hint: "Vai para aprovação no Canal do time (e no Telegram, se configurado)",
      run: async (ctx) => {
        const c = await demoCase(ctx);
        if (!c) return "Nenhum atendimento em aberto para propor a ação.";
        const fresh: any = await data(`/support/contacts/${c.id}`);
        const prev = (fresh?.operations || []).find((o: any) => o.action_type === "support_reshipment" && o.status !== "rejected");
        if (prev) return prev.status === "pending_approval"
          ? "Este reenvio já está aguardando aprovação no Canal do time — siga para a próxima etapa."
          : `Este reenvio já foi decidido (situação: ${prev.status}).`;
        const op: any = (await api.post(`/support/contacts/${c.id}/actions`, { action_type: "support_reshipment", note: "Demonstração (modo apresentação)" })).data;
        return op?.status === "pending_approval"
          ? "Proposta enviada: aguardando aprovação de um responsável no Canal do time."
          : `Ação registrada (situação: ${op?.status || "—"}).`;
      },
    },
  },
  {
    id: "canal", path: "/canal", target: "team-feed",
    kicker: "Agente colega · mora onde o time conversa", title: "A aprovação chega onde o time já está",
    text: "Pedidos de aprovação, alertas de SLA, incidentes e o resumo do dia chegam no Canal do time — e, com Telegram configurado, no grupo, com botões Aprovar e Rejeitar.",
    bullets: ["Aprovação pelo celular fica registrada em nome de quem aprovou", "Aprovada, o agente executa (simulado) e encerra o atendimento"],
    say: "Aprovo pelo Telegram, no celular, e o agente segue sozinho.",
  },
  {
    id: "prevencao", path: "/atendimento/prevencao", target: "proactive",
    kicker: "Conceito · evitar recontato", title: "Atacar a causa, não o sintoma",
    text: "O agente mede recontato e contatos evitáveis, mostra onde se concentram (assunto × transportadora × produto) e propõe avisar antes que o cliente chame.",
    live: async () => {
      const d: any = await data("/support/overview");
      return d?.ready ? [
        { label: "Recontato", value: fmt.pct(d.recontact?.rate), hint: `${fmt.num(d.recontact?.repeats)} reaberturas` },
        { label: "Evitáveis", value: fmt.pct(d.recontact?.avoidable_rate), hint: "aviso proativo teria dispensado" },
      ] : [];
    },
  },
  {
    id: "agentes", path: "/agents", target: "agents-kpis",
    kicker: "Agente colega · chama outros agentes", title: "Uma equipe de agentes, cada um com o seu papel",
    text: "Supervisor, Monitor, Investigação, Resolução, Validação e Atendimento trabalham com estado controlado e permissões mínimas. A maior parte das decisões é regra e estatística; a IA entra onde ajuda, com custo registrado.",
    live: async () => {
      const res = await api.get<any[]>("/agents");
      const r: any = (res.meta as any)?.routing;
      return r ? [
        { label: "Resolvido sem LLM", value: fmt.pct(r.pct_without_llm), hint: "regras e estatística" },
        { label: "Custo de IA", value: `US$ ${fmt.num(r.cost_usd, 4)}`, hint: `${fmt.num(r.llm_calls)} chamadas` },
      ] : [];
    },
  },
  {
    id: "como-decide", path: "/agents/support", target: "agent-decides", tab: "decides",
    kicker: "Transparência", title: "Como o agente decide, sem caixa-preta",
    text: "Regras, fórmulas e os parâmetros em vigor lidos da configuração, quando passa para uma pessoa e as decisões recentes reais, com os números e os motivos.",
  },
  {
    id: "instrucoes", path: "/agents/support", target: "agent-instructions", tab: "instructions",
    kicker: "Adaptabilidade", title: "O time ajusta a IA sem mexer em código",
    text: "Cada tarefa de IA tem uma instrução editável e regras fixas que não mudam. Editar cria um rascunho; nada vai ao ar sem testar, comparar e publicar — com histórico e restauração.",
    bullets: ["O teste mostra o prompt exato e verifica números fora das evidências", "A matriz automático × pessoa também é configurável (Configurações › Atendimento)"],
  },
  {
    id: "validacao", path: "/agents/validacao", target: "validation-kpis",
    kicker: "Modelagem · a IA foi verificada", title: "O que a tela diz é o que o código faz",
    text: "A validação ponta a ponta gera dados num ambiente isolado — inclusive casos-limite como tentativa de manipulação e foto anterior à entrega — executa os agentes e recalcula cada decisão de forma independente.",
    live: async () => {
      const r: any = await data("/agents/validation");
      return r?.summary ? [{ label: "Verificações aprovadas", value: `${r.summary.passed}/${r.summary.cases}`, hint: r.summary.failed ? `${r.summary.failed} reprovada(s)` : "todas aprovadas" }] : [];
    },
    say: "Isto roda pela tela, pelo terminal e na suíte de testes: é como provamos que verificamos e corrigimos o que a IA construiu.",
  },
  {
    id: "fechamento", path: "/atendimento", placement: "center",
    kicker: "Pense 360°, prove em uma frente", title: "Provamos o atendimento. O mesmo colega cobre a área toda.",
    text: "Logística, pós-venda, prevenção, estoque, reputação e gestão usam o mesmo motor de políticas, aprovações e canal do time. Integrar canais reais troca só os conectores.",
    bullets: [
      "Ações críticas sempre com uma pessoa",
      "Tudo auditado: motivos de cada decisão e quem aprovou",
      "Próximo passo: piloto com um grupo do atendimento e canais reais",
    ],
    say: "Dados sintéticos e execução simulada nesta versão; o desenho já está pronto para os sistemas reais.",
  },
];
