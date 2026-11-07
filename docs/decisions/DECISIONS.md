# Decisões arquiteturais (ADR resumidas)

**ADR-01 — Lakehouse em camadas com Gold híbrida e semântica híbrida (D1–D5).** Obrigatórias pela especificação; implementadas como Bronze JSONL, Silver/Gold Parquet, Corporate + Domain Gold, Corporate + Domain Semantic Registry.

**ADR-02 — SQL parametrizado próprio em vez de SQLAlchemy/Alembic.** O ambiente de construção não tinha acesso a pacotes; para manter o núcleo testável, foi criado um adaptador mínimo (`goops_core/db.py`) que roda o mesmo SQL em SQLite e PostgreSQL, com migrações versionadas em `.sql`. Reduz dependências; migrar para SQLAlchemy Core é direto se desejado.

**ADR-03 — pandas no MVP (Polars depois).** Transformações isoladas em funções puras por camada; troca por Polars não altera contratos.

**ADR-04 — Grafo de estados próprio em vez de LangGraph.** `agents/workflows/graph.py` segue o modelo StateGraph (nós, arestas condicionais, interrupção humana, estado persistido). Evita dependência pesada no MVP; migração mecânica.

**ADR-05 — Núcleo analítico determinístico; LLM só para narrativa.** Atende D6/D7/D11 e a regra de não apresentar respostas fictícias: sem modelo configurado, tudo funciona e é rotulado `deterministic`.

**ADR-06 — Execução de ações somente simulada.** Sem contratos reais de sistemas operacionais; simuladores calculam o efeito previsto sobre os dados atuais.

**ADR-07 — Data de referência (as_of) = maior data observada nos dados.** Evita que a idade dos dados de demo (2026-01..06) distorça atrasos/risco em relação ao relógio do servidor.

**ADR-08 — Mapeamentos de fonte versionados como ponto de adaptação.** Contratos de API não confirmados (D14): nomes de campos em `silver/mappings.py`; conector HTTP configurável sem contrato presumido.

**ADR-09 — Parquet com fallback CSV+schema.** Garante execução mesmo sem pyarrow, preservando tipos (IDs como string).

**ADR-10 — Pacotes Python `data_platform` (com underscore).** Nome com hífen não é importável; estrutura de pastas da especificação mantida nos demais níveis.

**ADR-11 — Hipótese de negócio documentada:** "Pedidos" do NPS por estado/linha/transportadora usam a entrega primária (primeiro envio) quando há múltiplas entregas.

**ADR-12 — Configuração operacional em tela com precedência sobre o ambiente.** Seções versionadas em `app_settings`; `.env` vira apenas padrão. Infraestrutura (banco, SECRET_KEY, CORS, rate-limit backend) continua no ambiente por segurança.

**ADR-13 — Cifragem de segredos com a biblioteca padrão.** Sem acesso a `cryptography` no ambiente de construção, foi adotada uma construção encrypt-then-MAC (keystream SHA-256 em modo contador + HMAC-SHA256, chaves derivadas do SECRET_KEY). Testada contra adulteração e chave errada. Recomenda-se migrar para Fernet/AES-GCM (`cryptography`) ou um cofre (Vault/KMS) em produção corporativa.

**ADR-14 — Sessão em cookie httpOnly + CSRF double-submit** em vez de token no localStorage (mitiga roubo de token via XSS). Requer frontend e API no mesmo site.

**ADR-15 — Agendador embutido com lease no banco** em vez de worker dedicado: simples para o MVP e seguro com múltiplas instâncias; migrável para Dagster/cron.

**ADR-16 — Retenção conservadora da Bronze:** expurgo apenas de arquivos cujos registros existem integralmente em execuções posteriores, garantindo reprocessamento sem perda inclusive em fontes incrementais.

**ADR-17 — Seed padrão com as planilhas do case Gocase.** Conector `file` (XLSX/CSV, restrito a `DATA_IMPORT_DIR`) +
perfil de mapeamento `gocase_xlsx`. `Name` e `Ipaddress` são excluídos já na ingestão (minimização). Itens de pedido são
agregados por pedido (linha principal = item de maior valor; brindes de valor zero não dominam).

**ADR-18 — Sem datas, sem atraso.** Quando a fonte não traz datas de previsão/entrega, `is_late` não é inferido: a taxa de
atraso fica nula e o prazo usa `METRIC_DELIVERY_DAYS_001` (datas quando houver; senão "Dias de entrega" informados, com
`lead_time_source`).

**ADR-19 — Decomposição do ΔNPS em efeito desempenho + efeito composição, com teste z.** Evita atribuir a um segmento uma
"queda" que é apenas mudança de participação; hipóteses sem significância (|z| < 2) recebem confiança menor e são
rotuladas como tal.

**ADR-20 — Mapeamentos editáveis pela interface, declarativos e versionados.** Perfis personalizados ficam em
`mapping_profiles`/`mapping_profile_versions`; só podem referenciar campos canônicos, tipos da lista fechada e derivações
controladas (sem código). A prévia aplica mapeamento + regras de qualidade a payloads reais sem gravar nada. Campos não
informados num perfil herdam a origem do perfil padrão. Caminhos aninhados (`a.b`, `itens.0.sku`) são suportados.

**ADR-21 — LangGraph + LangChain para o assistente, multi-provedor.** O chat usa um `StateGraph` do LangGraph com modelos
LangChain (Anthropic, OpenAI, Gemini, Ollama, OpenAI-compatível) escolhidos pelo usuário entre os cadastrados em Settings.
Dependências são opcionais em tempo de execução: sem elas, há loop nativo para Anthropic/OpenAI-compatível e fallback
determinístico — a demo nunca quebra. O workflow de incidentes permanece no grafo próprio (interrupção HITL persistida no banco).

**ADR-22 — Complemento sintético com proveniência por campo.** Para uma visão completa na demo, lacunas da seed real
(datas de envio/previsão/entrega, pedidos em aberto) são preenchidas por fontes `is_demo` com `role: complement`, que
**só preenchem campos nulos** por chave natural. Cada linha registra `_synthetic_fields`; cada dataset, `synthetic_fields`
(propagado para colunas derivadas na Gold); cada métrica devolve `synthetic`, `synthetic_fields` e `includes_demo_rows`,
exibidos como selo "sintético" na interface e citados pelo assistente. "Dias de entrega" passa a ser interpretado como
prazo de transporte (envio→entrega) — premissa documentada, com base no intervalo pedido→pesquisa (mediana 15 dias) vs.
mediana de 3 dias de entrega. Revisa a ADR-18.

**ADR-23 — Setores como configuração.** Um setor novo = domínio + fontes (`entity: custom`) + conjunto de dados
declarativo (`custom_datasets`: campos, tipos, papéis, chave, data, derivações controladas, relacionamentos com a Gold
corporativa) + métricas do catálogo semântico + painel (`dashboards`: widgets ligados a métricas) + agentes por modelo
(`custom_agents`: monitor de métrica e resumo). Nada executa código ou SQL do usuário; dados pessoais são recusados na
definição; métricas novas seguem a aprovação com segregação de funções (rascunhos aparecem sinalizados para quem edita);
agentes rodam com principal próprio restrito ao domínio e só observam métricas aprovadas. O motor de métricas ganhou
soma, mediana, percentil e contagem distinta. As análises dedicadas (NPS, Logística…) continuam como "receitas" prontas.

**ADR-24 — IA como assistente de configuração, nunca como fonte de verdade.** O refino por IA recebe só o perfil dos
campos (tipos, preenchimento, até 3 exemplos curtos mascarados) e devolve JSON validado contra listas fechadas; campos
pessoais nunca são incluídos pela IA e métricas sugeridas seguem o fluxo de aprovação. Agentes "Tarefa com ação" só
PROPÕEM ações genéricas de setor (`sector_operational_review`, `sector_customer_contact`) — esta última toca a área
crítica "clientes" e sempre exige aprovação humana. Relacionamentos aceitam qualquer Gold, mas bloqueiam colunas de
identificação pessoal.

**ADR-25 — Recursos de demonstração como chaves liga/desliga.** Setor Estoque (receita FIFO em código, pois a regra não
é expressável na configuração declarativa), simulação "e se…" e briefing diário ficam na seção `features` da
configuração em tela. Desligar o setor inativa domínio, fontes e agentes sem apagar dados; desligar o "e se…" bloqueia a
API correspondente; o briefing automático depende do agendador. Entregas em canais externos são sempre simuladas
(nenhum contrato de API externa foi assumido).

**ADR-26 — Atendimento como caixa operacional + Gold.** Contatos têm ciclo de vida (triagem, resposta, ação, resolução),
por isso vivem na tabela operacional `support_contacts`; a Bronze preserva o payload original e a Gold
`gold_support_contacts` (sem texto livre nem id do cliente) alimenta as métricas `SUP_*` do catálogo semântico. Ações
reutilizam `operations` (coluna `contact_id`), com política, aprovação humana, execução simulada e auditoria; ganchos
(`operations.HOOKS`) mantêm o contato sincronizado.

**ADR-27 — Veracidade explicável e assimétrica.** O agente pode liberar reparações quando os dados sustentam a reclamação
(ainda sujeitas à aprovação), mas nunca nega: "não sustentada" sempre vai para uma pessoa com as evidências e a
verificação recomendada. A acurácia exibida é medida contra o gabarito do gerador sintético e indica coerência das regras,
não desempenho em produção.

**ADR-28 — Endurecimento de segurança.** Conector HTTP: credencial só por variável com padrão de fonte (`SOURCE_*`,
`*_TOKEN`, `*_USER`, `*_PASSWORD` ou `SOURCE_CREDENTIAL_ENV_ALLOWLIST`), nunca variáveis de infraestrutura; hosts
privados/loopback/link-local bloqueados (salvo `SOURCE_ALLOWED_PRIVATE_HOSTS`) e sem seguir redirecionamentos.
Rate limit pelo IP real (`X-Forwarded-For` apenas de proxy confiável/`TRUSTED_PROXIES`) e limite próprio no login.
Custo de LLM sem preço cadastrado usa estimativa conservadora para que os limites valham. Sessões revogáveis
(logout encerra a sessão no servidor; troca de senha/papel invalida tokens antigos).

**ADR-29 — Atendimento conversacional (chat por cliente e canal, com atendimentos dentro).** Padrão de mercado
(Zendesk: "conversa persistente única" no WhatsApp e ticket de continuação ao responder um ticket fechado; Intercom:
janela configurável para tratar a mensagem como conversa nova; Blip/Octadesk: encerramento por inatividade e histórico
do contato). `support_conversations` (canal + identidade) e `support_messages` (cliente, robô, atendente, sistema, nota)
guardam o chat; `support_contacts` passa a ser o atendimento. Horários do chat seguem o relógio dos dados. Recontato =
novo atendimento do mesmo pedido após o encerramento; mensagens com o atendimento aberto são continuação ou cobrança.
Bancos anteriores são reconstruídos automaticamente a partir da Bronze no primeiro pipeline.

**ADR-30 — Instruções de IA editáveis em duas camadas e agentes com instruções.** As tarefas de IA dos agentes nativos
viram *slots* com instrução editável (versionada, auditada, restaurável) + regras fixas não editáveis; o guarda do
roteador e as validações de saída permanecem no código. Agentes novos "com instruções" (`llm_task`) reutilizam o motor
do assistente e as ferramentas governadas somente leitura, com principal restrito ao setor. A IA apenas redige e
sinaliza alerta; abrir incidente e propor ação do catálogo são passos determinísticos, e a ação continua sujeita à
política de aprovação. Sem modelo, há resumo determinístico e nenhum alerta é inferido.

**ADR-31 — Nada de IA vai ao ar sem teste visível.** Instruções passam por rascunho → teste com evidências de exemplo
→ publicação (padrão de Glean/Zendesk/OpenAI). O teste mostra o prompt exato e verificações determinísticas (ex.:
número fora das evidências). Agentes personalizados têm teste sem efeito colateral, critérios de aceite e rastro passo a
passo (padrão Decagon Trace View / Intercom Simulations). Publicar sem teste é permitido, mas exige confirmação e fica
registrado na auditoria.

**ADR-32 — Transparência verificável dos agentes.** Cada agente expõe como decide (regras, fórmulas e parâmetros em
vigor) e as decisões recentes. Uma validação ponta a ponta reproduzível recalcula cada decisão de forma independente
num ambiente isolado com dados gerados, inclusive casos-limite sob medida; roda pela tela, pelo terminal e na suíte de
testes. O relatório é a evidência para a banca de que as regras do código são as mesmas que a tela descreve.
