"""Prevenção de recontato e de contatos evitáveis.

* Recontato: o cliente voltou pelo mesmo assunto dentro da janela configurada (o 1º atendimento não resolveu).
* Evitáveis: contatos que um aviso proativo teria dispensado (atraso não comunicado, status de entrega, prazo de estorno).
* Causas-raiz: onde os contatos se concentram (assunto × transportadora × linha de produto).
* Aviso proativo: pedidos em aberto com risco de atraso que ainda não geraram contato → propõe o aviso (com aprovação,
  pois toca a área crítica "clientes"), estimando quantos contatos seriam evitados pela taxa histórica.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from goops_core.db import Database
from goops_core.operations import propose_operation
from goops_core.permissions import Principal, require_permission
from goops_core.support_catalog import CHANNELS, INTENTS

NOTICE = ("Olá! Seu pedido #{pedido} está em trânsito com {transportadora} e pode chegar com alguns dias de atraso em "
          "relação à previsão de {previsao}. Já estamos acompanhando com a transportadora e avisaremos a nova data. "
          "Não é preciso entrar em contato.")


def _frame(db: Database) -> pd.DataFrame:
    rows = db.fetchall("SELECT id, channel, customer_id, order_id, intent, received_at, is_repeat, contact_number, avoidable, "
                       "avoidable_reason, routing, status, veracity_label, is_claim FROM support_contacts WHERE status <> 'new'")
    return pd.DataFrame(rows)


def recontact_analysis(db: Database) -> Dict[str, Any]:
    df = _frame(db)
    if df.empty:
        return {"total": 0}
    df["is_repeat"] = df["is_repeat"].astype(bool)
    df["avoidable"] = df["avoidable"].astype(bool)
    total = len(df)
    rep = df[df["is_repeat"]]
    by_intent = (df.groupby("intent").agg(contacts=("id", "count"), repeats=("is_repeat", "sum"))
                 .assign(rate=lambda x: (x["repeats"] / x["contacts"] * 100).round(1))
                 .sort_values("repeats", ascending=False).reset_index())
    by_intent["label"] = by_intent["intent"].map(lambda i: INTENTS.get(i, {}).get("label", i))
    to_ra = int(((rep["channel"] == "reclameaqui")).sum())
    reasons = (df[df["avoidable"]].groupby("avoidable_reason")["id"].count().sort_values(ascending=False)
               .rename("contacts").reset_index())
    return {
        "total": total, "repeats": int(len(rep)), "repeat_rate": round(len(rep) / total * 100, 1),
        "repeats_escalated_to_reclameaqui": to_ra,
        "avoidable": int(df["avoidable"].sum()), "avoidable_rate": round(df["avoidable"].mean() * 100, 1),
        "avoidable_by_reason": reasons.to_dict("records"),
        "by_intent": by_intent.head(12).to_dict("records"),
        "contacts_per_thread_max": int(df["contact_number"].max()),
    }


def root_causes(db: Database, lake) -> List[Dict[str, Any]]:
    """Concentrações de contatos por assunto × transportadora × linha de produto (com pedido vinculado)."""
    df = _frame(db)
    if df.empty:
        return []
    orders = lake.read_table("gold/corporate", "gold_orders")[["order_id", "carrier", "product_line"]]
    orders["order_id"] = orders["order_id"].astype(str)
    m = df.dropna(subset=["order_id"]).merge(orders, on="order_id", how="left")
    g = (m.groupby(["intent", "carrier", "product_line"]).agg(contacts=("id", "count"),
                                                            repeats=("is_repeat", lambda s: int(s.astype(bool).sum())))
         .reset_index().sort_values("contacts", ascending=False))
    total = len(m)
    out = []
    for r in g.head(10).to_dict("records"):
        out.append({**r, "intent_label": INTENTS.get(r["intent"], {}).get("label", r["intent"]),
                    "share_pct": round(r["contacts"] / total * 100, 1)})
    return out


def proactive_candidates(db: Database, lake=None) -> Dict[str, Any]:
    from data_platform.storage import get_lakehouse
    lake = lake or get_lakehouse()
    try:
        risk = lake.read_table("gold/domains/logistics", "logistics_delay_risk")
    except FileNotFoundError:
        return {"count": 0, "expected_contacts_avoided": 0, "orders": []}
    risk = risk[risk["risk_level"].isin(["high", "medium"])].copy()
    risk["order_id"] = risk["order_id"].astype(str)
    contacted = {r["order_id"] for r in db.fetchall("SELECT DISTINCT order_id FROM support_contacts WHERE order_id IS NOT NULL")}
    pending = risk[~risk["order_id"].isin(contacted)].sort_values("risk_score", ascending=False)
    # taxa histórica: contatos de status/atraso por pedido atrasado
    late_contacts = db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE intent IN ('atraso_entrega', "
                                "'onde_esta_pedido') AND status <> 'new'")["n"]
    late_orders = db.fetchone("SELECT COUNT(DISTINCT order_id) AS n FROM support_contacts WHERE intent = 'atraso_entrega' "
                              "AND veracity_label = 'consistente'")["n"]
    rate = min(1.5, late_contacts / late_orders) if late_orders else 0.8
    sample = pending.head(1).to_dict("records")
    preview = NOTICE.format(pedido=sample[0]["order_id"], transportadora=sample[0]["carrier"],
                            previsao=pd.to_datetime(sample[0]["estimated_delivery_date"]).strftime("%d/%m")) if sample else None
    return {"count": int(len(pending)), "by_risk": pending["risk_level"].value_counts().to_dict(),
            "by_carrier": pending["carrier"].value_counts().to_dict(), "contacts_per_late_order": round(rate, 2),
            "expected_contacts_avoided": int(round(len(pending) * rate * 0.6)),
            "assumption": "Contatos evitados ≈ pedidos avisados × contatos históricos por pedido atrasado × 60% de eficácia "
                          "do aviso (premissa).",
            "message_preview": preview,
            "orders": pending.head(15)[["order_id", "carrier", "state", "estimated_delivery_date", "risk_level",
                                        "risk_score"]].astype({"estimated_delivery_date": str}).to_dict("records")}


def propose_proactive_notice(db: Database, actor: Principal, segment: str = "high,medium") -> Dict[str, Any]:
    require_permission(actor, "support:write", "atendimento")
    cand = proactive_candidates(db)
    if not cand["count"]:
        from goops_core.errors import ValidationError
        raise ValidationError("Não há pedidos em risco sem contato para avisar.")
    return propose_operation(db, actor, action_type="support_proactive_notice",
                             description=f"Avisar {cand['count']} clientes com pedidos em risco de atraso antes que entrem em "
                                         f"contato (≈{cand['expected_contacts_avoided']} contatos evitados, premissa).",
                             params={"segment": segment, "orders": int(cand["count"]),
                                     "message": cand["message_preview"] or ""},
                             expected_impact={"expected_contacts_avoided": cand["expected_contacts_avoided"],
                                              "assumption": cand["assumption"]})


def channel_label(c: str) -> str:
    return CHANNELS.get(c, c)
