"""Inicialização de runtime da API (banco, lakehouse, seeds)."""
from __future__ import annotations

import logging
import os

from goops_core.config import get_settings
from goops_core.db import get_db
from goops_core.logging_setup import setup_logging
from data_platform.bootstrap import bootstrap, default_scenario, load_demo
from data_platform.storage import get_lakehouse

log = logging.getLogger("goops.api")


def startup() -> dict:
    setup_logging()
    settings = get_settings()
    db = get_db()
    info = bootstrap(db, demo_users=settings.demo_mode)
    lake = get_lakehouse()
    if settings.demo_mode and os.environ.get("AUTO_LOAD_DEMO", "true").lower() == "true" \
            and not db.fetchone("SELECT key FROM datasets LIMIT 1"):
        log.info("Carregando seed inicial (planilhas Gocase se presentes; senão dados sintéticos). AUTO_LOAD_DEMO=false desativa.")
        scenario = default_scenario()
        info["demo_load"] = {"scenario": scenario, "status": load_demo(db, lake, scenario, reset=False)["status"]}
    if info.get("demo_password_generated"):
        log.warning("Senha de demonstração gerada em var/demo_credentials.txt (apenas ambiente local).")
    log.info("GoOps AI iniciado (env=%s, db=%s, storage=%s)", settings.app_env, db.dialect, get_lakehouse().format)
    return info
