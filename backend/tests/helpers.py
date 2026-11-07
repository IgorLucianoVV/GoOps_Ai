"""Ambientes isolados de teste (SQLite + Lakehouse temporários)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from goops_core.config import reset_settings
from goops_core.db import Database, set_db
from goops_core.permissions import SYSTEM_PRINCIPAL, Principal
from data_platform.bootstrap import bootstrap, load_demo
from data_platform.storage import Lakehouse, set_lakehouse
from data_platform.semantic.registry import clear_cache

_CACHE: Dict[str, "Env"] = {}


@dataclass
class Env:
    db: Database
    lake: Lakehouse
    path: Path
    pipeline: dict


def make_env(scenario: str = "full", shared: bool = True) -> Env:
    """Cria (ou reutiliza, se shared) um ambiente com dados de demonstração processados."""
    if shared and scenario in _CACHE:
        env = _CACHE[scenario]
        set_lakehouse(env.lake); set_db(env.db); clear_cache()
        return env
    reset_settings()
    tmp = Path(tempfile.mkdtemp(prefix="goops-test-"))
    db = Database(f"sqlite:///{(tmp / 'goops.db').as_posix()}")
    lake = Lakehouse(tmp / "lake", "auto")
    set_db(db); set_lakehouse(lake); clear_cache()
    from data_platform.connectors import demo_connector
    demo_connector._CACHE.clear()
    bootstrap(db, demo_users=False)
    result = load_demo(db, lake, scenario)
    assert result["status"] == "success", result
    env = Env(db, lake, tmp, result)
    if shared:
        _CACHE[scenario] = env
    return env


def user(role: str, domains=None, uid: str = None) -> Principal:
    return Principal(id=uid or f"USR-{role}", name=role, kind="user", role=role, domains=domains or ["*"])


ADMIN = SYSTEM_PRINCIPAL


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"Esperava {exc_type.__name__}")
