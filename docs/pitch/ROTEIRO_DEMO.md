# Roteiro de demonstração (3 minutos)

**Público:** time de Atendimento da Gocase (atendentes e coordenação). **Dor:** milhares de contatos/mês, cada um
exigindo vários sistemas; reclamações que nem sempre procedem; clientes que voltam porque ninguém avisou.

| Tempo | Mostrar | Fala |
|---|---|---|
| 0:00 | *Atendimento › Visão* | "Este é o colega digital do atendimento. ≈38% dos atendimentos ele resolve sozinho; nos outros, entrega o caso pronto. ≈45% do esforço manual poupado (premissas editáveis)." |
| 0:30 | **Rodar turno agora** / **Avançar 12 h** | "Sem ninguém pedir, ele processa a caixa, lembra o cliente, encerra por inatividade, avisa o time quando o SLA estoura e, se uma transportadora concentra reclamações, abre incidente e chama os agentes de Investigação e Resolução." |
| 1:00 | *Caixa unificada* → conversa de avaria | "Uma conversa por cliente, como no WhatsApp. O agente pediu a foto, o cliente mandou, a veracidade foi recalculada. Aqui estão as evidências — inclusive quando a foto é anterior à entrega." |
| 1:40 | Aba **Ações** → Propor reenvio | "Reenvio mexe em pedido e estoque: ele não decide sozinho, levanta a mão." |
| 2:00 | **Telegram** no celular (ou *Canal do time*) → ✅ Aprovar | "A aprovação chega onde o time já conversa. Aprovei pelo celular; o agente executou e encerrou o atendimento." |
| 2:30 | *Prevenção de recontato* | "E ataca a causa: mostra os contatos evitáveis e propõe avisar os clientes com pedido em risco antes que eles chamem." |
| 2:40 *(bônus, se houver tempo)* | *Agentes de IA › Supervisor › Instruções* → editar → **Testar** → **Comparar** | "A equipe ajusta como a IA escreve sem mexer em código — e nada vai ao ar sem teste: aqui a verificação pegou um número que não estava nas evidências. Só depois a pessoa publica." |
| 2:50 | *docs/architecture/COLEGA_DIGITAL.md* | "Provamos a frente de atendimento; o mesmo colega cobre logística, pós-venda, estoque e reputação, sempre com a pessoa no controle das ações críticas." |

**Antes de apresentar:** `demo-load --scenario full`; configure o AI Proxy (Configurações › Modelos e chaves › Usar AI
Proxy Gogroup) e o Telegram (Configurações › Canal do time); vincule sua conta no Canal do time; ligue o turno no
agendador ou use o botão. Para o bônus de agentes, deixe um agente com instruções criado e testado (Agentes de IA › Novo agente › exemplo "Vigia de NPS por transportadora").
