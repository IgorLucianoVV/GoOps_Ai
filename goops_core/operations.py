"""Ações operacionais: proposta (agentes), aprovação/rejeição (humanos), execução (simulada) e histórico."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .audit import list_audit, record_audit
from .config import get_settings
from .runtime_config import get_section
from .db import Database
from .errors import Conflict, NotFound, PermissionDenied, PolicyViolation
from .permissions import Principal, has_permission, require_permission
from .policies import ACTION_CATALOG, can_approve, evaluate_action_policy, validate_action_params
from .util import jdump, jload, new_id, now_iso

STATUSES = ["proposed", "pending_approval", "approved", "rejected", "executing", "executed", "failed"]
_JSON = ("params", "impacted_areas", "approver_roles", "expected_impact", "result")

# Executores simulados registrados pela plataforma de dados (calculam o efeito *previsto* sem alterar nada).
SIMULATORS: Dict[str, Callable[[dict], dict]] = {}


def register_simulator(action_type: str, fn: Callable[[dict], dict]) -> None:
    SIMULATORS[action_type] = fn


# Ganchos chamados após decisão (aprovar/rejeitar) e execução — ex.: o Atendimento atualiza o contato ligado à ação.
HOOKS: Dict[str, List[Callable[[Database, Principal, dict], None]]] = {"proposed": [], "decided": [], "executed": []}


def register_hook(event: str, fn: Callable[[Database, Principal, dict], None]) -> None:
    if fn not in HOOKS[event]:
        HOOKS[event].append(fn)


def _run_hooks(event: str, db: Database, actor: Principal, op: dict) -> None:
    import logging
    for fn in HOOKS.get(event, []):
        try:
            fn(db, actor, op)
        except Exception:  # noqa: BLE001 - gancho nunca desfaz a decisão/execução já registrada
            logging.getLogger("goops.operations").exception("hook %s failed for %s", event, op.get("id"))


def _row(row: dict) -> dict:
    for f in _JSON:
        row[f] = jload(row.get(f), None)
    row["requires_approval"] = bool(row["requires_approval"])
    return row


def get_operation(db: Database, op_id: str) -> dict:
    row = db.fetchone("SELECT * FROM operations WHERE id = ?", (op_id,))
    if not row:
        raise NotFound(f"Operação {op_id} não encontrada.")
    return _row(row)


def list_operations(db: Database, status: Optional[str] = None, incident_id: Optional[str] = None,
                    contact_id: Optional[str] = None) -> List[dict]:
    clauses, params = [], []
    if contact_id:
        clauses.append("contact_id = ?"); params.append(contact_id)
    if status:
        clauses.append("status = ?"); params.append(status)
    if incident_id:
        clauses.append("incident_id = ?"); params.append(incident_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return [_row(r) for r in db.fetchall(f"SELECT * FROM operations {where} ORDER BY created_at DESC", params)]


def propose_operation(db: Database, actor: Principal, *, action_type: str, description: str,
                      params: dict, incident_id: Optional[str] = None,
                      expected_impact: Optional[dict] = None, contact_id: Optional[str] = None) -> dict:
    if not (has_permission(actor, "operations:propose") or has_permission(actor, "incidents:write")):
        raise PermissionDenied(f"{actor.actor_label} não pode propor operações.")
    validate_action_params(action_type, params)
    policy = evaluate_action_policy(action_type, get_section(db, "policies"))
    op_id = new_id("OP")
    ts = now_iso()
    status = "pending_approval" if policy["requires_approval"] else "approved"
    db.execute(
        "INSERT INTO operations (id, incident_id, contact_id, action_type, title, description, params, impacted_areas, risk, "
        "expected_impact, requires_approval, approver_roles, status, proposed_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (op_id, incident_id, contact_id, action_type, ACTION_CATALOG[action_type]["title"], description, jdump(params),
         jdump(policy["impacted_areas"]), policy["risk"], jdump(expected_impact or {}),
         int(policy["requires_approval"]), jdump(policy["approver_roles"]), status, actor.actor_label, ts, ts))
    record_audit(db, actor, "operation.propose", "operation", op_id,
                 {"action_type": action_type, "incident_id": incident_id, "contact_id": contact_id, "policy": policy})
    if not policy["requires_approval"]:
        record_audit(db, actor, "operation.auto_approved_by_policy", "operation", op_id, {"reasons": policy["reasons"]})
    out = get_operation(db, op_id)
    _run_hooks("proposed", db, actor, out)
    return out


def decide_operation(db: Database, actor: Principal, op_id: str, approve: bool, note: str = "") -> dict:
    op = get_operation(db, op_id)
    if op["status"] != "pending_approval":
        raise Conflict(f"Operação não está aguardando aprovação (status: {op['status']}).")
    if not can_approve(actor, op["action_type"], get_section(db, "policies")):
        raise PermissionDenied("Usuário sem autorização para aprovar esta ação (papel/domínio).")
    status = "approved" if approve else "rejected"
    db.execute("UPDATE operations SET status = ?, approved_by = ?, approved_at = ?, decision_note = ?, updated_at = ? "
               "WHERE id = ?", (status, actor.actor_label, now_iso(), note, now_iso(), op_id))
    record_audit(db, actor, f"operation.{status}", "operation", op_id, {"note": note})
    out = get_operation(db, op_id)
    _run_hooks("decided", db, actor, out)
    return out


def execute_operation(db: Database, actor: Principal, op_id: str) -> dict:
    """Executa uma operação aprovada. Nesta versão a execução é sempre SIMULADA."""
    op = get_operation(db, op_id)
    if op["status"] != "approved":
        raise PolicyViolation(f"Operação só pode ser executada após aprovação (status atual: {op['status']}).")
    if op["requires_approval"] and not (op.get("approved_by") or "").startswith("user:"):
        raise PolicyViolation("Ação crítica sem aprovação humana registrada.")
    if actor.kind == "agent":
        require_permission(actor, "operations:execute_approved")
    elif actor.kind == "user":
        require_permission(actor, "operations:execute")
    mode = get_settings().action_execution_mode
    if mode != "simulated":
        raise PolicyViolation("Somente o modo 'simulated' está implementado nesta versão.")
    db.execute("UPDATE operations SET status = 'executing', updated_at = ? WHERE id = ?", (now_iso(), op_id))
    try:
        simulator = SIMULATORS.get(op["action_type"])
        preview = simulator(op["params"] or {}) if simulator else {"note": "Sem simulador específico registrado."}
        result = {"mode": "simulated", "executed": False, "simulated": True,
                  "message": "Execução simulada: nenhum sistema externo foi alterado.", "preview": preview}
        status = "executed"
    except Exception as exc:  # noqa: BLE001
        result = {"mode": "simulated", "error": type(exc).__name__, "message": str(exc)[:300]}
        status = "failed"
    db.execute("UPDATE operations SET status = ?, executed_by = ?, executed_at = ?, execution_mode = ?, result = ?, "
               "updated_at = ? WHERE id = ?", (status, actor.actor_label, now_iso(), mode, jdump(result), now_iso(), op_id))
    record_audit(db, actor, f"operation.{status}", "operation", op_id, {"mode": mode})
    out = get_operation(db, op_id)
    _run_hooks("executed", db, actor, out)
    return out


def operation_history(db: Database, op_id: str) -> List[dict]:
    get_operation(db, op_id)
    return list(reversed(list_audit(db, entity_type="operation", entity_id=op_id)))
