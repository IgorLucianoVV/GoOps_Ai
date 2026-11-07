"""Testes de governança (seção 16.3) e segurança."""
from helpers import ADMIN, assert_raises, make_env, user
from data_platform.lineage.registry import graph, upstream_path
from data_platform.semantic.registry import (compute_metric, create_metric, get_metric, list_versions, propose_change,
                                             review_version)
from agents.tools.registry import call_tool
from agents.base import AgentContext
from goops_core.errors import AuthenticationError, PermissionDenied, ValidationError
from goops_core.permissions import agent_principal
from goops_core.security import create_token, decode_token, hash_password, verify_password


def test_corporate_metric_shared_between_domains():
    env = make_env()
    cx = compute_metric(env.db, env.lake, user("data_analyst", ["cx"]), "METRIC_NPS_001")
    lo = compute_metric(env.db, env.lake, user("data_analyst", ["logistics"]), "METRIC_NPS_001")
    assert cx["result"] == lo["result"]
    assert cx["metric"]["scope"] == "corporate"


def test_domain_metric_identified_and_not_equivalent():
    env = make_env()
    m = get_metric(env.db, "CX_NPS_COMMENTED_001")
    assert m["scope"] == "domain" and m["equivalent_to"] is None
    assert "NÃO equivalente" in m["relationship"]
    res = compute_metric(env.db, env.lake, ADMIN, "CX_NPS_COMMENTED_001")
    corp = compute_metric(env.db, env.lake, ADMIN, "METRIC_NPS_001")
    assert res["result"]["n"] < corp["result"]["n"]


def test_domain_metric_cannot_claim_false_equivalence():
    env = make_env()
    payload = {"metric_key": "CX_NPS_FAKE_001", "scope": "domain", "domain": "cx", "name": "NPS CX",
               "description": "teste", "formula_text": "x",
               "formula_definition": {"type": "nps", "score_field": "score", "promoter_min": 8, "detractor_max": 6,
                                      "valid_min": 0, "valid_max": 10, "time_field": "evaluation_date"},
               "unit": "pts", "dimensions": ["state"], "source_datasets": ["gold_nps_analytics"], "filters": [],
               "owner": "cx", "equivalent_to": "METRIC_NPS_001"}
    assert_raises(ValidationError, create_metric, env.db, user("domain_owner", ["cx"]), payload)


def test_domain_owner_cannot_create_corporate_or_other_domain_metric():
    env = make_env()
    base = {"name": "x", "description": "x", "formula_text": "x", "formula_definition": {"type": "count"},
            "unit": "n", "dimensions": [], "source_datasets": ["gold_nps_analytics"], "filters": [], "owner": "x"}
    assert_raises(PermissionDenied, create_metric, env.db, user("domain_owner", ["cx"]),
                  {**base, "metric_key": "METRIC_X_001", "scope": "corporate"})
    assert_raises(PermissionDenied, create_metric, env.db, user("domain_owner", ["cx"]),
                  {**base, "metric_key": "LOG_X_001", "scope": "domain", "domain": "logistics"})


def test_formula_change_creates_new_version_and_preserves_history():
    env = make_env("basic10", shared=False)
    proposer, approver = user("data_owner", uid="USR-a"), user("data_owner", uid="USR-b")
    res = propose_change(env.db, proposer, "METRIC_AVG_SCORE_001", {"description": "Média das notas válidas."}, "doc")
    assert res["proposed_version"] == "1.1" and not res["major_change"]
    assert get_metric(env.db, "METRIC_AVG_SCORE_001")["version"] == "1.0"  # não entra em vigor sem aprovação
    assert_raises(PermissionDenied, review_version, env.db, proposer, "METRIC_AVG_SCORE_001", "1.1", True)
    review_version(env.db, approver, "METRIC_AVG_SCORE_001", "1.1", True)
    m = get_metric(env.db, "METRIC_AVG_SCORE_001")
    assert m["version"] == "1.1" and m["description"] == "Média das notas válidas."
    res2 = propose_change(env.db, proposer, "METRIC_AVG_SCORE_001",
                          {"formula_definition": {"type": "mean", "field": "score", "time_field": "order_date"}}, "período")
    assert res2["proposed_version"] == "2.0" and res2["major_change"]
    versions = list_versions(env.db, "METRIC_AVG_SCORE_001")
    assert [v["version"] for v in versions] == ["1.0", "1.1", "2.0"]
    assert versions[0]["snapshot"]["description"] != m["description"]


def test_arbitrary_formula_rejected():
    env = make_env()
    assert_raises(ValidationError, propose_change, env.db, ADMIN, "METRIC_NPS_001",
                  {"formula_definition": {"type": "python", "code": "__import__('os')"}}, "ataque")


def test_user_without_permission_blocked():
    env = make_env()
    assert_raises(PermissionDenied, propose_change, env.db, user("viewer"), "METRIC_NPS_001", {"description": "x"}, "x")
    assert_raises(PermissionDenied, compute_metric, env.db, env.lake, user("data_analyst", ["cx"]),
                  "LOG_ON_TIME_TOLERANCE_001")


def test_agent_without_permission_blocked():
    env = make_env()
    ctx = AgentContext(env.db, env.lake)
    monitor = agent_principal("monitor")
    assert_raises(PermissionDenied, call_tool, ctx, agent_principal("resolution"), "data_quality_status", {})
    assert call_tool(ctx, monitor, "nps_total", {})["result"]["n"] > 0
    assert_raises(ValidationError, call_tool, ctx, monitor, "sql_query", {"sql": "DROP TABLE users"})
    assert_raises(ValidationError, call_tool, ctx, monitor, "nps_breakdown", {"dimension": "customer_id"})
    assert "operations:approve" not in monitor.permissions()


def test_lineage_identifies_dependencies():
    env = make_env()
    path = upstream_path(env.db, "metric:METRIC_NPS_001")
    for node in ("dataset:gold_nps_analytics", "dataset:silver_nps_evaluations", "bronze:demo_nps", "source:demo_nps",
                 "dataset:gold_orders", "source:demo_orders", "source:demo_deliveries"):
        assert node in path, node
    g = graph(env.db, "source:demo_nps", "downstream")
    assert any(n["id"] == "metric:METRIC_NPS_001" for n in g["nodes"])


def test_passwords_and_tokens():
    h = hash_password("senha-segura-123")
    assert verify_password("senha-segura-123", h) and not verify_password("x", h)
    tok = create_token({"sub": "u1"}, "s3cret", 5)
    assert decode_token(tok, "s3cret")["sub"] == "u1"
    tampered = tok[:-2] + ("AA" if not tok.endswith("AA") else "BB")
    assert_raises(AuthenticationError, decode_token, tampered, "s3cret")
    assert_raises(AuthenticationError, decode_token, tok, "outra-chave")
