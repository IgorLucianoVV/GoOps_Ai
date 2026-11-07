"""Analytics de Logística, Produtos, Regional e CX (consomem Gold + métricas governadas)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from goops_core.db import Database
from goops_core.permissions import Principal, require_permission
from goops_core.util import to_jsonable

from ..catalog import get_dataset, storage_layer_for
from ..semantic.registry import compute_metric
from ..storage import Lakehouse


def _records(db: Database, lake: Lakehouse, key: str, sort: Optional[str] = None, ascending: bool = True,
             limit: Optional[int] = None) -> Dict[str, Any]:
    ds = get_dataset(db, key)
    df = lake.read_table(storage_layer_for(ds), key)
    if sort and sort in df.columns:
        df = df.sort_values(sort, ascending=ascending)
    if limit:
        df = df.head(limit)
    return {"rows": [to_jsonable(r) for r in df.to_dict(orient="records")],
            "meta": {"dataset": key, "layer": ds["layer"], "domain": ds["domain"], "built_at": ds["last_built_at"],
                     "is_demo": ds["is_demo"], "grain": ds["grain"],
                     "synthetic_fields": ds.get("synthetic_fields") or []}}


def logistics_overview(db: Database, lake: Lakehouse, actor: Principal) -> Dict[str, Any]:
    require_permission(actor, "analytics:read", "logistics")
    late = compute_metric(db, lake, actor, "METRIC_LATE_DELIVERY_RATE_001")
    late_by_carrier = compute_metric(db, lake, actor, "METRIC_LATE_DELIVERY_RATE_001", group_by="carrier")
    lead_by_carrier = compute_metric(db, lake, actor, "METRIC_DELIVERY_LEAD_TIME_001", group_by="carrier")
    on_time_tol = compute_metric(db, lake, actor, "LOG_ON_TIME_TOLERANCE_001")
    late_by_type = compute_metric(db, lake, actor, "METRIC_LATE_DELIVERY_RATE_001", group_by="shipping_type")
    days = compute_metric(db, lake, actor, "METRIC_DELIVERY_DAYS_001")
    days_by_carrier = compute_metric(db, lake, actor, "METRIC_DELIVERY_DAYS_001", group_by="carrier")
    days_by_type = compute_metric(db, lake, actor, "METRIC_DELIVERY_DAYS_001", group_by="shipping_type")
    lead = compute_metric(db, lake, actor, "METRIC_DELIVERY_LEAD_TIME_001")
    lead_by_type = compute_metric(db, lake, actor, "METRIC_DELIVERY_LEAD_TIME_001", group_by="shipping_type")
    return {
        "late_rate": late, "late_by_carrier": late_by_carrier, "lead_time_by_carrier": lead_by_carrier,
        "lead_time": lead, "lead_time_by_shipping_type": lead_by_type,
        "late_by_shipping_type": late_by_type, "on_time_with_tolerance": on_time_tol,
        "delivery_days": days, "delivery_days_by_carrier": days_by_carrier, "delivery_days_by_shipping_type": days_by_type,
        "scorecard": _records(db, lake, "logistics_carrier_scorecard", "month"),
        "delay_risk": _records(db, lake, "logistics_delay_risk", "risk_score", ascending=False, limit=100),
    }


def products_overview(db: Database, lake: Lakehouse, actor: Principal) -> Dict[str, Any]:
    require_permission(actor, "analytics:read", "products")
    return {
        "performance": _records(db, lake, "gold_product_performance", "detractor_rate", ascending=False),
        "complaints": _records(db, lake, "products_complaint_frequency", "mentions", ascending=False),
        "complaint_rate_by_line": compute_metric(db, lake, actor, "PRD_COMPLAINT_RATE_001", group_by="product_line"),
    }


def regional_overview(db: Database, lake: Lakehouse, actor: Principal) -> Dict[str, Any]:
    require_permission(actor, "analytics:read")
    return {"regions": _records(db, lake, "gold_regional_performance", "nps"),
            "nps_by_state": compute_metric(db, lake, actor, "METRIC_NPS_001", group_by="state")}


def cx_overview(db: Database, lake: Lakehouse, actor: Principal) -> Dict[str, Any]:
    require_permission(actor, "analytics:read", "cx")
    return {
        "nps_corporate": compute_metric(db, lake, actor, "METRIC_NPS_001"),
        "nps_commented_domain": compute_metric(db, lake, actor, "CX_NPS_COMMENTED_001"),
        "drivers": _records(db, lake, "cx_detractor_drivers", "detractor_rate", ascending=False, limit=60),
        "customers": {"note": "gold_customer_experience contém dados pessoais pseudonimizados; agregados apenas.",
                      "summary": _customer_summary(db, lake)},
    }


def _customer_summary(db: Database, lake: Lakehouse) -> Dict[str, Any]:
    df = lake.read_table("gold/corporate", "gold_customer_experience")
    rated = df[df["n_evaluations"] > 0]
    return {"customers": int(len(df)), "customers_with_evaluation": int(len(rated)),
            "repeat_customers": int((df["n_orders"] > 1).sum()),
            "customers_last_detractor": int((rated["last_category"] == "detractor").sum())}
