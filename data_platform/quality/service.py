"""Consultas de Data Quality: regras, resultados da última execução e quarentena."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from goops_core.db import Database
from goops_core.util import jload

from .engine import META_RULES, ROW_RULES


def seed_rules(db: Database) -> None:
    with db.connect() as c:
        for r in ROW_RULES:
            c.execute("INSERT INTO dq_rules (rule_key, dataset, description, severity, version, active) "
                      "VALUES (?, ?, ?, ?, ?, 1) ON CONFLICT (rule_key) DO UPDATE SET description = excluded.description, "
                      "severity = excluded.severity, version = excluded.version",
                      (r.key, r.dataset, r.description, r.severity, r.version))
        for key, ds, desc, sev in META_RULES:
            c.execute("INSERT INTO dq_rules (rule_key, dataset, description, severity, version, active) "
                      "VALUES (?, ?, ?, ?, '1.0', 1) ON CONFLICT (rule_key) DO NOTHING", (key, ds, desc, sev))


def quality_overview(db: Database, pipeline_run_id: Optional[str] = None) -> Dict[str, Any]:
    if not pipeline_run_id:
        last = db.fetchone("SELECT pipeline_run_id FROM dq_results ORDER BY executed_at DESC LIMIT 1")
        pipeline_run_id = last["pipeline_run_id"] if last else None
    if not pipeline_run_id:
        return {"pipeline_run_id": None, "results": [], "summary": {}, "rules": db.fetchall("SELECT * FROM dq_rules")}
    results = db.fetchall("SELECT r.*, q.description FROM dq_results r LEFT JOIN dq_rules q ON q.rule_key = r.rule_key "
                          "WHERE r.pipeline_run_id = ? ORDER BY r.dataset, r.severity, r.rule_key", (pipeline_run_id,))
    for r in results:
        r["sample"] = jload(r["sample"], [])
        r["fail_rate"] = round(r["failed"] / r["checked"] * 100, 3) if r["checked"] else None
    quarantine = db.fetchall("SELECT dataset, COUNT(*) AS n FROM quarantine WHERE pipeline_run_id = ? GROUP BY dataset",
                             (pipeline_run_id,))
    summary = {
        "rules_evaluated": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "warnings": sum(1 for r in results if r["status"] == "warning"),
        "errors": sum(1 for r in results if r["status"] == "failed"),
        "quarantined_by_dataset": {q["dataset"]: q["n"] for q in quarantine},
        "quarantined_total": sum(q["n"] for q in quarantine),
    }
    return {"pipeline_run_id": pipeline_run_id, "summary": summary, "results": results}


def list_quarantine(db: Database, dataset: Optional[str] = None, limit: int = 200) -> List[dict]:
    last = db.fetchone("SELECT pipeline_run_id FROM quarantine ORDER BY created_at DESC LIMIT 1")
    if not last:
        return []
    params: List[Any] = [last["pipeline_run_id"]]
    extra = ""
    if dataset:
        extra = " AND dataset = ?"; params.append(dataset)
    rows = db.fetchall(f"SELECT * FROM quarantine WHERE pipeline_run_id = ?{extra} ORDER BY dataset, record_key "
                       f"LIMIT {max(1, min(int(limit), 1000))}", params)
    for r in rows:
        r["payload"] = jload(r["payload"], {})
        r["reasons"] = r["reasons"].split("|") if r["reasons"] else []
    return rows
