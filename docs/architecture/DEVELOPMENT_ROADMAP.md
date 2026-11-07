# Roadmap

| Fase | Entrega | Status |
|---|---|---|
| 1 Fundação | Estrutura, Docker Compose, banco + migrações, API, frontend, auth, demo | ✅ implementado |
| 2 Lakehouse | Conectores, Bronze, Silver, Corporate/Domain Gold, DQ, quarentena, histórico | ✅ implementado |
| 3 Governança | Dictionary, Metric Registry corporativo/domínio, versionamento, aprovações, lineage, auditoria | ✅ implementado |
| 4 Analytics | Módulo NPS (11 indicadores, filtros, Pearson/Spearman, NLP), CX, Logística, Produtos, Regional | ✅ implementado |
| 5 Agentes | Supervisor, Monitor, Investigation, Resolution, Validation, Cost Routing | ✅ implementado (núcleo determinístico; LLM opcional) |
| 6 Operações | Incidentes, recomendações, aprovações, execução simulada, validação, histórico | ✅ implementado |

## v2 (implementado)
Configuração em tela (modelos, chaves cifradas, preços, limites, monitor, agendador, retenção, políticas), agendador com lease,
retenção sem perda de dados, gestão de usuários/domínios/fontes, cookie httpOnly + CSRF, rate limit compartilhado,
uso real dos níveis 1 e 2 do Cost Routing, exclusão de conteúdo com prompt injection dos prompts, testes HTTP (TestClient),
responsividade (menu móvel) e melhorias de acessibilidade (skip link, ARIA, foco visível, reduced motion).

## Pendências conhecidas
- Contratos reais das APIs (Pedidos, NPS, Entregas) — conectores e mapeamentos aguardam documentação.
- Execução real de ações (integração com sistemas de pedidos/clientes) — apenas modo simulado.
- Orquestração Dagster, Iceberg/Delta, Polars, SQLAlchemy, LangGraph, RAG e MCP — decisões registradas em DECISIONS.md;
  não adotados por exigirem dependências que não puderam ser instaladas/testadas neste ciclo.
- SSO/OIDC; papéis com permissões customizáveis (hoje os papéis são fixos e atribuídos por usuário/domínio).
- Validação pós-ação depende de novos dados reais após a execução.
- Auditoria de acessibilidade com leitor de tela e testes E2E do frontend (Playwright).
