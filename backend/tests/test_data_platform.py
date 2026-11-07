"""Testes de dados (seção 16.1)."""
import pandas as pd

from helpers import ADMIN, assert_raises, make_env
from data_platform.ingestion.service import create_source, sync_source
from data_platform.pipelines.runner import run_pipeline
from data_platform.silver.transforms import deduplicate, map_records
from goops_core.errors import ValidationError


def _silver(env, key):
    return env.lake.read_table("silver", key)


def test_leading_zeros_preserved():
    env = make_env()
    orders = _silver(env, "silver_orders")
    assert orders["order_id"].str.startswith("0000").all()
    gold = env.lake.read_table("gold/corporate", "gold_nps_analytics")
    assert gold["order_id"].dropna().map(lambda s: isinstance(s, str) and len(s) == 8).all()


def test_numeric_id_is_flagged_not_silently_converted():
    env_rec = [{"_source": "x", "_run_id": "r", "_bronze_id": "r:1", "_ingested_at": "2026-01-01", "_payload_hash": "h",
                "payload": {"Order ID": 123, "order_date": "2026-01-01 10:00:00"}}]
    df = map_records(env_rec, "orders")
    assert df.loc[0, "order_id"] == "123"
    assert df.loc[0, "_cast_errors"]["order_id"] == "id_numeric"


def test_duplicates_detected_and_removed():
    env = make_env()
    stats = env.pipeline["steps"][1]["output"]["datasets"]
    assert stats["silver_nps_evaluations"]["dedup"]["exact_duplicates"] == 12
    assert stats["silver_orders"]["dedup"]["exact_duplicates"] == 8
    assert stats["silver_nps_evaluations"]["dedup"]["version_conflicts"] == 3
    nps = _silver(env, "silver_nps_evaluations")
    assert not nps["evaluation_id"].duplicated().any()
    assert not _silver(env, "silver_orders")["order_id"].duplicated().any()


def test_orphan_evaluations_and_deliveries_flagged_not_dropped():
    env = make_env()
    nps = _silver(env, "silver_nps_evaluations")
    deliv = _silver(env, "silver_deliveries")
    assert int(nps["is_orphan"].sum()) >= 20
    assert int(deliv["is_orphan"].sum()) >= 6
    gold = env.lake.read_table("gold/corporate", "gold_nps_analytics")
    assert (gold.loc[gold["is_orphan"].astype(bool), "state"] == "Não identificado").all()


def test_multiple_deliveries_do_not_multiply_evaluations():
    env = make_env()
    deliv = _silver(env, "silver_deliveries")
    multi = deliv.groupby("order_id").size()
    assert (multi > 1).sum() > 0
    nps = _silver(env, "silver_nps_evaluations")
    gold = env.lake.read_table("gold/corporate", "gold_nps_analytics")
    assert len(gold) == len(nps)
    gold_orders = env.lake.read_table("gold/corporate", "gold_orders")
    assert not gold_orders["order_id"].duplicated().any()
    assert gold_orders["n_deliveries"].max() >= 2


def test_multiple_evaluations_per_order_preserved():
    env = make_env()
    nps = _silver(env, "silver_nps_evaluations")
    assert (nps.groupby("order_id").size() > 1).any()


def test_required_fields_and_invalid_dates_quarantined():
    env = make_env()
    q = env.db.fetchall("SELECT dataset, reasons FROM quarantine")
    reasons = "|".join(r["reasons"] for r in q)
    assert "nps_order_id_required" in reasons
    assert "nps_evaluation_date_valid" in reasons
    assert "orders_order_date_valid" in reasons
    assert "deliveries_dates_coherent" in reasons
    assert "nps_score_range" in reasons


def test_api_failure_is_recorded():
    env = make_env("basic10", shared=False)
    create_source(env.db, ADMIN, key="demo_failing", name="Falha", entity="orders", connector="demo",
                  config={"simulate_failure": True, "max_retries": 1, "backoff_seconds": 0.01}, is_demo=True)
    res = sync_source(env.db, env.lake, ADMIN, "demo_failing")
    assert res["status"] == "failed"
    run = env.db.fetchone("SELECT status, error FROM ingestion_runs WHERE id = ?", (res["run_id"],))
    assert run["status"] == "failed" and run["error"]
    assert env.db.fetchone("SELECT COUNT(*) AS n FROM ingestion_failures WHERE run_id = ?", (res["run_id"],))["n"] == 1


def test_transient_failure_retried():
    env = make_env("basic10", shared=False)
    create_source(env.db, ADMIN, key="demo_flaky", name="Instável", entity="nps", connector="demo",
                  config={"scenario": "basic10", "simulate_failure": "transient", "backoff_seconds": 0.01}, is_demo=True)
    assert sync_source(env.db, env.lake, ADMIN, "demo_flaky")["status"] == "success"


def test_reprocessing_is_idempotent():
    env = make_env("basic10", shared=False)
    before = {k: _silver(env, k).drop(columns=["_run_id", "_bronze_id", "_ingested_at"]).sort_values(
        _silver(env, k).columns[0]).reset_index(drop=True) for k in ("silver_orders", "silver_nps_evaluations")}
    assert run_pipeline(env.db, env.lake, ADMIN, sync=True)["status"] == "success"   # re-ingestão
    assert run_pipeline(env.db, env.lake, ADMIN, sync=False)["status"] == "success"  # reprocessamento
    for k, df in before.items():
        after = _silver(env, k).drop(columns=["_run_id", "_bronze_id", "_ingested_at"]).sort_values(
            _silver(env, k).columns[0]).reset_index(drop=True)
        pd.testing.assert_frame_equal(df, after, check_dtype=False)
    runs = env.db.fetchone("SELECT COUNT(*) AS n FROM ingestion_runs")["n"]
    assert runs >= 6  # bronze preservou todas as execuções (append-only)


def test_bronze_is_append_only():
    env = make_env("basic10", shared=False)
    env.lake.write_bronze("demo_x", "RUN1", [{"a": 1}], "1", True)
    assert_raises(FileExistsError, env.lake.write_bronze, "demo_x", "RUN1", [{"a": 2}], "1", True)


def test_inline_secrets_rejected():
    env = make_env("basic10")
    assert_raises(ValidationError, create_source, env.db, ADMIN, key="bad_src", name="x", entity="orders",
                  connector="http_json", config={"base_url": "https://example.invalid", "api_key": "abc123"})


def test_dedup_keeps_latest_version():
    df = pd.DataFrame({"k": ["1", "1", "2"], "_ingested_at": ["2026-01-01", "2026-01-02", "2026-01-01"],
                       "_bronze_id": ["a", "b", "c"], "_payload_hash": ["h1", "h2", "h3"], "v": [1, 2, 3]})
    out, stats = deduplicate(df, "k")
    assert sorted(out["v"].tolist()) == [2, 3]
    assert stats["superseded_versions"] == 1
