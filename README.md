# GoOps AI

**Autonomous Business Operations / AI-Powered Data Intelligence Platform**

GoOps AI conecta fontes empresariais, organiza os dados em um **Data Lakehouse governado** (Bronze → Silver → Gold Corporate + Domain → Semântica), padroniza indicadores num **catálogo semântico híbrido** e usa **agentes de IA supervisionados** para detectar anomalias, investigar causas com evidências, recomendar ações e — com aprovação humana — executá-las (nesta versão, em modo **simulado**).

> **Seed padrão: planilhas reais do case Gocase** (`data/seed/gocase/` — NPS, Pedidos e Entregas), carregadas pelo conector
> `file` com o perfil de mapeamento `gocase_xlsx`. Resultado de referência: **NPS 87,52** (8.869 avaliações; 8.111 promotores,
> 409 neutros, 349 detratores). Também há cenários **sintéticos** (`full`, com anomalias e um incidente encenado, e `basic10`),
> marcados como demonstração. Os contratos das APIs reais ainda não foram confirmados; os conectores HTTP são configuráveis.

## Início rápido

### Opção A — Docker (PostgreSQL + API + Frontend)
```bash
cp .env.example .env          # defina SECRET_KEY, POSTGRES_PASSWORD e DEMO_ADMIN_PASSWORD
docker compose up --build
```
- Frontend: http://localhost:3000 · API: http://localhost:8000/api · OpenAPI: http://localhost:8000/api/docs
- Na primeira inicialização (DEMO_MODE=true), a demo é carregada automaticamente.
- Login: `admin@goops.local` com a senha definida em `DEMO_ADMIN_PASSWORD`.
- A sessão usa cookie httpOnly + CSRF: sirva frontend e API no mesmo site (ex.: `localhost`, ou atrás do mesmo domínio via proxy reverso).

### Opção B — Local (Windows/Linux, SQLite)
```bash
python -m venv .venv && .venv\Scripts\activate        # Linux: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
copy .env.example .env                                  # Linux: cp; defina DEMO_ADMIN_PASSWORD
python manage.py init
python manage.py demo-load --scenario full
uvicorn backend.app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```
Scripts prontos: `infrastructure/scripts/dev.ps1` (Windows) e `dev.sh`.

### Comandos
| Comando | O que faz |
|---|---|
| `python manage.py init` | Migrações, catálogos (domínios, regras DQ, métricas) e usuários demo |
| `python manage.py demo-load [--scenario gocase\|full\|basic10]` | Recria o ambiente (padrão: planilhas Gocase) e roda o pipeline |
| `python manage.py pipeline [--no-sync]` | Fonte → Bronze → Silver → Gold → Semântica |
| `python manage.py monitor` | Ciclo do Supervisor: Monitor Agent + workflows de investigação |
| `python manage.py test` | Testes (pytest; sem pytest usa o executor stdlib) |

### Usuários de demonstração
`admin@`, `owner@` (Data Owner), `steward@`, `cx.owner@` (Domain Owner CX), `logistics.owner@` (Domain Owner Logística), `analyst@`, `viewer@` — todos `@goops.local`, mesma senha de demonstração.

## Seed Gocase — o que observar
- As planilhas não trazem datas de envio/previsão/entrega (só "Dias de entrega") nem pedidos em aberto. Para a visão
  completa, a seed inclui um **complemento sintético** (fontes `gocase_complemento_datas_entrega`,
  `gocase_demo_pedidos_transito`, `gocase_demo_entregas_transito`, todas `is_demo`):
  - datas de envio/previsão/entrega derivadas da data real do pedido + produção simulada + "Dias de entrega" real
    (prazo de transporte) + SLA prometido simulado por tipo de frete e região (origem assumida: Fortaleza/CE);
  - 120 pedidos fictícios em trânsito (`DEMO-…`) para o risco de atraso.
  O complemento **só preenche lacunas** (nunca sobrescreve dado real) e tudo que depende dele aparece com o selo
  **sintético** (métricas, gráficos, datasets e respostas do assistente). O **prazo envio→entrega** (6,1 dias) usa os dias
  reais da planilha. Para ver só os dados reais, desative as três fontes em *Lakehouse › Fontes* e execute o pipeline.
- O cliente do pedido (`customer_id`) é derivado da avaliação NPS do mesmo pedido (dado real).
- Pedidos vêm por item (22.074 itens → 8.642 pedidos); a linha de produto do pedido é a do item de maior valor.
- Com os limiares padrão o Monitor **não** abre incidentes (as variações mensais são pequenas e não significativas).
  Para ver o fluxo dos agentes nestes dados, reduza "Queda de NPS" para 2 pontos em *Configurações › Monitor* — a investigação
  mostrará hipóteses com z-score indicando que a diferença **não é estatisticamente significativa**.
- Para a demonstração completa (incidente, aprovações, execução), use `demo-load --scenario full` (dados sintéticos).

## Roteiro de demonstração (critérios de aceite)
1. **Integração** — *Data Lakehouse › Sources / Ingestion*: três fontes demo, execuções Bronze append-only.
2. **Transformação** — *Silver* e *Data Quality*: regras, duplicidades, órfãos e quarentena.
3. **Gold híbrida** — *Corporate Gold* e *Domain Gold* (CX, Logística, Produtos).
4. **Governança semântica** — *Semantic Governance*: `METRIC_NPS_001` oficial; métricas de domínio identificadas como não equivalentes.
5. **Dashboard** — *Analytics › NPS* com filtros (período, UF, linha, transportadora, frete).
6. **Lineage** — *Data Lineage*: selecione `metric:METRIC_NPS_001` → origem até as fontes.
7. **Investigação por IA** — no cenário sintético `full`, Visão geral › *Executar ciclo de monitoramento*: a queda de NPS em jun/2026 é detectada e investigada (hipótese: transportadora DeltaFrete, z = −7,4, com evidências e limitações).
8. **Recomendação e validação** — *Operations*: aprove com `logistics.owner@` (realocação) e `cx.owner@` (contato); a execução simulada roda e o Validation Agent verifica.
9. **Auditoria** — timeline do incidente, *Audit*, histórico de agentes e transformações.

## Interface
Design system com tema claro/escuro, superfícies neutras e acentos inspirados nas cores públicas da Gocase (azul `#005BAA` para ação; coral `#F37053` e primrose `#E9ED9A` como acentos), heurísticas de Nielsen e WCAG 2.2 AA aplicadas — ver `docs/architecture/DESIGN_SYSTEM.md`. Atalho **Ctrl/⌘ + K** abre a busca de páginas e ações.

## Documentação
`docs/architecture/` (ARCHITECTURE, DESIGN_SYSTEM, DATA_MODEL, DATA_GOVERNANCE, DATA_LINEAGE, AGENTS, SECURITY, DEVELOPMENT_ROADMAP), `docs/metrics/SEMANTIC_LAYER.md`, `docs/api/API_DOCUMENTATION.md`, `docs/decisions/DECISIONS.md`.

## IA na demo (Claude) e “Pergunte ao GoOps”
1. *Configurações › Modelos e chaves* → **Usar Claude (Anthropic)** (preenche Haiku nos níveis 1–2 e Sonnet no nível 3),
   cole a chave Anthropic, **Salvar modelos** → **Testar conexão**. Opcional: preços por milhão de tokens para ver o custo.
2. **Pergunte ao GoOps** (menu ou botão “Perguntar” no topo): ex. “Por que o NPS de Copos é menor?”. O modelo só consulta
   ferramentas governadas (métricas oficiais, temas de comentários, incidentes) com as permissões de quem pergunta; a
   resposta mostra o selo “Gerado por LLM”, as métricas citadas (chave/versão, recorte, n) e as consultas executadas.
   Sem modelo, um motor determinístico responde com os mesmos dados (selo “Resposta determinística”).
3. Narrativas de investigação, planos de resolução e o resumo executivo dos incidentes passam a ser escritos pelo modelo
   (selo na timeline e no resumo); os números continuam vindo do núcleo determinístico.

### Escolher provedor e modelo (LangGraph)
O “Pergunte ao GoOps” roda como um grafo **LangGraph** (`agente → ferramentas → agente`, até 6 passos) sobre modelos
**LangChain** de vários provedores: **Anthropic (Claude), OpenAI, Google Gemini, Ollama (local, sem chave)** e qualquer
endpoint **OpenAI-compatível**.
1. `pip install -r backend/requirements.txt` (instala `langgraph` e os pacotes `langchain-*` de cada provedor).
2. *Configurações › Modelos e chaves* → cole as chaves dos provedores desejados (ou a URL do Ollama) e, em
   **Provedores e modelos do “Pergunte ao GoOps”**, clique em **Adicionar modelo**, escolha o provedor e selecione o modelo
   na lista daquele provedor (“Atualizar do provedor” busca os modelos que a sua chave enxerga; “Outro…” aceita um id livre)
   → **Salvar modelos**. Os níveis de custo usam a mesma lista de seleção.
   A tabela mostra para cada provedor se o pacote está instalado e se há credencial.
3. Na tela **Pergunte ao GoOps**, escolha o modelo no seletor “Modelo”; cada resposta mostra provedor, modelo e motor
   (LangGraph ou loop nativo). Sem os pacotes, Anthropic/OpenAI-compatível seguem pelo loop nativo e os demais aparecem
   como indisponíveis; sem modelo algum, responde o motor determinístico.

## Atendimento ao Cliente (Desafio 1)
> **Visão 360° do colega digital:** `docs/architecture/COLEGA_DIGITAL.md` · **Transparência sobre IA:**
> `docs/IA_TRANSPARENCIA.md` · **Roteiro de demo (3 min):** `docs/pitch/ROTEIRO_DEMO.md`

**O agente como colega de trabalho:**

- **Turno autônomo** (agendador ou botão): processa a caixa, lembra e encerra por inatividade, alerta SLA, cobra
  aprovações e manda o resumo do dia.
- **Canal do time** (mural no app + **Telegram real** com aprovação por botão e comandos `/fila`, `/resumo`, `/caso`;
  Slack por webhook): avisa e pede aprovação onde o time já conversa.
- **Equipe de agentes:** um pico de reclamações por transportadora vira incidente e aciona Supervisor → Investigação →
  Resolução.
- **IA com plano B:** Jev (AI Proxy Gogroup) desempata intenções ambíguas; um LLM resume o caso para quem assume.
  Sem IA configurada, tudo segue por regras.

Menu **Atendimento** — contatos de **WhatsApp, e-mail e Reclame Aqui** numa caixa só, triados pelo **Agente de Atendimento**
(regras explicáveis; IA opcional só para reescrever respostas). Na demo, os contatos são **sintéticos** e coerentes com os
pedidos/entregas (fonte `support_demo_contatos`, etapa `support` do pipeline), com reclamações falsas e recontatos plantados.

| Desafio | Como a plataforma responde |
|---|---|
| Volume e tempo por contato | Assuntos informativos (onde está, prazo, estorno, dúvidas, elogios) respondidos na hora com dados do pedido; o resto chega priorizado (urgência 0–100). Horas poupadas estimadas por premissas editáveis. |
| Trabalho espalhado entre sistemas | Visão 360 do contato (pedido, entrega, transportadora, histórico, NPS) e ações de um clique: chamado na transportadora, troca, reenvio, reembolso, cancelamento — execução **simulada**, com aprovação humana nas áreas críticas. |
| A reclamação é verdadeira? | Score de **veracidade** 0–100 com fatores e evidências (entrega registrada, prazo, foto e data da foto, tempo desde a entrega, reclamações em série, transportadora, fragilidade). "Não sustentada" vai para uma pessoa — **nunca é negada automaticamente**. |
| Sozinho × pessoa | Matriz configurável em *Configurações › Atendimento* (assuntos automáticos, canais públicos, urgência, recontato, valor, confiança). Reclamações de reparação nunca são automáticas. |
| Contatos que se repetem | Detecção de recontato e de contatos evitáveis, causas (assunto × transportadora × linha) e **aviso proativo** aos pedidos em risco de atraso (com aprovação). |

**Caixa unificada estilo WhatsApp** — uma conversa contínua por cliente e canal (padrão de Zendesk, Intercom, Blip e
Octadesk): cliente à esquerda; Agente de Atendimento (automático) e atendentes à direita; ações e encerramentos como avisos
no centro; notas internas destacadas. Dentro da conversa, cada **atendimento** é separado por um divisor. Mensagem nova
com atendimento aberto continua o mesmo atendimento e refaz a triagem com o contexto (ex.: chegou a foto pedida); depois
do encerramento, abre um atendimento de continuação (recontato se for o mesmo pedido); "obrigado" logo após não reabre;
atendimento aguardando o cliente é encerrado por inatividade; o campo de resposta mostra a janela de 24 h do WhatsApp.
Janelas configuráveis em *Configurações › Atendimento*.

Roteiro rápido: *Atendimento › Visão do atendimento* → **Simular chegada de contatos** → *Caixa unificada* → abra um contato de
avaria (veja os fatores de veracidade) → **Propor** reenvio com `atendente@` → aprove com `atendimento.owner@` (o agente executa
em modo simulado e o contato é resolvido) → *Prevenção de recontato* → **Propor aviso**.
Novos usuários de demonstração: `atendente@goops.local` (Atendente) e `atendimento.owner@goops.local` (Responsável pelo
Atendimento), com a mesma senha de demo. Bancos existentes: `python manage.py init` e depois `python manage.py pipeline`.

## Publicar (Render)
O arquivo `render.yaml` cria frontend público, API privada, disco e PostgreSQL no Render (*New › Blueprint*).
Passo a passo, custos e acessos da banca em [`docs/deploy/RENDER.md`](docs/deploy/RENDER.md).

## Agentes de IA — ver, ajustar instruções e criar novos
Menu **Agentes de IA**:
- **Agentes nativos**: cada um mostra *o que faz*, *quando roda*, *limites* e as **instruções de IA** de cada tarefa
  (ex.: narrativa da investigação, reescrita da resposta ao cliente, instrução de sistema do "Pergunte ao GoOps").
  Editar cria uma nova versão (com motivo e histórico; "Restaurar padrão"). As regras fixas aparecem ao lado e não
  mudam. Monitor e Validação são 100% regras. Permissão: administrador ou Responsável pelos dados.
- **Novo agente**: descreva a **missão** em texto, escolha as **ferramentas** (somente leitura, as mesmas do
  "Pergunte ao GoOps"), a **saída** (relatório, canal do time, incidente quando houver alerta ou incidente + proposta
  de ação com aprovação), o modelo, a frequência e **critérios de aceite**. Sem modelo configurado, o agente entrega um
  resumo determinístico e não sinaliza alerta.
- **Editar → Testar → Publicar**: a instrução editada vira rascunho; **Testar** mostra a resposta para evidências de
  exemplo, o prompt exato e verificações automáticas (ex.: número fora das evidências); **Comparar** mostra a diferença
  para a versão publicada; só **Publicar** coloca no ar.
- **Testar agente** (no formulário e na página do agente): roda com dados reais sem abrir incidente, propor ação ou
  publicar no canal, e mostra os critérios e o **passo a passo** (instrução, chamadas ao modelo, ferramentas, decisão).
- Lista com busca, filtros (tipo, setor, situação), **saúde dos últimos 7 dias** e pausar/retomar.
- **Como decide** (aba em cada agente nativo): regras e fórmulas, parâmetros em vigor, quando passa para uma pessoa,
  ações possíveis e decisões recentes reais.
- **Validação ponta a ponta** (*Agentes de IA › Validação ponta a ponta* ou `python manage.py validate-agents`): gera
  dados sintéticos num ambiente isolado (inclusive casos sob medida como prompt injection e foto anterior à entrega),
  executa todos os fluxos e recalcula cada decisão. `--with-ai` usa os modelos configurados.
Bancos existentes: `python manage.py init` aplica as migrações `0011` e `0012`.

## Setores dinâmicos (novo setor sem código)
Menu **Setores › Novo setor / conjunto** — assistente em 5 passos:
1. **Setor**: escolha um existente ou crie (ex.: Atendimento, Estoque).
2. **Fonte**: planilha (XLSX/CSV dentro de `data/`) ou **API REST JSON** (URL, endpoint, caminho da lista; token só pelo
   *nome* da variável de ambiente).
3. **Campos**: o GoOps lê uma amostra e sugere tipo (texto, número, data, sim/não, identificador) e papel (chave, data,
   dimensão, medida); dados pessoais vêm desmarcados. Dá para criar campos calculados (dias entre duas datas).
4. **Processar**: Bronze → Silver tipada/deduplicada (com quarentena) → Gold do setor (com dimensão `month`).
5. **Métricas e painel**: métricas sugeridas (volume, médias, P90, % sim) entram como *aguardando aprovação* e já
   aparecem no painel como rascunho; o painel é montado automaticamente e editável (KPI, linha, barras, tabela).

Recursos do assistente: **Refinar com IA** (o modelo configurado propõe nomes, rótulos, papéis e métricas a partir do
*perfil* dos campos — nunca inclui dados pessoais e tudo volta para revisão; sem modelo vale a sugestão por regras) e
**relacionamentos** com qualquer Gold (núcleo ou de outro setor), trazendo colunas como dimensão (identificadores de
cliente e campos pessoais são bloqueados).

Na página do setor: **Painel** (filtro de período, edição de widgets), **Agentes** e **Métricas** (construtor sem código
com prévia: contagem, média, soma, mediana, percentil, contagem distinta e taxa com condição). Modelos de agente:
*Monitor de métrica* (abre incidente quando a métrica cai/sobe/ultrapassa um limite, no total ou por segmento),
*Tarefa com ação* (idem + propõe uma ação do catálogo, que segue a política de aprovação), *Investigação de causas*
(decompõe a variação entre os dois últimos meses em efeito desempenho × composição por dimensões escolhidas) e
*Resumo do período* (opcionalmente com narrativa executiva por IA). Frequência manual/horária/diária/semanal.
O **Pergunte ao GoOps** enxerga as métricas e dimensões dos setores automaticamente. Exemplo pronto: setor **Reputação (ReclameAqui)**,
criado inteiramente por configuração a partir da planilha do Desafio 3 (sem e-mail, telefone ou texto da reclamação).

## Recursos opcionais (Configurações › Recursos — cada um liga/desliga sem perder dados)
- **Setor Estoque · Pedidos travados** (Desafio 2): estoque × pedidos com regra FIFO (estoque zero, estoque
  insuficiente para os pedidos mais novos, produto fora do catálogo não trava). Nome/telefone/e-mail dos clientes não
  são ingeridos. O agente *Avisar clientes de pedidos travados* abre incidente e **propõe** o contato (opções A aguardar,
  B trocar, C cancelar) — sempre com aprovação humana e execução simulada.
- **Simulação "e se…"**: em toda ação aguardando aprovação, projeta o efeito antes de decidir — realocação de
  transportadora (taxa de atraso e NPS projetados, com controle de % de volume) e contato com clientes (alcance e prévia
  da mensagem). Premissas exibidas; nada é alterado.
- **Briefing diário** (menu *Briefing diário*): indicadores principais, KPIs de cada setor, incidentes abertos e ações
  aguardando decisão, com narrativa opcional por IA. Geração manual ou automática (agendador); entrega em Slack/e-mail
  registrada como **simulada**.

## Configuração pela interface
Em **Configurações** (perfil admin) você configura, sem editar arquivos:
- **Modelos e chaves**: provedor/modelo por nível do Cost Routing (1 = JEF, 2 = econômico, 3 = avançado), chaves de API (cifradas no banco, nunca reexibidas), base URL OpenAI-compatível, tabela de preços, limites de custo e botão **Testar conexão**.
- **Monitor, agendador e retenção**: limiares do Monitor Agent, jobs periódicos (pipeline, monitoramento, retenção) com "Executar agora", e política de retenção com simulação.
- **Políticas** de aprovação, **Usuários** (criar, papel, domínios, ativar/desativar, redefinir senha), **Domínios** e **Integrações**.
Valores salvos na interface têm precedência sobre o `.env`. Defina um `SECRET_KEY` estável — ele protege as chaves salvas.

## Configurar integrações reais e mudanças de API
1. **Conexão** — *Data Lakehouse › Sources*: conector `http_json` (URL, endpoint, paginação page/offset/cursor, `data_path`,
   incremental e o **nome** da variável de ambiente da credencial) ou `file` (XLSX/CSV em `data/`). Use "Testar".
2. **Campos** — *Data Lakehouse › Mapeamentos*: para cada campo canônico, informe de onde ele vem (aceita alternativas
   separadas por vírgula e caminhos aninhados como `order.code`), o tipo e, se preciso, chave composta. **Pré-visualize**
   com os payloads reais da Bronze (ou cole um exemplo da nova versão da API): a tela mostra cobertura por campo, erros de
   tipo, o que iria para quarentena e os campos do payload ainda não usados (normalmente os renomeados).
3. **Salvar e reprocessar** — cada salvamento cria uma versão do perfil (histórico e auditoria); a fonte passa a usar o
   perfil e a Silver/Gold são reconstruídas a partir da Bronze, sem chamar a API de novo.
Perfis embutidos (`default`, `gocase_xlsx`) são somente leitura — duplique para editar. Métricas e dashboards não mudam,
pois leem apenas os campos canônicos.
