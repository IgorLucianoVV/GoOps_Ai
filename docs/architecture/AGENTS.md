# Agentes

Arquitetura **hierárquica** com estado controlado: não há conversa livre entre agentes.

| Agente | Função | Permissões explícitas |
|---|---|---|
| Supervisor | Prioriza incidentes (severidade), aciona o grafo, retoma após decisão humana | incidents:read/write, agents:read, operations:read |
| Monitor | Regras nível 0: queda de NPS (MoM ou vs. média 3 meses), aumento de atraso por transportadora, concentração de detratores por linha; dedup por fingerprint | analytics/data/semantic:read, incidents:write |
| Investigation | Decomposição do ΔNPS por dimensão em efeito **desempenho** (w̄ᵢ·ΔNPSᵢ) e **composição** (Δwᵢ·(N̄PSᵢ−N̄PS)), teste z por segmento, corroboração com atraso ou prazo médio, temas, DQ e lineage; hipóteses com confiança e evidências | analytics/data/semantic:read, incidents:write |
| Resolution | Seleciona ações do **catálogo** (nunca livres), estima impacto com premissas, propõe operações; executa só aprovadas (simulado) | analytics:read, operations:propose, operations:execute_approved |
| Validation | Valida dados antes da investigação; após execução verifica política, status e re-mede o indicador | analytics/data/semantic:read, operations:read |

## Workflow `incident_resolution`
`validate_inputs → investigate → plan_resolution → (await_approval ⏸ | execute | finalize) → execute → validate_outcome → finalize`
Estado e passos persistidos em `workflow_runs`; a interrupção humana é retomada em `Supervisor.decide`.

## Ferramentas governadas (`agents/tools/registry.py`)
nps_total, nps_monthly, nps_breakdown, delivery_late_rate, comment_themes, data_quality_status, lineage_upstream, metric_definition, delay_risk_summary. Contratos explícitos, dimensões em allowlist, **sem SQL arbitrário**, cada chamada registrada na timeline.

## Intelligent Cost Routing (`agents/routing`)
Nível 0 determinístico · 1 modelo pequeno (alias **JEF**, configurável) · 2 LLM econômico · 3 LLM avançado. Sem modelo configurado, orçamento excedido ou falha ⇒ **fallback determinístico registrado** e saída rotulada `generated_by: deterministic`. Registra custo, tokens, latência, modelo, sucesso e % por nível. O LLM recebe apenas evidências já calculadas, delimitadas como dados.

## Uso real de cada nível
| Nível | Tarefa | Onde |
|---|---|---|
| 0 | Detecção, decomposição, seleção de ações, validação | Monitor, Investigation, Resolution, Validation |
| 1 (JEF) | Classificar comentários de detratores **sem tema** em lista fechada (saída validada) | Investigation (`classify.py`) |
| 2 | Resumo executivo do incidente; explicação de métricas | Supervisor (finalize), Semantic › "Explicar métrica" |
| 3 | Narrativa da investigação e do plano de resolução | Investigation, Resolution |
Modelos, chaves, preços e limites são configurados em **Settings › Modelos e chaves** (com teste de conexão).

## Agendador
`agents/scheduler.py`: jobs `pipeline`, `monitor`, `retention` com intervalo/ativação definidos na interface; thread no processo da API com **lease** no banco (compare-and-set) para evitar execução duplicada entre instâncias; histórico em `scheduler_runs`.

## Confiança das hipóteses (heurística documentada)
`0.5·concentração da piora + 0.15·[z ≤ −2] + 0.2·[1ª corroboração] + 0.1·[2ª corroboração] − 0.15·[n<30] − 0.1·[DQ>5%]`, limitada a [0.05, 0.95]. Contribuição ≠ causalidade (explicitado nas limitações).

## Pergunte ao GoOps — grafo LangGraph (`agents/llm/assistant_graph.py`)
```
START → agent (LLM com bind_tools) ──tool_calls?──► tools (Toolbox governado, permissões do usuário) ─┐
              ▲                                   └─não─► END                                        │
              └──────────────────────────────────────────────────────────────────────────────────────┘
```
- Estado: `messages` (reducer `add_messages`) + `steps`; limite de 6 passos e orçamento de custo checado a cada chamada.
- Provedores (`agents/llm/providers.py`): `ChatAnthropic`, `ChatOpenAI` (também para endpoints OpenAI-compatíveis),
  `ChatGoogleGenerativeAI`, `ChatOllama`, importados sob demanda. O usuário escolhe o modelo por requisição (`model_id`)
  entre os cadastrados em Settings; modelos fora da lista são recusados.
- Resultados de ferramenta voltam como `ToolMessage` e são tratados como dados (nunca instruções). Toda chamada é
  registrada em `llm_calls` (tokens, custo, latência). Se a resposta não citar ferramentas, cai no motor determinístico.
- O workflow de incidentes continua no grafo interno (`agents/workflows/graph.py`) por exigir interrupção persistida
  para aprovação humana; as narrativas desse workflow usam o mesmo `build_chat_model` quando os pacotes estão instalados.

## Pergunte ao GoOps (`agents/ask.py`)
Loop de *tool calling* (Anthropic Messages API ou OpenAI-compatível), até 6 etapas, com ferramentas somente leitura:
`list_metrics`, `dimension_values`, `metric_value`, `metric_breakdown`, `nps_monthly`, `comment_themes`, `data_quality`,
`open_incidents`. Regras: as ferramentas executam com as permissões do usuário; as citações exibidas vêm das chamadas
reais (não do texto do modelo); resposta sem nenhuma consulta é descartada e substituída pela determinística;
comentários enviados ao modelo passam por `safe_comments` (exclui suspeitas de prompt injection); custo e tokens
registrados em `llm_calls`, com limites por execução e diário.

## Agentes configuráveis por setor (`agents/custom.py`)
Criados na interface a partir de modelos, sem código:
- **metric_monitor** — calcula a métrica governada por mês (e opcionalmente por segmento), aplica a regra
  (queda/alta de pelo menos X, acima/abaixo de X) com amostra mínima e abre incidente (com fingerprint para não duplicar).
- **summary** — último mês vs. anterior para uma lista de métricas, em markdown.
Executam com principal `custom:<chave>` (kind=agent, domínio do setor, permissões: analytics/semantic/incidents read +
incidents:write). Rodam pelo agendador conforme a frequência configurada ou pelo botão "Executar"; cada execução fica em
`agent_runs` e na auditoria. Métricas aguardando aprovação não disparam alertas.
- **driver_analysis** — investigação genérica: para métricas de média/taxa, decompõe a variação entre os dois últimos
  meses por dimensão em efeito desempenho e efeito composição; segmentos abaixo da amostra mínima são ignorados.
- **action_task** — monitor + proposta de ação do catálogo (`operations`), vinculada ao incidente; a política decide se
  exige aprovação (contato com clientes sempre exige). O agente nunca aprova nem executa.
- **summary** com `use_ai` — narrativa executiva pelo nível 2 do roteamento de custo, baseada apenas no resumo
  determinístico (fallback identificado).

## Instruções de IA editáveis (agentes nativos) — `agents/instructions.py`
Na tela **Agentes de IA › (agente)** cada tarefa de IA aparece como um *slot* com:
- **instrução editável** (tom, foco, tamanho) — versionada em `agent_instructions` (migração 0011), com motivo,
  histórico, "Restaurar padrão" e "Restaurar esta versão"; cada mudança vai para a auditoria (`agent.instruction_*`);
- **regras fixas** (somente leitura) — sempre anexadas ao prompt: formato de saída, proibição de números novos, dado ≠
  instrução. O `SYSTEM_GUARDRAIL` do roteador e os guardas de pós-processamento continuam valendo.

| Slot | Agente | Nível |
|---|---|---|
| summarize_incident, explain_metric | Supervisor | 2 |
| investigation_narrative · classify_comment | Investigation | 3 · 1 |
| resolution_plan_narrative | Resolution | 3 |
| support_classify (Jev) · support_reply · support_summary | Atendimento | 1 · 2 · 2 |
| ask_question (instrução de sistema) · daily_briefing · sector_summary | Assistente | 3 · 2 · 2 |

Monitor e Validation não usam IA. Editar instruções exige `agents:configure` (admin e Responsável pelos dados).
A instrução muda só o texto que a IA escreve — não muda regras, limiares, números, catálogo de ações nem aprovações.
Leitura com falha (ex.: banco sem a migração) devolve o padrão: o fluxo de IA nunca para por causa disso.

## Agentes com instruções (`llm_task`) — `agents/custom.py`
Criados em **Agentes de IA › Novo agente** (ou via `POST /api/agents/custom`), guardados em `custom_agents`:
- **missão** em texto (20–4000 caracteres, sem marcadores de dados), **ferramentas** escolhidas entre as do
  "Pergunte ao GoOps" (somente leitura; qualquer outra é recusada na validação e bloqueada na execução),
  **saída** (`report`, `team_channel`, `incident`, `propose_action`), **modelo** (padrão 3/2 ou um cadastrado),
  **frequência** (manual/hora/dia/semana, pelo agendador) e **setor** (escopo de dados e permissões).
- Execução: mesmo motor do assistente (LangGraph ou loop nativo), instrução de sistema = regras fixas + `<missao>`;
  principal `custom:<chave>` restrito ao setor; custo em `llm_calls` (`agent_key = custom:<chave>`, tarefa
  `custom_llm_task`, nível 3) e limites por execução/diário.
- Alerta: a IA só escreve `ALERTA: SIM|NÃO` na última linha. Quem abre o incidente (no máximo 1 por dia por agente,
  via fingerprint) e propõe a ação do catálogo é o código; a ação segue a política de aprovação.
- Sem modelo, orçamento estourado, erro ou resposta com números sem consulta ⇒ **resumo determinístico** das
  ferramentas sem parâmetros, rotulado, e **nenhum alerta**.

## Ciclo editar → testar → publicar (inspirado em Glean, Zendesk, OpenAI AgentKit, Intercom e Decagon)
- **Rascunho** (`agent_instruction_drafts`, migração 0012): um por tarefa; não afeta os agentes. "Publicar" cria a
  versão e registra na auditoria se foi publicada **após teste** (`agent.instruction_publish_check`).
- **Testar instrução** (`preview`): monta o prompt exato (instrução + regras fixas + evidências de EXEMPLO do cenário
  de demonstração) e chama o modelo do nível da tarefa; o "Pergunte ao GoOps" é testado com uma pergunta real e a
  instrução de sistema do rascunho. Verificações automáticas: saída não vazia, sem marcadores de dados, **nenhum número
  fora das evidências**, tamanho e, na classificação, JSON válido. Custo em `llm_calls` (tarefa `preview_instruction`).
- **Comparar**: diferença por palavra entre rascunho e publicada, e entre versões do histórico.
- **Testar agente personalizado** (`test_agent`): roda a configuração (salva ou não) com dados reais e o mesmo
  modelo, **sem** abrir incidente, propor ação, publicar no canal ou alterar o estado do agente; execuções ficam em
  `agent_runs` como `custom-test:<chave>` (não contam na saúde do agente).
- **Critérios de aceite** por agente (`checks`): cita a métrica, consulta a ferramenta, contém/não contém texto, alerta
  esperado, máximo de linhas — avaliados em todo teste e execução, junto com os automáticos.
- **Passo a passo** (`run_trace`): instrução enviada → cada chamada ao modelo (tokens, latência, custo) seguida das
  ferramentas que ela pediu (argumentos e resultado resumido) → decisão de alerta → ações do sistema.
- **Saúde (7 dias)** por agente: execuções, falhas, % de contingência sem IA, alertas e custo; filtros na lista e
  pausar/retomar sem excluir.

## Transparência: “Como decide” (`agents/decisions.py`)
Aba em cada agente nativo com: resumo, passos de decisão (regra/fórmula + o que decide), **parâmetros em vigor** lidos da
configuração atual (com onde mudar), quando passa para uma pessoa, uso de IA, ações do catálogo (risco, áreas,
aprovação) e **decisões recentes reais** (números e motivos registrados), além do resultado da última validação.

## Validação ponta a ponta (`agents/walkthrough.py` · `python manage.py validate-agents [--with-ai]`)
Banco e Lakehouse **temporários** (nada da aplicação é alterado; pela tela roda em processo separado). Gera o cenário
sintético `full` e, quando falta dado, **casos sob medida** (prompt injection, foto anterior à entrega, dúvida
informativa por WhatsApp e por Reclame Aqui, pico de reclamações por transportadora). Executa cada fluxo com as funções de
produção e **recalcula cada decisão de forma independente**: queda de NPS e severidade, deduplicação, sensibilidade ao
limiar, soma da decomposição = ΔNPS, confiança das hipóteses, regra de causa provável, plano coerente com a hipótese,
política de aprovação, bloqueios (agente/domínio errado/leitor/execução sem aprovação), retomada do fluxo e execução
simulada, veracidade de todos os contatos, matriz automático × pessoa, acerto contra o gabarito, ações do atendimento,
turno com pico → incidente → Investigação, agentes de setor, agente com instruções (teste sem efeito) e plano B de IA.
Relatório em `var/validation/latest.json` e `.md`; tela *Agentes de IA › Validação ponta a ponta*.

Achados corrigidos na primeira execução: ação do atendimento dispensada de aprovação ficava “aprovada” sem ser
executada (agora o Agente de Atendimento executa, como na triagem automática); agente de setor “Causas da variação de
contatos” decompunha uma contagem e nunca rodava (passou a usar a taxa de recontato; a configuração agora recusa
contagens/somas nesse modelo).
