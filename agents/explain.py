"""Explicações em linguagem de negócio (nível 2 — LLM econômico) com fallback determinístico."""
from __future__ import annotations

from typing import Any, Dict

from goops_core.db import Database
from goops_core.permissions import Principal, require_permission
from data_platform.semantic.registry import get_metric
from data_platform.storage import Lakehouse

from .base import AgentContext, AgentRun
from .instructions import prompt_for


def explain_metric(db: Database, lake: Lakehouse, actor: Principal, key: str) -> Dict[str, Any]:
    require_permission(actor, "semantic:read")
    m = get_metric(db, key)
    ctx = AgentContext(db, lake)

    def deterministic() -> str:
        dims = ", ".join(m["dimensions"]) or "nenhuma"
        return (f"{m['name']} ({m['metric_key']} v{m['version']}) — {m['description']} Fórmula: {m['formula_text']}. "
                f"Unidade: {m['unit']}. Fonte: {', '.join(m['source_datasets'])}. Pode ser analisada por: {dims}. "
                f"{m['relationship']}. Responsável: {m['owner']}.")

    with AgentRun(ctx, "supervisor", "explain_metric", {"metric_key": key}) as run:
        res = ctx.router.run(agent_key="supervisor", task="explain_metric", deterministic=deterministic,
                             agent_run_id=run.id, max_tokens=350,
                             prompt=lambda: prompt_for(db, "explain_metric") + "\n<evidence>\n"
                                            + deterministic() + "\n</evidence>")
        run.output = {"generated_by": res["generated_by"]}
        return {"metric_key": key, "explanation": res["output"], "generated_by": res["generated_by"],
                "fallback_reason": res.get("fallback_reason")}
