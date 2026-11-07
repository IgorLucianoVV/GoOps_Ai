# apresentacao.md — direcional para os slides

Base para montar os slides do pitch do **GoOps AI · Colega digital do Atendimento** (Desafio 1). Cada slide traz a
mensagem principal, o conteúdo, a sugestão visual e qual critério de avaliação ele atende.

---

## 1. Ideia central (repetir do início ao fim)

> **"Não é um chatbot. É um colega de trabalho do atendimento: faz sozinho o que é simples, levanta a mão quando
> não deve decidir, chama outros agentes quando o problema é maior — e mora onde o time já conversa."**

Frase de fechamento: **"Pensamos 360°, provamos em uma frente: o atendimento funcionando de ponta a ponta."**

## 2. Critérios e onde cada um aparece

| Critério | Peso | Onde provar |
|---|---|---|
| **Modelagem** (funciona ponta a ponta, usa agentes/IA, autonomia, IA verificada e corrigida) | 40% | Slides 4–7 + demo ao vivo + slide 9 |
| **Adaptabilidade** | 20% | Slide 8 (matriz configurável, conectores trocáveis, mesmo colega em outras frentes) |
| **Conceito** | 20% | Slides 2–3 e 8 (problema real → colega digital → 360°) |
| **Aderência cultural** | 20% | Slides 3, 6 e 10 (Telegram/Slack, pessoa no controle, linguagem do time) |
| **Transparência sobre IA** | — | Slide 9 (o agente avaliador vai resumir; deixe explícito) |

## 3. Roteiro sugerido (10 slides + demo · ~6–7 min)

### Slide 1 — Capa
- **Título:** GoOps AI — o colega digital do Atendimento
- Subtítulo: Desafio 1 · Atendimento ao Cliente · nome do time
- Visual: tela da caixa unificada estilo WhatsApp ao fundo, escurecida.

### Slide 2 — O problema (Conceito)
- **Mensagem:** o atendimento gasta o tempo pulando entre sistemas, não resolvendo o cliente.
- Pontos: milhares de contatos por WhatsApp, e-mail e Reclame Aqui · um pedido toca vários sistemas (pedidos,
  transportadora, ERP, financeiro) · nem toda reclamação procede · cliente volta porque ninguém avisou (recontato).
- Visual: um atendente no centro com setas para 5–7 sistemas (pedidos, transportadora, chamados, ERP de trocas,
  financeiro, catálogo, CRM).

### Slide 3 — A virada: um colega, não um chatbot (Conceito + Aderência)
- **Mensagem:** quatro comportamentos de colega.
- 4 cards: **Age nos sistemas** (consulta pedido, abre chamado na transportadora) · **Levanta a mão** (pede aprovação
  para reenvio/reembolso) · **Chama outros agentes** (pico → Investigação → Resolução) · **Mora no canal do time**
  (Telegram com botão de aprovar, Slack, app).
- Visual: 4 ícones grandes, uma linha de texto cada.

### Slide 4 — Como funciona um atendimento (Modelagem)
- **Mensagem:** do contato à resolução, com a pessoa só onde importa.
- Fluxo: Contato → Triagem (regras + IA Jev) → Visão 360 do pedido → Veracidade → Decide: **automático** (responde
  com dados) ou **pessoa** (com motivos) → Ação do catálogo → Aprovação → Execução → Validação.
- Visual: fluxograma horizontal; use o diagrama de `docs/architecture/COLEGA_DIGITAL.md` como base.

### Slide 5 — O que é automático e o que é da pessoa (Modelagem)
- **Mensagem:** a decisão é explicável e configurável pelo time.
- Esquerda "Agente resolve": onde está meu pedido, atraso, status de reembolso, dúvida, elogio, chamado na transportadora.
- Direita "Pessoa decide": Reclame Aqui, urgência alta, recontato, pedido > R$ 300, atraso 7+ dias, reclamação que os
  dados não sustentam, reenvio/troca/reembolso/cancelamento.
- Rodapé: **reclamação falsa nunca é negada pelo agente** — vai para a pessoa com as evidências (ex.: foto anterior à entrega).

### Slide 6 — Autonomia de verdade: o turno do agente (Modelagem + Aderência)
- **Mensagem:** ninguém precisa mandar; ele trabalha em turnos.
- Lista: processa a caixa · lembra o cliente antes de encerrar · encerra por inatividade · alerta SLA estourado ·
  cobra aprovação parada · detecta pico por transportadora e abre incidente · manda o resumo do dia.
- Visual: print do canal do time / Telegram com mensagem de aprovação e botões ✅ ❌.

### Slide 7 — Resultados na demo (Modelagem)
- **Mensagem:** números da simulação, com premissas editáveis.
- KPIs grandes: **≈ 38%** dos atendimentos resolvidos sozinho · **≈ 45%** do esforço manual poupado (≈ 171 h no
  período) · **≈ 99%** de acurácia de intenção · **98%** das reclamações falsas sinalizadas · recontato **12,7%** medido
  e atacado com aviso proativo.
- **Obrigatório no slide:** "dados sintéticos · premissas de tempo editáveis em Configurações". Não apresentar como
  resultado de produção.

### → DEMO AO VIVO (3 min) — seguir `docs/pitch/ROTEIRO_DEMO.md`
1. Visão do Atendimento → **Rodar turno / Avançar 12 h**.
2. Caixa unificada → conversa de avaria (foto, veracidade, evidências).
3. Propor reenvio → o agente levanta a mão.
4. **Aprovar pelo Telegram no celular** → executa e encerra.
5. Prevenção de recontato → aviso proativo.
Plano B: vídeo gravado da demo + prints, caso a rede ou o Telegram falhem.

### Slide 8 — Pensamos 360°, provamos em uma frente (Conceito + Adaptabilidade)
- **Mensagem:** o mesmo colega cobre a área toda; trocar simulador por integração real troca só o conector.
- Tabela resumida das frentes: Atendimento ✅ · Logística ✅ · Pós-venda ✅ · Prevenção ✅ · Estoque ✅ ·
  Reputação 🟡 · Gestão ✅ (fonte: `COLEGA_DIGITAL.md`).
- Adaptabilidade: matriz automático × pessoa editável na UI · canal do time trocável (app/Telegram/Slack) ·
  modelos de IA trocáveis com fallback determinístico · conectores configuráveis (WhatsApp Cloud API, e-mail, RA HugMe, ERP).

### Slide 9 — Transparência sobre IA (Modelagem: "verificou e corrigiu")
- **Mensagem:** IA onde ajuda, regra onde precisa de garantia — e tudo verificado.
- Na construção: como a IA foi usada, o que foi revisado e corrigido (exemplos reais de `docs/IA_TRANSPARENCIA.md`:
  vinculação de pedido errada corrigida para ~98%, falso positivo "não recebi atualização", mensagens com "Pedido"
  solto, duplicação de dados).
- No produto: Jev só desempata com confiança ≥ 0,7 · resumo de caso não pode inventar números · custo de cada chamada
  registrado · sem IA, tudo continua funcionando com regras · DeepSeek bloqueado · ações críticas sempre com pessoa.
- **Revisar este slide com o time**: descrever com honestidade como a IA foi usada em todo o projeto.

### Slide 10 — Próximos passos e pedido
- Integrar canais reais (WhatsApp Cloud API, e-mail, RA HugMe) e ERP/transportadoras · piloto com um grupo do
  atendimento por 2–4 semanas · medir tempo de resposta, recontato e horas poupadas reais · liberar automações aos
  poucos pela matriz.
- Fechamento: frase central da seção 1.

## 4. Limitações para dizer sem rodeio
- Execução de ações é **simulada**; dados do atendimento são **sintéticos**.
- Slack só recebe avisos; aprovar por botão funciona no Telegram e no app.
- Chamadas de chat do AI Proxy informam tokens, não preço; o Jev informa custo estimado.

## 5. Perguntas prováveis e respostas curtas
| Pergunta | Resposta |
|---|---|
| E se a IA errar? | Ela não decide nada crítico. Confiança baixa vai para pessoa; toda decisão tem motivo e auditoria. |
| Como evita negar cliente honesto? | O agente nunca nega; reclamação inconsistente vai para pessoa com evidências. |
| Quanto custa rodar? | A maior parte é regra (custo zero); IA só no desempate (Jev, frações de centavo) e no resumo. Custo fica registrado. |
| Escala para outras áreas? | Sim: mesmo motor de políticas, aprovações e canal; estoque e logística já usam. |
| Por que Telegram? | Porque é onde o time conversa; o mesmo canal pode ser Slack ou o próprio app. |

## 6. Direção visual
- Cores Gocase: azul `#005BAA` (principal), coral `#F37053` e primrose `#E9ED9A` (destaques); fundo neutro.
- Pouco texto por slide (máx. ~5 linhas); números grandes; prints reais do produto em vez de ilustrações genéricas.
- Mesma linguagem do time: "atendimento", "caso", "levantar a mão", "aprovar no Telegram".
- Selo "dados sintéticos" discreto em todo slide com número.
