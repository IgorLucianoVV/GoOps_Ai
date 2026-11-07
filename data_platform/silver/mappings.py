"""Mapeamentos versionados Fonte -> Silver, com PERFIS por formato de origem.

O conjunto de campos canônicos (MAPPINGS) é único por entidade; cada perfil apenas define de onde
cada campo vem ("from"), o tipo e, quando necessário, o grão e a chave natural da fonte. Assim,
fontes heterogêneas produzem exatamente o mesmo schema Silver.

Chave canônica de relacionamento: `order_id` (string; zeros à esquerda preservados).
  * perfil "default" (especificação / demo sintética): Pedidos "Order ID" · Avaliações "Código do Pedido" · Entregas "reference"
  * perfil "gocase_xlsx" (planilhas do case):        Pedidos "reference" · Avaliações "Order ID" · Entregas "Código do Pedido"

Tipos: id | id_int | string | upper | uf | int | float | datetime. Derivações controladas:
  {"compose": [campos de origem]}           -> concatena valores com ":" (chave composta)
  {"derive": "product_line_from_name"}      -> regra de classificação de linha de produto (v1.0)
"""
from __future__ import annotations

import copy
from typing import Any, Dict

MAPPINGS: Dict[str, Dict[str, Any]] = {
    "orders": {
        "version": "1.1",
        "dataset": "silver_orders",
        "natural_key": "order_id",
        "grain": "order",
        "fields": {
            "order_id": {"from": ["Order ID", "order_id"], "type": "id", "required": True},
            "reference": {"from": ["Order ID", "order_id"], "type": "id"},
            "order_item_id": {"from": [], "type": "id"},
            "external_order_number": {"from": [], "type": "id_int"},
            "customer_id": {"from": ["customer_id"], "type": "id"},
            "order_date": {"from": ["order_date"], "type": "datetime", "required": True},
            "product_id": {"from": ["product_id"], "type": "id"},
            "product_name": {"from": ["product_name"], "type": "string"},
            "product_line": {"from": ["product_line"], "type": "string"},
            "order_status": {"from": ["status"], "type": "string"},
            "order_total": {"from": ["total"], "type": "float"},
            "state": {"from": ["state"], "type": "uf"},
            "updated_at": {"from": ["updated_at"], "type": "datetime"},
        },
    },
    "nps": {
        "version": "1.1",
        "dataset": "silver_nps_evaluations",
        "natural_key": "evaluation_id",
        "grain": "evaluation",
        "fields": {
            "evaluation_id": {"from": ["evaluation_id"], "type": "id", "required": True},
            "order_id": {"from": ["Código do Pedido", "codigo_pedido"], "type": "id", "required": True},
            "reference": {"from": ["Código do Pedido", "codigo_pedido"], "type": "id"},
            "score": {"from": ["nota", "score"], "type": "int"},
            "comment": {"from": ["comentario", "comment"], "type": "string"},
            "evaluation_date": {"from": ["data_avaliacao", "evaluation_date"], "type": "datetime", "required": True},
            "customer_id": {"from": ["customer_id"], "type": "id"},
            "channel": {"from": ["canal"], "type": "string"},
        },
    },
    "deliveries": {
        "version": "1.1",
        "dataset": "silver_deliveries",
        "natural_key": "delivery_id",
        "grain": "delivery",
        "fields": {
            "delivery_id": {"from": ["delivery_id"], "type": "id", "required": True},
            "order_id": {"from": ["reference"], "type": "id", "required": True},
            "reference": {"from": ["reference"], "type": "id"},
            "carrier": {"from": ["transportadora", "carrier"], "type": "string"},
            "shipping_type": {"from": ["tipo_frete", "shipping_type"], "type": "string"},
            "shipping_date": {"from": ["data_envio"], "type": "datetime"},
            "estimated_delivery_date": {"from": ["previsao_entrega"], "type": "datetime"},
            "actual_delivery_date": {"from": ["data_entrega"], "type": "datetime"},
            "delivery_days": {"from": ["dias_entrega"], "type": "int"},
            "delivery_status": {"from": ["status"], "type": "string"},
            "city": {"from": ["cidade"], "type": "string"},
            "state": {"from": ["uf"], "type": "uf"},
            "updated_at": {"from": ["updated_at"], "type": "datetime"},
        },
    },
}

PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "default": {},
    "gocase_xlsx": {
        "orders": {
            "version": "gocase-1.0",
            "grain": "item",                     # 1 linha por item; agregado para 1 linha por pedido na Silver
            "natural_key": "order_item_id",
            "fields": {
                "order_id": {"from": ["reference"], "type": "id", "required": True},
                "reference": {"from": ["reference"], "type": "id"},
                "order_item_id": {"compose": ["reference", "order_id"], "type": "id"},
                "external_order_number": {"from": ["order_id"], "type": "id_int"},
                "customer_id": {"from": [], "type": "id"},
                "order_date": {"from": ["order_creation_date"], "type": "datetime", "required": True},
                "product_id": {"from": ["material_name"], "type": "string"},
                "product_name": {"from": ["material_name"], "type": "string"},
                "product_line": {"derive": "product_line_from_name", "source": "material_name", "type": "string"},
                "order_status": {"from": [], "type": "string"},
                "order_total": {"from": ["Valor"], "type": "float"},
                "state": {"from": [], "type": "uf"},
                "updated_at": {"from": [], "type": "datetime"},
            },
        },
        "nps": {
            "version": "gocase-1.0",
            "fields": {
                "evaluation_id": {"from": ["Queuereviewemailid"], "type": "id_int", "required": True},
                "order_id": {"from": ["Order ID"], "type": "id", "required": True},
                "reference": {"from": ["Order ID"], "type": "id"},
                "score": {"from": ["Rating"], "type": "int"},
                "comment": {"from": ["Body"], "type": "string"},
                "evaluation_date": {"from": ["Datecreated", "Dateadded"], "type": "datetime", "required": True},
                "customer_id": {"from": ["Client ID"], "type": "id_int"},
                "channel": {"from": ["Surveysource"], "type": "string"},
            },
        },
        "deliveries": {
            "version": "gocase-1.0",
            "fields": {
                "delivery_id": {"from": ["Código do Pedido"], "type": "id", "required": True},  # 1 entrega por pedido na fonte
                "order_id": {"from": ["Código do Pedido"], "type": "id", "required": True},
                "reference": {"from": ["Código do Pedido"], "type": "id"},
                "carrier": {"from": ["delivery_service"], "type": "string"},
                "shipping_type": {"from": ["tipo_frete"], "type": "string"},
                "shipping_date": {"from": [], "type": "datetime"},
                "estimated_delivery_date": {"from": [], "type": "datetime"},
                "actual_delivery_date": {"from": [], "type": "datetime"},
                "delivery_days": {"from": ["Dias de entrega"], "type": "int"},
                "delivery_status": {"from": [], "type": "string"},
                "city": {"from": ["City"], "type": "string"},
                "state": {"from": ["State"], "type": "uf"},
                "updated_at": {"from": [], "type": "datetime"},
            },
        },
    },
}


def mapping_for(entity: str, profile: str = "default", override: Dict[str, Any] = None) -> Dict[str, Any]:
    """Mapeamento efetivo = campos canônicos + sobreposição do perfil (embutido ou, se `override`, criado na interface)."""
    if override is None:
        if profile not in PROFILES:
            raise ValueError(f"Perfil de mapeamento desconhecido: {profile}")
        override = PROFILES[profile].get(entity, {})
    base = copy.deepcopy(MAPPINGS[entity])
    for key in ("version", "grain", "natural_key"):
        if key in override:
            base[key] = override[key]
    for field, spec in override.get("fields", {}).items():
        if field not in base["fields"]:
            raise ValueError(f"Perfil {profile} define campo não canônico: {field}")
        base["fields"][field] = spec
    base["profile"] = profile
    return base


# Regra de linha de produto (v1.0) para nomes de material do catálogo Gocase
PRODUCT_LINE_RULES = [
    (("case", "pc", "tpu", "capinha", "skin"), "Capinha"),
    (("copo",), "Copo"),
    (("garrafa",), "Garrafa"),
    (("tote", "bags", "clutch", "mala", "mochila", "backpackcd", "backpack", "travel"), "Bolsas e Malas"),
    (("necessaire", "necessairecd"), "Necessaire"),
    (("lunch", "lancheira"), "Lancheira"),
    (("gift",), "Gift"),
    (("powerbank",), "Eletrônicos"),
    (("base", "tampa", "placa", "ventosa", "acessorios", "accessories"), "Acessórios"),
]


def product_line_from_name(name: Any) -> Any:
    if not name or not str(name).strip():
        return None
    first = str(name).strip().split()[0].lower()
    for tokens, line in PRODUCT_LINE_RULES:
        if first in tokens:
            return line
    return "Outros"
