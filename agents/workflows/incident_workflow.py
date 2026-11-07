"""Workflow hierárquico de incidentes coordenado pelo Supervisor.

validate_inputs → investigate → plan_resolution ─┬─(ações pendentes)→ await_approval ⏸ (interrupção humana)
                                                 └─(sem pendências)─→ execute → validate_outcome → finalize
Retomada após decisão humana: execute (se houver aprovação) ou finalize (se tudo rejeitado).
"""
from __future__ import annotations

from typing import Any, Dict

from goops_core.incidents import get_incident, update_fields
from goops_core.operations import list_operations

from ..base import AgentContext, AgentRun
from ..instructions import prompt_for
from ..investigation.agent import run_investigation
from ..resolution.agent import run_execution, run_resolution
from ..validation.agent import validate_inputs, validate_outcome
from .graph import END, Interrupt, StateGraph


def build_incident_graph(ctx: AgentContext) -> StateGraph:
    def n_validate_inputs(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"data_validation": validate_inputs(ctx)}

    def n_investigate(state: Dict[str, Any]) -> Dict[str, Any]:
        res = run_investigation(ctx)
        return {"hypotheses": [{k: h[k] for k in ("id", "statement", "confidence")} for h in res["hypotheses"]]}

    def n_plan(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"resolution": run_resolution(ctx)}

    def route_after_plan(state: Dict[str, Any]) -> str:
        if not state["resolution"]["operations"]:
            return "finalize"
        return "await_approval" if state["resolution"]["pending_approval"] else "execute"

    def n_await(state: Dict[str, Any]) -> Dict[str, Any]:
        ops = list_operations(ctx.db, incident_id=ctx.incident_id)
        if any(o["status"] == "pending_approval" for o in ops):
            raise Interrupt("await_approval", "Aguardando aprovação humana")
        return {"approval": {o["id"]: o["status"] for o in ops}}

    def route_after_await(state: Dict[str, Any]) -> str:
        return "execute" if any(s == "approved" for s in state["approval"].values()) else "finalize"

    def n_execute(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"execution": run_execution(ctx)}

    def n_validate_outcome(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"outcome": validate_outcome(ctx)}

    def n_finalize(state: Dict[str, Any]) -> Dict[str, Any]:
        inc = get_incident(ctx.db, ctx.incident_id)
        ops = list_operations(ctx.db, incident_id=ctx.incident_id)

        def deterministic() -> str:
            acts = "; ".join(f"{o['title']} ({o['status']})" for o in ops) or "nenhuma ação"
            res = (inc.get("result") or {}).get("status", "n/d")
            return (f"{inc['title']}. Causa provável: {inc.get('root_cause') or 'inconclusiva'}. "
                    f"Ações: {acts}. Resultado: {res}. Status atual: {inc['status']}.")

        with AgentRun(ctx, "supervisor", "summarize_incident", {"incident_id": inc["id"]}) as run:
            res = ctx.router.run(agent_key="supervisor", task="summarize_incident", deterministic=deterministic,
                                 agent_run_id=run.id, max_tokens=350,
                                 prompt=lambda: prompt_for(ctx.db, "summarize_incident") + "\n<evidence>\n"
                                                + deterministic() + "\n</evidence>")
            update_fields(ctx.db, inc["id"], summary=res["output"])
            run.event("summary", res["output"], {"generated_by": res["generated_by"],
                                                 "fallback_reason": res.get("fallback_reason")})
            run.output = {"generated_by": res["generated_by"]}
        return {"final_status": inc["status"]}

    g = StateGraph("incident_resolution")
    g.add_node("validate_inputs", n_validate_inputs).add_node("investigate", n_investigate)
    g.add_node("plan_resolution", n_plan).add_node("await_approval", n_await)
    g.add_node("execute", n_execute).add_node("validate_outcome", n_validate_outcome).add_node("finalize", n_finalize)
    g.set_entry("validate_inputs")
    g.add_edge("validate_inputs", "investigate").add_edge("investigate", "plan_resolution")
    g.add_edge("plan_resolution", route_after_plan).add_edge("await_approval", route_after_await)
    g.add_edge("execute", "validate_outcome").add_edge("validate_outcome", "finalize").add_edge("finalize", END)
    return g
