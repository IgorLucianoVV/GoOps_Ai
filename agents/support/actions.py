"""Ações do Atendimento: simuladores (efeito previsto, sem tocar sistemas externos) e ganchos que mantêm o contato
sincronizado com o ciclo de vida da ação (proposta → aprovação → execução).

Cada simulador representa um passo que hoje exige outro sistema/portal: portal da transportadora (chamado),
ERP (troca/reenvio), financeiro (reembolso/cancelamento). A integração real substitui apenas o simulador.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any, Dict

from goops_core.db import Database
from goops_core.operations import register_hook, register_simulator
from goops_core.permissions import Principal
from goops_core.util import jdump, new_id, now_iso


def _protocol(prefix: str, *parts: Any) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()
    return f"{prefix}-{h}"


def _order(order_id: str) -> Dict[str, Any]:
    from data_platform.storage import get_lakehouse
    try:
        df = get_lakehouse().read_table("gold/corporate", "gold_orders")
        row = df[df["order_id"].astype(str) == str(order_id)]
        return row.iloc[0].to_dict() if len(row) else {}
    except Exception:  # noqa: BLE001
        return {}


def sim_carrier_ticket(p: Dict[str, Any]) -> Dict[str, Any]:
    o = _order(p.get("order_id", ""))
    return {"system": "Portal da transportadora (simulado)", "carrier": p.get("carrier") or o.get("carrier"),
            "protocol": _protocol("TRP", p.get("order_id"), p.get("reason")), "reason": p.get("reason"),
            "sla_response": "48h úteis", "tracking_status": o.get("order_status")}


def sim_reshipment(p: Dict[str, Any]) -> Dict[str, Any]:
    o = _order(p.get("order_id", ""))
    total = float(o.get("order_total") or 0)
    return {"system": "ERP · reenvio (simulado)", "new_shipment": _protocol("RENV", p.get("order_id")),
            "product": o.get("product_name"), "estimated_cost_brl": round(total * 0.55 + 18.0, 2),
            "note": "Custo estimado = custo do produto (≈55% do preço) + frete médio."}


def sim_exchange(p: Dict[str, Any]) -> Dict[str, Any]:
    return {"system": "ERP · trocas (simulado)", "reverse_logistics_code": _protocol("TROCA", p.get("order_id")),
            "instructions": "Código de postagem enviado ao cliente (simulado)."}


def sim_refund(p: Dict[str, Any]) -> Dict[str, Any]:
    o = _order(p.get("order_id", ""))
    amount = p.get("amount") or o.get("order_total")
    return {"system": "Financeiro (simulado)", "refund_id": _protocol("EST", p.get("order_id")), "amount_brl": amount}


def sim_cancel(p: Dict[str, Any]) -> Dict[str, Any]:
    o = _order(p.get("order_id", ""))
    return {"system": "Pedidos + Financeiro (simulado)", "cancellation_id": _protocol("CANC", p.get("order_id")),
            "refund_brl": o.get("order_total"), "shipment_intercept": o.get("order_status") == "em_transito"}


def sim_proactive_notice(p: Dict[str, Any]) -> Dict[str, Any]:
    from goops_core.db import get_db
    from .prevention import proactive_candidates
    cand = proactive_candidates(get_db())
    return {"channel": "WhatsApp/e-mail (simulado)", "orders_notified": cand["count"],
            "expected_contacts_avoided": cand["expected_contacts_avoided"], "message": p.get("message")}


def _chat(db: Database, cid: str, text: str) -> None:
    from .conversations import system_message
    system_message(db, cid, text)


def _on_decided(db: Database, actor: Principal, op: dict) -> None:
    cid = op.get("contact_id")
    if not cid:
        return
    ok = op["status"] == "approved"
    msg = f"{op['title']}: {'aprovada' if ok else 'rejeitada'} por {actor.name}."
    _event(db, cid, actor.actor_label, "action_approved" if ok else "action_rejected", msg, {"operation_id": op["id"]})
    _chat(db, cid, msg)
    if not ok:
        db.execute("UPDATE support_contacts SET status = 'pending_human', updated_at = ? WHERE id = ? AND status = "
                   "'pending_approval'", (now_iso(), cid))
        return
    # Aprovada por uma pessoa: o Agente de Atendimento executa (modo simulado), como no fluxo de incidentes.
    from goops_core.operations import execute_operation
    from goops_core.permissions import agent_principal
    execute_operation(db, agent_principal("support"), op["id"])


def _on_executed(db: Database, actor: Principal, op: dict) -> None:
    cid = op.get("contact_id")
    if not cid:
        return
    preview = (op.get("result") or {}).get("preview") or {}
    ref = preview.get("protocol") or preview.get("new_shipment") or preview.get("reverse_logistics_code") or \
        preview.get("refund_id") or preview.get("cancellation_id")
    msg = f"{op['title']} executada (simulada){f' · {ref}' if ref else ''}."
    _event(db, cid, actor.actor_label, "action_executed", msg, {"operation_id": op["id"], "result": preview})
    _chat(db, cid, msg)
    pending = db.fetchone("SELECT COUNT(*) AS n FROM operations WHERE contact_id = ? AND status IN "
                          "('pending_approval', 'approved', 'executing')", (cid,))["n"]
    if pending == 0 and op["action_type"] != "support_carrier_ticket":
        from .conversations import data_clock
        db.execute("UPDATE support_contacts SET status = 'resolved', resolved_at = ?, "
                   "resolution = ?, updated_at = ? WHERE id = ? AND status IN ('pending_approval', 'pending_human')",
                   ((data_clock(db) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S"), f"{op['title']} (execução simulada)",
                    now_iso(), cid))
        _chat(db, cid, f"Atendimento encerrado · {op['title']} (execução simulada).")


def _event(db: Database, contact_id: str, actor: str, event_type: str, message: str, data: Any = None) -> None:
    db.execute("INSERT INTO support_events (id, contact_id, actor, event_type, message, data, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?)", (new_id("SEV"), contact_id, actor, event_type, message, jdump(data or {}),
                                                now_iso()))


def register_all() -> None:
    register_simulator("support_carrier_ticket", sim_carrier_ticket)
    register_simulator("support_reshipment", sim_reshipment)
    register_simulator("support_exchange", sim_exchange)
    register_simulator("support_refund", sim_refund)
    register_simulator("support_cancel_order", sim_cancel)
    register_simulator("support_proactive_notice", sim_proactive_notice)
    register_hook("decided", _on_decided)
    register_hook("executed", _on_executed)
    from agents.team_channel import register_hooks as register_team
    register_team()
