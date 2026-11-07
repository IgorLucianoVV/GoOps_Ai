"""Veracidade da reclamação: a reclamação é consistente com os dados antes de agir?

Score 0–100 a partir de fatores EXPLICÁVEIS, cada um com o efeito em pontos e a evidência usada (dados governados do
pedido, da entrega e do histórico do cliente). Faixas configuráveis em Configurações › Atendimento.

Princípio: o agente NUNCA nega uma reclamação. "Inconsistente" significa que os dados não sustentam a reclamação e o
caso vai para uma pessoa, com as evidências e a verificação recomendada (ex.: pedir foto, pedir comprovante de
entrega à transportadora). "Consistente" libera as ações de reparação (que ainda seguem a política de aprovação).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from goops_core.support_catalog import INTENTS

FRAGILE_LINES = {"Copo", "Garrafa"}


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if isinstance(v, datetime) else "—"


def assess(intent: str, *, received: datetime, ctx: Dict[str, Any], attachments: List[dict], cfg: Dict[str, Any]
           ) -> Dict[str, Any]:
    if not INTENTS.get(intent, {}).get("claim"):
        return {"score": None, "label": "nao_aplicavel", "factors": [], "checks": []}
    factors: List[Dict[str, Any]] = []
    checks: List[str] = []

    def f(points: int, factor: str, evidence: str, source: str) -> None:
        factors.append({"points": points, "factor": factor, "evidence": evidence, "source": source})

    order = ctx.get("order")
    if not order:
        f(-15, "Pedido não localizado", "Nenhum pedido vinculado pelo número informado nem pelo cliente.", "pedidos")
        checks.append("Solicitar o número do pedido ao cliente.")
    delivered: Optional[datetime] = ctx.get("delivered_at")
    eta: Optional[datetime] = ctx.get("eta")
    history = ctx.get("customer_claims_180d", 0)

    if order and intent == "atraso_entrega":
        if delivered and eta and delivered > eta:
            f(40, "Atraso confirmado", f"Entregue em {_d(delivered)}, previsão era {_d(eta)}.", "entregas")
        elif not delivered and eta and eta < received:
            days = (received - eta).days
            f(40, "Atraso confirmado", f"Ainda não entregue; previsão era {_d(eta)} ({days} dia(s) de atraso).", "entregas")
        elif not delivered and eta and eta >= received:
            f(-35, "Pedido ainda no prazo", f"Previsão de entrega em {_d(eta)}; o contato chegou antes do prazo.", "entregas")
            checks.append("Informar a previsão e o rastreio; não há atraso a reparar.")
        elif delivered and eta and delivered <= eta and delivered <= received:
            f(-30, "Entregue no prazo", f"Entregue em {_d(delivered)} (previsão {_d(eta)}).", "entregas")
            checks.append("Confirmar com o cliente se o pedido foi recebido.")
        else:
            f(0, "Prazo não avaliável", "Sem datas suficientes de previsão/entrega.", "entregas")

    elif order and intent == "nao_recebido":
        if not delivered and eta and eta < received:
            f(30, "Entrega não registrada e vencida", f"Sem registro de entrega; previsão era {_d(eta)}.", "entregas")
            checks.append("Tratar como possível extravio: chamado na transportadora.")
        elif delivered:
            f(-10, "Transportadora registra entrega", f"Entrega registrada em {_d(delivered)} por {ctx.get('carrier') or '—'}.",
              "transportadora")
            checks.append("Pedir à transportadora o comprovante de entrega (assinatura/foto/geolocalização).")
        prior = ctx.get("customer_not_received_180d", 0)
        if prior >= 1:
            f(-20, "Reincidência de 'não recebi'", f"{prior} reclamação(ões) de não recebimento nos últimos 180 dias.", "atendimento")
        elif ctx.get("customer_orders", 0) >= 2:
            f(8, "Histórico sem reclamações de não recebimento", f"{ctx.get('customer_orders')} pedidos anteriores.", "crm")

    elif order and intent in ("avaria", "defeito", "produto_errado"):
        if not delivered:
            f(-40, "Reclamação antes da entrega", "Não há registro de entrega deste pedido.", "entregas")
            checks.append("Verificar se o pedido já foi entregue antes de qualquer reparação.")
        images = [a for a in attachments or [] if a.get("type") == "image"]
        if images:
            taken = [a.get("taken_at") for a in images if a.get("taken_at")]
            taken_dt = [datetime.fromisoformat(str(t)[:19]) for t in taken]
            if delivered and taken_dt and min(taken_dt) < delivered.replace(hour=0, minute=0, second=0):
                f(-35, "Foto anterior à entrega", f"Metadados da foto: {_d(min(taken_dt))}; entrega em {_d(delivered)}.",
                  "anexo")
                checks.append("Solicitar nova foto do produto recebido.")
            else:
                f(15, "Foto do produto anexada", f"{len(images)} imagem(ns) com data compatível com a entrega.", "anexo")
        elif intent != "defeito":
            f(-15, "Sem evidência", "Nenhuma foto anexada.", "anexo")
            checks.append("Solicitar foto do produto e da embalagem.")
        if delivered:
            days = (received - delivered).days
            limit = 90 if intent == "defeito" else 30
            if days <= 7:
                f(10, "Reclamação logo após a entrega", f"{days} dia(s) após a entrega.", "entregas")
            elif days > limit:
                f(-15, "Reclamação tardia", f"{days} dias após a entrega (referência: até {limit} dias).", "entregas")
        if history >= 2:
            f(-20, "Reclamações em série", f"{history} reclamações de reparação nos últimos 180 dias.", "atendimento")
        elif history == 1:
            f(-5, "Reclamação recente anterior", "1 reclamação de reparação nos últimos 180 dias.", "atendimento")
        elif ctx.get("customer_orders", 0) >= 2:
            f(5, "Bom histórico do cliente", "Sem reclamações de reparação recentes.", "crm")
        if intent == "avaria":
            if ctx.get("product_line") in FRAGILE_LINES:
                f(5, "Produto frágil", f"Linha {ctx.get('product_line')} tem maior incidência de avarias.", "catalogo")
            rate, avg = ctx.get("carrier_damage_rate"), ctx.get("avg_damage_rate")
            if rate is not None and avg and rate > avg * 1.25:
                f(5, "Transportadora com mais avarias", f"{ctx.get('carrier')}: {rate:.1f}% de avarias × média {avg:.1f}%.",
                  "transportadora")

    score = max(0, min(100, 50 + sum(x["points"] for x in factors)))
    lo, hi = int(cfg.get("veracity_inconsistent_max", 39)), int(cfg.get("veracity_consistent_min", 70))
    label = "consistente" if score >= hi else "inconsistente" if score <= lo else "inconclusiva"
    if label == "inconsistente":
        checks.insert(0, "Revisão humana com as evidências acima — não negar automaticamente.")
    return {"score": int(score), "label": label, "factors": factors, "checks": checks}
