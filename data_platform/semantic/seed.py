"""Catálogo semântico inicial (Corporate + Domain)."""
from __future__ import annotations

NPS_DEF = {"type": "nps", "score_field": "score", "promoter_min": 9, "detractor_max": 6, "valid_min": 0,
           "valid_max": 10, "time_field": "evaluation_date"}
NPS_DIMS = ["eval_month", "state", "product_line", "carrier", "shipping_type"]

CORPORATE_METRICS = [
    {"metric_key": "METRIC_NPS_001", "name": "Net Promoter Score (NPS)",
     "description": "NPS oficial corporativo calculado sobre avaliações válidas (nota inteira entre 0 e 10).",
     "formula_text": "NPS = ((Promotores - Detratores) / Total de avaliações válidas) * 100; Promotor: 9-10; "
                     "Neutro: 7-8; Detrator: 0-6; sem avaliações válidas => nulo",
     "formula_definition": NPS_DEF, "unit": "pontos (-100 a +100)", "dimensions": NPS_DIMS,
     "source_datasets": ["gold_nps_analytics"], "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_PROMOTER_RATE_001", "name": "Taxa de Promotores",
     "description": "Percentual de avaliações válidas com nota 9 ou 10.",
     "formula_text": "Promotores / Avaliações válidas * 100",
     "formula_definition": {"type": "rate", "numerator": {"field": "score_category", "op": "eq", "value": "promoter"},
                            "time_field": "evaluation_date"},
     "unit": "%", "dimensions": NPS_DIMS, "source_datasets": ["gold_nps_analytics"], "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_DETRACTOR_RATE_001", "name": "Taxa de Detratores",
     "description": "Percentual de avaliações válidas com nota de 0 a 6.",
     "formula_text": "Detratores / Avaliações válidas * 100",
     "formula_definition": {"type": "rate", "numerator": {"field": "score_category", "op": "eq", "value": "detractor"},
                            "time_field": "evaluation_date"},
     "unit": "%", "dimensions": NPS_DIMS, "source_datasets": ["gold_nps_analytics"], "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_AVG_SCORE_001", "name": "Nota média de avaliação",
     "description": "Média aritmética das notas válidas (0-10).", "formula_text": "média(nota)",
     "formula_definition": {"type": "mean", "field": "score", "time_field": "evaluation_date"},
     "unit": "nota (0-10)", "dimensions": NPS_DIMS, "source_datasets": ["gold_nps_analytics"],
     "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_EVALUATIONS_001", "name": "Total de avaliações válidas",
     "description": "Quantidade de avaliações válidas.", "formula_text": "contagem(avaliações válidas)",
     "formula_definition": {"type": "count", "time_field": "evaluation_date"}, "unit": "avaliações",
     "dimensions": NPS_DIMS, "source_datasets": ["gold_nps_analytics"], "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_LATE_DELIVERY_RATE_001", "name": "Taxa de entregas atrasadas",
     "description": "Percentual de entregas concluídas após a data prevista (sem tolerância).",
     "formula_text": "Entregas com data_entrega > previsao_entrega / Entregas concluídas * 100",
     "formula_definition": {"type": "rate", "numerator": {"field": "is_late", "op": "is_true"},
                            "base_filter": {"field": "actual_delivery_date", "op": "not_null"},
                            "time_field": "shipping_date"},
     "unit": "%", "dimensions": ["ship_month", "carrier", "shipping_type", "state"],
     "source_datasets": ["gold_delivery_performance"], "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_DELIVERY_LEAD_TIME_001", "name": "Prazo médio envio→entrega",
     "description": "Média de dias entre envio e entrega para entregas concluídas.",
     "formula_text": "média(data_entrega - data_envio) em dias",
     "formula_definition": {"type": "mean", "field": "lead_time_ship_to_delivery_days", "time_field": "shipping_date"},
     "unit": "dias", "dimensions": ["ship_month", "carrier", "shipping_type", "state"],
     "source_datasets": ["gold_delivery_performance"], "owner": "Data Owner Corporativo"},
    {"metric_key": "METRIC_DELIVERY_DAYS_001", "name": "Prazo médio de entrega (pedido→entrega)",
     "description": "Média de dias entre pedido e entrega. Usa as datas quando disponíveis; caso a fonte informe apenas "
                    "'Dias de entrega' (ex.: planilha Gocase), usa o valor informado (campo lead_time_source).",
     "formula_text": "média(data_entrega - data_pedido) ou média(dias de entrega informados) em dias",
     "formula_definition": {"type": "mean", "field": "lead_time_order_to_delivery_days", "time_field": "order_date"},
     "unit": "dias", "dimensions": ["ship_month", "carrier", "shipping_type", "state"],
     "source_datasets": ["gold_delivery_performance"], "owner": "Data Owner Corporativo"},
]

DOMAIN_METRICS = [
    {"metric_key": "CX_NPS_COMMENTED_001", "domain": "cx", "name": "NPS de avaliações com comentário",
     "description": "Variante de domínio CX: NPS calculado APENAS sobre avaliações que possuem comentário. "
                    "NÃO é equivalente ao NPS corporativo (METRIC_NPS_001).",
     "formula_text": "Mesma fórmula do NPS, filtrando avaliações com comentário",
     "formula_definition": NPS_DEF, "filters": [{"field": "has_comment", "op": "is_true"}],
     "unit": "pontos (-100 a +100)", "dimensions": NPS_DIMS, "source_datasets": ["gold_nps_analytics"],
     "related_corporate_metric": "METRIC_NPS_001", "owner": "CX Domain Owner"},
    {"metric_key": "LOG_ON_TIME_TOLERANCE_001", "domain": "logistics", "name": "Entregas no prazo (tolerância 1 dia)",
     "description": "Métrica operacional de Logística: considera no prazo entregas com até 1 dia de atraso. "
                    "Usa critério diferente da métrica corporativa METRIC_LATE_DELIVERY_RATE_001.",
     "formula_text": "Entregas com atraso <= 1 dia / Entregas concluídas * 100",
     "formula_definition": {"type": "rate", "numerator": {"field": "delay_days", "op": "le", "value": 1},
                            "base_filter": {"field": "actual_delivery_date", "op": "not_null"},
                            "time_field": "shipping_date"},
     "unit": "%", "dimensions": ["ship_month", "carrier", "shipping_type", "state"],
     "source_datasets": ["gold_delivery_performance"], "related_corporate_metric": "METRIC_LATE_DELIVERY_RATE_001",
     "owner": "Logistics Domain Owner"},
    {"metric_key": "PRD_COMPLAINT_RATE_001", "domain": "products", "name": "Taxa de reclamação por produto",
     "description": "Percentual de avaliações cujo comentário contém tema negativo (dicionário de temas v1.0).",
     "formula_text": "Avaliações com tema negativo / Avaliações válidas * 100",
     "formula_definition": {"type": "rate", "numerator": {"field": "has_negative_theme", "op": "is_true"},
                            "time_field": "evaluation_date"},
     "unit": "%", "dimensions": ["eval_month", "product_line", "state"], "source_datasets": ["gold_nps_analytics"],
     "owner": "Products Domain Owner"},
]

DOMAINS = [
    ("corporate", "Corporativo", "Definições oficiais compartilhadas por toda a empresa"),
    ("cx", "Experiência do cliente", "Satisfação, NPS, comentários, reclamações"),
    ("logistics", "Logística", "Prazos, atrasos, transportadoras, fretes, risco de atraso"),
    ("products", "Produtos", "Qualidade, avaliações e reclamações por produto"),
    ("atendimento", "Atendimento ao cliente", "Contatos por WhatsApp, e-mail e Reclame Aqui: triagem, veracidade, "
     "automação e prevenção de recontato"),
    ("finance", "Financeiro (preparado)", "Domínio preparado para expansão futura — sem dados nesta versão"),
]
