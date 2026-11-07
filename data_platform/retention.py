"""Política de retenção (configurável na interface — seção 'retention').

* Bronze: um arquivo de execução mais antigo que `bronze_days` só é expurgado se TODOS os seus
  registros (por chave natural) existirem em execuções posteriores — assim o reprocessamento da
  Silver nunca perde dados, inclusive em fontes incrementais. A execução é marcada (purged_at).
* Quarentena: registros de execuções de pipeline mais antigas que `quarantine_days`, exceto a última.
* Logs de roteamento/LLM: mais antigos que `logs_days`.
* Auditoria (audit_log) e timelines de incidentes NÃO são expurgadas.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.permissions import Principal, require_permission
from goops_core.runtime_config import get_section
from goops_core.util import now_iso

from .silver.mappings import mapping_for
from .storage import Lakehouse


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).replace(microsecond=0).isoformat()


def _natural_key(db: Database, source_entity: str, profile: str = "default") -> tuple:
    from .silver.profiles import resolve_mapping
    m = resolve_mapping(db, source_entity, profile)
    spec = m["fields"][m["natural_key"]]
    return m["natural_key"], spec.get("compose") or spec.get("from", [])


def _keys_in_file(path, from_fields) -> set:
    keys = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            payload = json.loads(line).get("payload") or {}
            from .silver.transforms import _MISSING, lookup
            values = [None if (v := lookup(payload, f)) is _MISSING else v for f in from_fields]
            present = [v for v in values if v not in (None, "")]
            if present:
                keys.add(":".join(str(v).strip() for v in present))
            else:
                keys.add(f"__nokey__{line[:40]}")
    return keys


def apply_retention(db: Database, lake: Lakehouse, actor: Principal, dry_run: bool = True) -> Dict[str, Any]:
    require_permission(actor, "data:write")
    policy = get_section(db, "retention")
    report: Dict[str, Any] = {"dry_run": dry_run, "policy": policy, "bronze": [], "quarantine_rows": 0, "log_rows": 0}
    bronze_cut = _cutoff(policy["bronze_days"])
    from goops_core.util import jload
    for src in db.fetchall("SELECT key, entity, config FROM sources"):
        runs = db.fetchall("SELECT id, started_at, bronze_path FROM ingestion_runs WHERE source_key = ? AND "
                           "bronze_path IS NOT NULL AND purged_at IS NULL AND status IN ('success', 'partial') "
                           "ORDER BY started_at", (src["key"],))
        if len(runs) < 2:
            continue
        cfg = jload(src["config"], {}) or {}
        if src["entity"] == "custom":
            # Fontes de setor/receita: só expurga quando a chave natural é conhecida (contatos: id externo);
            # nas demais, a Bronze é mantida (conservador — nunca perde dado).
            if cfg.get("recipe") != "support":
                continue
            from_fields = ["external_id"]
        else:
            _, from_fields = _natural_key(db, src["entity"], cfg.get("mapping_profile", "default"))
        later_keys: set = set()
        for run in reversed(runs):  # do mais recente para o mais antigo
            path = lake.base / run["bronze_path"]
            keys = _keys_in_file(path, from_fields) if path.exists() else set()
            is_latest = run is runs[-1]
            if not is_latest and run["started_at"] < bronze_cut and keys and keys <= later_keys:
                report["bronze"].append({"run_id": run["id"], "source": src["key"], "records": len(keys)})
                if not dry_run:
                    shutil.rmtree(path.parent, ignore_errors=True)
                    db.execute("UPDATE ingestion_runs SET purged_at = ? WHERE id = ?", (now_iso(), run["id"]))
            later_keys |= keys
    q_cut = _cutoff(policy["quarantine_days"])
    latest = db.fetchone("SELECT pipeline_run_id FROM quarantine ORDER BY created_at DESC LIMIT 1")
    latest_id = latest["pipeline_run_id"] if latest else ""
    report["quarantine_rows"] = db.fetchone("SELECT COUNT(*) AS n FROM quarantine WHERE created_at < ? AND pipeline_run_id <> ?",
                                            (q_cut, latest_id))["n"]
    l_cut = _cutoff(policy["logs_days"])
    report["log_rows"] = (db.fetchone("SELECT COUNT(*) AS n FROM routing_decisions WHERE created_at < ?", (l_cut,))["n"]
                          + db.fetchone("SELECT COUNT(*) AS n FROM llm_calls WHERE created_at < ?", (l_cut,))["n"])
    if not dry_run:
        with db.connect() as c:
            c.execute("DELETE FROM quarantine WHERE created_at < ? AND pipeline_run_id <> ?", (q_cut, latest_id))
            c.execute("DELETE FROM routing_decisions WHERE created_at < ?", (l_cut,))
            c.execute("DELETE FROM llm_calls WHERE created_at < ?", (l_cut,))
        record_audit(db, actor, "retention.apply", "platform", None,
                     {"bronze_runs": len(report["bronze"]), "quarantine_rows": report["quarantine_rows"],
                      "log_rows": report["log_rows"]})
    return report
