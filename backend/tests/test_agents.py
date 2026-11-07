"""Testes dos agentes e do ciclo operacional supervisionado (seção 16.4)."""
from helpers import ADMIN, assert_raises, make_env, user
from agents.supervisor.agent import Supervisor
from goops_core.errors import PermissionDenied, PolicyViolation
from goops_core.incidents import get_incident, list_incidents, timeline
from goops_core.operations import execute_operation, list_operations
from goops_core.permissions import agent_principal


def _env_with_cycle():
    env = make_env("full", shared=False)
    sup = Supervisor(env.db, env.lake)
    out = sup.run_monitoring_cycle(ADMIN)
    return env, sup, out


_STATE = {}


def _shared():
    if "env" not in _STATE:
        _STATE["env"], _STATE["sup"], _STATE["out"] = _env_with_cycle()
    return _STATE["env"], _STATE["sup"], _STATE["out"]


def _nps_incident(env):
    return next(i for i in list_incidents(env.db) if (i["signal"] or {}).get("type") == "nps_drop")


def test_1_monitor_detects_nps_drop():
    env, sup, out = _shared()
    inc = _nps_incident(env)
    assert inc["signal"]["month"] == "2026-06" and inc["signal"]["drop"] >= 8
    assert inc["source"] == "monitor_agent" and inc["is_demo"]
    assert out["monitor"]["generated_by"] == "deterministic"


def test_2_monitor_deduplicates_incidents():
    env, sup, out = _shared()
    before = len(list_incidents(env.db))
    again = sup.run_monitoring_cycle(ADMIN, auto_investigate=False)
    assert again["monitor"]["created"] == [] and len(list_incidents(env.db)) == before


def test_3_investigation_uses_authorized_tools_and_presents_evidence():
    env, sup, out = _shared()
    inc = _nps_incident(env)
    events = timeline(env.db, inc["id"])
    tools = {e["data"]["tool"] for e in events if e["event_type"] == "tool_call"}
    assert {"nps_breakdown", "delivery_late_rate", "data_quality_status", "lineage_upstream"} <= tools
    top = inc["hypotheses"][0]
    assert top["segment"] == "DeltaFrete" and 0 < top["confidence"] <= 0.95
    assert any(e["type"] == "late_rate_change" for e in top["evidence"])
    assert inc["evidence"] and inc["root_cause"]
    hyp_event = next(e for e in events if e["event_type"] == "hypothesis")
    assert hyp_event["data"]["generated_by"] == "deterministic"   # sem LLM configurado: identificado como tal
    assert hyp_event["data"]["limitations"]


def test_4_resolution_generates_recommendation_requiring_approval():
    env, sup, out = _shared()
    inc = _nps_incident(env)
    ops = list_operations(env.db, incident_id=inc["id"])
    types = {o["action_type"] for o in ops}
    assert "carrier_reallocation" in types and "proactive_customer_contact" in types
    critical = [o for o in ops if o["action_type"] == "carrier_reallocation"][0]
    assert critical["requires_approval"] and critical["status"] == "pending_approval"
    assert inc["status"] == "awaiting_approval"
    assert_raises(PolicyViolation, execute_operation, env.db, agent_principal("resolution"), critical["id"])


def test_5_agents_and_wrong_domain_cannot_approve():
    env, sup, out = _shared()
    inc = _nps_incident(env)
    op = [o for o in list_operations(env.db, incident_id=inc["id"]) if o["action_type"] == "carrier_reallocation"][0]
    assert_raises(PermissionDenied, sup.decide, op["id"], agent_principal("supervisor"), True)
    assert_raises(PermissionDenied, sup.decide, op["id"], user("domain_owner", ["cx"]), True)
    assert_raises(PermissionDenied, sup.decide, op["id"], user("viewer"), True)


def test_6_full_cycle_approval_execution_validation_and_history():
    env, sup, out = _shared()
    inc = _nps_incident(env)
    ops = [o for o in list_operations(env.db, incident_id=inc["id"]) if o["status"] == "pending_approval"]
    log_owner, cx_owner = user("domain_owner", ["logistics"], "USR-lo"), user("domain_owner", ["cx"], "USR-cx")
    for o in ops:
        approver = log_owner if o["action_type"] == "carrier_reallocation" else cx_owner
        res = sup.decide(o["id"], approver, True, "aprovado em teste")
    assert res["workflow"]["status"] == "completed"
    inc = get_incident(env.db, inc["id"])
    assert inc["status"] == "executing"   # sem dados pós-ação: permanece em monitoramento
    assert inc["result"]["status"] == "monitoring" and inc["result"]["policies_ok"]
    assert inc["summary"] and "DeltaFrete" in inc["summary"]          # resumo executivo (nível 2 → fallback determinístico)
    top = inc["hypotheses"][0]
    cls = next(e for e in top["evidence"] if e["type"] == "comment_classification")
    assert cls["generated_by"] == "deterministic" and "unclassified" in cls
    executed = list_operations(env.db, incident_id=inc["id"])
    assert all(o["status"] == "executed" and o["result"]["simulated"] for o in executed)
    kinds = [e["event_type"] for e in timeline(env.db, inc["id"])]
    for k in ("detected", "anomaly_detected", "supervisor", "data_validation", "investigation_started", "hypothesis",
              "recommendation", "approval_requested", "human_decision", "execution", "validation"):
        assert k in kinds, k
    sup.close_incident(inc["id"], user("admin"), "encerrado em teste")
    assert get_incident(env.db, inc["id"])["status"] == "closed"


def test_7_rejection_blocks_critical_actions():
    env = make_env("full", shared=False)
    sup = Supervisor(env.db, env.lake)
    sup.run_monitoring_cycle(ADMIN)
    inc = _nps_incident(env)
    for o in [o for o in list_operations(env.db, incident_id=inc["id"]) if o["status"] == "pending_approval"]:
        sup.decide(o["id"], user("admin"), False, "não aprovado")
    inc = get_incident(env.db, inc["id"])
    assert inc["status"] != "awaiting_approval"
    ops = list_operations(env.db, incident_id=inc["id"])
    assert all(o["status"] == "rejected" for o in ops if o["requires_approval"])
    assert all(not (o["requires_approval"] and o["status"] == "executed") for o in ops)
    assert sum(1 for e in timeline(env.db, inc["id"]) if e["event_type"] == "human_decision") >= 2


def test_8_routing_metrics_without_llm():
    env, sup, out = _shared()
    from agents.routing.router import efficiency_metrics
    m = efficiency_metrics(env.db)
    assert m["pct_without_llm"] == 100.0 and m["llm_calls"] == 0 and m["fallbacks_to_deterministic"] > 0
