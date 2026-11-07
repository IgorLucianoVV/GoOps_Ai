"""Pacote demo: setor Estoque (FIFO), simulação "e se…" e briefing diário — todos ligáveis/desligáveis."""
import unittest

import pandas as pd

from helpers import ADMIN, assert_raises, make_env
from agents.briefing import briefing_due, run_briefing
from agents.custom import run_agent
from agents.whatif import simulate
from data_platform.ingestion.service import apply_features, gocase_seed_available
from data_platform.sectors.stock import compute_stuck
from data_platform.semantic.registry import compute_metric
from goops_core.errors import ValidationError
from goops_core.operations import propose_operation
from goops_core.runtime_config import update_section


def test_stock_fifo_rules():
    clientes = pd.DataFrame({"Código do Pedido": ["P1", "P2", "P3", "P4", "P5"],
                             "Data do Pedido": ["2024-11-01", "2024-11-02", "2024-11-03", "2024-11-04", "2024-11-05"]})
    detalhes = pd.DataFrame({"Pedido": ["P1", "P2", "P3", "P4", "P5", "P5"],
                             "Detalhe do pedido": ["Copo A", "Copo A", "Copo A", "Case Z", "Mala Fora", "Case Z"]})
    estoque = pd.DataFrame({"Produtos": ["Copo A", "Case Z"], "Estoque": [1, 0]})
    out = compute_stuck(clientes, detalhes, estoque)["items"].set_index(["pedido", "produto"])
    assert out.loc[("P1", "Copo A"), "situacao"] == "Atendível"                 # mais antigo atendido (FIFO)
    assert out.loc[("P3", "Copo A"), "situacao"] == "Estoque insuficiente"
    assert out.loc[("P4", "Case Z"), "situacao"] == "Estoque zero"
    assert out.loc[("P5", "Mala Fora"), "situacao"] == "Fora do catálogo" and not out.loc[("P5", "Mala Fora"), "travado"]


def test_stock_sector_agent_whatif_and_toggle():
    if not gocase_seed_available():
        raise unittest.SkipTest("seed Gocase ausente")
    env = make_env("gocase", shared=False)
    gold = env.lake.read_table("gold/domains/estoque", "gold_estoque_pedidos")
    assert not {"Nome do Cliente", "Telefone", "E-mail", "nome", "email"} & set(gold.columns)   # sem dados pessoais
    v = compute_metric(env.db, env.lake, ADMIN, "ESTQ_PEDIDOS_TRAVADOS")["result"]["value"]
    assert v and v > 0
    r = run_agent(env.db, env.lake, ADMIN, "estq_avisar_clientes")
    op = r["incidents"][0]["operation"]
    assert r["status"] == "alert" and op["status"] == "pending_approval"           # contato com cliente exige aprovação
    w = simulate(env.db, env.lake, ADMIN, op["id"])
    assert w["available"] and w["orders_to_contact"] > 0 and "(A)" in w["message_preview"]
    update_section(env.db, ADMIN, "features", {"whatif": False, "sector_stock": False})
    apply_features(env.db)
    assert_raises(ValidationError, simulate, env.db, env.lake, ADMIN, op["id"])
    assert env.db.fetchone("SELECT status FROM domains WHERE key = 'estoque'")["status"] == "inactive"
    assert env.db.fetchone("SELECT COUNT(*) AS n FROM custom_agents WHERE domain = 'estoque' AND enabled = 1")["n"] == 0
    assert env.db.fetchone("SELECT status FROM sources WHERE key = 'estoque_relatorio'")["status"] == "inactive"


def test_whatif_carrier_projection():
    env = make_env("full")
    op = propose_operation(env.db, ADMIN, action_type="carrier_reallocation", description="teste",
                           params={"carrier": "DeltaFrete", "target_carrier": "BetaLog", "states": ["BA", "PE", "CE"],
                                   "share_pct": 50})
    w = simulate(env.db, env.lake, ADMIN, op["id"])
    assert w["available"] and w["late_rate_projected"] < w["late_rate_current"]
    assert w["nps_projected"] is None or w["nps_projected"] >= w["nps_current"]
    w0 = simulate(env.db, env.lake, ADMIN, op["id"], {"share_pct": 0})
    assert w0["late_rate_projected"] == w0["late_rate_current"]


def test_briefing_manual_and_schedule_toggle():
    env = make_env("basic10", shared=False)
    b = run_briefing(env.db, env.lake, ADMIN)
    assert "Briefing GoOps" in b["content_md"] and "NPS" in b["content_md"]
    assert b["deliveries"] == [{"channel": "slack", "target": "#operacoes", "status": "simulado"}]
    assert b["generated_by"] == "deterministic"
    assert not briefing_due(env.db)                                                  # desligado por padrão
    update_section(env.db, ADMIN, "features", {"briefing_enabled": True, "briefing_email": True,
                                               "briefing_email_to": "gestor@empresa.com"})
    assert briefing_due(env.db)
    assert_raises(ValidationError, update_section, env.db, ADMIN, "features", {"briefing_email_to": "não-é-email"})
    b2 = run_briefing(env.db, env.lake, ADMIN, "scheduler")
    assert {d["channel"] for d in b2["deliveries"]} == {"slack", "email"} and not briefing_due(env.db)
