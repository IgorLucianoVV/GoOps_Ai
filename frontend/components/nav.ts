import { Activity, Blocks, Bot, Headphones, MessagesSquare, Newspaper, Database, LayoutDashboard, LineChart, Scale, Settings, ShieldCheck, Siren, Sparkles, Workflow } from "lucide-react";

export type NavItem = { href: string; label: string; hint?: string };
export type NavSection = { label: string; icon: any; href?: string; hint?: string; items?: NavItem[] };

/** Arquitetura de informação única, usada pela barra lateral, breadcrumbs e paleta de comandos (consistência — H4). */
export const NAV: NavSection[] = [
  { label: "Visão geral", icon: LayoutDashboard, href: "/", hint: "Visão executiva da operação" },
  { label: "Briefing diário", icon: Newspaper, href: "/briefing", hint: "Resumo do dia e decisões pendentes" },
  { label: "Pergunte ao GoOps", icon: Sparkles, href: "/ask", hint: "Perguntas em linguagem natural com métricas oficiais" },
  { label: "Canal do time", icon: MessagesSquare, href: "/canal", hint: "Onde os agentes avisam, pedem aprovação e recebem pedidos (app, Telegram ou Slack)" },
  { label: "Atendimento", icon: Headphones, items: [
    { href: "/atendimento", label: "Visão do atendimento", hint: "Volume, automação, veracidade, recontato e esforço poupado" },
    { href: "/atendimento/caixa", label: "Caixa unificada", hint: "WhatsApp, e-mail e Reclame Aqui triados pelo agente" },
    { href: "/atendimento/prevencao", label: "Prevenção de recontato", hint: "Causas, contatos evitáveis e aviso proativo" },
  ] },
  { label: "Setores", icon: Blocks, items: [
    { href: "/setores", label: "Todos os setores", hint: "Painéis, métricas e agentes por setor" },
    { href: "/setores/novo", label: "Novo setor / conjunto", hint: "Conectar API, escolher campos e gerar painel" },
  ] },
  { label: "Análises", icon: LineChart, items: [
    { href: "/analytics/nps", label: "NPS", hint: "Painel de NPS com filtros" },
    { href: "/analytics/cx", label: "Experiência do cliente", hint: "Fatores de detração e clientes" },
    { href: "/analytics/logistics", label: "Logística", hint: "Prazos, transportadoras e risco" },
    { href: "/analytics/products", label: "Produtos", hint: "Desempenho e reclamações por produto" },
    { href: "/analytics/regional", label: "Desempenho regional", hint: "Indicadores por UF" },
  ] },
  { label: "Incidentes", icon: Siren, href: "/incidents", hint: "Incidentes detectados e investigações" },
  { label: "Operações", icon: Activity, href: "/operations", hint: "Ações e aprovações pendentes" },
  { label: "Agentes de IA", icon: Bot, href: "/agents", hint: "Agentes, custos e roteamento" },
  { label: "Fluxos de trabalho", icon: Workflow, href: "/workflows", hint: "Execuções do Supervisor" },
  { label: "Lakehouse de dados", icon: Database, items: [
    { href: "/lakehouse", label: "Camadas", hint: "Bronze → Silver → Gold" },
    { href: "/lakehouse/sources", label: "Fontes", hint: "Fontes e conectores" },
    { href: "/lakehouse/mappings", label: "Mapeamentos", hint: "De onde vem cada campo quando a API muda" },
    { href: "/lakehouse/ingestion", label: "Ingestão", hint: "Histórico de ingestão" },
    { href: "/lakehouse/layer/bronze", label: "Bronze" },
    { href: "/lakehouse/layer/silver", label: "Silver" },
    { href: "/lakehouse/layer/gold_corporate", label: "Gold corporativa" },
    { href: "/lakehouse/layer/gold_domain", label: "Gold de domínio" },
    { href: "/lakehouse/quality", label: "Qualidade de dados", hint: "Regras e quarentena" },
    { href: "/lakehouse/lineage", label: "Linhagem de dados", hint: "Origem de cada indicador" },
    { href: "/lakehouse/dictionary", label: "Dicionário de dados", hint: "Campos e definições" },
  ] },
  { label: "Governança semântica", icon: Scale, items: [
    { href: "/semantic?scope=corporate", label: "Métricas corporativas" },
    { href: "/semantic?scope=domain", label: "Métricas de domínio" },
    { href: "/semantic", label: "Catálogo de métricas", hint: "Catálogo de métricas" },
    { href: "/semantic/approvals", label: "Aprovações", hint: "Versões pendentes" },
    { href: "/semantic/audit", label: "Auditoria" },
  ] },
  { label: "Auditoria", icon: ShieldCheck, href: "/audit", hint: "Trilha de auditoria" },
  { label: "Configurações", icon: Settings, href: "/settings", hint: "Modelos, chaves, usuários e políticas" },
];

export function flatNav(): (NavItem & { section: string })[] {
  return NAV.flatMap((s) => (s.href ? [{ href: s.href, label: s.label, hint: s.hint, section: s.label }]
    : (s.items || []).map((i) => ({ ...i, section: s.label }))));
}

export function breadcrumbFor(pathname: string): { section?: string; page?: string } {
  const all = flatNav().filter((i) => !i.href.includes("?"));
  const match = all.filter((i) => (i.href === "/" ? pathname === "/" : pathname === i.href || pathname.startsWith(i.href + "/")))
    .sort((a, b) => b.href.length - a.href.length)[0];
  if (!match) return {};
  return match.section === match.label ? { section: match.label } : { section: match.section, page: match.label };
}
