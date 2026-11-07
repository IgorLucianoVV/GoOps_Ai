"""Agendador de jobs (pipeline, ciclo de monitoramento, retenção) configurado pela interface.

Roda como thread no processo da API. Para evitar execuções duplicadas com várias instâncias,
usa um "lease" no banco com compare-and-set (app_settings 'scheduler:lease'). Intervalos e
habilitação vêm da seção 'scheduler' da configuração em tela.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from goops_core.db import Database
from goops_core.errors import GoOpsError
from goops_core.permissions import SYSTEM_PRINCIPAL, Principal, require_permission
from goops_core.runtime_config import get_section
from goops_core.util import jdump, jload, new_id, now_iso
from data_platform.storage import Lakehouse

log = logging.getLogger("goops.scheduler")
INSTANCE_ID = uuid.uuid4().hex[:10]
LEASE_SECONDS = 120
JOBS = ("pipeline", "monitor", "retention", "support")


def _job_fn(job: str, db: Database, lake: Lakehouse, actor: Principal) -> Callable[[], Any]:
    if job == "pipeline":
        from data_platform.pipelines.runner import run_pipeline
        return lambda: {k: v for k, v in run_pipeline(db, lake, actor, sync=True).items() if k in ("run_id", "status", "error")}
    if job == "monitor":
        from .supervisor.agent import Supervisor
        return lambda: Supervisor(db, lake).run_monitoring_cycle(actor)
    if job == "retention":
        from data_platform.retention import apply_retention
        return lambda: {k: (len(v) if isinstance(v, list) else v) for k, v in
                        apply_retention(db, lake, actor, dry_run=False).items() if k != "policy"}
    if job == "support":
        from .support.shift import run_shift
        from goops_core.permissions import agent_principal
        return lambda: run_shift(db, lake, agent_principal("support"))
    raise ValueError(job)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def acquire_lease(db: Database, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    row = db.fetchone("SELECT value FROM app_settings WHERE key = 'scheduler:lease'")
    new_value = jdump({"holder": INSTANCE_ID, "expires": (now + timedelta(seconds=LEASE_SECONDS)).isoformat()})
    if row is None:
        try:
            db.execute("INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES ('scheduler:lease', ?, ?, ?)",
                       (new_value, INSTANCE_ID, now.isoformat()))
            return True
        except Exception:  # noqa: BLE001 - outra instância inseriu antes
            return False
    current = jload(row["value"], {})
    if current.get("holder") != INSTANCE_ID and _parse(current.get("expires", "1970-01-01T00:00:00+00:00")) > now:
        return False
    with db.connect() as c:  # compare-and-set
        cur = c.execute("UPDATE app_settings SET value = ?, updated_by = ?, updated_at = ? "
                        "WHERE key = 'scheduler:lease' AND value = ?", (new_value, INSTANCE_ID, now.isoformat(), row["value"]))
        return cur.rowcount == 1


def last_run(db: Database, job: str) -> Optional[dict]:
    return db.fetchone("SELECT * FROM scheduler_runs WHERE job = ? ORDER BY started_at DESC LIMIT 1", (job,))


def run_job(db: Database, lake: Lakehouse, job: str, actor: Principal, triggered_by: str) -> dict:
    if job not in JOBS:
        raise GoOpsError(f"Job desconhecido: {job}")
    run_id = new_id("SCH")
    db.execute("INSERT INTO scheduler_runs (id, job, started_at, status, triggered_by) VALUES (?, ?, ?, 'running', ?)",
               (run_id, job, now_iso(), triggered_by))
    try:
        out = _job_fn(job, db, lake, actor)()
        status, error = "success", None
    except Exception as exc:  # noqa: BLE001 - registrado e exibido na interface
        out, status = None, "failed"
        error = exc.message if isinstance(exc, GoOpsError) else f"{type(exc).__name__}: {str(exc)[:300]}"
        log.exception("scheduler job %s failed", job)
    db.execute("UPDATE scheduler_runs SET finished_at = ?, status = ?, output = ?, error = ? WHERE id = ?",
               (now_iso(), status, jdump(out), error, run_id))
    return {"id": run_id, "job": job, "status": status, "error": error, "output": out}


def due_jobs(db: Database, now: Optional[datetime] = None) -> List[str]:
    now = now or datetime.now(timezone.utc)
    cfg = get_section(db, "scheduler")
    due = []
    for job in JOBS:
        if not cfg.get(f"{job}_enabled"):
            continue
        last = last_run(db, job)
        interval = timedelta(minutes=int(cfg[f"{job}_interval_minutes"]))
        if last is None or _parse(last["started_at"]) + interval <= now:
            due.append(job)
    return due


def run_due_jobs(db: Database, lake: Lakehouse, now: Optional[datetime] = None) -> List[dict]:
    from .briefing import briefing_due, run_briefing
    from .custom import due_agents, run_agent
    jobs = due_jobs(db, now)
    agents = due_agents(db, now)
    brief = briefing_due(db, now)
    if not (jobs or agents or brief) or not acquire_lease(db, now):
        return []
    out = [run_job(db, lake, j, SYSTEM_PRINCIPAL, "scheduler") for j in jobs]
    if brief:                                        # briefing diário (Configurações › Recursos)
        try:
            out.append({"job": "briefing", "id": run_briefing(db, lake, SYSTEM_PRINCIPAL, "scheduler")["id"]})
        except Exception:  # noqa: BLE001
            log.exception("briefing failed")
    for key in agents:                               # agentes configurados nos setores (frequência própria)
        try:
            out.append({"job": f"agent:{key}", **run_agent(db, lake, SYSTEM_PRINCIPAL, key, "scheduler")})
        except Exception:  # noqa: BLE001
            log.exception("custom agent %s failed", key)
    return out


def scheduler_status(db: Database) -> Dict[str, Any]:
    cfg = get_section(db, "scheduler")
    out = {"config": cfg, "jobs": [], "instance": INSTANCE_ID, "thread_running": _THREAD is not None and _THREAD.is_alive()}
    for job in JOBS:
        last = last_run(db, job)
        nxt = None
        if cfg.get(f"{job}_enabled"):
            nxt = (_parse(last["started_at"]) + timedelta(minutes=int(cfg[f"{job}_interval_minutes"]))).isoformat() \
                if last else "na próxima verificação"
        if last:
            last = {**last, "output": jload(last.get("output"), None)}
        out["jobs"].append({"job": job, "enabled": bool(cfg.get(f"{job}_enabled")),
                            "interval_minutes": cfg[f"{job}_interval_minutes"], "last_run": last, "next_run": nxt})
    out["history"] = [{**r, "output": jload(r.get("output"), None)} for r in
                      db.fetchall("SELECT * FROM scheduler_runs ORDER BY started_at DESC LIMIT 30")]
    return out


def trigger(db: Database, lake: Lakehouse, actor: Principal, job: str) -> dict:
    perm = {"pipeline": "data:sync", "monitor": "agents:execute", "retention": "data:write"}.get(job)
    if perm is None:
        raise GoOpsError(f"Job desconhecido: {job}")
    require_permission(actor, perm)
    return run_job(db, lake, job, actor, actor.actor_label)


class SchedulerThread(threading.Thread):
    def __init__(self, db: Database, lake: Lakehouse, poll_seconds: int = 30):
        super().__init__(daemon=True, name="goops-scheduler")
        self.db, self.lake, self.poll = db, lake, poll_seconds
        self.stop_event = threading.Event()

    def run(self) -> None:
        log.info("scheduler started (instance %s)", INSTANCE_ID)
        while not self.stop_event.wait(self.poll):
            try:
                run_due_jobs(self.db, self.lake)
            except Exception:  # noqa: BLE001
                log.exception("scheduler loop error")

    def stop(self) -> None:
        self.stop_event.set()


_THREAD: Optional[SchedulerThread] = None


def start_scheduler(db: Database, lake: Lakehouse) -> None:
    global _THREAD
    if _THREAD is None or not _THREAD.is_alive():
        _THREAD = SchedulerThread(db, lake)
        _THREAD.start()


def stop_scheduler() -> None:
    if _THREAD is not None:
        _THREAD.stop()
