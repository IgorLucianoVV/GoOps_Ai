"""Validation Agent — valida dados usados, políticas e resultados (nível 0)."""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from goops_core.incidents import get_incident, set_status, update_fields
from goops_core.operations import list_operations

from ..base import AgentContext, AgentRun
from ..tools.registry import call_tool


def validate_inputs(ctx: AgentContext) -> Dict[str, Any]:
    with AgentRun(ctx, "validation", "check_data_quality", {"incident_id": ctx.incident_id}) as run:
        dq = call_tool(ctx, run.principal, "data_quality_status", {}, run)
        errors = [i for i in dq["issues"] if i["severity"] == "error"]
        max_rate = max([i["fail_rate"] or 0 for i in errors], default=0)
        ds = ctx.db.fetchone("SELECT last_built_at, is_demo FROM datasets WHERE key = 'gold_nps_analytics'")
        ok = max_rate <= 5 and ds is not None
        verdict = {"ok": ok, "max_error_rate": max_rate, "quarantined_total": dq["summary"].get("quarantined_total"),
                   "dataset_built_at": ds["last_built_at"] if ds else None, "is_demo_data": bool(ds and ds["is_demo"])}
        run.event("data_validation", ("Dados validados para a investigação" if ok else
                                      "ATENÇÃO: qualidade de dados abaixo do limiar — conclusões com ressalvas")
                  + f" (maior taxa de erro {max_rate}%; quarentena: {verdict['quarantined_total']}).", verdict)
        run.output = verdict
        return verdict


def validate_outcome(ctx: AgentContext) -> Dict[str, Any]:
    with AgentRun(ctx, "validation", "validate_result", {"incident_id": ctx.incident_id}) as run:
        inc = get_incident(ctx.db, ctx.incident_id)
        ops = list_operations(ctx.db, incident_id=inc["id"])
        checks = []
        for op in ops:
            if op["status"] in ("executed", "failed"):
                policy_ok = (not op["requires_approval"]) or (op.get("approved_by") or "").startswith("user:")
                checks.append({"operation_id": op["id"], "status": op["status"], "mode": op.get("execution_mode"),
                               "policy_respected": policy_ok, "approved_by": op.get("approved_by")})
        sig = inc.get("signal") or {}
        outcome = {"status": "monitoring", "checks": checks}
        if sig.get("type") == "nps_drop":
            rows = [r for r in call_tool(ctx, run.principal, "nps_monthly", {}, run)["rows"] if r["has_data"]]
            later = [r for r in rows if r["month"] > sig["month"]]
            if later:
                recovered = later[-1]["nps"] >= sig["value"] + 0.5 * sig["drop"]
                outcome.update(status="resolved" if recovered else "not_resolved", latest_month=later[-1]["month"],
                               latest_nps=later[-1]["nps"], target=round(sig["value"] + 0.5 * sig["drop"], 2))
            else:
                outcome.update(message=f"Ainda não há dados posteriores a {sig['month']} para medir o efeito. "
                                       "A execução foi SIMULADA; o incidente permanece em monitoramento.")
        else:
            outcome["message"] = "Efeito ainda não mensurável; execução simulada. Incidente em monitoramento."
        all_ok = all(c["policy_respected"] for c in checks)
        outcome["policies_ok"] = all_ok
        update_fields(ctx.db, inc["id"], result=outcome)
        run.event("validation", ("Validação concluída: " + {"resolved": "problema resolvido segundo o indicador.",
                                                             "not_resolved": "indicador ainda não recuperou.",
                                                             "monitoring": outcome.get("message", "")}[outcome["status"]])
                  + (" Políticas respeitadas." if all_ok else " VIOLAÇÃO de política detectada."), outcome)
        if outcome["status"] == "resolved" and inc["status"] == "executing":
            set_status(ctx.db, inc["id"], "resolved", run.principal, "Indicador recuperado")
        run.output = outcome
        return outcome
