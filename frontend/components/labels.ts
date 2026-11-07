export const STATUS_LABEL: Record<string, string> = {
  detected: "Detectado", investigating: "Em investigação", awaiting_approval: "Aguardando aprovação",
  executing: "Em execução", resolved: "Resolvido", reopened: "Reaberto", closed: "Encerrado",
  proposed: "Proposta", pending_approval: "Aguardando aprovação", approved: "Aprovada", rejected: "Rejeitada",
  executed: "Executada (simulada)", failed: "Falhou", success: "Sucesso", partial: "Parcial", running: "Em execução",
  waiting: "Aguardando humano", completed: "Concluído", active: "Ativa", pending: "Pendente", superseded: "Substituída",
  passed: "OK", warning: "Alerta", info: "Info", monitoring: "Monitorando", not_resolved: "Não resolvido",
  idle: "Ocioso", never_run: "Nunca executado",
};
export const SEVERITY_LABEL: Record<string, string> = { low: "Baixa", medium: "Média", high: "Alta", critical: "Crítica" };
export const CATEGORY_LABEL: Record<string, string> = {
  orders: "Pedidos", payments: "Pagamentos", inventory: "Estoque", logistics: "Logística",
  customer_service: "Atendimento", customer_experience: "Experiência do cliente", products: "Produtos",
  reputation: "Reputação", other: "Outros",
};
export const DIM_LABEL: Record<string, string> = {
  state: "UF", carrier: "Transportadora", product_line: "Linha de produto", shipping_type: "Tipo de frete",
};
export const fmt = {
  num: (v: any, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v: any, d = 1) => (v === null || v === undefined ? "—" : `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: d, minimumFractionDigits: d })}%`),
  date: (v: any) => (v ? new Date(v).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—"),
  day: (v: any) => (v ? new Date(v).toLocaleDateString("pt-BR") : "—"),
};
export const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador", data_owner: "Responsável pelos dados", data_steward: "Curador de dados",
  domain_owner: "Responsável pelo domínio", data_analyst: "Analista de dados", support_agent: "Atendente", viewer: "Leitor", ai_agent: "Agente de IA",
};
export const DOMAIN_LABEL: Record<string, string> = { corporate: "Corporativo", cx: "Experiência do cliente", logistics: "Logística", products: "Produtos", atendimento: "Atendimento" };
export const ENTITY_LABEL: Record<string, string> = {
  incident: "Incidente", operation: "Operação", support_contact: "Contato de atendimento", metric: "Métrica", source: "Fonte", pipeline: "Pipeline", user: "Usuário", platform: "Plataforma",
};
export const FIELD_TYPE_LABEL: Record<string, string> = {
  id: "Identificador (texto)", id_int: "Identificador (número)", string: "Texto", upper: "Texto em maiúsculas", uf: "UF",
  int: "Número inteiro", float: "Número decimal", datetime: "Data e hora",
};
export const ENTITY_SOURCE_LABEL: Record<string, string> = { orders: "Pedidos", nps: "Avaliações/NPS", deliveries: "Entregas" };
export const SCOPE_LABEL: Record<string, string> = { corporate: "corporativo", domain: "de domínio" };
/** "deterministic" | "llm:<modelo>" → rótulo em português. */
export const generatedByLabel = (v?: string) => (!v ? "" : v === "deterministic" ? "determinístico" : v.startsWith("llm:") ? `IA · ${v.slice(4)}` : v);
