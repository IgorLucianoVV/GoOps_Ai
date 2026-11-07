"""Orquestração do pipeline (Fonte -> Bronze -> Silver -> Gold -> Semântica).

Implementação própria e leve; cada etapa é registrada em pipeline_runs. Etapas são funções
isoladas, permitindo migração futura para Dagster sem reescrever a lógica (ver DECISIONS.md).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import GoOpsError
from goops_core.permissions import Principal, require_permission
from goops_core.util import jdump, jload, new_id, now_iso

from ..dictionary.catalog import sync_dictionary
from ..gold.corporate import build_corporate_gold
from ..gold.domains.builders import build_domain_gold
from ..ingestion.service import sync_source
from ..semantic.registry import clear_cache, seed_metrics
from ..silver.transforms import build_silver
from ..storage import Lakehouse

log = logging.getLogger("goops.pipeline")


def run_pipeline(db: Database, lake: Lakehouse, actor: Principal, sync: bool = True,
                 sources: Optional[List[str]] = None) -> Dict[str, Any]:
    require_permission(actor, "data:sync")
    run_id = new_id("PIP")
    db.execute("INSERT INTO pipeline_runs (id, started_at, status, triggered_by, steps) VALUES (?, ?, 'running', ?, ?)",
               (run_id, now_iso(), actor.actor_label, jdump([])))
    steps: List[Dict[str, Any]] = []

    def step(name: str, fn):
        t0 = time.perf_counter()
        try:
            out = fn()
            steps.append({"step": name, "status": "success", "ms": int((time.perf_counter() - t0) * 1000), "output": out})
            db.execute("UPDATE pipeline_runs SET steps = ? WHERE id = ?", (jdump(steps), run_id))
            return out
        except Exception as exc:
            steps.append({"step": name, "status": "failed", "ms": int((time.perf_counter() - t0) * 1000),
                          "error": exc.message if isinstance(exc, GoOpsError) else f"{type(exc).__name__}: {exc}"[:300]})
            db.execute("UPDATE pipeline_runs SET steps = ? WHERE id = ?", (jdump(steps), run_id))
            raise

    try:
        if sync:
            # contatos sintéticos de atendimento dependem da Gold: sincronizados na etapa "support"
            keys = sources or [r["key"] for r in db.fetchall("SELECT key FROM sources WHERE status = 'active' "
                                                             "AND connector <> 'support_demo'")]
            results = step("ingestion", lambda: {k: sync_source(db, lake, actor, k) for k in keys})
            if all(r.get("status") == "failed" for r in results.values()) and results:
                raise GoOpsError("Todas as ingestões falharam; pipeline interrompido.")
        silver = step("silver", lambda: build_silver(db, lake, run_id, actor.actor_label))
        step("data_quality", lambda: {
            "rules": len(silver["dq_results"]),
            "failed_or_warning": sum(1 for r in silver["dq_results"] if r["status"] in ("failed", "warning")),
            "quarantined": sum(d.get("quarantined", 0) for d in silver["datasets"].values())})
        step("gold_corporate", lambda: build_corporate_gold(db, lake, run_id, actor.actor_label))
        step("gold_domain", lambda: build_domain_gold(db, lake, run_id, actor.actor_label))
        from ..sectors.datasets import build_custom_datasets
        step("sectors", lambda: build_custom_datasets(db, lake, run_id, actor.actor_label))
        from ..sectors.stock import build_stock
        step("stock_recipe", lambda: build_stock(db, lake, run_id, actor.actor_label))
        from ..support.pipeline import build_support
        step("support", lambda: build_support(db, lake, run_id, actor))
        step("semantic", lambda: {"metrics_seeded": seed_metrics(db)})
        step("dictionary", lambda: {"fields": sync_dictionary(db)})
        clear_cache()
        db.execute("UPDATE pipeline_runs SET status = 'success', finished_at = ?, steps = ? WHERE id = ?",
                   (now_iso(), jdump(steps), run_id))
        record_audit(db, actor, "pipeline.run", "pipeline", run_id, {"status": "success"})
        return {"run_id": run_id, "status": "success", "steps": steps}
    except Exception as exc:
        msg = exc.message if isinstance(exc, GoOpsError) else f"{type(exc).__name__}: {exc}"[:300]
        db.execute("UPDATE pipeline_runs SET status = 'failed', finished_at = ?, error = ?, steps = ? WHERE id = ?",
                   (now_iso(), msg, jdump(steps), run_id))
        record_audit(db, actor, "pipeline.run", "pipeline", run_id, {"status": "failed", "error": msg})
        log.exception("pipeline failed")
        return {"run_id": run_id, "status": "failed", "error": msg, "steps": steps}


def list_pipeline_runs(db: Database, limit: int = 50) -> List[dict]:
    rows = db.fetchall(f"SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT {max(1, min(int(limit), 200))}")
    for r in rows:
        r["steps"] = jload(r["steps"], [])
    return rows


def latest_successful_run(db: Database) -> Optional[dict]:
    return db.fetchone("SELECT * FROM pipeline_runs WHERE status = 'success' ORDER BY started_at DESC LIMIT 1")
