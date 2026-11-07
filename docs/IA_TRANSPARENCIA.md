# Transparência sobre o uso de IA

## Como a IA foi usada para CONSTRUIR o projeto

O GoOps foi desenvolvido com apoio de um assistente de IA (**Claude, da Anthropic**, no modo Cowork) trabalhando
sobre o repositório: análise do código, implementação, testes automatizados e verificação visual das telas. As
decisões de produto (escopo do Desafio 1, chat estilo WhatsApp, dois botões em vez de "enviar e encerrar", canal do
time) foram tomadas pela pessoa responsável, a partir de propostas e perguntas da IA.

### O que foi conferido e corrigido (exemplos reais)

| O que a IA entregou / encontrou | Como foi verificado | Correção |
|---|---|---|
| Um teste de CSRF existente falhava | Rodando a suíte (77 ok, 1 falha) | O teste fazia 2 logins e usava o token antigo; corrigido o teste |
| Conector HTTP permitia enviar `SECRET_KEY` para um servidor externo | Revisão de segurança | Lista de variáveis permitidas + bloqueio de hosts internos + sem redirecionamento |
| Vínculo contato → pedido escolhia o pedido errado (≈76% de acerto) | Comparação com o gabarito sintético | Pontuação por coerência com o assunto e produto citado → ≈98% |
| "Não recebi atualização" era lido como "pedido não recebido" | Matriz de confusão das intenções | Regra com exceção; acerto de intenção ≈99% na base sintética |
| Retenção da Bronze quebrava com fontes de setor | Teste de retenção falhou após a mudança | Chave natural por receita; fontes sem chave nunca são expurgadas |
| Respostas do chat apareciam fora de ordem (relógio do servidor × dos dados) | Inspeção das conversas | Falas datadas no relógio dos dados |
| Mensagens com "Pedido" solto no fim | Captura de tela enviada pela pessoa | Limpeza do texto no gerador |
| Recontato inflado por cobranças com o atendimento aberto | Pesquisa de mercado (Zendesk/Intercom) | Modelo de conversa: continuação × novo atendimento |

Cada entrega passou por: suíte de testes (100+ testes), build do frontend e captura de tela das telas alteradas.

## Como a IA é usada DENTRO do produto

| Onde | IA | Plano B (sem IA) | Guarda-corpos |
|---|---|---|---|
| Intenção de mensagens ambíguas | **Jev** (AI Proxy Gogroup, decisão tipada com probabilidade) | Regras explicáveis | Confiança < 0,7 → pessoa; texto do cliente mascarado (telefone/e-mail/CPF) e tratado como dado |
| Resumo do caso para quem assume | LLM nível 2 (ex.: AI Proxy `gpt-6-luna`) | Resumo por regras com os fatos | O modelo não pode introduzir números/datas que não estejam nos fatos (validação) |
| Reescrever resposta ao cliente | LLM nível 2 (sob demanda) | Resposta montada com dados do pedido | Mesma validação; não promete reparação |
| Pergunte ao GoOps / narrativas de incidentes | LLM com ferramentas governadas | Motor determinístico | Só métricas oficiais; citações |
| Agentes com instruções (criados pela equipe) | LLM com ferramentas governadas escolhidas | Resumo determinístico, sem alerta | Regras fixas + missão; IA só sinaliza alerta; incidente/ação pelo código e ação com aprovação |

As **instruções** de cada tarefa de IA são editáveis em *Agentes de IA* (versionadas e auditadas); as regras fixas de
cada tarefa e o guarda do roteador não são editáveis. Toda mudança passa por rascunho e pode ser **testada antes de
publicar** (prompt exato visível + verificação de números fora das evidências); agentes personalizados têm teste sem
efeito colateral, critérios de aceite e rastro passo a passo de cada execução. A aba **Como decide** mostra as
regras e parâmetros em vigor de cada agente, e a **validação ponta a ponta** recalcula cada decisão sobre dados gerados.

**Números nunca vêm do modelo:** métricas, veracidade, roteamento e ações são calculados por regras auditáveis.
Custos e tokens de cada chamada ficam em `llm_calls` (o AI Proxy informa tokens; o Jev informa custo estimado).
DeepSeek é bloqueado conforme as regras do evento; o token do proxy fica no cofre cifrado (nunca no código).

## Limitações declaradas

* Os contatos de atendimento são **sintéticos** (gerados a partir dos pedidos), com reclamações falsas plantadas.
  A acurácia exibida é medida contra o gabarito do próprio gerador: indica coerência das regras, não desempenho real.
* Ações em sistemas externos (ERP, transportadora, financeiro, envio ao cliente) são **simuladas**.
* Desfechos de atendimentos antigos da carga inicial são **simulados** (sinalizados como tal).
