"""Motor de cálculo de métricas governadas.

As fórmulas são DEFINIÇÕES DECLARATIVAS validadas e executadas por funções controladas.
Nunca se executa código ou SQL fornecido por usuários ou por LLMs.
Tipos suportados: nps | rate | mean | count | sum | median | percentile | count_distinct.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from goops_core.errors import ValidationError

ALLOWED_TYPES = {"nps", "rate", "mean", "count", "sum", "median", "percentile", "count_distinct"}
FIELD_TYPES = {"mean", "sum", "median", "percentile", "count_distinct"}
ALLOWED_OPS = {"eq", "ne", "gt", "ge", "lt", "le", "in", "is_true", "is_false", "not_null", "is_null"}


def validate_condition(cond: dict, fields: Optional[set] = None) -> None:
    if not isinstance(cond, dict) or "field" not in cond or "op" not in cond:
        raise ValidationError("Condição deve conter 'field' e 'op'.")
    if cond["op"] not in ALLOWED_OPS:
        raise ValidationError(f"Operador não permitido: {cond['op']}")
    if fields is not None and cond["field"] not in fields:
        raise ValidationError(f"Campo inexistente no dataset de origem: {cond['field']}")
    if cond["op"] == "in" and not isinstance(cond.get("value"), list):
        raise ValidationError("Operador 'in' exige lista em 'value'.")


def validate_definition(defn: dict, fields: Optional[set] = None) -> None:
    if not isinstance(defn, dict) or defn.get("type") not in ALLOWED_TYPES:
        raise ValidationError(f"formula_definition.type deve ser um de {sorted(ALLOWED_TYPES)}")
    t = defn["type"]
    allowed_keys = {"type", "time_field", "score_field", "promoter_min", "detractor_max", "valid_min", "valid_max",
                    "numerator", "base_filter", "field", "q"}
    unknown = set(defn) - allowed_keys
    if unknown:
        raise ValidationError(f"Chaves não permitidas na definição: {sorted(unknown)}")
    if t == "nps":
        for k in ("score_field", "promoter_min", "detractor_max", "valid_min", "valid_max"):
            if k not in defn:
                raise ValidationError(f"Definição NPS requer '{k}'.")
        if not (defn["valid_min"] <= defn["detractor_max"] < defn["promoter_min"] <= defn["valid_max"]):
            raise ValidationError("Limites NPS incoerentes.")
        if fields is not None and defn["score_field"] not in fields:
            raise ValidationError(f"Campo inexistente: {defn['score_field']}")
    if t == "rate":
        validate_condition(defn.get("numerator") or {}, fields)
        if defn.get("base_filter"):
            validate_condition(defn["base_filter"], fields)
    if t == "percentile" and not (isinstance(defn.get("q"), (int, float)) and 0 < defn["q"] < 100):
        raise ValidationError("Definição 'percentile' requer 'q' entre 0 e 100 (ex.: 90).")
    if t in FIELD_TYPES:
        if not defn.get("field"):
            raise ValidationError(f"Definição '{t}' requer 'field'.")
        if fields is not None and defn["field"] not in fields:
            raise ValidationError(f"Campo inexistente: {defn['field']}")
    if defn.get("time_field") and fields is not None and defn["time_field"] not in fields:
        raise ValidationError(f"time_field inexistente: {defn['time_field']}")


_BOOL_TEXT = {"true": True, "false": False, "1": True, "0": False, "1.0": True, "0.0": False, "sim": True, "não": False,
              "nao": False}


def _as_bool(col: pd.Series) -> pd.Series:
    """Booleano tolerante ao formato de armazenamento (bool, 0/1 ou texto 'True'/'False')."""
    if pd.api.types.is_bool_dtype(col):
        return col.astype("boolean")
    return col.map(lambda v: v if isinstance(v, bool) or v is None else _BOOL_TEXT.get(str(v).strip().lower())
                   if not (isinstance(v, float) and v != v) else None).astype("boolean")


def condition_mask(df: pd.DataFrame, cond: dict) -> pd.Series:
    col = df[cond["field"]]
    op, val = cond["op"], cond.get("value")
    if op == "eq":
        m = col == val
    elif op == "ne":
        m = col != val
    elif op == "gt":
        m = col > val
    elif op == "ge":
        m = col >= val
    elif op == "lt":
        m = col < val
    elif op == "le":
        m = col <= val
    elif op == "in":
        m = col.isin(val)
    elif op in ("is_true", "is_false"):
        b = _as_bool(col)
        m = b == (op == "is_true")
    elif op == "not_null":
        m = col.notna()
    else:
        m = col.isna()
    return m.fillna(False).astype(bool)


def apply_filters(df: pd.DataFrame, filters: Optional[List[dict]]) -> pd.DataFrame:
    for cond in filters or []:
        df = df[condition_mask(df, cond)]
    return df


def compute(defn: dict, df: pd.DataFrame) -> Dict[str, Any]:
    t = defn["type"]
    if t == "nps":
        s = pd.to_numeric(df[defn["score_field"]], errors="coerce")
        valid = s[s.between(defn["valid_min"], defn["valid_max"])]
        total = int(len(valid))
        prom = int((valid >= defn["promoter_min"]).sum())
        det = int((valid <= defn["detractor_max"]).sum())
        neu = total - prom - det
        value = None if total == 0 else round((prom - det) / total * 100, 2)  # sem avaliações válidas -> nulo
        return {"value": value, "n": total, "promoters": prom, "neutrals": neu, "detractors": det,
                "invalid_excluded": int(len(s) - total),
                "promoter_pct": round(prom / total * 100, 2) if total else None,
                "neutral_pct": round(neu / total * 100, 2) if total else None,
                "detractor_pct": round(det / total * 100, 2) if total else None}
    if t == "rate":
        base = df[condition_mask(df, defn["base_filter"])] if defn.get("base_filter") else df
        n = int(len(base))
        num = int(condition_mask(base, defn["numerator"]).sum()) if n else 0
        return {"value": round(num / n * 100, 2) if n else None, "n": n, "numerator": num}
    if t == "mean":
        s = pd.to_numeric(df[defn["field"]], errors="coerce").dropna()
        return {"value": round(float(s.mean()), 4) if len(s) else None, "n": int(len(s))}
    if t == "count":
        return {"value": int(len(df)), "n": int(len(df))}
    if t == "count_distinct":
        s = df[defn["field"]].dropna()
        return {"value": int(s.nunique()), "n": int(len(s))}
    if t in ("sum", "median", "percentile"):
        s = pd.to_numeric(df[defn["field"]], errors="coerce").dropna()
        if not len(s):
            return {"value": None, "n": 0}
        v = s.sum() if t == "sum" else s.median() if t == "median" else s.quantile(defn["q"] / 100)
        return {"value": round(float(v), 4), "n": int(len(s))}
    raise ValidationError(f"Tipo de métrica não suportado: {t}")


def compute_grouped(defn: dict, df: pd.DataFrame, by: str) -> List[Dict[str, Any]]:
    if by not in df.columns:
        raise ValidationError(f"Dimensão inexistente: {by}")
    out = []
    keys = df[by].astype(object).where(df[by].notna(), "Não identificado")
    for value, part in df.groupby(keys, sort=True):
        res = compute(defn, part)
        res[by] = value
        out.append(res)
    return out
