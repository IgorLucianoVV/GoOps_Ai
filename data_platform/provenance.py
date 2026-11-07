"""Proveniência de dados sintéticos em datasets reais.

Quando o complemento sintético preenche lacunas (ex.: datas de envio/previsão/entrega da seed Gocase), cada linha
recebe `_synthetic_fields` e cada dataset registra `synthetic_fields` — colunas cujo valor depende (direta ou
indiretamente) de dado sintético. Métricas que usam essas colunas são sinalizadas na API e na interface.
"""
from __future__ import annotations

from typing import Iterable, List, Set

import pandas as pd

DATE_FIELDS = {"shipping_date", "estimated_delivery_date", "actual_delivery_date"}
# Colunas derivadas das datas de entrega (Gold corporativa e de domínio)
DERIVED_FROM_DATES = {
    "shipping_date", "estimated_delivery_date", "actual_delivery_date", "ship_month", "late_evaluable", "is_late",
    "any_late", "delay_days", "lead_time_order_to_delivery_days", "is_overdue_open", "late_rate", "late",
    "avg_delay_days", "avg_lead_time_days", "days_overdue", "elapsed_ratio", "risk_score", "risk_level",
    "carrier_recent_late_rate", "is_delivered", "delivery_status",
}


def row_fields(df: pd.DataFrame) -> Set[str]:
    if "_synthetic_fields" not in df.columns:
        return set()
    out: Set[str] = set()
    for v in df["_synthetic_fields"].dropna().unique():
        out.update(x for x in str(v).split("|") if x)
    return out


def synthetic_columns(columns: Iterable[str], base_synthetic: Set[str]) -> List[str]:
    """Colunas de um dataset derivado que dependem de campos sintéticos da Silver."""
    cols = set(columns)
    derived = set(base_synthetic)
    if base_synthetic & DATE_FIELDS:
        derived |= DERIVED_FROM_DATES
    return sorted(c for c in cols & derived if not c.startswith("_"))


def any_demo(*frames: pd.DataFrame) -> bool:
    return any(bool(f["_is_demo"].astype(bool).any()) for f in frames if f is not None and len(f) and "_is_demo" in f)
