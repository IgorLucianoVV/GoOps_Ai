"""Matriz "resolve sozinho × precisa de uma pessoa" e próximas ações recomendadas.

Cada decisão traz os motivos (para o atendente e para a auditoria). A matriz é configurável em
Configurações › Atendimento; reclamações que pedem reparação nunca são resolvidas sem pessoa, e ações em áreas críticas
(pedidos, pagamentos, estoque, clientes) continuam exigindo aprovação humana pela política de ações.
"""
from __future__ import annotations

from typing import Any, Dict, List

from goops_core.policies import ACTION_CATALOG, evaluate_action_policy
from goops_core.support_catalog import INTENTS, URGENCY_LEVELS


def _action(action_type: str, why: str, policies: Dict[str, Any], auto: bool = False) -> Dict[str, Any]:
    pol = evaluate_action_policy(action_type, policies)
    return {"action_type": action_type, "title": ACTION_CATALOG[action_type]["title"], "why": why,
            "requires_approval": pol["requires_approval"], "risk": pol["risk"], "auto": auto and not pol["requires_approval"]}


def recommend_actions(intent: str, ver: Dict[str, Any], ctx: Dict[str, Any], cfg: Dict[str, Any],
                      policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    label = ver.get("label")
    order = ctx.get("order")
    if not order:
        return []
    acts: List[Dict[str, Any]] = []
    delivered, eta, received = ctx.get("delivered_at"), ctx.get("eta"), ctx.get("received_at")
    late_open = (not delivered) and eta is not None and received is not None and eta < received
    if intent == "atraso_entrega" and label == "consistente":
        if late_open:
            acts.append(_action("support_carrier_ticket", "Atraso confirmado: cobrar a transportadora pela entrega.",
                                policies, auto=cfg.get("auto_carrier_ticket", True)))
        if (ctx.get("delay_days") or 0) >= 7:
            acts.append(_action("support_reshipment", "Atraso de 7+ dias: oferecer reenvio.", policies))
    elif intent == "nao_recebido":
        acts.append(_action("support_carrier_ticket", "Solicitar comprovante de entrega / investigar extravio.",
                            policies, auto=cfg.get("auto_carrier_ticket", True)))
        if label == "consistente":
            acts.append(_action("support_reshipment", "Não recebimento consistente com os dados: reenvio.", policies))
    elif intent == "avaria":
        if label == "consistente":
            acts.append(_action("support_reshipment", "Avaria consistente com as evidências: reenviar o produto.", policies))
            acts.append(_action("support_carrier_ticket", "Registrar avaria no transporte com a transportadora.", policies,
                                auto=cfg.get("auto_carrier_ticket", True)))
    elif intent in ("defeito", "produto_errado") and label == "consistente":
        acts.append(_action("support_exchange", "Reclamação consistente: gerar troca.", policies))
    elif intent == "troca_devolucao":
        acts.append(_action("support_exchange", "Solicitação de troca/devolução do cliente.", policies))
    elif intent == "cancelamento":
        if not ctx.get("shipped_at") and not delivered:
            acts.append(_action("support_cancel_order", "Pedido ainda não enviado: cancelamento possível.", policies))
        elif not delivered:
            acts.append(_action("support_cancel_order", "Pedido em trânsito: cancelar exige recusa/retorno da entrega.",
                                policies))
    return acts


def decide(*, intent: str, confidence: float, channel: str, urgency: str, is_repeat: bool, injection: bool,
           ctx: Dict[str, Any], ver: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    meta = INTENTS.get(intent, INTENTS["outros"])
    if injection:
        reasons.append("Mensagem com tentativa de manipulação de instruções (tratada como dado; revisão humana).")
    if intent not in cfg.get("auto_intents", []):
        reasons.append(f"Intenção '{meta['label']}' exige análise ou ação de uma pessoa.")
    if confidence < float(cfg.get("min_confidence", 0.6)):
        reasons.append(f"Intenção incerta (confiança {confidence:.0%}).")
    if channel in cfg.get("human_channels", []):
        reasons.append("Canal público (Reclame Aqui): resposta revisada por uma pessoa.")
    if URGENCY_LEVELS.index(urgency) >= URGENCY_LEVELS.index(cfg.get("human_from_urgency", "alta")):
        reasons.append(f"Urgência {urgency}.")
    if is_repeat and cfg.get("repeat_to_human", True):
        reasons.append("Recontato: a primeira resposta não resolveu.")
    total = (ctx.get("order") or {}).get("order_total")
    if meta["claim"] and total and float(total) > float(cfg.get("claim_value_human_brl", 300)):
        reasons.append(f"Reclamação em pedido acima de R$ {float(cfg.get('claim_value_human_brl', 300)):.0f}.")
    if intent == "atraso_entrega" and (ctx.get("delay_days") or 0) >= 7:
        reasons.append("Atraso crítico (7+ dias).")
    if ver.get("label") == "inconsistente":
        reasons.append("Dados não sustentam a reclamação: verificação humana com as evidências.")
    status = "pending_human" if reasons else "auto_resolved"
    if not reasons and meta["order_required"] and not ctx.get("order"):
        status = "awaiting_customer"   # resposta automática pedindo o número do pedido
    return {"routing": "human" if reasons else "auto", "status": status,
            "reasons": reasons or ["Assunto informativo respondido com dados governados (sem ação crítica)."]}
