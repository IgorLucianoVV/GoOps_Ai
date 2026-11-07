"""L3 Domain Gold — conjuntos especializados por domínio (CX, Logística, Produtos).

Reutilizam a Corporate Gold, sem alterar definições corporativas. Finance está preparado
como domínio futuro (sem datasets nesta versão).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from goops_core.db import Database

from ...analytics.nlp import THEMES, sentiment
from ...catalog import record_transformation, register_dataset
from ...lineage.registry import add_edge
from ...provenance import any_demo, row_fields, synthetic_columns
from ...storage import Lakehouse
from ..corporate import GOLD_VERSION, data_watermark

DIMENSIONS = ["state", "product_line", "carrier", "shipping_type"]


def cx_comment_insights(nps_a: pd.DataFrame) -> pd.DataFrame:
    c = nps_a[nps_a["has_comment"].astype(bool)].copy()
    c["sentiment"] = c["comment"].map(sentiment)
    return c[["evaluation_id", "eval_month", "score", "score_category", "comment", "themes", "sentiment",
              "injection_suspected", "state", "product_line", "carrier", "shipping_type"]]


def cx_detractor_drivers(nps_a: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dim in DIMENSIONS:
        g = nps_a.groupby(["eval_month", dim])
        for (month, value), part in g:
            total = len(part)
            det = int((part["score_category"] == "detractor").sum())
            prom = int((part["score_category"] == "promoter").sum())
            rows.append({"eval_month": month, "dimension": dim, "value": value, "evaluations": total,
                         "detractors": det, "detractor_rate": round(det / total * 100, 2) if total else None,
                         "nps": round((prom - det) / total * 100, 2) if total else None})
    return pd.DataFrame(rows)


def logistics_carrier_scorecard(dperf: pd.DataFrame, nps_a: pd.DataFrame) -> pd.DataFrame:
    d = dperf[dperf["is_delivered"].astype(bool) & ~dperf["is_orphan"].astype(bool)]
    g = d.groupby(["carrier", "ship_month"]).agg(
        deliveries=("delivery_id", "count"), late_evaluable=("late_evaluable", "sum"), late=("is_late", "sum"),
        avg_delay_days=("delay_days", "mean"), avg_lead_time_days=("lead_time_order_to_delivery_days", "mean"))
    g["late_rate"] = np.where(g["late_evaluable"] > 0, (g["late"] / g["late_evaluable"].replace(0, np.nan) * 100).round(2), np.nan)
    e = nps_a.groupby(["carrier", "eval_month"]).agg(
        evaluations=("evaluation_id", "count"), avg_score=("score", "mean"),
        nps=("score", lambda s: round(((s >= 9).sum() - (s <= 6).sum()) / len(s) * 100, 2)))
    e.index = e.index.set_names(["carrier", "ship_month"])
    out = g.join(e, how="outer").reset_index().rename(columns={"ship_month": "month"})
    for c in ("deliveries", "late", "late_evaluable", "evaluations"):
        out[c] = out[c].fillna(0).astype(int)
    for c in ("avg_delay_days", "avg_lead_time_days", "avg_score"):
        out[c] = out[c].astype(float).round(2)
    return out


def logistics_delay_risk(dperf: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Risco de atraso para entregas em aberto (heurística determinística e explicável)."""
    delivered = dperf[dperf["late_evaluable"].astype(bool)]
    recent_cut = as_of - pd.Timedelta(days=60)
    recent = delivered[delivered["actual_delivery_date"] >= recent_cut]
    carrier_rate = recent.groupby("carrier")["is_late"].mean()
    open_d = dperf[~dperf["is_delivered"].astype(bool) & ~dperf["is_orphan"].astype(bool)
                   & dperf["estimated_delivery_date"].notna() & dperf["shipping_date"].notna()].copy()
    if open_d.empty:
        return pd.DataFrame(columns=["delivery_id", "order_id", "carrier", "state", "shipping_date",
                                     "estimated_delivery_date", "days_overdue", "carrier_recent_late_rate",
                                     "elapsed_ratio", "risk_score", "risk_level", "as_of"])
    planned = (open_d["estimated_delivery_date"] - open_d["shipping_date"]).dt.total_seconds().clip(lower=86400)
    elapsed = (as_of - open_d["shipping_date"]).dt.total_seconds()
    open_d["elapsed_ratio"] = (elapsed / planned).round(2)
    open_d["days_overdue"] = ((as_of - open_d["estimated_delivery_date"]).dt.total_seconds() / 86400).clip(lower=0).round(1)
    open_d["carrier_recent_late_rate"] = open_d["carrier"].map(carrier_rate).fillna(carrier_rate.mean()).round(4)
    score = np.where(open_d["days_overdue"] > 0, 1.0,
                     (0.6 * open_d["elapsed_ratio"].clip(upper=1) + 0.4 * open_d["carrier_recent_late_rate"] * 2).clip(0, 1))
    open_d["risk_score"] = np.round(score, 3)
    open_d["risk_level"] = np.select([open_d["risk_score"] >= 0.85, open_d["risk_score"] >= 0.5], ["high", "medium"], "low")
    open_d["as_of"] = as_of
    return open_d[["delivery_id", "order_id", "carrier", "state", "shipping_date", "estimated_delivery_date",
                   "days_overdue", "carrier_recent_late_rate", "elapsed_ratio", "risk_score", "risk_level", "as_of"]]


def products_complaint_frequency(nps_a: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for line, part in nps_a.groupby("product_line"):
        total = len(part)
        theme_lists = part["themes"].fillna("").map(lambda s: [t for t in s.split("|") if t])
        for theme, spec in THEMES.items():
            mask = theme_lists.map(lambda ts: theme in ts)
            mentions = int(mask.sum())
            if mentions == 0:
                continue
            rows.append({"product_line": line, "theme": theme, "theme_label": spec["label"],
                         "polarity": spec["polarity"], "mentions": mentions,
                         "detractor_mentions": int((mask & (part["score_category"] == "detractor")).sum()),
                         "evaluations": total, "mention_rate": round(mentions / total * 100, 2)})
    return pd.DataFrame(rows)


def build_domain_gold(db: Database, lake: Lakehouse, pipeline_run_id: str, actor: str = "pipeline") -> Dict[str, int]:
    nps_a = lake.read_table("gold/corporate", "gold_nps_analytics")
    dperf = lake.read_table("gold/corporate", "gold_delivery_performance")
    orders = lake.read_table("silver", "silver_orders")
    nps = lake.read_table("silver", "silver_nps_evaluations")
    deliveries = lake.read_table("silver", "silver_deliveries")
    as_of = data_watermark(orders, deliveries, nps)
    base_synthetic = row_fields(deliveries) | row_fields(orders)
    demo_nps, demo_log = any_demo(nps_a), any_demo(dperf, nps_a)
    specs: List[tuple] = [
        ("cx", "cx_comment_insights", cx_comment_insights(nps_a), "Comentários e temas (CX)",
         "1 linha por avaliação com comentário", ["gold_nps_analytics"], "nlp themes + sentiment"),
        ("cx", "cx_detractor_drivers", cx_detractor_drivers(nps_a), "Drivers de detratores (CX)",
         "1 linha por mês × dimensão × valor", ["gold_nps_analytics"], "detractor rate by dimension/month"),
        ("logistics", "logistics_carrier_scorecard", logistics_carrier_scorecard(dperf, nps_a),
         "Scorecard de transportadoras", "1 linha por transportadora × mês",
         ["gold_delivery_performance", "gold_nps_analytics"], "carrier late rate + nps by month"),
        ("logistics", "logistics_delay_risk", logistics_delay_risk(dperf, as_of), "Risco de atraso (entregas em aberto)",
         "1 linha por entrega em aberto", ["gold_delivery_performance"], "heuristic risk score v1.0"),
        ("products", "products_complaint_frequency", products_complaint_frequency(nps_a),
         "Frequência de reclamações por linha", "1 linha por linha de produto × tema", ["gold_nps_analytics"],
         "theme mentions by product line"),
    ]
    rows = {}
    for domain, key, df, name, grain, inputs, transform in specs:
        w = lake.write_table(f"gold/domains/{domain}", key, df)
        register_dataset(db, key=key, layer="gold_domain", scope="domain", domain=domain, name=name,
                         description=f"Domain Gold ({domain}) · {name}", grain=grain, path=w["path"], fmt=w["format"],
                         row_count=w["rows"], schema=w["schema"], schema_version=GOLD_VERSION,
                         is_demo=demo_log if domain == "logistics" else demo_nps, pipeline_run_id=pipeline_run_id,
                         synthetic_fields=synthetic_columns(df.columns, base_synthetic))
        record_transformation(db, dataset_key=key, inputs=inputs, transform=transform, rule_version=GOLD_VERSION,
                              rows_in=len(nps_a), rows_out=w["rows"], actor=actor, pipeline_run_id=pipeline_run_id)
        for i in inputs:
            add_edge(db, f"dataset:{i}", f"dataset:{key}", transform)
        rows[key] = w["rows"]
    return rows
