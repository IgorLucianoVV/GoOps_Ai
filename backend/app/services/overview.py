"""Visão executiva agregada (Overview)."""
from __future__ import annotations

from typing import Any, Dict

from goops_core.db import Database
from goops_core.errors import GoOpsError, NotFound
from goops_core.incidents import OPEN_STATUSES, list_incidents
from goops_core.operations import list_operations
from goops_core.permissions import Principal
from data_platform.analytics.nps import NpsAnalytics
from data_platform.pipelines.runner import list_pipeline_runs
from data_platform.quality.service import quality_overview
from data_platform.semantic.registry import compute_metric
from data_platform.storage import Lakehouse
from agents.base import list_agent_runs
from agents.routing.router import efficiency_metrics


def build_overview(db: Database, lake: Lakehouse, actor: Principal) -> Dict[str, Any]:
    incidents = list_incidents(db, limit=500)
    open_inc = [i for i in incidents if i["status"] in OPEN_STATUSES]
    out: Dict[str, Any] = {
        "incidents": {
            "open": len(open_inc), "critical": sum(1 for i in open_inc if i["severity"] == "critical"),
            "high": sum(1 for i in open_inc if i["severity"] == "high"),
            "awaiting_approval": sum(1 for i in open_inc if i["status"] == "awaiting_approval"),
            "recent": [{k: i[k] for k in ("id", "title", "severity", "status", "category", "detected_at", "is_demo")}
                       for i in incidents[:6]],
        },
        "operations_pending": len(list_operations(db, status="pending_approval")),
        "pipeline": (list_pipeline_runs(db, 1) or [None])[0],
        "agent_activity": [{k: r[k] for k in ("id", "agent_key", "task", "status", "started_at", "incident_id")}
                           for r in list_agent_runs(db, limit=10)],
        "routing": efficiency_metrics(db),
        "data_quality": quality_overview(db).get("summary", {}),
        "nps": None, "logistics": None, "ready": False,
    }
    try:
        a = NpsAnalytics(db, lake, actor)
        ov = a.overview()
        evo = [r for r in a.evolution()["rows"] if r["has_data"]]
        out["nps"] = {"current": ov["nps"], "metric": ov["metric"], "trend": evo[-6:], "meta": ov["meta"]}
        late = compute_metric(db, lake, actor, "METRIC_LATE_DELIVERY_RATE_001")
        by_carrier = compute_metric(db, lake, actor, "METRIC_LATE_DELIVERY_RATE_001", group_by="carrier")
        days = compute_metric(db, lake, actor, "METRIC_DELIVERY_DAYS_001")
        days_by_carrier = compute_metric(db, lake, actor, "METRIC_DELIVERY_DAYS_001", group_by="carrier")
        out["logistics"] = {"late_rate": late["result"], "metric": late["metric"], "by_carrier": by_carrier["groups"],
                            "delivery_days": days["result"], "days_metric": days["metric"],
                            "days_by_carrier": days_by_carrier["groups"]}
        out["ready"] = True
    except (FileNotFoundError, NotFound):
        out["message"] = "Nenhum dado processado ainda. Execute o pipeline ou carregue os dados de demonstração."
    except GoOpsError as exc:
        out["message"] = exc.message
    return out
