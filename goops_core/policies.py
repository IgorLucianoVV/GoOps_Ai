"""Políticas de ações operacionais (catálogo declarativo + regras de aprovação).

Regra central: ações com impacto em pagamentos, pedidos, estoque ou clientes exigem
aprovação humana explícita por um papel autorizado no domínio da ação.
Agentes nunca aprovam ações. A execução nesta versão é SEMPRE simulada.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .errors import ValidationError
from .permissions import Principal, can_access_domain, has_permission

CRITICAL_AREAS = {"pagamentos", "pedidos", "estoque", "clientes"}

ACTION_CATALOG: Dict[str, dict] = {
    "carrier_reallocation": {
        "title": "Realocar volume de transportadora",
        "domain": "logistics",
        "impacted_areas": ["pedidos", "logistica"],
        "risk": "high",
        "params": {"carrier": str, "states": list, "target_carrier": str, "share_pct": (int, float)},
    },
    "proactive_customer_contact": {
        "title": "Contato proativo com clientes afetados",
        "domain": "cx",
        "impacted_areas": ["clientes"],
        "risk": "medium",
        "params": {"carrier": str, "states": list, "segment": str},
    },
    "product_quality_review": {
        "title": "Abrir revisão de qualidade de produto",
        "domain": "products",
        "impacted_areas": ["produtos"],
        "risk": "low",
        "params": {"product_line": str, "themes": list},
    },
    "regional_logistics_review": {
        "title": "Revisão logística regional",
        "domain": "logistics",
        "impacted_areas": ["logistica"],
        "risk": "low",
        "params": {"states": list},
    },
    # Ações genéricas para setores criados na interface (agente "Tarefa com ação")
    "sector_operational_review": {
        "title": "Revisão operacional do setor",
        "domain": "corporate",
        "impacted_areas": ["operacao"],
        "risk": "low",
        "params": {"sector": str, "metric": str, "segment": str, "note": str},
    },
    "sector_customer_contact": {
        "title": "Contato com clientes do segmento afetado",
        "domain": "corporate",
        "impacted_areas": ["clientes"],
        "risk": "medium",
        "params": {"sector": str, "metric": str, "segment": str, "message": str},
    },
    # ---------- Atendimento ao Cliente (Desafio 1) ----------
    # Cada ação substitui um passo manual feito em outro sistema/portal. Execução sempre simulada nesta versão.
    "support_carrier_ticket": {
        "title": "Abrir chamado na transportadora",
        "domain": "atendimento",
        "impacted_areas": ["logistica"],
        "risk": "low",
        "params": {"contact_id": str, "order_id": str, "carrier": str, "reason": str},
    },
    "support_reshipment": {
        "title": "Reenviar pedido",
        "domain": "atendimento",
        "impacted_areas": ["pedidos", "estoque", "clientes"],
        "risk": "high",
        "params": {"contact_id": str, "order_id": str, "reason": str, "note": str},
    },
    "support_exchange": {
        "title": "Gerar troca",
        "domain": "atendimento",
        "impacted_areas": ["pedidos", "estoque", "clientes"],
        "risk": "medium",
        "params": {"contact_id": str, "order_id": str, "reason": str, "note": str},
    },
    "support_refund": {
        "title": "Reembolsar cliente",
        "domain": "atendimento",
        "impacted_areas": ["pagamentos", "clientes"],
        "risk": "high",
        "params": {"contact_id": str, "order_id": str, "reason": str, "amount": (int, float), "note": str},
    },
    "support_cancel_order": {
        "title": "Cancelar pedido",
        "domain": "atendimento",
        "impacted_areas": ["pedidos", "pagamentos", "clientes"],
        "risk": "medium",
        "params": {"contact_id": str, "order_id": str, "reason": str, "note": str},
    },
    "support_proactive_notice": {
        "title": "Aviso proativo de atraso aos clientes",
        "domain": "atendimento",
        "impacted_areas": ["clientes"],
        "risk": "low",
        "params": {"segment": str, "orders": int, "message": str},
    },
    "data_quality_fix": {
        "title": "Correção de qualidade de dados",
        "domain": "corporate",
        "impacted_areas": ["dados"],
        "risk": "low",
        "params": {"datasets": list, "rules": list},
    },
}

APPROVER_ROLES = ["admin", "data_owner", "domain_owner"]


def validate_action_params(action_type: str, params: dict) -> None:
    spec = ACTION_CATALOG.get(action_type)
    if spec is None:
        raise ValidationError(f"Tipo de ação desconhecido: {action_type}")
    for key, value in (params or {}).items():
        if key not in spec["params"]:
            raise ValidationError(f"Parâmetro não permitido para {action_type}: {key}")
        if value is not None and not isinstance(value, spec["params"][key]):
            raise ValidationError(f"Tipo inválido para parâmetro {key}")


def evaluate_action_policy(action_type: str, overrides: Optional[dict] = None) -> dict:
    """Política efetiva. `overrides` vem da configuração em tela (seção 'policies'); áreas críticas
    SEMPRE exigem aprovação, independentemente da configuração."""
    spec = ACTION_CATALOG.get(action_type)
    if spec is None:
        raise ValidationError(f"Tipo de ação desconhecido: {action_type}")
    critical: List[str] = sorted(set(spec["impacted_areas"]) & CRITICAL_AREAS)
    ov = (overrides or {}).get(action_type) or {}
    requires = bool(critical) or bool(ov.get("requires_approval", False))
    reasons = ([f"Impacta área crítica: {', '.join(critical)}"] if critical
               else (["Aprovação exigida pela configuração de políticas."] if requires
                     else ["Ação interna sem impacto em áreas críticas; ainda assim registrada e auditada."]))
    return {
        "requires_approval": requires,
        "approver_roles": list(ov.get("approver_roles") or APPROVER_ROLES),
        "customized": bool(ov),
        "risk": spec["risk"],
        "impacted_areas": spec["impacted_areas"],
        "domain": spec["domain"],
        "reasons": reasons,
    }


def can_approve(principal: Principal, action_type: str, overrides: Optional[dict] = None) -> bool:
    if principal.kind != "user":
        return False  # agentes e sistema nunca aprovam
    policy = evaluate_action_policy(action_type, overrides)
    if principal.role not in policy["approver_roles"]:
        return False
    return has_permission(principal, "operations:approve") and can_access_domain(principal, policy["domain"])
