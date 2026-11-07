"""Simulação "e se…" ANTES de aprovar uma ação: projeção determinística e explicável sobre os dados atuais.

Não altera nada. As projeções são estimativas lineares (premissas exibidas junto do resultado) — nunca promessas.
Ligável/desligável em Configurações › Recursos ("whatif").
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from goops_core.db import Database
from goops_core.errors import ValidationError
from goops_core.operations import get_operation
from goops_core.permissions import Principal, require_permission
from goops_core.runtime_config import get_section
from data_platform.storage import Lakehouse


def _bool(s: pd.Series) -> pd.Series:
    return s.map(lambda v: v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1"))


def _nps(scores: pd.Series) -> Optional[float]:
    s = pd.to_numeric(scores, errors="coerce").dropna()
    return round(((s >= 9).sum() - (s <= 6).sum()) / len(s) * 100, 2) if len(s) else None


def whatif_carrier(lake: Lakehouse, params: Dict[str, Any]) -> Dict[str, Any]:
    carrier, target = params.get("carrier"), params.get("target_carrier")
    share = float(params.get("share_pct") or 0) / 100
    if not carrier or not target or not 0 <= share <= 1:
        raise ValidationError("Informe transportadora de origem, destino e % entre 0 e 100.")
    d = lake.read_table("gold/corporate", "gold_delivery_performance")
    d = d[_bool(d["late_evaluable"])]
    if params.get("states"):
        d = d[d["state"].isin(params["states"])]
    if d.empty:
        return {"available": False, "message": "Sem entregas avaliáveis no recorte."}
    late = _bool(d["is_late"])
    rate = late.groupby(d["carrier"]).mean()
    vol = d["carrier"].value_counts()
    if carrier not in rate or target not in rate:
        return {"available": False, "message": "Transportadora sem histórico de entregas avaliáveis no recorte."}
    total = int(len(d))
    current = float(late.mean())
    moved = vol[carrier] * share
    projected = current - moved * (rate[carrier] - rate[target]) / total
    n = lake.read_table("gold/corporate", "gold_nps_analytics")
    n = n[_bool(n["late_evaluable"])]
    if params.get("states"):
        n = n[n["state"].isin(params["states"])]
    nps_late, nps_ok = _nps(n[_bool(n["is_late"])]["score"]), _nps(n[~_bool(n["is_late"])]["score"])
    nps_now = _nps(n["score"])
    nps_proj = (round(nps_now + (current - projected) * (nps_ok - nps_late), 2)
                if None not in (nps_late, nps_ok, nps_now) else None)
    return {"available": True, "scope_deliveries": total,
            "late_rate_current": round(current * 100, 2), "late_rate_projected": round(projected * 100, 2),
            "carrier_late_rate": round(float(rate[carrier]) * 100, 2), "target_late_rate": round(float(rate[target]) * 100, 2),
            "volume_moved": int(round(moved)), "nps_current": nps_now, "nps_projected": nps_proj,
            "nps_on_time": nps_ok, "nps_late": nps_late,
            "assumptions": ["A transportadora de destino mantém a taxa de atraso histórica com o volume extra.",
                            "Efeito no NPS estimado pela diferença histórica de NPS entre entregas no prazo e atrasadas.",
                            "Estimativa linear sobre dados atuais (podem incluir campos sintéticos de demonstração)."]}


def whatif_contact(lake: Lakehouse, params: Dict[str, Any]) -> Dict[str, Any]:
    if params.get("sector") == "estoque":
        from data_platform.sectors.stock import contact_reach
        r = contact_reach(lake, params.get("segment") or "total")
        return {"available": True, "orders_to_contact": r["orders"], "items": r["items"], "by_reason": r["by_reason"],
                "message_preview": r["message_preview"], "channel": "e-mail/WhatsApp (simulado)",
                "assumptions": ["Contato oferece 3 opções (aguardar, trocar, cancelar) — regra RN5 do case.",
                                "Nenhuma mensagem é enviada: execução simulada após aprovação."]}
    d = lake.read_table("gold/domains/logistics", "logistics_delay_risk")
    if params.get("carrier"):
        d = d[d["carrier"] == params["carrier"]]
    if params.get("states"):
        d = d[d["state"].isin(params["states"])]
    d = d[d["risk_level"].isin(["high", "medium"])]
    return {"available": True, "orders_to_contact": int(d["order_id"].nunique()), "by_reason": d["risk_level"].value_counts().to_dict(),
            "channel": "e-mail (simulado)", "assumptions": ["Contato com pedidos em aberto de risco alto/médio no recorte."]}


def simulate(db: Database, lake: Lakehouse, actor: Principal, op_id: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    require_permission(actor, "operations:read")
    if not get_section(db, "features").get("whatif"):
        raise ValidationError("A simulação 'e se…' está desligada em Configurações › Recursos.")
    op = get_operation(db, op_id)
    params = {**(op.get("params") or {}), **{k: v for k, v in (overrides or {}).items() if k in ("share_pct", "segment")}}
    t = op["action_type"]
    if t == "carrier_reallocation":
        out = whatif_carrier(lake, params)
    elif t in ("proactive_customer_contact", "sector_customer_contact"):
        out = whatif_contact(lake, params)
    else:
        out = {"available": False, "message": "Ainda não há modelo de projeção para este tipo de ação."}
    return {"operation_id": op_id, "action_type": t, "params": params, **out}
