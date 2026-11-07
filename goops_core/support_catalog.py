"""Catálogo do Atendimento ao Cliente (Desafio 1): intenções, canais e premissas de esforço manual.

Dados puros (sem dependências) compartilhados pela configuração em tela, pela triagem e pelos indicadores.
`manual_minutes` e `systems` descrevem o atendimento 100% manual de referência — quantos sistemas/portais um
atendente precisa abrir e quanto tempo leva — e servem para estimar o esforço poupado pela automação.
São PREMISSAS editáveis em Configurações › Atendimento, não medições.
"""
from __future__ import annotations

CHANNELS = {
    "whatsapp": "WhatsApp",
    "email": "E-mail",
    "reclameaqui": "Reclame Aqui",
}

SYSTEMS = {
    "pedidos": "Sistema de pedidos",
    "transportadora": "Portal da transportadora",
    "chamados": "Abertura de chamado (transportadora)",
    "erp_trocas": "ERP · trocas e reenvios",
    "financeiro": "Financeiro · reembolsos",
    "catalogo": "Catálogo de produtos",
    "crm": "CRM / histórico do cliente",
}

# claim: reclamação que pede reparação (exige verificação de veracidade antes de agir)
# order_required: precisa de um pedido vinculado para ser tratada
# auto_default: elegível à resolução automática por padrão (resposta informativa com dados governados)
INTENTS = {
    "onde_esta_pedido": {"label": "Onde está meu pedido", "claim": False, "order_required": True, "auto_default": True,
                         "manual_minutes": 6, "systems": ["crm", "pedidos", "transportadora"]},
    "atraso_entrega": {"label": "Atraso na entrega", "claim": True, "order_required": True, "auto_default": True,
                       "manual_minutes": 12, "systems": ["crm", "pedidos", "transportadora", "chamados"]},
    "nao_recebido": {"label": "Pedido não recebido (consta entregue)", "claim": True, "order_required": True,
                     "auto_default": False, "manual_minutes": 25,
                     "systems": ["crm", "pedidos", "transportadora", "chamados", "erp_trocas"]},
    "avaria": {"label": "Produto avariado", "claim": True, "order_required": True, "auto_default": False,
               "manual_minutes": 22, "systems": ["crm", "pedidos", "transportadora", "chamados", "erp_trocas"]},
    "defeito": {"label": "Defeito de fabricação", "claim": True, "order_required": True, "auto_default": False,
                "manual_minutes": 18, "systems": ["crm", "pedidos", "catalogo", "erp_trocas"]},
    "produto_errado": {"label": "Produto ou personalização errada", "claim": True, "order_required": True,
                       "auto_default": False, "manual_minutes": 18, "systems": ["crm", "pedidos", "catalogo", "erp_trocas"]},
    "troca_devolucao": {"label": "Troca ou devolução", "claim": False, "order_required": True, "auto_default": False,
                        "manual_minutes": 14, "systems": ["crm", "pedidos", "erp_trocas"]},
    "cancelamento": {"label": "Cancelamento", "claim": False, "order_required": True, "auto_default": False,
                     "manual_minutes": 10, "systems": ["crm", "pedidos", "financeiro"]},
    "status_reembolso": {"label": "Status de reembolso", "claim": False, "order_required": True, "auto_default": True,
                         "manual_minutes": 7, "systems": ["crm", "pedidos", "financeiro"]},
    "duvida_produto": {"label": "Dúvida sobre produto / pré-venda", "claim": False, "order_required": False,
                       "auto_default": True, "manual_minutes": 5, "systems": ["catalogo"]},
    "elogio": {"label": "Elogio", "claim": False, "order_required": False, "auto_default": True,
               "manual_minutes": 2, "systems": ["crm"]},
    "outros": {"label": "Outros assuntos", "claim": False, "order_required": False, "auto_default": False,
               "manual_minutes": 8, "systems": ["crm"]},
}

URGENCY_LEVELS = ["baixa", "media", "alta", "critica"]
STATUSES = {
    "new": "Novo",
    "auto_resolved": "Resolvido automaticamente",
    "pending_human": "Na fila humana",
    "awaiting_customer": "Aguardando cliente",
    "pending_approval": "Aguardando aprovação de ação",
    "resolved": "Resolvido",
}

DEFAULT_CONFIG = {
    # Matriz "resolve sozinho × precisa de uma pessoa"
    "auto_intents": [k for k, v in INTENTS.items() if v["auto_default"]],
    "min_confidence": 0.6,                 # abaixo disso a intenção é incerta → pessoa
    "human_channels": ["reclameaqui"],     # canais públicos sempre com revisão humana
    "human_from_urgency": "alta",          # urgência a partir da qual vai para pessoa
    "repeat_to_human": True,               # recontato (cliente voltou pelo mesmo assunto) → pessoa
    "claim_value_human_brl": 300.0,        # reclamações com pedido acima deste valor → pessoa
    # Veracidade (0–100): faixas
    "veracity_consistent_min": 70,
    "veracity_inconsistent_max": 39,
    # Ações automáticas sem aprovação (a política continua valendo para as críticas)
    "auto_carrier_ticket": True,
    # Prevenção de recontato
    "recontact_window_days": 7,
    # Conversa (padrão de mercado: chat contínuo por cliente e canal, com atendimentos dentro)
    "reopen_window_hours": 24,             # "obrigado" até X h após o encerramento não abre novo atendimento
    "inactivity_close_hours": 48,          # atendimento aguardando o cliente é encerrado após X h sem resposta
    "continue_window_hours": 72,           # (histórico da demo) mensagem até X h após a anterior continua o atendimento
    # IA (opcional; sem modelo, regras determinísticas)
    "llm_classify_low_confidence": True,   # Jev (AI Proxy) desempata intenções ambíguas — só com token configurado
    "llm_summary": True,                   # resumo do caso para quem assume — só com modelo configurado
    "llm_reply": False,
    # Turno autônomo do agente
    "sla_first_response_hours": 4,         # sem resposta humana após X h → alerta no canal do time
    "reminder_before_close_hours": 12,     # lembrete ao cliente X h antes de encerrar por inatividade
    "spike_min_contacts": 5,               # reclamações de entrega da mesma transportadora em 48 h → incidente
    # Premissas de esforço manual (minutos por contato), editáveis
    "manual_minutes": {k: v["manual_minutes"] for k, v in INTENTS.items()},
    "auto_minutes": 1.0,                   # revisão residual de um contato resolvido automaticamente
}
