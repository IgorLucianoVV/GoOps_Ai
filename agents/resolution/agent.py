"""Resolution Agent — plano de resolução a partir do CATÁLOGO de ações (nunca ações livres).

Seleção de ações é determinística (nível 0) a partir das hipóteses. O impacto esperado é
uma estimativa explícita com premissas. Ações em áreas críticas ficam aguardando aprovação
humana; a execução (somente após aprovação) é SIMULADA nesta versão.
"""
from __future__ import annotations

from typing import Any, Dict, List

from goops_core.incidents import get_incident, set_status, update_fields
from goops_core.operations import execute_operation, get_operation, list_operations, propose_operation
from goops_core.policies import evaluate_action_policy
from goops_core.runtime_config import get_section

from ..base import AgentContext, AgentRun
from ..instructions import prompt_for
from ..tools.registry import call_tool


def _best_alternative_carrier(ctx: AgentContext, run: AgentRun, carrier: str, period: dict) -> str:
    groups = call_tool(ctx, run.principal, "delivery_late_rate", {"group_by": "carrier", **period}, run)["groups"]
    alts = [g for g in groups if g["carrier"] not in (carrier, "Não identificada") and g["n"] >= 30 and g["value"] is not None]
    return min(alts, key=lambda g: g["value"])["carrier"] if alts else "a definir"


def plan_actions(ctx: AgentContext, run: AgentRun, inc: dict) -> List[Dict[str, Any]]:
    sig = inc.get("signal") or {}
    hyps = [h for h in (inc.get("hypotheses") or []) if h["confidence"] >= 0.4]
    plans: List[Dict[str, Any]] = []
    seen = set()
    for h in hyps[:2]:
        dim, seg = h["dimension"], h["segment"]
        if dim == "carrier" and ("carrier", seg) not in seen:
            seen.add(("carrier", seg))
            month = sig.get("month")
            period = {}
            if month:
                import pandas as pd
                pr = pd.Period(month, freq="M")
                period = {"start": pr.start_time.strftime("%Y-%m-%d"), "end": pr.end_time.strftime("%Y-%m-%d")}
            risk = call_tool(ctx, run.principal, "delay_risk_summary", {"carrier": seg}, run)
            states = list(risk["by_state"].keys())[:5]
            target = _best_alternative_carrier(ctx, run, seg, period)
            decomp = next((e for e in h["evidence"] if e["type"] == "nps_decomposition"), None)
            recover = None
            if decomp and decomp.get("nps_baseline") is not None and decomp.get("nps_current") is not None:
                recover = round(-decomp["rate_effect"], 2)
            impact = {"metric": "METRIC_NPS_001",
                      "estimate_pts": recover,
                      "assumption": f"Se o NPS dos pedidos de {seg} voltar ao patamar do período base, mantido o mix.",
                      "open_deliveries_at_risk": risk["high_risk"] + risk["medium_risk"]}
            plans.append({"action_type": "carrier_reallocation",
                          "description": f"Realocar 30% do volume de {seg} nas UFs {', '.join(states) or 'afetadas'} "
                                         f"para {target} até normalização dos prazos.",
                          "params": {"carrier": seg, "states": states, "target_carrier": target, "share_pct": 30},
                          "expected_impact": impact, "hypothesis": h["id"]})
            plans.append({"action_type": "proactive_customer_contact",
                          "description": f"Contatar proativamente clientes com entregas de {seg} em aberto e risco "
                                         f"médio/alto, informando novo prazo.",
                          "params": {"carrier": seg, "states": states, "segment": "entregas em aberto com risco médio/alto"},
                          "expected_impact": {"customers": risk["high_risk"] + risk["medium_risk"],
                                              "assumption": "Comunicação proativa reduz detração por atraso "
                                                            "(efeito a medir após execução)."},
                          "hypothesis": h["id"]})
        elif dim == "product_line" and ("product", seg) not in seen:
            seen.add(("product", seg))
            themes = [e for e in h["evidence"] if e["type"] == "comment_themes"]
            labels = []
            for t in themes:
                labels += [x["label"] for x in t.get("themes", [])] if "themes" in t else [t.get("top_theme")]
            plans.append({"action_type": "product_quality_review",
                          "description": f"Abrir revisão de qualidade para a linha {seg}.",
                          "params": {"product_line": seg, "themes": [x for x in labels if x][:3]},
                          "expected_impact": {"assumption": "Redução de reclamações após correção na origem."},
                          "hypothesis": h["id"]})
        elif dim in ("state", "shipping_type") and ("state", seg) not in seen and not any(s[0] == "carrier" for s in seen):
            seen.add(("state", seg))
            plans.append({"action_type": "regional_logistics_review",
                          "description": f"Revisão logística para {seg}.", "params": {"states": [seg]},
                          "expected_impact": {"assumption": "Diagnóstico regional detalhado."}, "hypothesis": h["id"]})
        elif dim == "data_quality" and ("dq", None) not in seen:
            seen.add(("dq", None))
            plans.append({"action_type": "data_quality_fix", "description": "Corrigir regras de qualidade com falhas.",
                          "params": {"datasets": ["silver_nps_evaluations"], "rules": []},
                          "expected_impact": {"assumption": "Aumenta confiabilidade do indicador."}, "hypothesis": h["id"]})
    return plans


def run_resolution(ctx: AgentContext) -> Dict[str, Any]:
    inc = get_incident(ctx.db, ctx.incident_id)
    with AgentRun(ctx, "resolution", "select_actions", {"incident_id": inc["id"]}) as run:
        plans = ctx.router.run(agent_key="resolution", task="select_actions", agent_run_id=run.id,
                               deterministic=lambda: plan_actions(ctx, run, inc))["output"]
        ops = []
        for plan in plans:
            op = propose_operation(ctx.db, run.principal, action_type=plan["action_type"], description=plan["description"],
                                   params=plan["params"], incident_id=inc["id"], expected_impact=plan["expected_impact"])
            policy = evaluate_action_policy(plan["action_type"], get_section(ctx.db, "policies"))
            run.event("recommendation", f"Recomendação: {op['title']} — {plan['description']} "
                                        f"(risco {op['risk']}; {'requer aprovação humana' if op['requires_approval'] else 'sem área crítica'}).",
                      {"operation_id": op["id"], "hypothesis": plan["hypothesis"], "expected_impact": plan["expected_impact"],
                       "policy": policy})
            ops.append(op)
        narrative = ctx.router.run(
            agent_key="resolution", task="resolution_plan_narrative", agent_run_id=run.id,
            deterministic=lambda: ("Plano: " + " | ".join(f"{o['title']} ({o['status']})" for o in ops)) if ops
            else "Nenhuma ação do catálogo é aplicável com confiança suficiente; recomenda-se análise humana.",
            prompt=lambda: prompt_for(ctx.db, "resolution_plan_narrative") + "\n"
                           "<evidence>\n" + str([{k: o[k] for k in ("title", "description", "risk", "expected_impact",
                                                                      "requires_approval")} for o in ops])[:8000]
                           + "\n</evidence>")
        recommendation = {"summary": narrative["output"], "generated_by": narrative["generated_by"],
                          "operations": [o["id"] for o in ops]}
        update_fields(ctx.db, inc["id"], recommendation=recommendation)
        pending = [o for o in ops if o["status"] == "pending_approval"]
        if pending:
            set_status(ctx.db, inc["id"], "awaiting_approval", run.principal,
                       f"{len(pending)} ação(ões) aguardando aprovação humana")
            run.event("approval_requested", "Aprovação humana solicitada: ações impactam áreas críticas (política de autorização).",
                      {"operations": [o["id"] for o in pending]})
        run.output = {"operations": [o["id"] for o in ops], "pending_approval": [o["id"] for o in pending]}
        return run.output


def run_execution(ctx: AgentContext) -> Dict[str, Any]:
    """Executa (em modo simulado) somente operações APROVADAS do incidente."""
    with AgentRun(ctx, "resolution", "execute_approved", {"incident_id": ctx.incident_id}) as run:
        inc = get_incident(ctx.db, ctx.incident_id)
        approved = [o for o in list_operations(ctx.db, incident_id=inc["id"]) if o["status"] == "approved"]
        if approved and inc["status"] != "executing":
            set_status(ctx.db, inc["id"], "executing", run.principal, "Execução (simulada) das ações aprovadas")
        done = []
        for op in approved:
            res = execute_operation(ctx.db, run.principal, op["id"])
            run.event("execution", f"Ação executada em MODO SIMULADO: {res['title']} — nenhum sistema externo foi "
                                   f"alterado.", {"operation_id": op["id"], "result": res["result"]})
            done.append(res["id"])
        run.output = {"executed": done}
        return run.output
