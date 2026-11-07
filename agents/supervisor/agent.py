"""GoOps Supervisor — coordena agentes, prioriza incidentes e controla o fluxo (com HITL)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from goops_core.runtime_config import effective_settings
from goops_core.db import Database
from goops_core.errors import Conflict, PermissionDenied
from goops_core.incidents import SEVERITY_RANK, add_event, get_incident, list_incidents, set_status
from goops_core.operations import decide_operation, get_operation, list_operations
from goops_core.permissions import Principal, agent_principal, require_permission
from data_platform.storage import Lakehouse

from ..base import AgentContext, AgentRun
from ..monitor.agent import run_monitor
from ..simulators import register_all
from ..workflows.graph import list_workflow_runs
from ..workflows.incident_workflow import build_incident_graph

register_all()
SUPERVISOR = agent_principal("supervisor")


class Supervisor:
    def __init__(self, db: Database, lake: Lakehouse):
        self.db, self.lake = db, lake

    def _ctx(self, incident_id: Optional[str] = None) -> AgentContext:
        is_demo = False
        if incident_id:
            is_demo = get_incident(self.db, incident_id)["is_demo"]
        else:
            row = self.db.fetchone("SELECT is_demo FROM datasets WHERE key = 'gold_nps_analytics'")
            is_demo = bool(row and row["is_demo"])
        return AgentContext(self.db, self.lake, incident_id=incident_id, is_demo=is_demo)

    def run_monitoring_cycle(self, actor: Principal, auto_investigate: Optional[bool] = None) -> Dict[str, Any]:
        require_permission(actor, "agents:execute")
        ctx = self._ctx()
        with AgentRun(ctx, "supervisor", "monitoring_cycle", {"triggered_by": actor.actor_label}) as run:
            mon = run_monitor(ctx)
            auto = effective_settings(self.db).auto_investigate if auto_investigate is None else auto_investigate
            started: List[Dict[str, Any]] = []
            if auto:
                queue = sorted([i for i in list_incidents(self.db, status="detected")],
                               key=lambda i: -SEVERITY_RANK.get(i["severity"], 0))
                for inc in queue:
                    started.append(self.investigate(inc["id"], actor, _internal=True))
            run.output = {"monitor": mon, "workflows": [{"incident_id": s["incident_id"], "status": s["status"]}
                                                        for s in started]}
            return run.output

    def investigate(self, incident_id: str, actor: Principal, _internal: bool = False) -> Dict[str, Any]:
        if not _internal:
            require_permission(actor, "agents:execute")
        inc = get_incident(self.db, incident_id)
        if inc["status"] in ("closed",):
            raise Conflict("Incidente encerrado; reabra antes de investigar.")
        if inc["status"] == "resolved":
            set_status(self.db, incident_id, "reopened", actor, "Nova investigação solicitada")
        if inc["status"] in ("awaiting_approval", "executing"):
            set_status(self.db, incident_id, "investigating", actor, "Nova investigação solicitada")
        ctx = self._ctx(incident_id)
        add_event(self.db, incident_id, SUPERVISOR, "supervisor",
                  f"Supervisor priorizou o incidente (severidade {inc['severity']}) e acionou o fluxo de investigação.",
                  {"requested_by": actor.actor_label}, is_demo=inc["is_demo"])
        graph = build_incident_graph(ctx)
        res = graph.run(self.db, {"incident_id": incident_id}, incident_id=incident_id)
        ctx.workflow_run_id = res["run_id"]
        return {"incident_id": incident_id, "workflow_run_id": res["run_id"], "status": res["status"],
                "error": res.get("error")}

    def decide(self, operation_id: str, actor: Principal, approve: bool, note: str = "") -> Dict[str, Any]:
        """Decisão humana sobre uma operação; retoma o workflow quando não houver mais pendências."""
        op = decide_operation(self.db, actor, operation_id, approve, note)
        result: Dict[str, Any] = {"operation": op, "workflow": None}
        if not op.get("incident_id"):
            return result
        inc = get_incident(self.db, op["incident_id"])
        add_event(self.db, inc["id"], actor, "human_decision",
                  f"{actor.name} {'APROVOU' if approve else 'REJEITOU'}: {op['title']}" + (f" — {note}" if note else ""),
                  {"operation_id": op["id"], "decision": op["status"]}, is_demo=inc["is_demo"])
        pending = [o for o in list_operations(self.db, incident_id=inc["id"]) if o["status"] == "pending_approval"]
        if pending:
            return result
        waiting = self.db.fetchone("SELECT id, current_node FROM workflow_runs WHERE incident_id = ? AND status = 'waiting' "
                                   "ORDER BY started_at DESC LIMIT 1", (inc["id"],))
        if waiting:
            ctx = self._ctx(inc["id"])
            ctx.workflow_run_id = waiting["id"]
            row = self.db.fetchone("SELECT state FROM workflow_runs WHERE id = ?", (waiting["id"],))
            from goops_core.util import jload
            state = jload(row["state"], {})
            res = build_incident_graph(ctx).run(self.db, state, run_id=waiting["id"], start=waiting["current_node"],
                                                incident_id=inc["id"])
            result["workflow"] = {"run_id": res["run_id"], "status": res["status"], "error": res.get("error")}
            if all(o["status"] == "rejected" for o in list_operations(self.db, incident_id=inc["id"])):
                set_status(self.db, inc["id"], "investigating", SUPERVISOR,
                           "Todas as ações foram rejeitadas; aguardando nova investigação ou decisão humana")
        return result

    def execute_operation_manual(self, operation_id: str, actor: Principal) -> Dict[str, Any]:
        """Execução manual (simulada) de operação aprovada sem incidente associado."""
        from goops_core.operations import execute_operation
        return execute_operation(self.db, actor, operation_id)

    def close_incident(self, incident_id: str, actor: Principal, note: str) -> Dict[str, Any]:
        require_permission(actor, "incidents:write")
        if actor.kind != "user":
            raise PermissionDenied("Somente pessoas encerram incidentes.")
        return set_status(self.db, incident_id, "closed", actor, note or "Encerrado manualmente")

    def workflow_definition(self) -> dict:
        return build_incident_graph(self._ctx()).describe()

    def workflow_runs(self, incident_id: Optional[str] = None) -> List[dict]:
        return list_workflow_runs(self.db, incident_id)
