"""Testes NPS (seção 16.2)."""
import pandas as pd

from helpers import ADMIN, make_env
from data_platform.analytics.nps import NpsAnalytics
from data_platform.gold.corporate import score_category
from data_platform.semantic.engine import compute
from data_platform.semantic.seed import NPS_DEF


def test_classification_boundaries():
    cats = score_category(pd.Series([0, 6, 7, 8, 9, 10, 11])).tolist()
    assert cats[:6] == ["detractor", "detractor", "neutral", "neutral", "promoter", "promoter"]


def test_score_11_rejected_from_calculation():
    res = compute(NPS_DEF, pd.DataFrame({"score": [10, 11, 0]}))
    assert res["n"] == 2 and res["invalid_excluded"] == 1 and res["value"] == 0.0


def test_nps_formula():
    res = compute(NPS_DEF, pd.DataFrame({"score": [10, 10, 9, 9, 10, 9, 8, 7, 3, 5]}))
    assert res["value"] == 40.0 and res["promoters"] == 6 and res["neutrals"] == 2 and res["detractors"] == 2


def test_empty_period_returns_null_not_zero():
    res = compute(NPS_DEF, pd.DataFrame({"score": pd.Series([], dtype=float)}))
    assert res["value"] is None


def test_basic10_scenario_end_to_end():
    env = make_env("basic10")
    ov = NpsAnalytics(env.db, env.lake, ADMIN).overview()
    assert ov["nps"]["value"] == 40.0
    assert ov["metric"]["metric_key"] == "METRIC_NPS_001" and ov["metric"]["version"] == "1.0"
    assert ov["meta"]["is_demo"] is True


def test_invalid_scores_quarantined_in_full_demo():
    env = make_env()
    q = env.db.fetchall("SELECT payload FROM quarantine WHERE reasons LIKE ?", ("%nps_score_range%",))
    assert len(q) == 7  # 5 notas 11 + 2 notas -1
    gold = env.lake.read_table("gold/corporate", "gold_nps_analytics")
    assert gold["score"].between(0, 10).all()


def test_filters_preserve_results():
    env = make_env()
    a = NpsAnalytics(env.db, env.lake, ADMIN)
    total = a.overview()["nps"]
    parts = a.by_dimension("carrier")["rows"]
    assert sum(r["total"] for r in parts) == total["n"]
    for r in parts:
        if r["value"] == "Não identificado":
            continue
        filtered = a.overview({"carrier": [r["value"]]})["nps"]
        assert filtered["value"] == r["nps"] and filtered["n"] == r["total"]


def test_period_without_data_is_null():
    env = make_env()
    res = NpsAnalytics(env.db, env.lake, ADMIN).overview({"start": "2030-01-01", "end": "2030-01-31"})
    assert res["nps"]["value"] is None and res["nps"]["n"] == 0


def test_evolution_months_and_deltas():
    env = make_env()
    rows = NpsAnalytics(env.db, env.lake, ADMIN).evolution()["rows"]
    assert [r["month"] for r in rows] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    assert rows[0]["delta"] is None
    assert abs(rows[1]["delta"] - (rows[1]["nps"] - rows[0]["nps"])) < 0.01


def test_correlation_reports_n_and_limitations():
    env = make_env()
    c = NpsAnalytics(env.db, env.lake, ADMIN).correlation()
    for v in c["correlations"].values():
        assert v["pearson"]["n"] > 1000 and v["spearman"]["r"] is not None
    assert any("causalidade" in l for l in c["limitations"])


def test_comments_report_processed_count_and_injection_flag():
    env = make_env()
    c = NpsAnalytics(env.db, env.lake, ADMIN).comments()
    assert c["all"]["comments_processed"] == c["comments_available"] > 0
    assert c["injection_suspected"] == 1
    det_themes = {t["theme"] for t in c["detractors"]["themes"]}
    assert "entrega_atrasada" in det_themes


def test_unlinked_group_flagged_and_last():
    """O grupo sem vínculo (órfãs) não é um segmento: vem sinalizado, por último e informado no meta."""
    env = make_env()
    res = NpsAnalytics(env.db, env.lake, ADMIN).by_dimension("state")
    rows = res["rows"]
    unl = [r for r in rows if r["unlinked"]]
    assert len(unl) == 1 and unl[0]["value"] == "Não identificado" and rows[-1] is unl[0]
    assert res["meta"]["unlinked"]["total"] == unl[0]["total"]
    linked = [r["nps"] for r in rows if not r["unlinked"]]
    assert linked == sorted(linked)


def test_orphan_scores_follow_realistic_distribution():
    """Notas das órfãs sintéticas não podem ser uniformes em 0-10 (o que daria NPS esperado de -45,5)."""
    from data_platform.demo.generator import generate
    orphans = [e["nota"] for e in generate("full")["nps"] if str(e["Código do Pedido"] or "").startswith("00099")]
    assert len(orphans) == 20 and all(0 <= s <= 10 for s in orphans)
    res = compute(NPS_DEF, pd.DataFrame({"score": orphans}))
    assert res["value"] > 0
