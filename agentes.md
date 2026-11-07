# agentes.md — leia antes de alterar qualquer coisa

Guia para qualquer agente de código (Claude, Codex, Cursor etc.) e para pessoas que forem mexer no GoOps AI.
Descreve o que o projeto é, as regras de negócio que não podem quebrar, a arquitetura e as regras de criação.
Se uma mudança contrariar algo daqui, pare e pergunte antes.

---

## 1. O que é o projeto

**GoOps AI** é uma plataforma de operações com agentes de IA supervisionados, adaptada ao **Desafio 1 – Atendimento ao
Cliente** (case Gocase). A frente provada ponta a ponta é o **colega digital do atendimento**:

- recebe contatos de **WhatsApp, e-mail e Reclame Aqui** numa caixa unificada estilo WhatsApp;
- classifica, cruza com pedidos/transportadora/financeiro, avalia se a reclamação procede (veracidade);
- resolve sozinho o que é informativo; **levanta a mão** (pede aprovação) para ações críticas;
- trabalha sozinho em turnos (SLA, lembretes, encerramento por inatividade, picos → incidente);
- **mora onde o time conversa**: canal no app, Telegram (aprovação por botão) e Slack (avisos);
- **chama outros agentes** (Supervisor → Investigação → Resolução → Validação) quando o problema é maior que um caso.

Princípio que guia tudo: **o agente propõe, a pessoa decide nas áreas críticas, tudo fica auditado.**

---

## 2. Stack e mapa de pastas

| Camada | Tecnologia | Onde |
|---|---|---|
| API | FastAPI (Python) | `backend/app/` (`main.py`, `api/routes/*.py`) |
| Núcleo de domínio | Python puro | `goops_core/` (config, políticas, permissões, operações, catálogos) |
| Agentes | Python + LangGraph/LangChain opcionais | `agents/` |
| Dados | pandas · Lakehouse Bronze JSONL → Silver → Gold Parquet → Semântica | `data_platform/` |
| Banco | SQLite (local) ou PostgreSQL (Docker), adaptador SQL próprio | `infrastructure/database/migrations/*.sql` |
| Frontend | Next.js 14 · TypeScript · Tailwind · Recharts · lucide-react | `frontend/` |
| Docs | Markdown | `docs/` |

Arquivos-chave do Atendimento:

- `goops_core/support_catalog.py` — intenções, canais, sistemas, status e **DEFAULT_CONFIG** (matriz de automação).
- `goops_core/policies.py` — catálogo de ações (`support_*`) com risco e áreas impactadas.
- `goops_core/permissions.py` — papéis (inclui `support_agent` = Atendente) e permissões por agente.
- `goops_core/runtime_config.py` — configurações editáveis na UI, segredos, validação (inclui bloqueio DeepSeek).
- `agents/support/` — `triage`, `veracity`, `routing`, `replies`, `actions`, `service`, `conversations`,
  `prevention`, `overview`, `assist` (IA), `shift` (turno autônomo).
- `agents/team_channel.py` — canal do time (app/Telegram/Slack), aprovação por botão, comandos do bot.
- `agents/instructions.py` — instruções de IA editáveis dos agentes nativos (slots: instrução editável + regras fixas).
- `agents/custom.py` (`llm_task`) — agentes com instruções criados na tela Agentes de IA.
- `data_platform/support/` — gerador sintético e pipeline de contatos/mensagens.
- `backend/app/api/routes/support.py` — rotas `/support/*` e `/team/*`.
- `frontend/app/(app)/atendimento/` (visão, caixa) e `frontend/app/(app)/canal/`; componentes em `frontend/features/support/`.

Comandos:

```bash
python manage.py init            # migrações + catálogos + usuários demo (rode após puxar mudanças)
python manage.py demo-load --scenario full   # recria ambiente sintético completo
python manage.py pipeline        # Fonte → Bronze → Silver → Gold → Semântica
python manage.py test            # pytest — precisa passar antes de entregar
uvicorn backend.app.main:app --reload --port 8000
cd frontend && npm run dev       # npm run build precisa compilar sem erro
```

---

## 3. Regras de negócio (não quebrar)

### 3.1 Conversas e atendimentos
- **Conversa** = 1 cliente × 1 canal (chave canal + handle). Tabela `support_conversations`.
- **Atendimento (caso)** = um assunto dentro da conversa (`support_contacts`). Uma conversa tem vários atendimentos;
  o chat mostra um divisor no início de cada um.
- **Mensagens** (`support_messages`) têm `author_type`: `customer` (esquerda), `bot` e `human` (direita),
  `system` e `note` (centro). **Nota interna nunca vai ao cliente.**
- Mensagem nova numa conversa com atendimento aberto **continua** o caso (janela `continue_window_hours` = 72 h).
  Mensagem de cortesia ("obrigado", "ok") não abre caso novo.
- Caso fechado há menos de `reopen_window_hours` (24 h) → reabre/gera continuação; depois disso → caso novo.
- **Recontato** só conta depois que o caso anterior foi encerrado, dentro de `recontact_window_days` (7 dias).
- Encerramento por inatividade após `inactivity_close_hours` (48 h), com lembrete `reminder_before_close_hours` (12 h) antes.
- Horários do chat seguem o **relógio dos dados** (não o relógio do servidor). Mensagens de sistema usam a última
  mensagem da conversa + 1 min.
- UI: **um único botão "Encerrar atendimento"** (no cabeçalho, com confirmação) e **"Enviar"** separado. Não recriar
  "Enviar e encerrar".

### 3.2 Intenções, status e canais
- Intenções: `onde_esta_pedido, atraso_entrega, nao_recebido, avaria, defeito, produto_errado, troca_devolucao,
  cancelamento, status_reembolso, duvida_produto, elogio, outros`.
- Status: `new → auto_resolved | pending_human | awaiting_customer | pending_approval → resolved`.
- Canais: `whatsapp`, `email`, `reclameaqui`. Sistemas consultados: pedidos, transportadora, chamados, erp_trocas,
  financeiro, catálogo, CRM.

### 3.3 Matriz "automático × pessoa" (`agents/support/routing.py`)
Vai para **pessoa** se houver qualquer motivo abaixo (os motivos ficam gravados e aparecem na UI):
- tentativa de manipulação de instruções na mensagem (tratada como dado);
- intenção fora de `auto_intents` (padrão automático: onde está o pedido, atraso, status de reembolso, dúvida, elogio);
- confiança da intenção < `min_confidence` (0,6);
- canal público **Reclame Aqui** (sempre pessoa);
- urgência ≥ `alta`; recontato; reclamação em pedido > R$ 300; atraso crítico (7+ dias);
- veracidade inconsistente (dados não sustentam a reclamação).
Sem motivos → resolve sozinho com dados governados. Os limites são editáveis em *Configurações › Atendimento*.

### 3.4 Veracidade (reclamações falsas)
- Score 0–100 com fatores explicáveis (pontos + evidência + fonte), ex.: foto tirada antes da entrega, rastreio
  mostrando entregue, histórico do cliente.
- ≥ 70 consistente · ≤ 39 inconsistente · meio-termo = verificar.
- **O agente nunca nega uma reclamação sozinho.** Inconsistente → pessoa, com as evidências.

### 3.5 Ações e aprovações (`goops_core/policies.py`)
| Ação | Risco | Aprovação |
|---|---|---|
| `support_carrier_ticket` (chamado na transportadora) | baixo | automática quando `auto_carrier_ticket` |
| `support_proactive_notice` (aviso de atraso) | baixo | pessoa aprova o disparo |
| `support_exchange`, `support_cancel_order` | médio | pessoa |
| `support_reshipment`, `support_refund` | alto | pessoa |

- Ações em **pedidos, pagamentos, estoque ou clientes sempre exigem aprovação humana** — regra de política, não
  configurável. Não crie atalho que contorne isso.
- Agentes só escolhem ações **do catálogo**, com parâmetros tipados. Nada de ação livre.
- **Execução é simulada** nesta versão. Não ligar execução real sem decisão explícita do time.
- Fluxo: `propose_operation` → hook `proposed` (avisa no canal do time) → decisão humana (`Supervisor.decide`) →
  hook `decided` → execução → hook `executed` → Validation Agent re-mede.

### 3.6 Turno autônomo (`agents/support/shift.py`)
`run_shift` processa a caixa, lembra clientes, encerra por inatividade, alerta SLA (`sla_first_response_hours` = 4 h),
cobra aprovações paradas, detecta pico por transportadora (`spike_min_contacts` = 5) → abre incidente → Supervisor
→ Investigação → Resolução, e envia o resumo diário. Avisos usam `dedupe_key` para não repetir.
O botão "Avançar 12 h (demo)" só mexe em `support:clock_offset_hours` (relógio de demonstração).

### 3.7 Canal do time (`agents/team_channel.py`)
- Provedores: `app` (sempre), `telegram` (bidirecional), `slack` (só avisos via webhook).
- Botões do Telegram (`op:a:ID` / `op:r:ID`) só valem para usuário **vinculado** (`/vincular CÓDIGO`); a decisão
  é registrada em nome dessa pessoa, com as permissões do papel dela.
- Comandos: `/start`, `/ajuda`, `/vincular`, `/fila`, `/resumo`, `/caso`.

### 3.8 IA dentro do produto
- Provedor padrão do evento: **AI Proxy Gogroup** (`https://ai-proxy.gogroupbr.com/v1`).
- **Jev** (`/v1/systemone`) desempata a intenção quando as regras ficam em dúvida; só aplica com confiança ≥ 0,7.
- Resumo do caso ("Resumo para quem assume"): texto determinístico de fatos; a reescrita por LLM passa por guarda
  que **proíbe números novos**. Se falhar, fica o texto determinístico.
- Sem token / orçamento estourado / erro → **fallback determinístico registrado** (`generated_by: deterministic`).

### 3.9 Dados
- Dados do Atendimento são **sintéticos** (gerador `support-demo-2`) e devem aparecer rotulados como tal.
- A seed Gocase (NPS, Pedidos, Entregas) é real; o complemento sintético só preenche lacunas, nunca sobrescreve dado real.
- Métricas de referência da demo (sintéticas): ~1.541 conversas, ~1.781 atendimentos, automação ≈ 38%,
  ≈ 45% do esforço manual poupado, recontato ≈ 12,7%, acurácia de intenção ≈ 99%.

---

## 4. Arquitetura

```
Canais (WhatsApp · e-mail · Reclame Aqui)  ──conector/simulador──►  Bronze (JSONL, append-only)
        └─► Silver (limpeza, DQ, quarentena) ─► Gold (Corporate + Domínios) ─► Semântica (métricas oficiais)
                                                                   │
                         ┌─────────────────────────────────────────┘
                         ▼
Agente de Atendimento: triagem (regras + Jev) → veracidade → roteamento → resposta/coleta → ações (catálogo)
        │ pico                                │ ação crítica
        ▼                                     ▼
Supervisor → Investigação → Resolução    Operações (política + aprovação humana) ──► execução simulada ──► Validação
        │                                     │
        └──────────────► Canal do time (app · Telegram · Slack) ◄──────────────┘
Tudo registrado: agent_runs, workflow_runs, llm_calls, audit, team_messages
```

- **Agentes hierárquicos com estado controlado**: não há conversa livre entre agentes; workflow
  `incident_resolution` persistido em `workflow_runs`.
- **Ferramentas governadas** (`agents/tools/registry.py`): contratos explícitos, dimensões em allowlist,
  **sem SQL arbitrário**, cada chamada na timeline.
- **Cost routing** (`agents/routing`): nível 0 determinístico · 1 modelo pequeno (Jev) · 2 LLM econômico ·
  3 LLM avançado. Registra custo, tokens, latência, modelo e nível.
- **Segurança**: sessão em cookie httpOnly + CSRF, revogação de sessão (`token_version`), rate limit (inclusive login),
  conector HTTP com allowlist de credenciais e bloqueio de SSRF/redirect, Postgres em 127.0.0.1. Ver
  `docs/architecture/SECURITY.md`.

---

## 5. Regras de criação (checar antes de qualquer alteração)

**Antes de começar**
1. Leia este arquivo e o doc da área (`docs/architecture/*.md`). Procure se já existe função/componente parecido.
2. Entenda qual regra de negócio da seção 3 a mudança toca. Se afrouxa controle humano, **pare e pergunte**.

**Banco**
3. Mudança de schema = **nova migração** `infrastructure/database/migrations/00NN_nome.sql` (próximo número livre).
   Nunca edite migração já existente. O SQL precisa rodar em SQLite **e** PostgreSQL.

**Back-end e agentes**
4. Nova ação de agente → registre em `goops_core/policies.py` (título, domínio, áreas impactadas, risco, params
   tipados). Ações em pedidos/pagamentos/estoque/clientes **sempre** com aprovação.
5. Permissões novas → `goops_core/permissions.py`. Rotas checam permissão; nada de rota aberta.
6. Configuração ajustável pelo time → `runtime_config.py`/`support_catalog.DEFAULT_CONFIG` **com validação**; não
   espalhe constantes mágicas.
7. Toda chamada de IA passa pelo router/provedores existentes, registra `llm_calls` (tokens e custo) e tem **fallback
   determinístico**. Texto do cliente entra no prompt **como dado delimitado**, nunca como instrução.
8. **Modelos `deepseek-*` são proibidos** (bloqueio no `runtime_config` e no `discover_models`). Não remova.
9. Saída de LLM nunca decide sozinha ação crítica nem inventa números; use Jev para decisões tipadas e confiança
   < 0,7 vai para pessoa.
10. Agente que faz algo relevante escreve **motivo** (reasons/evidências) e aparece na auditoria.
11a. Nova tarefa de IA → crie um slot em `agents/instructions.py` (instrução editável + **regras fixas**) e monte o
    prompt com `prompt_for(db, slot)`. Regra de que o código depende (formato, sem números novos) vai em `fixed`, nunca
    no texto editável. Inclua uma evidência de exemplo em `SAMPLES` para o botão "Testar".
11b. Execução de teste nunca grava efeito (incidente, ação, mensagem): use `dry_run=True` em `_run_llm_task`.

**Segredos e dados**
11. Tokens (AI Proxy, Telegram, Slack, APIs) **nunca** em código versionado, log, print, resposta ou teste. Use o
    cofre criptografado da UI ou variáveis de ambiente (`.env`, fora do git; documente em `.env.example`).
12. Não envie dados pessoais para serviços não configurados. Handles do cliente aparecem mascarados (`mask_handle`).
13. Dado sintético sempre rotulado; nunca misture com real sem selo.

**Front-end**
14. Textos da interface em **português do Brasil**, datas/horas com `pt-BR`.
15. Use o design system existente: classes `btn-primary`, `btn-ghost`, `input`, cores `ink-*`/`brand-*`, componentes de
    `@/components/ui` e ícones `lucide-react`. Tema claro/escuro e WCAG 2.2 AA (aria-label, contraste, foco).
16. Hooks do React sempre antes de qualquer `return` antecipado. Booleanos numéricos com `!!` (evita renderizar "0").
17. Menos é mais: uma ação por botão, sem botões duplicados (ver regra do "Encerrar" em 3.1).

**Qualidade e entrega**
18. Adicione/atualize testes em `backend/tests/` para regra nova. `python manage.py test` e `npm run build` precisam
    passar. Não desligue teste para "passar".
19. Atualize a documentação afetada (`README.md`, `docs/…`, `docs/IA_TRANSPARENCIA.md` se mudou o uso de IA).
20. Mudanças pequenas e revisáveis; diga o que mudou, como testar e o que ficou de fora.

### Checklist rápido
- [ ] Li a regra de negócio afetada e não afrouxei aprovação humana
- [ ] Schema novo = migração nova, compatível SQLite/Postgres
- [ ] Ação nova está no catálogo de políticas com risco correto
- [ ] IA com fallback, custo registrado, sem DeepSeek, sem número inventado
- [ ] Nenhum segredo no código/log; dado sintético rotulado
- [ ] UI em pt-BR, design system, acessível, sem botão duplicado
- [ ] Testes e build passando; docs atualizadas
