"""Inicialização da plataforma: migrações, seeds de catálogo e (opcionalmente) dados de demonstração."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.permissions import SYSTEM_PRINCIPAL
from goops_core.users import seed_demo_users

from .ingestion.service import gocase_seed_available, seed_demo_sources, seed_gocase_sources
from .pipelines.runner import run_pipeline
from .quality.service import seed_rules
from .semantic.registry import seed_domains, seed_metrics
from .storage import Lakehouse

log = logging.getLogger("goops.bootstrap")


def bootstrap(db: Database, demo_users: bool = True) -> Dict[str, Any]:
    applied = db.migrate()
    seed_domains(db)
    seed_rules(db)
    seed_metrics(db)
    generated = seed_demo_users(db) if demo_users else None
    if db.fetchone("SELECT id FROM sources WHERE key = 'gocase_nps'") and gocase_seed_available():
        seed_gocase_sources(db, SYSTEM_PRINCIPAL)   # bancos existentes ganham as fontes de complemento novas
    elif db.fetchone("SELECT id FROM sources WHERE key = 'demo_orders'"):
        from .ingestion.service import apply_features
        apply_features(db)                          # bancos existentes da demo ganham o Atendimento (Desafio 1)
    return {"migrations_applied": applied, "demo_password_generated": bool(generated)}


DEFAULT_SCENARIO = "gocase"


def default_scenario() -> str:
    return "gocase" if gocase_seed_available() else "full"


def load_demo(db: Database, lake: Lakehouse, scenario: str = DEFAULT_SCENARIO, reset: bool = False) -> Dict[str, Any]:
    """Carrega (ou recria) o ambiente inicial.
    * "gocase"  — planilhas reais do case Gocase (seed padrão; dados NÃO sintéticos);
    * "full"    — dados SINTÉTICOS com anomalias e incidente encenado;
    * "basic10" — 10 avaliações sintéticas (NPS esperado = 40)."""
    if scenario not in ("gocase", "full", "basic10"):
        raise ValueError(f"Cenário inválido: {scenario}")
    if reset:
        lake.reset()
        with db.connect() as c:
            for table in ("support_events", "support_contacts", "quarantine", "dq_results", "transformations", "lineage_edges", "datasets", "ingestion_failures",
                          "ingestion_runs", "pipeline_runs", "incident_events", "incidents", "operations",
                          "workflow_runs", "agent_runs", "routing_decisions", "llm_calls"):
                c.execute(f"DELETE FROM {table}")
            c.execute("DELETE FROM sources WHERE is_demo = 1")
            for row in c.fetchall("SELECT id, config FROM sources WHERE connector = 'file'"):
                from goops_core.util import jload
                if (jload(row["config"], {}) or {}).get("seed"):
                    c.execute("DELETE FROM sources WHERE id = ?", (row["id"],))
        from .semantic.registry import clear_cache
        clear_cache()
        from data_platform.connectors import demo_connector
        demo_connector._CACHE.clear()
        from .semantic.registry import rebuild_metric_lineage
        rebuild_metric_lineage(db)
        record_audit(db, SYSTEM_PRINCIPAL, "demo.reset", "platform", None, {"scenario": scenario})
    if scenario == "gocase":
        if not gocase_seed_available():
            raise FileNotFoundError("Planilhas da seed Gocase não encontradas em data/seed/gocase/.")
        seed_gocase_sources(db, SYSTEM_PRINCIPAL)
    else:
        seed_demo_sources(db, SYSTEM_PRINCIPAL, scenario)
    result = run_pipeline(db, lake, SYSTEM_PRINCIPAL, sync=True)
    record_audit(db, SYSTEM_PRINCIPAL, "demo.load", "platform", None, {"scenario": scenario, "status": result["status"]})
    return result
