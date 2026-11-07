"""Briefing diário: o que mudou, onde olhar e o que está esperando decisão — em uma mensagem.

Conteúdo 100% calculado pelas métricas governadas, incidentes e operações; a narrativa por IA (opcional) só reescreve
o texto determinístico. Entrega em Slack/e-mail SEMPRE simulada (registrada, nada é enviado).
Ligável/desligável e configurável em Configurações › Recursos.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import GoOpsError
from goops_core.incidents import list_incidents
from goops_core.operations import list_operations
from goops_core.permissions import Principal, require_permission
from goops_core.runtime_config import get_section
from goops_core.util import jdump, jload, new_id, now_iso
from data_platform.storage import Lakehouse

from .custom import _fmt, _months
from .instructions import prompt_for

SEV = {"critical": "crítica", "high": "alta", "medium": "média", "low": "baixa"}


def _metric_line(db: Database, lake: Lakehouse, p: Principal, key: str, label: Optional[str] = None) -> Optional[Dict[str, Any]]:
    from data_platform.semantic.registry import compute_metric, get_metric
    try:
        m = get_metric(db, key)
        if m["status"] != "active":
            return None
        dim = "month" if "month" in m["dimensions"] else ("eval_month" if "eval_month" in m["dimensions"] else
                                                           "ship_month" if "ship_month" in m["dimensions"] else None)
        if dim:
            groups = compute_metric(db, lake, p, key, group_by=dim)
            rows = [{**g, "month": g[dim]} for g in groups["groups"]]
            s = _months(rows, 1)
            last, prev = (s[-1] if s else None), (s[-2] if len(s) > 1 else None)
            synthetic = groups["metric"].get("synthetic")
        else:
            r = compute_metric(db, lake, p, key)
            last, prev, synthetic = {"month": "total", **r["result"]}, None, r["metric"].get("synthetic")
        if not last or last.get("value") is None:
            return None
        delta = last["value"] - prev["value"] if prev and prev.get("value") is not None else None
        arrow = "" if delta is None else (" ▲ " if delta > 0 else " ▼ " if delta < 0 else " = ")
        unit = m["unit"].split(" (")[0]                     # "pontos (-100 a +100)" -> "pontos"
        txt = f"- **{label or m['name']}** ({last['month']}): **{_fmt(last['value'], unit)}**"
        if delta is not None:
            dtxt = _fmt(abs(delta), "").strip() + " p.p." if unit == "%" else _fmt(abs(delta), unit)
            txt += f"{arrow}{dtxt} vs. {prev['month']}"
        if synthetic:
            txt += " _(inclui dados sintéticos de demonstração)_"
        return {"line": txt, "metric_key": key, "value": last["value"], "previous": prev["value"] if prev else None}
    except GoOpsError:
        return None


def build_briefing(db: Database, lake: Lakehouse, p: Principal) -> Dict[str, Any]:
    sections: List[str] = []
    data: Dict[str, Any] = {"metrics": []}
    core = [("METRIC_NPS_001", "NPS"), ("METRIC_LATE_DELIVERY_RATE_001", "Entregas atrasadas"),
            ("METRIC_DELIVERY_LEAD_TIME_001", "Prazo envio→entrega")]
    lines = [x for x in (_metric_line(db, lake, p, k, lbl) for k, lbl in core) if x]
    if lines:
        sections.append("**Indicadores principais**\n" + "\n".join(x["line"] for x in lines))
        data["metrics"] += lines
    from data_platform.sectors.dashboards import get_dashboard
    for d in db.fetchall("SELECT key, name FROM domains WHERE status = 'active' AND key <> 'corporate' ORDER BY key"):
        dash = get_dashboard(db, d["key"])
        if not dash:
            continue
        kpis = [w for w in dash["widgets"] if w["chart"] == "kpi"][:3]
        sl = [x for x in (_metric_line(db, lake, p, w["metric_key"], w["title"]) for w in kpis) if x]
        if sl:
            sections.append(f"**{d['name']}**\n" + "\n".join(x["line"] for x in sl))
            data["metrics"] += sl
    open_inc = list_incidents(db, only_open=True)
    data["incidents_open"] = len(open_inc)
    if open_inc:
        top = sorted(open_inc, key=lambda i: ["critical", "high", "medium", "low"].index(i["severity"]))[:3]
        sections.append(f"**Incidentes abertos: {len(open_inc)}**\n" + "\n".join(
            f"- [{SEV.get(i['severity'], i['severity'])}] {i['title']}" for i in top))
    else:
        sections.append("**Incidentes abertos:** nenhum.")
    pending = list_operations(db, status="pending_approval")
    data["operations_pending"] = len(pending)
    if pending:
        sections.append(f"**Aguardando sua decisão: {len(pending)} ação(ões)**\n" + "\n".join(
            f"- {o['title']} — {o['description'][:120]}" for o in pending[:3]))
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    md = f"### Briefing GoOps — {today}\n\n" + "\n\n".join(sections) + \
        "\n\n_Números das métricas governadas; variações não implicam causa. Detalhes no GoOps._"
    return {"content_md": md, "data": data}


def _ai(db: Database, md: str) -> Dict[str, Any]:
    from .routing.router import CostRouter
    res = CostRouter(db).run(agent_key="assistant", task="daily_briefing", deterministic=lambda: None, max_tokens=450,
                             prompt=lambda: (prompt_for(db, "daily_briefing") + f"\n<evidence>{md}</evidence>"))
    return {"narrative_md": res["output"], "generated_by": res["generated_by"], "fallback": res.get("fallback_reason")}


def run_briefing(db: Database, lake: Lakehouse, actor: Principal, triggered_by: str = "manual") -> Dict[str, Any]:
    if triggered_by != "scheduler":
        require_permission(actor, "agents:execute")
    cfg = get_section(db, "features")
    b = build_briefing(db, lake, actor)
    ai = _ai(db, b["content_md"]) if cfg.get("briefing_ai") else {"narrative_md": None, "generated_by": "deterministic"}
    deliveries = []
    if cfg.get("briefing_slack"):
        deliveries.append({"channel": "slack", "target": cfg.get("briefing_slack_channel"), "status": "simulado"})
    if cfg.get("briefing_email") and cfg.get("briefing_email_to"):
        deliveries.append({"channel": "email", "target": ", ".join(cfg["briefing_email_to"]), "status": "simulado"})
    bid = new_id("BRF")
    db.execute("INSERT INTO briefings (id, created_at, triggered_by, content_md, narrative_md, generated_by, data, deliveries) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (bid, now_iso(), triggered_by, b["content_md"], ai.get("narrative_md"),
                                                    ai["generated_by"], jdump(b["data"]), jdump(deliveries)))
    record_audit(db, actor, "briefing.generate", "briefing", bid, {"deliveries": [d["channel"] for d in deliveries],
                                                                   "simulated": True})
    return get_briefing(db, bid)


def _row(r: dict) -> dict:
    r["data"] = jload(r.get("data"), {})
    r["deliveries"] = jload(r.get("deliveries"), [])
    return r


def get_briefing(db: Database, bid: str) -> dict:
    return _row(db.fetchone("SELECT * FROM briefings WHERE id = ?", (bid,)))


def list_briefings(db: Database, limit: int = 20) -> List[dict]:
    return [_row(r) for r in db.fetchall(f"SELECT * FROM briefings ORDER BY created_at DESC LIMIT {int(limit)}")]


def briefing_due(db: Database, now: Optional[datetime] = None) -> bool:
    cfg = get_section(db, "features")
    if not cfg.get("briefing_enabled"):
        return False
    now = now or datetime.now(timezone.utc)
    last = db.fetchone("SELECT created_at FROM briefings WHERE triggered_by = 'scheduler' ORDER BY created_at DESC LIMIT 1")
    return last is None or datetime.fromisoformat(last["created_at"]) + timedelta(minutes=int(cfg["briefing_interval_minutes"])) <= now
