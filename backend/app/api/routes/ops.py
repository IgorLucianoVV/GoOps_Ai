"""Incidentes, agentes, workflows e operações (human-in-the-loop)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from goops_core.db import Database
from goops_core.errors import NotFound, ValidationError
from goops_core.incidents import create_incident, get_incident, list_incidents, timeline
from goops_core.operations import get_operation, list_operations, operation_history
from goops_core.permissions import Principal
from data_platform.storage import Lakehouse
from agents.base import AGENT_CATALOG, AGENT_PROFILES, agent_stats, list_agent_runs
from agents.custom import (CHECK_TYPES, LLM_OUTPUTS, SECTOR_ACTIONS, TEMPLATES, delete_agent, get_agent, list_agents,
                           run_agent, run_trace, save_agent, set_enabled, test_agent, with_stats)
from agents.instructions import (discard_draft, history, list_slots, preview, publish_draft, reset_instruction,
                                 restore_version, save_draft, save_instruction)
from agents.routing.router import efficiency_metrics
from agents.supervisor.agent import Supervisor
from agents.workflows.graph import list_workflow_runs

from ...schemas.requests import AskRequest, AgentExecute, CloseRequest, Decision, IncidentCreate
from ..deps import db_dep, lake_dep, ok, require

router = APIRouter()


def _sup(db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)) -> Supervisor:
    return Supervisor(db, lake)


# ------------------------------------------------------------------ incidentes
@router.get("/incidents", tags=["incidents"])
def incidents(status: Optional[str] = None, severity: Optional[str] = None, category: Optional[str] = None,
              domain: Optional[str] = None, only_open: bool = False,
              p: Principal = Depends(require("incidents:read")), db: Database = Depends(db_dep)):
    return ok(list_incidents(db, status, severity, category, domain, only_open))


@router.post("/incidents", tags=["incidents"], status_code=201)
def incidents_create(body: IncidentCreate, p: Principal = Depends(require("incidents:write")),
                     db: Database = Depends(db_dep)):
    return ok(create_incident(db, p, title=body.title, description=body.description, category=body.category,
                              domain=body.domain, severity=body.severity, source="manual")["incident"])


@router.get("/incidents/{incident_id}", tags=["incidents"])
def incident_detail(incident_id: str, p: Principal = Depends(require("incidents:read")), db: Database = Depends(db_dep)):
    inc = get_incident(db, incident_id)
    return ok({**inc, "operations": list_operations(db, incident_id=incident_id),
               "workflows": list_workflow_runs(db, incident_id)})


@router.get("/incidents/{incident_id}/timeline", tags=["incidents"])
def incident_timeline(incident_id: str, p: Principal = Depends(require("incidents:read")), db: Database = Depends(db_dep)):
    return ok(timeline(db, incident_id))


@router.post("/incidents/{incident_id}/investigate", tags=["incidents"])
def incident_investigate(incident_id: str, p: Principal = Depends(require("agents:execute")),
                         sup: Supervisor = Depends(_sup)):
    return ok(sup.investigate(incident_id, p))


def _single_pending(db: Database, incident_id: str, operation_id: Optional[str]) -> str:
    if operation_id:
        return operation_id
    pending = [o for o in list_operations(db, incident_id=incident_id) if o["status"] == "pending_approval"]
    if len(pending) != 1:
        raise ValidationError("Informe operation_id: há zero ou várias operações pendentes neste incidente.",
                              {"pending": [o["id"] for o in pending]})
    return pending[0]["id"]


@router.post("/incidents/{incident_id}/approve", tags=["incidents"])
def incident_approve(incident_id: str, body: Decision = Decision(), operation_id: Optional[str] = Query(default=None),
                     p: Principal = Depends(require("operations:approve")), db: Database = Depends(db_dep),
                     sup: Supervisor = Depends(_sup)):
    get_incident(db, incident_id)
    return ok(sup.decide(_single_pending(db, incident_id, operation_id), p, True, body.note))


@router.post("/incidents/{incident_id}/reject", tags=["incidents"])
def incident_reject(incident_id: str, body: Decision = Decision(), operation_id: Optional[str] = Query(default=None),
                    p: Principal = Depends(require("operations:approve")), db: Database = Depends(db_dep),
                    sup: Supervisor = Depends(_sup)):
    get_incident(db, incident_id)
    return ok(sup.decide(_single_pending(db, incident_id, operation_id), p, False, body.note))


@router.post("/incidents/{incident_id}/close", tags=["incidents"])
def incident_close(incident_id: str, body: CloseRequest, p: Principal = Depends(require("incidents:write")),
                   sup: Supervisor = Depends(_sup)):
    return ok(sup.close_incident(incident_id, p, body.note))


# ------------------------------------------------------------------ agentes
class InstructionSave(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    note: Optional[str] = Field(default=None, max_length=300)


class InstructionRestore(BaseModel):
    version: int = Field(ge=1)


class CustomAgentSave(BaseModel):
    key: str = Field(min_length=3, max_length=50)
    domain: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=80)
    template: str
    config: Dict[str, Any]
    interval_minutes: Optional[int] = None
    enabled: bool = True


class InstructionTest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=8000)
    question: Optional[str] = Field(default=None, max_length=1000)


class CustomAgentTest(BaseModel):
    domain: str = Field(min_length=2, max_length=50)
    name: str = Field(default="Rascunho", max_length=80)
    key: Optional[str] = Field(default=None, max_length=50)
    config: Dict[str, Any]


class EnabledBody(BaseModel):
    enabled: bool


class ValidationRun(BaseModel):
    with_ai: bool = False


@router.get("/agents/validation", tags=["agents"])
def agents_validation(p: Principal = Depends(require("agents:read"))):
    from agents.walkthrough import latest
    return ok(latest())


@router.post("/agents/validation/run", tags=["agents"])
def agents_validation_run(body: ValidationRun = ValidationRun(), p: Principal = Depends(require("agents:execute")),
                          db: Database = Depends(db_dep)):
    """Validação ponta a ponta em AMBIENTE ISOLADO (processo separado, banco e Lakehouse temporários)."""
    import subprocess
    import sys
    from goops_core.audit import record_audit
    from agents.walkthrough import ROOT, latest
    cmd = [sys.executable, str(ROOT / "manage.py"), "validate-agents", "--quiet"] + (["--with-ai"] if body.with_ai else [])
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=280)
    except subprocess.TimeoutExpired:
        raise ValidationError("A validação passou de 280 s e foi interrompida. Rode pelo terminal: python manage.py validate-agents")
    report = latest()
    if report is None:
        raise ValidationError("A validação não gerou relatório: " + (proc.stderr or proc.stdout or "")[-300:])
    record_audit(db, p, "agent.validation_run", "agents", "walkthrough",
                 {"passed": report["summary"]["passed"], "cases": report["summary"]["cases"], "with_ai": body.with_ai})
    return ok(report)


# Rotas específicas ANTES de /agents/{agent_key} (o FastAPI casa na ordem de declaração).
@router.post("/agents/custom/test", tags=["agents"])
def custom_agent_test(body: CustomAgentTest, p: Principal = Depends(require("agents:execute")), db: Database = Depends(db_dep),
                      lake: Lakehouse = Depends(lake_dep)):
    return ok(test_agent(db, lake, p, domain=body.domain, name=body.name, config=body.config, key=body.key))


@router.post("/agents/custom/{key}/enabled", tags=["agents"])
def custom_agent_enabled(key: str, body: EnabledBody, p: Principal = Depends(require("agents:read")),
                         db: Database = Depends(db_dep)):
    return ok(with_stats(db, set_enabled(db, p, key, body.enabled)))


@router.post("/agents/instructions/{slot}/draft", tags=["agents"])
def instruction_draft(slot: str, body: InstructionSave, p: Principal = Depends(require("agents:configure")),
                      db: Database = Depends(db_dep)):
    return ok(save_draft(db, p, slot, body.text, body.note))


@router.post("/agents/instructions/{slot}/draft/discard", tags=["agents"])
def instruction_draft_discard(slot: str, p: Principal = Depends(require("agents:configure")), db: Database = Depends(db_dep)):
    return ok(discard_draft(db, p, slot))


@router.post("/agents/instructions/{slot}/publish", tags=["agents"])
def instruction_publish(slot: str, p: Principal = Depends(require("agents:configure")), db: Database = Depends(db_dep)):
    return ok(publish_draft(db, p, slot))


@router.post("/agents/instructions/{slot}/test", tags=["agents"])
def instruction_test(slot: str, body: InstructionTest, p: Principal = Depends(require("agents:configure")),
                     db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    return ok(preview(db, lake, p, slot, body.text, body.question))

@router.get("/agents/custom/options", tags=["agents"])
def custom_agent_options(p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    from agents.ask import Toolbox, chat_model_options
    from data_platform.semantic.registry import list_domains
    from data_platform.sectors.dashboards import can_edit
    from goops_core.incidents import CATEGORIES, SEVERITIES
    from goops_core.runtime_config import effective_settings
    models = [{"id": m["id"], "label": m.get("label") or m["model"], "available": m["available"]}
              for m in chat_model_options(effective_settings(db))]
    return ok({"templates": TEMPLATES, "outputs": LLM_OUTPUTS, "actions": SECTOR_ACTIONS, "severities": SEVERITIES,
               "categories": CATEGORIES, "models": models, "check_types": CHECK_TYPES,
               "tools": [{"name": t["name"], "description": t["description"]} for t in Toolbox.SPECS],
               "domains": [{"key": d["key"], "name": d["name"], "can_edit": can_edit(p, d["key"])} for d in list_domains(db)]})


@router.get("/agents/custom", tags=["agents"])
def custom_agents(p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    return ok([with_stats(db, a) for a in list_agents(db)])


@router.post("/agents/custom", tags=["agents"])
def custom_agent_save(body: CustomAgentSave, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    from data_platform.semantic.registry import list_domains
    if body.domain not in {d["key"] for d in list_domains(db)}:
        raise NotFound("Setor/domínio não encontrado.")
    a = save_agent(db, p, key=body.key, domain=body.domain, name=body.name, template=body.template, config=body.config,
                   interval_minutes=body.interval_minutes, enabled=body.enabled)
    return ok(with_stats(db, a))


@router.get("/agents/custom/{key}", tags=["agents"])
def custom_agent_detail(key: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    from data_platform.sectors.dashboards import can_edit
    a = with_stats(db, get_agent(db, key))
    runs = list_agent_runs(db, f"custom:{key}", 20)
    if a["template"] == "llm_task":
        for r in runs:
            r["trace"] = run_trace(db, r)
    return ok({**a, "can_edit": can_edit(p, a["domain"]), "recent_runs": runs})


@router.post("/agents/custom/{key}/run", tags=["agents"])
def custom_agent_run(key: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep),
                     lake: Lakehouse = Depends(lake_dep)):
    return ok(run_agent(db, lake, p, key))


@router.post("/agents/custom/{key}/delete", tags=["agents"])
def custom_agent_delete(key: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    delete_agent(db, p, key)
    return ok({"deleted": key})


@router.get("/agents/instructions/{slot}/history", tags=["agents"])
def instruction_history(slot: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    return ok(history(db, slot))


@router.post("/agents/instructions/{slot}", tags=["agents"])
def instruction_save(slot: str, body: InstructionSave, p: Principal = Depends(require("agents:configure")),
                     db: Database = Depends(db_dep)):
    return ok(save_instruction(db, p, slot, body.text, body.note))


@router.post("/agents/instructions/{slot}/reset", tags=["agents"])
def instruction_reset(slot: str, p: Principal = Depends(require("agents:configure")), db: Database = Depends(db_dep)):
    return ok(reset_instruction(db, p, slot))


@router.post("/agents/instructions/{slot}/restore", tags=["agents"])
def instruction_restore(slot: str, body: InstructionRestore, p: Principal = Depends(require("agents:configure")),
                        db: Database = Depends(db_dep)):
    return ok(restore_version(db, p, slot, body.version))


@router.get("/agents", tags=["agents"])
def agents(p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    return ok(agent_stats(db), {"routing": efficiency_metrics(db)})


@router.get("/agents/routing/metrics", tags=["agents"])
def routing_metrics(p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    return ok(efficiency_metrics(db))


@router.get("/agents/{agent_key}", tags=["agents"])
def agent_detail(agent_key: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    if agent_key not in AGENT_CATALOG:
        raise NotFound("Agente não encontrado.")
    stats = next(a for a in agent_stats(db) if a["key"] == agent_key)
    from agents.decisions import decision_logic, recent_decisions
    return ok({**stats, "profile": AGENT_PROFILES.get(agent_key, {}), "instructions": list_slots(db, agent_key),
               "decision_logic": decision_logic(db, agent_key), "recent_decisions": recent_decisions(db, agent_key),
               "recent_runs": list_agent_runs(db, agent_key, 20)})


@router.get("/agents/{agent_key}/runs", tags=["agents"])
def agent_runs(agent_key: str, limit: int = Query(default=100, ge=1, le=500),
               p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    if agent_key not in AGENT_CATALOG:
        raise NotFound("Agente não encontrado.")
    return ok(list_agent_runs(db, agent_key, limit))


@router.post("/agents/{agent_key}/execute", tags=["agents"])
def agent_execute(agent_key: str, body: AgentExecute = AgentExecute(), p: Principal = Depends(require("agents:execute")),
                  sup: Supervisor = Depends(_sup)):
    if agent_key in ("supervisor", "monitor"):
        return ok(sup.run_monitoring_cycle(p, body.auto_investigate if agent_key == "supervisor" else False))
    if agent_key == "investigation":
        if not body.incident_id:
            raise ValidationError("incident_id é obrigatório para o Investigation Agent.")
        return ok(sup.investigate(body.incident_id, p))
    raise ValidationError("Resolution e Validation são acionados pelo Supervisor dentro do fluxo do incidente "
                          "(após investigação / aprovação humana).")


# ------------------------------------------------------------------ workflows
@router.get("/workflows", tags=["workflows"])
def workflows(incident_id: Optional[str] = None, p: Principal = Depends(require("agents:read")),
              sup: Supervisor = Depends(_sup)):
    return ok(sup.workflow_runs(incident_id), {"definition": sup.workflow_definition()})


# ------------------------------------------------------------------ operações
@router.get("/operations", tags=["operations"])
def operations(status: Optional[str] = None, p: Principal = Depends(require("operations:read")),
               db: Database = Depends(db_dep)):
    return ok(list_operations(db, status))


@router.post("/operations/{operation_id}/approve", tags=["operations"])
def operation_approve(operation_id: str, body: Decision = Decision(), p: Principal = Depends(require("operations:approve")),
                      sup: Supervisor = Depends(_sup)):
    return ok(sup.decide(operation_id, p, True, body.note))


@router.post("/operations/{operation_id}/reject", tags=["operations"])
def operation_reject(operation_id: str, body: Decision = Decision(), p: Principal = Depends(require("operations:approve")),
                     sup: Supervisor = Depends(_sup)):
    return ok(sup.decide(operation_id, p, False, body.note))


@router.post("/operations/{operation_id}/execute", tags=["operations"])
def operation_execute(operation_id: str, p: Principal = Depends(require("operations:execute")),
                      sup: Supervisor = Depends(_sup)):
    return ok(sup.execute_operation_manual(operation_id, p), {"execution_mode": "simulated"})


@router.get("/operations/{operation_id}/history", tags=["operations"])
def operation_hist(operation_id: str, p: Principal = Depends(require("operations:read")), db: Database = Depends(db_dep)):
    return ok({"operation": get_operation(db, operation_id), "history": operation_history(db, operation_id)})


# ------------------------------------------------------------------ Pergunte ao GoOps
@router.post("/assistant/ask", tags=["assistant"])
def assistant_ask(body: AskRequest, p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
                  lake: Lakehouse = Depends(lake_dep)):
    from agents.ask import ask
    return ok(ask(db, lake, p, body.question, [h.model_dump() for h in body.history], body.model_id))


@router.get("/assistant/status", tags=["assistant"])
def assistant_status(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep)):
    from goops_core.runtime_config import effective_settings
    from agents.ask import _pick_tier, chat_model_options
    from agents.llm.providers import langgraph_available
    settings = effective_settings(db)
    level, tier = _pick_tier(settings)
    options = chat_model_options(settings)
    return ok({"llm_enabled": any(o["available"] for o in options), "level": level,
               "provider": tier.provider if tier else None, "model": tier.model if tier else None,
               "options": options, "engine": "langgraph" if langgraph_available() else "builtin"})


# ------------------------------------------------------------------ simulação "e se…" e briefing diário
class WhatIfRequest(BaseModel):
    overrides: Dict[str, Any] = Field(default_factory=dict)


@router.post("/operations/{operation_id}/whatif", tags=["operations"])
def operation_whatif(operation_id: str, body: WhatIfRequest, p: Principal = Depends(require("operations:read")),
                     db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    from agents.whatif import simulate
    return ok(simulate(db, lake, p, operation_id, body.overrides))


@router.get("/briefings", tags=["briefing"])
def briefings(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep)):
    from agents.briefing import list_briefings
    return ok(list_briefings(db))


@router.post("/briefings/run", tags=["briefing"])
def briefing_run(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
                 lake: Lakehouse = Depends(lake_dep)):
    from agents.briefing import run_briefing
    return ok(run_briefing(db, lake, p))
