"""Painéis configuráveis por setor: widgets declarativos ligados a métricas governadas.

Widget: {"id", "title", "metric_key", "chart": kpi|bar|line|table, "group_by": dimensão|null}
Todos os números são calculados no backend pela métrica oficial (compute_metric); o frontend só desenha.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import GoOpsError, ValidationError
from goops_core.permissions import Principal, has_permission, require_permission
from goops_core.util import jdump, jload, new_id, now_iso

from ..semantic.registry import compute_metric, get_metric, list_metrics
from ..storage import Lakehouse

CHARTS = {"kpi", "bar", "line", "table"}


def get_dashboard(db: Database, domain: str) -> Optional[dict]:
    r = db.fetchone("SELECT * FROM dashboards WHERE key = ?", (domain,))
    if not r:
        return None
    r["widgets"] = jload(r["widgets"], [])
    return r


def validate_widgets(db: Database, domain: str, widgets: List[dict]) -> List[dict]:
    if not isinstance(widgets, list) or len(widgets) > 40:
        raise ValidationError("Até 40 widgets por painel.")
    out = []
    for w in widgets:
        m = get_metric(db, str(w.get("metric_key") or ""))
        if m["domain"] not in (domain, "corporate"):
            raise ValidationError(f"A métrica {m['metric_key']} não pertence ao setor {domain}.")
        chart = w.get("chart")
        if chart not in CHARTS:
            raise ValidationError(f"Tipo de gráfico inválido: {chart}")
        gb = w.get("group_by") or None
        if chart in ("bar", "line", "table") and not gb:
            raise ValidationError(f"O gráfico '{w.get('title')}' precisa de um agrupamento.")
        if gb and gb not in m["dimensions"]:
            raise ValidationError(f"'{gb}' não é dimensão permitida de {m['metric_key']}.")
        out.append({"id": str(w.get("id") or new_id("W")), "title": str(w.get("title") or m["name"])[:120],
                    "metric_key": m["metric_key"], "chart": chart, "group_by": gb if chart != "kpi" else None})
    return out


def save_dashboard(db: Database, actor: Principal, domain: str, name: str, widgets: List[dict]) -> dict:
    require_permission(actor, "semantic:write", domain)
    clean = validate_widgets(db, domain, widgets)
    ts = now_iso()
    if db.fetchone("SELECT id FROM dashboards WHERE key = ?", (domain,)):
        db.execute("UPDATE dashboards SET name = ?, widgets = ?, updated_by = ?, updated_at = ? WHERE key = ?",
                   (name, jdump(clean), actor.actor_label, ts, domain))
    else:
        db.execute("INSERT INTO dashboards (id, key, domain, name, widgets, created_by, created_at, updated_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (new_id("DSH"), domain, domain, name, jdump(clean), actor.actor_label, ts, ts))
    record_audit(db, actor, "sector.dashboard_save", "dashboard", domain, {"widgets": len(clean)})
    return get_dashboard(db, domain)


def render_dashboard(db: Database, lake: Lakehouse, actor: Principal, domain: str,
                     filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    require_permission(actor, "analytics:read", domain)
    dash = get_dashboard(db, domain)
    if not dash:
        return {"dashboard": None, "widgets": []}
    out = []
    for w in dash["widgets"]:
        try:
            res = compute_metric(db, lake, actor, w["metric_key"], filters or {}, w["group_by"], allow_draft=True)
            if w["group_by"] == "month" and "groups" in res:
                res["groups"] = [g for g in res["groups"] if g.get("month") != "Não identificado"]
            out.append({**w, "data": res, "error": None})
        except GoOpsError as exc:
            out.append({**w, "data": None, "error": exc.message})
    return {"dashboard": dash, "widgets": out}


def sector_metrics(db: Database, domain: str) -> List[dict]:
    return [m for m in list_metrics(db) if m["domain"] == domain]


def can_edit(actor: Principal, domain: str) -> bool:
    return has_permission(actor, "semantic:write", domain)
