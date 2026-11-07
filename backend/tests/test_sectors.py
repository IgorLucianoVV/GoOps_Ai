"""Setores dinâmicos: descoberta de campos, conjunto configurável, métricas novas, painel e agentes por modelo."""
import unittest

from helpers import ADMIN, assert_raises, make_env, user
from agents.custom import run_agent, save_agent
from data_platform.ingestion.service import create_source, gocase_seed_available
from data_platform.pipelines.runner import run_pipeline
from data_platform.sectors.dashboards import render_dashboard, save_dashboard
from data_platform.sectors.datasets import get_custom_dataset, save_custom_dataset, suggest_metrics
from data_platform.sectors.discovery import infer_type, profile
from data_platform.semantic.engine import compute
from data_platform.semantic.registry import compute_metric, create_domain, create_metric, review_version
from goops_core.errors import PermissionDenied, ValidationError
import pandas as pd


def _env():
    if not gocase_seed_available():
        raise unittest.SkipTest("planilhas da seed Gocase ausentes")
    return make_env("gocase")


def test_discovery_infers_types_roles_and_pii():
    recs = [{"payload": {"ticket": {"id": f"T{i}", "canal": "chat" if i % 2 else "email"}, "aberto_em": f"2026-0{1 + i % 3}-10",
                         "tempo": i * 1.5, "resolvido": "Sim" if i % 3 else "Não", "email": f"a{i}@x.com"}} for i in range(60)]
    prof = profile(recs)
    f = {x["path"]: x for x in prof["fields"]}
    assert f["ticket.id"]["type"] == "id" and prof["suggested_key"] == "id"
    assert f["aberto_em"]["type"] == "datetime" and prof["suggested_time_field"] == "aberto_em"
    assert f["resolvido"]["type"] == "bool" and f["tempo"]["role"] == "measure"
    assert f["email"]["pii"] and not f["email"]["include"] and f["email"]["examples"][0] == "•••"
    assert infer_type(["1", "2", "3.5"]) == "float"


def test_new_metric_types():
    df = pd.DataFrame({"v": [1, 2, 3, 4, 100], "c": ["a", "a", "b", None, "c"]})
    assert compute({"type": "sum", "field": "v"}, df)["value"] == 110
    assert compute({"type": "median", "field": "v"}, df)["value"] == 3
    assert compute({"type": "percentile", "q": 80, "field": "v"}, df)["value"] == 23.2
    assert compute({"type": "count_distinct", "field": "c"}, df)["value"] == 3


def test_reputation_example_sector_end_to_end():
    env = _env()
    ds = get_custom_dataset(env.db, "reclameaqui")
    gold = env.lake.read_table("gold/domains/reputacao", "gold_reclameaqui")
    assert len(gold) > 1500 and "month" in gold and "dias_resposta" in gold
    assert not {"e_mail", "email", "reclamacao"} & set(gold.columns)                 # PII não ingerida
    r = compute_metric(env.db, env.lake, ADMIN, "REP_RA_NOTA_MEDIA")
    assert 0 <= r["result"]["value"] <= 10 and r["result"]["n"] > 600
    dash = render_dashboard(env.db, env.lake, ADMIN, "reputacao")
    assert len(dash["widgets"]) == 9 and all(w["error"] is None for w in dash["widgets"])
    out = run_agent(env.db, env.lake, ADMIN, "rep_resumo_semanal")
    assert out["status"] == "ok" and "Nota média" in out["summary_md"]
    mon = run_agent(env.db, env.lake, ADMIN, "rep_monitor_nota")
    assert mon["status"] in ("ok", "alert") and "message" in mon
    assert ds["definition"]["key_field"] == "id"


def test_create_sector_from_scratch_with_governance():
    env = make_env("basic10", shared=False)
    import os
    from pathlib import Path
    from data_platform.connectors.file_connector import import_dir
    folder = import_dir() / "tests_tmp"
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Protocolo": [f"P{i}" for i in range(40)], "Aberto em": [f"2026-0{1 + i % 2}-0{1 + i % 9}" for i in range(40)],
                  "Canal": ["chat", "email"] * 20, "Minutos": [10 + i for i in range(40)],
                  "Resolvido": ["Sim", "Não", "Sim", "Sim"] * 10}).to_csv(folder / "atendimento.csv", index=False)
    try:
        create_domain(env.db, ADMIN, "sac", "SAC (teste)")
        create_source(env.db, ADMIN, key="atd_csv", name="Atendimento CSV", entity="custom", connector="file",
                      config={"path": "tests_tmp/atendimento.csv", "format": "csv"})
        bad = {"source_keys": ["atd_csv"], "key_field": "protocolo", "time_field": "aberto_em",
               "fields": [{"name": "protocolo", "from": "Protocolo", "type": "id", "role": "key", "pii": True}]}
        assert_raises(ValidationError, save_custom_dataset, env.db, ADMIN, key="tickets", domain="sac", name="x",
                      description="", definition=bad)
        definition = {"source_keys": ["atd_csv"], "key_field": "protocolo", "time_field": "aberto_em", "fields": [
            {"name": "protocolo", "from": "Protocolo", "type": "id", "role": "key"},
            {"name": "aberto_em", "from": "Aberto em", "type": "datetime", "role": "time"},
            {"name": "canal", "from": "Canal", "type": "string", "role": "dimension"},
            {"name": "minutos", "from": "Minutos", "type": "float", "role": "measure"},
            {"name": "resolvido", "from": "Resolvido", "type": "bool", "role": "dimension"}]}
        ds = save_custom_dataset(env.db, ADMIN, key="tickets", domain="sac", name="Tickets", description="",
                                 definition=definition)
        assert run_pipeline(env.db, env.lake, ADMIN, sync=True)["status"] == "success"
        sugg = suggest_metrics(ds)
        keys = [m["metric_key"] for m in sugg]
        assert "SAC_TICKETS_VOLUME" in keys and "SAC_TICKETS_RATE_RESOLVIDO" in keys
        m = create_metric(env.db, ADMIN, next(x for x in sugg if x["metric_key"] == "SAC_TICKETS_RATE_RESOLVIDO"))
        assert m["status"] == "pending_approval"
        assert_raises(ValidationError, compute_metric, env.db, env.lake, ADMIN, m["metric_key"])         # não ativa
        draft = compute_metric(env.db, env.lake, ADMIN, m["metric_key"], allow_draft=True)
        assert draft["metric"]["draft"] and draft["result"]["value"] == 75.0
        save_dashboard(env.db, ADMIN, "sac", "Painel", [
            {"title": "Resolvidos", "metric_key": m["metric_key"], "chart": "kpi"},
            {"title": "Resolvidos por canal", "metric_key": m["metric_key"], "chart": "bar", "group_by": "canal"}])
        assert_raises(ValidationError, save_dashboard, env.db, ADMIN, "sac", "P",
                      [{"metric_key": m["metric_key"], "chart": "bar", "group_by": "inexistente"}])
        a = save_agent(env.db, ADMIN, key="atd_monitor", domain="sac", name="Monitor", template="metric_monitor",
                       config={"metric_key": m["metric_key"], "rule": "below", "threshold": 90, "min_n": 5}, interval_minutes=60)
        assert run_agent(env.db, env.lake, ADMIN, a["key"])["status"] == "skipped"          # métrica ainda não aprovada
        review_version(env.db, user("data_owner"), m["metric_key"], "1.0", True, "ok")
        res = run_agent(env.db, env.lake, ADMIN, a["key"])
        assert res["status"] == "alert" and res["incidents"] and res["incidents"][0]["created"]
        assert_raises(PermissionDenied, save_agent, env.db, user("viewer"), key="x_agent", domain="sac", name="x",
                      template="summary", config={"metric_keys": [m["metric_key"]]}, interval_minutes=None)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_ai_merge_never_includes_pii_and_validates():
    from agents.sector_setup import _merge, refine_with_ai
    prof = profile([{"payload": {"id": f"X{i}", "email": f"a{i}@b.com", "valor": i * 2.5, "data": "2026-01-0%d" % (1 + i % 9)}}
                    for i in range(30)])
    ai = {"fields": [{"path": "email", "include": True, "role": "dimension"},
                     {"path": "valor", "name": "valor_pedido", "label": "Valor do pedido", "type": "python", "role": "measure"}],
          "key_field": "inexistente", "metrics": [
              {"key_suffix": "ticket", "name": "Ticket", "formula": {"type": "mean", "field": "valor_pedido"}},
              {"key_suffix": "bad", "formula": {"type": "sql", "field": "x"}},
              {"key_suffix": "bad2", "formula": {"type": "mean", "field": "nao_existe"}}]}
    out = _merge(prof, ai)
    f = {x["path"]: x for x in out["fields"]}
    assert f["email"]["pii"] and not f["email"]["include"]                       # IA não inclui dado pessoal
    assert f["valor"]["name"] == "valor_pedido" and f["valor"]["type"] == "float"  # tipo inválido descartado
    assert out["suggested_key"] == prof["suggested_key"]
    assert [m["key_suffix"] for m in out["ai_metrics"]] == ["TICKET"]
    env = make_env("basic10", shared=False)
    r = refine_with_ai(env.db, "Teste", prof)                                     # sem modelo: heurística
    assert r["generated_by"] == "deterministic" and r["fallback_reason"]


def test_agents_drivers_action_relationships_preview_and_ask():
    env = make_env("basic10", shared=False)
    from data_platform.connectors.file_connector import import_dir
    from data_platform.sectors.metrics import preview_metric
    import shutil
    orders = env.lake.read_table("gold/corporate", "gold_orders")["order_id"].astype(str).tolist()
    folder = import_dir() / "tests_tmp2"
    folder.mkdir(parents=True, exist_ok=True)
    rows = 80
    pd.DataFrame({"Ticket": [f"T{i}" for i in range(rows)], "Pedido": [orders[i % len(orders)] for i in range(rows)],
                  "Data": [("2026-01-%02d" if i < 40 else "2026-02-%02d") % (1 + i % 20) for i in range(rows)],
                  "Canal": ["chat" if i % 2 else "email" for i in range(rows)],
                  "Nota": [9 if (i < 40 or i % 2 == 0) else 3 for i in range(rows)]}).to_csv(folder / "t.csv", index=False)
    try:
        create_domain(env.db, ADMIN, "suporte", "Suporte")
        create_source(env.db, ADMIN, key="sup_csv", name="Suporte", entity="custom", connector="file",
                      config={"path": "tests_tmp2/t.csv", "format": "csv"})
        definition = {"source_keys": ["sup_csv"], "key_field": "ticket", "time_field": "data", "fields": [
            {"name": "ticket", "from": "Ticket", "type": "id", "role": "key"},
            {"name": "pedido", "from": "Pedido", "type": "id", "role": "attribute"},
            {"name": "data", "from": "Data", "type": "datetime", "role": "time"},
            {"name": "canal", "from": "Canal", "type": "string", "role": "dimension"},
            {"name": "nota", "from": "Nota", "type": "float", "role": "measure"}],
            "relationships": [{"field": "pedido", "dataset": "gold_orders", "on": "order_id", "bring": ["product_line", "customer_id"]}]}
        ds = save_custom_dataset(env.db, ADMIN, key="tickets_sup", domain="suporte", name="Tickets", description="", definition=definition)
        assert ds["definition"]["relationships"][0]["bring"] == ["product_line"]          # customer_id bloqueado
        assert run_pipeline(env.db, env.lake, ADMIN, sync=True)["status"] == "success"
        gold = env.lake.read_table("gold/domains/suporte", "gold_tickets_sup")
        assert gold["product_line"].notna().sum() == rows
        payload = {"source_datasets": ["gold_tickets_sup"], "formula_definition": {"type": "mean", "field": "nota", "time_field": "data"}}
        pv = preview_metric(env.db, env.lake, ADMIN, "suporte", payload)
        assert pv["result"]["n"] == rows and [g["month"] for g in pv["groups"]] == ["2026-01", "2026-02"]
        m = create_metric(env.db, ADMIN, {"metric_key": "SUP_NOTA", "scope": "domain", "domain": "suporte", "name": "Nota",
                                          "description": "Nota média", "formula_text": "média(nota)", "unit": "nota",
                                          "formula_definition": payload["formula_definition"], "owner": "Suporte",
                                          "dimensions": ["month", "canal", "product_line"], "source_datasets": ["gold_tickets_sup"]})
        review_version(env.db, user("data_owner"), m["metric_key"], "1.0", True, "ok")
        save_agent(env.db, ADMIN, key="sup_drivers", domain="suporte", name="Causas", template="driver_analysis",
                   config={"metric_key": "SUP_NOTA", "dimensions": ["canal"], "min_n": 5}, interval_minutes=None)
        d = run_agent(env.db, env.lake, ADMIN, "sup_drivers")
        assert d["status"] == "ok" and d["drivers"][0]["segment"] == "chat" and "chat" in d["summary_md"]
        save_agent(env.db, ADMIN, key="sup_acao", domain="suporte", name="Ação", template="action_task",
                   config={"metric_key": "SUP_NOTA", "rule": "drop", "threshold": 1, "min_n": 5,
                           "action_type": "sector_customer_contact", "action_note": "Ligar para os clientes"}, interval_minutes=None)
        r = run_agent(env.db, env.lake, ADMIN, "sup_acao")
        op = r["incidents"][0]["operation"]
        assert r["status"] == "alert" and op["status"] == "pending_approval" and op["requires_approval"]   # área crítica
        assert_raises(ValidationError, save_agent, env.db, ADMIN, key="sup_bad", domain="suporte", name="x", template="action_task",
                      config={"metric_key": "SUP_NOTA", "rule": "drop", "threshold": 1, "action_type": "carrier_reallocation"},
                      interval_minutes=None)
        import agents.ask as A
        tb = A.Toolbox(env.db, env.lake, ADMIN)
        assert tb.run("dimension_values", {"dimension": "canal", "metric_key": "SUP_NOTA"})["values"] == ["chat", "email"]
        v = tb.run("metric_value", {"metric_key": "SUP_NOTA", "filters": {"canal": ["email"]}})
        assert v["result"]["value"] == 9.0
    finally:
        shutil.rmtree(folder, ignore_errors=True)
