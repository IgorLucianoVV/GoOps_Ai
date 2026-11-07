"""L3 Corporate Gold — base analítica corporativa compartilhada.

Cuidado com o grão: entregas (1:N) são agregadas por pedido ANTES de qualquer junção com
avaliações, evitando multiplicação de registros. Cada dataset documenta seu grão.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from goops_core.db import Database

from ..analytics.nlp import THEMES, detect_themes, injection_suspected
from ..catalog import record_transformation, register_dataset
from ..lineage.registry import add_edge
from ..provenance import any_demo, row_fields, synthetic_columns
from ..storage import Lakehouse

GOLD_VERSION = "1.0"


def score_category(score: pd.Series) -> pd.Series:
    s = pd.to_numeric(score, errors="coerce")
    return pd.Series(np.select([s >= 9, s >= 7, s >= 0], ["promoter", "neutral", "detractor"], default=None),
                     index=score.index, dtype=object)


def _days(a: pd.Series, b: pd.Series) -> pd.Series:
    return ((a - b).dt.total_seconds() / 86400).round(2)


def data_watermark(orders: pd.DataFrame, deliveries: pd.DataFrame, nps: pd.DataFrame) -> pd.Timestamp:
    """Data de referência ("as of") = maior data observada nos dados (evita depender do relógio do servidor)."""
    cands = [orders["order_date"].max(), deliveries["shipping_date"].max(), deliveries["actual_delivery_date"].max(),
             nps["evaluation_date"].max()]
    cands = [c for c in cands if pd.notna(c)]
    return max(cands) if cands else pd.Timestamp.utcnow().tz_localize(None)


def build_delivery_performance(orders: pd.DataFrame, deliveries: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    d = deliveries.copy()
    o = orders[["order_id", "order_date", "state", "product_line"]].rename(columns={"state": "order_state"})
    d = d.merge(o, on="order_id", how="left")
    # UF de entrega da própria entrega tem precedência; senão, a do pedido
    d["state"] = d["state"].where(d["state"].notna(), d["order_state"])
    has_days = d["delivery_days"].notna() if "delivery_days" in d else pd.Series(False, index=d.index)
    d["is_delivered"] = d["actual_delivery_date"].notna() | has_days
    d["late_evaluable"] = d["actual_delivery_date"].notna() & d["estimated_delivery_date"].notna()
    d["is_late"] = d["late_evaluable"] & (d["actual_delivery_date"] > d["estimated_delivery_date"])
    d["delay_days"] = _days(d["actual_delivery_date"], d["estimated_delivery_date"]).clip(lower=0)
    d.loc[~d["late_evaluable"], "delay_days"] = np.nan
    # "Dias de entrega" informado pela fonte = prazo de transporte (envio→entrega); tem precedência sobre as datas
    informed = pd.to_numeric(d["delivery_days"], errors="coerce").astype(float)
    ship_dates = _days(d["actual_delivery_date"], d["shipping_date"])
    d["lead_time_ship_to_delivery_days"] = informed.where(informed.notna(), ship_dates)
    computed = _days(d["actual_delivery_date"], d["order_date"])
    d["lead_time_order_to_delivery_days"] = computed
    d["lead_time_source"] = np.where(informed.notna(), "dias_informados", np.where(ship_dates.notna(), "datas", None))
    status = d["delivery_status"].astype(object)
    d["delivery_status"] = status.where(status.notna(), np.where(d["is_delivered"], "entregue",
                                                                  np.where(d["shipping_date"].notna(), "em_transito", None)))
    d["is_overdue_open"] = (~d["is_delivered"]) & d["estimated_delivery_date"].notna() & (d["estimated_delivery_date"] < as_of)
    ref = d["shipping_date"].where(d["shipping_date"].notna(), d["order_date"])
    d["ship_month"] = ref.dt.strftime("%Y-%m")  # mês de envio; na ausência, mês do pedido
    d["carrier"] = d["carrier"].fillna("Não identificada")
    d["state"] = d["state"].fillna("Não identificado")
    cols = ["delivery_id", "order_id", "carrier", "shipping_type", "state", "city", "product_line", "order_date",
            "shipping_date", "estimated_delivery_date", "actual_delivery_date", "delivery_days", "delivery_status",
            "is_delivered", "late_evaluable", "is_late", "delay_days", "lead_time_ship_to_delivery_days",
            "lead_time_order_to_delivery_days", "lead_time_source", "is_overdue_open", "ship_month", "is_orphan", "_is_demo",
            "_synthetic_fields"]
    if "_synthetic_fields" not in d.columns:
        d["_synthetic_fields"] = None
    return d[cols]


def primary_deliveries(delivery_perf: pd.DataFrame) -> pd.DataFrame:
    """Entrega primária por pedido (primeiro envio), inclusive para entregas órfãs."""
    d = delivery_perf.sort_values(["order_id", "shipping_date", "delivery_id"], na_position="last")
    first = d.drop_duplicates("order_id", keep="first").set_index("order_id")
    agg = d.groupby("order_id").agg(n_deliveries=("delivery_id", "count"), any_late=("is_late", "any"))
    return first.join(agg)


def build_orders(orders: pd.DataFrame, delivery_perf: pd.DataFrame) -> pd.DataFrame:
    prim = primary_deliveries(delivery_perf[~delivery_perf["is_orphan"].astype(bool)])
    o = orders.copy().set_index("order_id")
    for col in ("carrier", "shipping_type", "shipping_date", "estimated_delivery_date", "actual_delivery_date",
                "delivery_days", "is_late", "late_evaluable", "delay_days", "lead_time_ship_to_delivery_days",
                "lead_time_order_to_delivery_days", "city"):
        o[col] = prim[col].reindex(o.index)
    dstate = prim["state"].reindex(o.index).replace("Não identificado", np.nan)
    o["state"] = o["state"].where(o["state"].notna(), dstate)
    o["n_deliveries"] = prim["n_deliveries"].reindex(o.index).fillna(0).astype(int)
    o["any_late"] = prim["any_late"].reindex(o.index).astype("boolean").fillna(False).astype(bool)
    o["is_late"] = o["is_late"].astype("boolean").fillna(False).astype(bool)
    o["late_evaluable"] = o["late_evaluable"].astype("boolean").fillna(False).astype(bool)
    o["order_month"] = o["order_date"].dt.strftime("%Y-%m")
    o = o.reset_index()
    for c in ("n_items", "product_lines"):
        if c not in o.columns:
            o[c] = None
    cols = ["order_id", "reference", "customer_id", "order_date", "order_month", "product_id", "product_name",
            "product_line", "product_lines", "n_items", "order_status", "order_total", "state", "city", "carrier",
            "shipping_type", "shipping_date", "estimated_delivery_date", "actual_delivery_date", "delivery_days",
            "late_evaluable", "is_late", "any_late", "delay_days", "lead_time_ship_to_delivery_days",
            "lead_time_order_to_delivery_days", "n_deliveries", "n_evaluations", "_is_demo"]
    return o[cols]


def build_nps_analytics(nps: pd.DataFrame, gold_orders: pd.DataFrame, delivery_perf: pd.DataFrame) -> pd.DataFrame:
    """Grão: 1 linha por avaliação válida. Dimensões de produto vêm do pedido (N:1); dimensões logísticas
    vêm da entrega primária do pedido (N:1) — inclusive quando o pedido não existe na base de pedidos."""
    n = nps.copy()
    assert not gold_orders["order_id"].duplicated().any(), "gold_orders deve ter 1 linha por pedido"
    prod = gold_orders[["order_id", "product_id", "product_line", "order_date", "state"]].rename(columns={"state": "order_state"})
    n = n.merge(prod, on="order_id", how="left", validate="many_to_one")
    prim = primary_deliveries(delivery_perf).reset_index()[
        ["order_id", "carrier", "shipping_type", "state", "late_evaluable", "is_late", "delay_days",
         "lead_time_ship_to_delivery_days", "lead_time_order_to_delivery_days", "delivery_days"]]
    n = n.merge(prim, on="order_id", how="left", validate="many_to_one")
    n["state"] = n["state"].where(n["state"].notna() & (n["state"] != "Não identificado"), n["order_state"])
    n["score_category"] = score_category(n["score"])
    n["eval_month"] = n["evaluation_date"].dt.strftime("%Y-%m")
    n["has_comment"] = n["comment"].notna() & (n["comment"].astype(str).str.strip() != "")
    themes = n["comment"].map(detect_themes)
    n["themes"] = themes.map(lambda t: "|".join(t) if t else None)
    neg = {k for k, v in THEMES.items() if v["polarity"] == "negative"}
    n["has_negative_theme"] = themes.map(lambda t: any(x in neg for x in t))
    n["injection_suspected"] = n["comment"].map(injection_suspected)
    for col in ("state", "product_line", "carrier", "shipping_type"):
        n[col] = n[col].fillna("Não identificado")
        n.loc[n[col] == "Não identificada", col] = "Não identificado"
    for col in ("is_late", "late_evaluable"):
        n[col] = n[col].astype("boolean").fillna(False).astype(bool)
    cols = ["evaluation_id", "order_id", "customer_id", "score", "score_category", "evaluation_date", "eval_month",
            "comment", "has_comment", "themes", "has_negative_theme", "injection_suspected", "state", "product_id",
            "product_line", "carrier", "shipping_type", "order_date", "late_evaluable", "is_late", "delay_days",
            "delivery_days", "lead_time_ship_to_delivery_days", "lead_time_order_to_delivery_days", "is_orphan", "_is_demo"]
    return n[cols]


def _nps(scores: pd.Series) -> float:
    s = pd.to_numeric(scores, errors="coerce").dropna()
    s = s[s.between(0, 10)]
    if len(s) == 0:
        return np.nan
    return round(((s >= 9).sum() - (s <= 6).sum()) / len(s) * 100, 2)


def build_customer_experience(nps_a: pd.DataFrame, gold_orders: pd.DataFrame) -> pd.DataFrame:
    """Grão: 1 linha por cliente."""
    orders_by_c = gold_orders.groupby("customer_id").size().rename("n_orders")
    e = nps_a.sort_values("evaluation_date")
    g = e.groupby("customer_id").agg(n_evaluations=("evaluation_id", "count"), avg_score=("score", "mean"),
                                     detractor_evaluations=("score_category", lambda s: int((s == "detractor").sum())),
                                     last_evaluation_date=("evaluation_date", "max"),
                                     last_score=("score", "last"), last_category=("score_category", "last"))
    out = pd.concat([orders_by_c, g], axis=1).reset_index().rename(columns={"index": "customer_id"})
    out["n_orders"] = out["n_orders"].fillna(0).astype(int)
    out["n_evaluations"] = out["n_evaluations"].fillna(0).astype(int)
    out["avg_score"] = out["avg_score"].astype(float).round(2)
    return out


def _segment_perf(nps_a: pd.DataFrame, gold_orders: pd.DataFrame, deliv: pd.DataFrame, key: str) -> pd.DataFrame:
    o = gold_orders.groupby(key).agg(orders=("order_id", "count"))
    e = nps_a.groupby(key).agg(evaluations=("evaluation_id", "count"), avg_score=("score", "mean"),
                               promoters=("score_category", lambda s: int((s == "promoter").sum())),
                               neutrals=("score_category", lambda s: int((s == "neutral").sum())),
                               detractors=("score_category", lambda s: int((s == "detractor").sum())),
                               nps=("score", _nps))
    out = o.join(e, how="outer")
    if key in deliv.columns:
        ev = deliv[deliv["late_evaluable"].astype(bool)].groupby(key)["is_late"].mean().mul(100).round(2).rename("late_rate")
        lt = deliv[deliv["is_delivered"].astype(bool)].groupby(key)["lead_time_order_to_delivery_days"].mean().rename("avg_lead_time_days")
        out = out.join(ev, how="left").join(lt, how="left")
    out = out.reset_index()
    for c in ("orders", "evaluations", "promoters", "neutrals", "detractors"):
        out[c] = out[c].fillna(0).astype(int)
    out["detractor_rate"] = np.where(out["evaluations"] > 0, (out["detractors"] / out["evaluations"] * 100).round(2), np.nan)
    out["avg_score"] = out["avg_score"].astype(float).round(2)
    return out


def build_corporate_gold(db: Database, lake: Lakehouse, pipeline_run_id: str, actor: str = "pipeline") -> Dict[str, int]:
    orders = lake.read_table("silver", "silver_orders")
    deliveries = lake.read_table("silver", "silver_deliveries")
    nps = lake.read_table("silver", "silver_nps_evaluations")
    as_of = data_watermark(orders, deliveries, nps)
    base_synthetic = row_fields(deliveries) | row_fields(orders)

    dperf = build_delivery_performance(orders, deliveries, as_of)
    gorders = build_orders(orders, dperf)
    nps_a = build_nps_analytics(nps, gorders, dperf)
    cx = build_customer_experience(nps_a, gorders)
    product = _segment_perf(nps_a, gorders, dperf.merge(gorders[["order_id", "product_id"]], on="order_id", how="left"),
                            "product_id")
    names = gorders.drop_duplicates("product_id").set_index("product_id")[["product_name", "product_line"]]
    product = product.join(names, on="product_id")
    regional = _segment_perf(nps_a, gorders, dperf, "state")

    demo_by_key = {"gold_delivery_performance": any_demo(dperf), "gold_orders": any_demo(gorders),
                   "gold_nps_analytics": any_demo(nps_a), "gold_customer_experience": any_demo(nps_a),
                   "gold_product_performance": any_demo(nps_a, gorders, dperf),
                   "gold_regional_performance": any_demo(nps_a, gorders, dperf)}
    specs: List[tuple] = [
        ("gold_delivery_performance", dperf, "Desempenho de entregas", "1 linha por entrega",
         ["silver_deliveries", "silver_orders"], "join deliveries->orders; is_late, delay_days, lead times", "internal"),
        ("gold_orders", gorders, "Pedidos consolidados", "1 linha por pedido (entrega primária agregada)",
         ["silver_orders", "gold_delivery_performance"], "aggregate deliveries per order (1:N -> 1:1)", "pii"),
        ("gold_nps_analytics", nps_a, "NPS analítico", "1 linha por avaliação válida",
         ["silver_nps_evaluations", "gold_orders"], "classify score; join N:1 orders; themes v" + "1.0", "pii"),
        ("gold_customer_experience", cx, "Experiência do cliente", "1 linha por cliente",
         ["gold_nps_analytics", "gold_orders"], "aggregate by customer", "pii"),
        ("gold_product_performance", product, "Desempenho por produto", "1 linha por produto",
         ["gold_nps_analytics", "gold_orders", "gold_delivery_performance"], "aggregate by product_id", "internal"),
        ("gold_regional_performance", regional, "Desempenho regional", "1 linha por UF",
         ["gold_nps_analytics", "gold_orders", "gold_delivery_performance"], "aggregate by state", "internal"),
    ]
    rows = {}
    for key, df, name, grain, inputs, transform, sensitivity in specs:
        w = lake.write_table("gold/corporate", key, df)
        register_dataset(db, key=key, layer="gold_corporate", scope="corporate", name=name,
                         description=f"Corporate Gold · {name}. Data de referência (as_of): {as_of:%Y-%m-%d}",
                         grain=grain, path=w["path"], fmt=w["format"], row_count=w["rows"], schema=w["schema"],
                         schema_version=GOLD_VERSION, is_demo=demo_by_key[key], pipeline_run_id=pipeline_run_id,
                         sensitivity=sensitivity, synthetic_fields=synthetic_columns(df.columns, base_synthetic))
        record_transformation(db, dataset_key=key, inputs=inputs, transform=transform, rule_version=GOLD_VERSION,
                              rows_in=sum(len(x) for x in (orders, deliveries, nps)), rows_out=w["rows"], actor=actor,
                              pipeline_run_id=pipeline_run_id)
        for i in inputs:
            add_edge(db, f"dataset:{i}", f"dataset:{key}", transform)
        rows[key] = w["rows"]
    rows["as_of"] = str(as_of)
    return rows
