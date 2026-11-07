"""Seed padrão com as planilhas reais do case Gocase (conector file + perfil gocase_xlsx)."""
import unittest

from helpers import ADMIN, assert_raises, make_env
from data_platform.connectors.file_connector import FileConnector
from data_platform.ingestion.service import gocase_seed_available
from data_platform.analytics.nps import NpsAnalytics
from data_platform.quality.engine import UFS
from data_platform.silver.mappings import product_line_from_name
from data_platform.silver.transforms import _parse_dt
from goops_core.errors import ValidationError


def _env():
    if not gocase_seed_available():
        raise unittest.SkipTest("planilhas da seed Gocase ausentes")
    return make_env("gocase")


def test_date_formats_from_spreadsheets():
    assert str(_parse_dt("2025-04-04T01:03:20.307Z")[0]) == "2025-04-04 01:03:20.307000"
    assert str(_parse_dt("2025-04-07T03:11:56.23Z")[0]) == "2025-04-07 03:11:56.230000"
    assert str(_parse_dt("9 May, 2025, 14:01")[0]) == "2025-05-09 14:01:00"
    assert _parse_dt("31 Feb, 2025, 10:00")[1] is True


def test_product_line_rule():
    assert product_line_from_name("Case Anti Impacto Slim / iPhone 13") == "Capinha"
    assert product_line_from_name("Tote Bag CD Mini Tote Cinza") == "Bolsas e Malas"
    assert product_line_from_name("Gift Kit 4 Esponjinhas") == "Gift"
    assert product_line_from_name("Xyz qualquer") == "Outros"


def test_file_connector_blocks_path_traversal():
    assert_raises(ValidationError, FileConnector, "x", {"path": "../.env"})
    assert_raises(ValidationError, FileConnector, "x", {"path": "/etc/passwd"})


def test_gocase_nps_matches_case_analysis():
    env = _env()
    nps = NpsAnalytics(env.db, env.lake, ADMIN).overview()
    r = nps["nps"]
    assert (r["value"], r["n"], r["promoters"], r["neutrals"], r["detractors"]) == (87.52, 8869, 8111, 409, 349)
    assert nps["meta"]["is_demo"] is False   # dados do case, não sintéticos


def test_gocase_grain_and_privacy():
    env = _env()
    orders = env.lake.read_table("silver", "silver_orders")
    items = env.lake.read_table("silver", "silver_order_items")
    real = orders[~orders["_is_demo"].astype(bool)]           # + pedidos fictícios em trânsito (complemento demo)
    assert len(real) == 8642 and not orders["order_id"].duplicated().any() and len(items) == 22074
    assert orders.loc[orders["_is_demo"].astype(bool), "order_id"].str.startswith("DEMO-").all()
    assert int(real["n_items"].sum()) == 22074
    assert real["customer_id"].notna().all()                  # cliente derivado da avaliação NPS (dado real)
    bronze = env.lake.read_bronze("gocase_nps")
    assert bronze and "Name" not in bronze[0]["payload"] and "Ipaddress" not in bronze[0]["payload"]
    assert env.db.fetchone("SELECT COUNT(*) AS n FROM quarantine WHERE dataset IN "
                           "('silver_orders', 'silver_nps_evaluations', 'silver_deliveries')")["n"] == 0


def test_gocase_dimensions_and_limits():
    env = _env()
    a = NpsAnalytics(env.db, env.lake, ADMIN)
    states = {r["value"] for r in a.by_dimension("state")["rows"]}
    assert states <= UFS | {"Não identificado"} and len(states) >= 27
    freight = {r["value"]: r["avg_score"] for r in a.by_dimension("shipping_type")["rows"]}
    assert freight["Grátis"] > freight["Econômico"]
    corrs = a.correlation()["correlations"]
    corr = corrs["ship_to_delivery"]                         # "Dias de entrega" real
    assert corr["pearson"]["n"] == 8869 and abs(corr["pearson"]["r"]) < 0.05 and not corr["synthetic"]
    assert corrs["order_to_delivery"]["synthetic"]            # depende da produção simulada
    from data_platform.analytics.domains import logistics_overview
    lo = logistics_overview(env.db, env.lake, ADMIN)
    # Atraso depende do complemento sintético (previsão/datas) e é SEMPRE sinalizado como tal
    late = lo["late_rate"]
    assert late["result"]["value"] is not None and late["metric"]["synthetic"] and "is_late" in late["metric"]["synthetic_fields"]
    assert not late["metric"]["includes_demo_rows"]           # entregas fictícias em trânsito não entram na taxa
    # Prazo envio→entrega = "Dias de entrega" REAL da planilha (sem campo sintético no valor)
    from data_platform.semantic.registry import compute_metric
    lead = compute_metric(env.db, env.lake, ADMIN, "METRIC_DELIVERY_LEAD_TIME_001")
    assert abs(lead["result"]["value"] - 6.06) < 0.01 and lead["result"]["n"] == 8869 and not lead["metric"]["synthetic"]
    assert len(lo["delay_risk"]["rows"]) > 0 and lo["delay_risk"]["meta"]["is_demo"]


def test_gocase_default_thresholds_do_not_invent_incidents():
    env = make_env("gocase", shared=False) if gocase_seed_available() else _env()
    from agents.supervisor.agent import Supervisor
    out = Supervisor(env.db, env.lake).run_monitoring_cycle(ADMIN)
    assert out["monitor"]["signals"] == 0


def test_complement_only_fills_gaps_and_can_be_disabled():
    if not gocase_seed_available():
        raise unittest.SkipTest("planilhas da seed Gocase ausentes")
    env = make_env("gocase", shared=False)
    d = env.lake.read_table("silver", "silver_deliveries")
    real = d[~d["_is_demo"].astype(bool)]
    assert (real["_synthetic_fields"].fillna("") != "").all()
    assert not any("carrier" in str(x) for x in real["_synthetic_fields"])          # campo real nunca sobrescrito
    tr = real["actual_delivery_date"] - real["shipping_date"]
    assert ((tr.dt.total_seconds() / 86400).round() - real["delivery_days"].astype(float)).abs().max() <= 1
    from data_platform.ingestion.service import update_source
    from data_platform.pipelines.runner import run_pipeline
    for key in ("gocase_complemento_datas_entrega", "gocase_demo_pedidos_transito", "gocase_demo_entregas_transito"):
        update_source(env.db, ADMIN, key, status="inactive")
    run_pipeline(env.db, env.lake, ADMIN, sync=False)
    d2 = env.lake.read_table("silver", "silver_deliveries")
    assert d2["shipping_date"].isna().all() and not d2["_is_demo"].astype(bool).any()
    from data_platform.analytics.domains import logistics_overview
    assert logistics_overview(env.db, env.lake, ADMIN)["late_rate"]["result"]["value"] is None
