"""Construtor de métricas sem código: prévia do cálculo sobre a Gold do setor ANTES de criar a métrica.

A prévia usa o mesmo motor governado (validate_definition/compute) e não grava nada.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from goops_core.db import Database
from goops_core.errors import ValidationError
from goops_core.permissions import Principal, require_permission

from ..semantic.engine import apply_filters, compute, compute_grouped, validate_condition, validate_definition
from ..semantic.registry import load_dataset_frame
from ..storage import Lakehouse


def preview_metric(db: Database, lake: Lakehouse, actor: Principal, domain: str, payload: Dict[str, Any],
                   group_by: Optional[str] = None) -> Dict[str, Any]:
    require_permission(actor, "semantic:write", domain)
    sources: List[str] = payload.get("source_datasets") or []
    if len(sources) != 1:
        raise ValidationError("Escolha um conjunto de dados.")
    ds = db.fetchone("SELECT key, domain, layer FROM datasets WHERE key = ?", (sources[0],))
    if not ds or ds["domain"] not in (domain, "corporate"):
        raise ValidationError("Conjunto de dados não pertence ao setor (execute o pipeline se acabou de criá-lo).")
    df = load_dataset_frame(db, lake, sources[0])
    fields = set(df.columns)
    defn = payload.get("formula_definition") or {}
    validate_definition(defn, fields)
    for cond in payload.get("filters") or []:
        validate_condition(cond, fields)
    df = apply_filters(df, payload.get("filters"))
    out: Dict[str, Any] = {"result": compute(defn, df), "rows_considered": int(len(df))}
    by = group_by or ("month" if "month" in fields else None)
    if by:
        if by not in fields:
            raise ValidationError(f"Dimensão inexistente: {by}")
        groups = [g for g in compute_grouped(defn, df, by) if g.get(by) != "Não identificado"]
        out["groups"] = sorted(groups, key=lambda g: str(g[by]))[:40]
        out["group_by"] = by
    return out
