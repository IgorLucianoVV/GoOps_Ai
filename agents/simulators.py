"""Simuladores de ações: calculam o efeito PREVISTO sobre os dados atuais, sem alterar nenhum sistema."""
from __future__ import annotations

from typing import Any, Dict

from goops_core.operations import register_simulator
from data_platform.storage import get_lakehouse


def _open_deliveries(params: Dict[str, Any]):
    df = get_lakehouse().read_table("gold/domains/logistics", "logistics_delay_risk")
    if params.get("carrier"):
        df = df[df["carrier"] == params["carrier"]]
    if params.get("states"):
        df = df[df["state"].isin(params["states"])]
    return df


def sim_carrier_reallocation(params: Dict[str, Any]) -> Dict[str, Any]:
    df = _open_deliveries(params)
    share = float(params.get("share_pct", 0)) / 100
    return {"open_deliveries_in_scope": int(len(df)), "would_reallocate_future_volume_pct": params.get("share_pct"),
            "estimated_open_orders_affected": int(round(len(df) * share)), "target_carrier": params.get("target_carrier")}


def sim_customer_contact(params: Dict[str, Any]) -> Dict[str, Any]:
    df = _open_deliveries(params)
    df = df[df["risk_level"].isin(["high", "medium"])]
    return {"customers_to_contact": int(df["order_id"].nunique()), "channel": "e-mail (simulado)",
            "by_risk": df["risk_level"].value_counts().to_dict()}


def sim_generic(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"ticket": "simulado", "params": params}


def register_all() -> None:
    register_simulator("carrier_reallocation", sim_carrier_reallocation)
    register_simulator("proactive_customer_contact", sim_customer_contact)
    for t in ("product_quality_review", "regional_logistics_review", "data_quality_fix", "sector_operational_review",
              "sector_customer_contact"):
        register_simulator(t, sim_generic)
    from .support.actions import register_all as register_support
    register_support()
