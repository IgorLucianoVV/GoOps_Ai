"""Módulo de incidentes: criação, deduplicação, ciclo de vida e timeline."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .audit import record_audit
from .db import Database
from .errors import Conflict, NotFound, ValidationError
from .permissions import Principal, require_permission
from .util import jdump, jload, new_id, now_iso

CATEGORIES = ["orders", "payments", "inventory", "logistics", "customer_service", "customer_experience", "products",
              "reputation", "other"]
SEVERITIES = ["low", "medium", "high", "critical"]
STATUSES = ["detected", "investigating", "awaiting_approval", "executing", "resolved", "reopened", "closed"]
OPEN_STATUSES = ["detected", "investigating", "awaiting_approval", "executing", "reopened"]
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

TRANSITIONS: Dict[str, set] = {
    "detected": {"investigating", "closed"},
    "investigating": {"awaiting_approval", "executing", "resolved", "closed"},
    "awaiting_approval": {"executing", "investigating", "closed"},
    "executing": {"resolved", "investigating", "closed"},
    "resolved": {"closed", "reopened"},
    "reopened": {"investigating", "closed"},
    "closed": {"reopened"},
}

_JSON_FIELDS = ("signal", "related_metrics", "evidence", "agents", "hypotheses", "recommendation", "result")


def _row_to_incident(row: dict) -> dict:
    for f in _JSON_FIELDS:
        row[f] = jload(row.get(f), None)
    row["is_demo"] = bool(row.get("is_demo"))
    return row


def get_incident(db: Database, incident_id: str) -> dict:
    row = db.fetchone("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    if not row:
        raise NotFound(f"Incidente {incident_id} não encontrado.")
    return _row_to_incident(row)


def list_incidents(db: Database, status: Optional[str] = None, severity: Optional[str] = None,
                   category: Optional[str] = None, domain: Optional[str] = None,
                   only_open: bool = False, limit: int = 200) -> List[dict]:
    clauses, params = [], []
    for col, val in (("status", status), ("severity", severity), ("category", category), ("domain", domain)):
        if val:
            clauses.append(f"{col} = ?"); params.append(val)
    if only_open:
        clauses.append(f"status IN ({','.join('?' * len(OPEN_STATUSES))})"); params.extend(OPEN_STATUSES)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit = max(1, min(int(limit), 1000))
    rows = db.fetchall(f"SELECT * FROM incidents {where} ORDER BY detected_at DESC LIMIT {limit}", params)
    items = [_row_to_incident(r) for r in rows]
    items.sort(key=lambda i: (i["status"] in ("resolved", "closed"), -SEVERITY_RANK.get(i["severity"], 0)))
    return items


def add_event(db: Database, incident_id: str, actor: Principal, event_type: str, message: str,
              data: Optional[Any] = None, is_demo: bool = False) -> dict:
    with db.connect() as c:
        row = c.fetchone("SELECT COALESCE(MAX(seq), 0) AS m FROM incident_events WHERE incident_id = ?", (incident_id,))
        seq = int(row["m"]) + 1
        event = {
            "id": new_id("EVT"), "incident_id": incident_id, "seq": seq, "ts": now_iso(),
            "actor_type": actor.kind, "actor": actor.id, "event_type": event_type,
            "message": message, "data": jdump(data) if data is not None else None, "is_demo": int(is_demo),
        }
        c.execute(
            "INSERT INTO incident_events (id, incident_id, seq, ts, actor_type, actor, event_type, message, data, is_demo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(event.values()))
    return event


def timeline(db: Database, incident_id: str) -> List[dict]:
    get_incident(db, incident_id)
    rows = db.fetchall("SELECT * FROM incident_events WHERE incident_id = ? ORDER BY seq", (incident_id,))
    for r in rows:
        r["data"] = jload(r["data"], None)
        r["is_demo"] = bool(r["is_demo"])
    return rows


def create_incident(db: Database, actor: Principal, *, title: str, description: str, category: str,
                    domain: str, severity: str, source: str, signal: Optional[dict] = None,
                    related_metrics: Optional[list] = None, fingerprint: Optional[str] = None,
                    is_demo: bool = False) -> Dict[str, Any]:
    require_permission(actor, "incidents:write", domain if domain != "corporate" else None)
    if category not in CATEGORIES:
        raise ValidationError(f"Categoria inválida: {category}")
    if severity not in SEVERITIES:
        raise ValidationError(f"Severidade inválida: {severity}")
    if not title or len(title) > 200:
        raise ValidationError("Título obrigatório (máx. 200 caracteres).")
    if fingerprint:
        existing = db.fetchone(
            f"SELECT id FROM incidents WHERE fingerprint = ? AND status IN ({','.join('?' * len(OPEN_STATUSES))})",
            (fingerprint, *OPEN_STATUSES))
        if existing:
            return {"incident": get_incident(db, existing["id"]), "created": False}
    incident_id = new_id("INC")
    ts = now_iso()
    db.execute(
        "INSERT INTO incidents (id, title, description, category, domain, severity, status, detected_at, source, "
        "fingerprint, signal, related_metrics, evidence, agents, is_demo, created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'detected', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (incident_id, title, description, category, domain, severity, ts, source, fingerprint,
         jdump(signal or {}), jdump(related_metrics or []), jdump([]),
         jdump([actor.id] if actor.kind == "agent" else []), int(is_demo), actor.actor_label, ts, ts))
    add_event(db, incident_id, actor, "detected", f"Incidente detectado: {title}",
              {"signal": signal, "source": source}, is_demo=is_demo)
    record_audit(db, actor, "incident.create", "incident", incident_id, {"title": title, "severity": severity})
    return {"incident": get_incident(db, incident_id), "created": True}


def set_status(db: Database, incident_id: str, new_status: str, actor: Principal, note: str = "") -> dict:
    inc = get_incident(db, incident_id)
    if new_status not in STATUSES:
        raise ValidationError(f"Status inválido: {new_status}")
    if new_status == inc["status"]:
        return inc
    if new_status not in TRANSITIONS.get(inc["status"], set()):
        raise Conflict(f"Transição não permitida: {inc['status']} -> {new_status}")
    db.execute("UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_iso(), incident_id))
    add_event(db, incident_id, actor, "status_changed",
              f"Status alterado: {inc['status']} → {new_status}" + (f" ({note})" if note else ""),
              {"from": inc["status"], "to": new_status}, is_demo=inc["is_demo"])
    record_audit(db, actor, "incident.status", "incident", incident_id, {"from": inc["status"], "to": new_status, "note": note})
    return get_incident(db, incident_id)


def update_fields(db: Database, incident_id: str, **fields: Any) -> dict:
    allowed = set(_JSON_FIELDS) | {"root_cause", "severity", "description", "summary"}
    sets, params = [], []
    for key, value in fields.items():
        if key not in allowed:
            raise ValidationError(f"Campo não atualizável: {key}")
        sets.append(f"{key} = ?")
        params.append(jdump(value) if key in _JSON_FIELDS else value)
    if not sets:
        return get_incident(db, incident_id)
    sets.append("updated_at = ?"); params.append(now_iso())
    params.append(incident_id)
    db.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id = ?", params)
    return get_incident(db, incident_id)


def register_agent(db: Database, incident_id: str, agent_key: str) -> None:
    inc = get_incident(db, incident_id)
    agents = list(inc.get("agents") or [])
    if agent_key not in agents:
        agents.append(agent_key)
        update_fields(db, incident_id, agents=agents)
