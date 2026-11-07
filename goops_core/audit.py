"""Trilha de auditoria imutável (append-only)."""
from __future__ import annotations

from typing import Any, Optional

from .db import Database
from .permissions import Principal
from .util import jdump, new_id, now_iso

_REDACT_KEYS = ("password", "token", "secret", "api_key", "apikey", "authorization")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if any(r in str(k).lower() for r in _REDACT_KEYS) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def record_audit(db: Database, actor: Principal, action: str, entity_type: str,
                 entity_id: Optional[str] = None, details: Optional[dict] = None, conn=None) -> str:
    audit_id = new_id("AUD")
    sql = ("INSERT INTO audit_log (id, ts, actor_type, actor_id, action, entity_type, entity_id, details) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    params = (audit_id, now_iso(), actor.kind, actor.id, action, entity_type, entity_id, jdump(_redact(details or {})))
    if conn is not None:
        conn.execute(sql, params)
    else:
        db.execute(sql, params)
    return audit_id


def list_audit(db: Database, entity_type: Optional[str] = None, entity_id: Optional[str] = None,
               actor_id: Optional[str] = None, limit: int = 200) -> list:
    clauses, params = [], []
    if entity_type:
        clauses.append("entity_type = ?"); params.append(entity_type)
    if entity_id:
        clauses.append("entity_id = ?"); params.append(entity_id)
    if actor_id:
        clauses.append("actor_id = ?"); params.append(actor_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit = max(1, min(int(limit), 1000))
    from .util import jload
    rows = db.fetchall(f"SELECT * FROM audit_log {where} ORDER BY ts DESC, id DESC LIMIT {limit}", params)
    for r in rows:
        r["details"] = jload(r["details"], {})
    return rows
