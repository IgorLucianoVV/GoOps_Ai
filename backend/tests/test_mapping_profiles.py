"""Perfis de mapeamento editáveis pela interface: validação, prévia, versionamento e uso no pipeline."""
from helpers import ADMIN, assert_raises, make_env, user
from data_platform.ingestion.service import update_source
from data_platform.pipelines.runner import run_pipeline
from data_platform.silver.profiles import list_profiles, preview, profile_versions, save_profile, validate_definition
from data_platform.silver.transforms import _MISSING, lookup
from goops_core.errors import PermissionDenied, ValidationError

DEMO_NPS = {"fields": {
    "evaluation_id": {"from": ["evaluation_id"], "type": "id"},
    "order_id": {"from": ["Código do Pedido"], "type": "id"},
    "score": {"from": ["nota"], "type": "int"},
    "evaluation_date": {"from": ["data_avaliacao"], "type": "datetime"},
}}


def test_lookup_supports_nested_paths():
    payload = {"order": {"code": "0001", "items": [{"sku": "A"}]}, "a.b": 1}
    assert lookup(payload, "order.code") == "0001"
    assert lookup(payload, "order.items.0.sku") == "A"
    assert lookup(payload, "a.b") == 1
    assert lookup(payload, "order.missing") is _MISSING


def test_definition_validation():
    assert_raises(ValidationError, validate_definition, "nps", {"fields": {"campo_novo": {"from": ["x"]}}})
    assert_raises(ValidationError, validate_definition, "nps", {"fields": {"score": {"from": ["x"], "type": "python"}}})
    assert_raises(ValidationError, validate_definition, "nps", {"fields": {"score": {"derive": "os.system", "source": "x"}}})
    assert_raises(ValidationError, validate_definition, "nps", {"fields": {"order_id": {"from": []}}})  # chave sem origem
    assert_raises(ValidationError, validate_definition, "nps", {"grain": "item", "fields": {}})
    ok = validate_definition("nps", DEMO_NPS)
    assert ok["fields"]["order_id"]["required"] is True and ok["natural_key"] == "evaluation_id"


def test_preview_reports_coverage_errors_and_unused_keys():
    env = make_env("basic10", shared=False)
    good = preview(env.db, env.lake, ADMIN, "nps", DEMO_NPS, source_key="demo_nps")
    assert good["records"] == 10 and good["valid"] == 10 and good["quarantined"] == 0
    assert good["unused_keys"] == []   # campos não sobrescritos herdam a origem do perfil padrão (comentario, canal...)
    renamed = {"fields": {**DEMO_NPS["fields"], "score": {"from": ["rating"], "type": "int"}}}
    bad = preview(env.db, env.lake, ADMIN, "nps", renamed, source_key="demo_nps")
    score = next(f for f in bad["fields"] if f["field"] == "score")
    assert score["coverage_pct"] == 0 and bad["quarantined"] == 10           # nota ausente => quarentena, nunca descarte silencioso
    sample = preview(env.db, env.lake, ADMIN, "nps", {"fields": {**DEMO_NPS["fields"], "score": {"from": ["review.rating"], "type": "int"}}},
                     sample=[{"evaluation_id": "E1", "Código do Pedido": "001", "review": {"rating": 9}, "data_avaliacao": "2026-01-02",
                              "nova_coluna": "x"}])
    assert sample["valid"] == 1 and sample["rows"][0]["values"]["score"] == 9
    assert "nova_coluna" in sample["unused_keys"] and "review.rating" not in sample["unused_keys"]


def test_save_versions_and_use_in_pipeline():
    env = make_env("basic10", shared=False)
    assert_raises(ValidationError, save_profile, env.db, ADMIN, "default", "nps", DEMO_NPS, "tentar editar embutido")
    assert_raises(PermissionDenied, save_profile, env.db, user("viewer"), "nps_api_v2", "nps", DEMO_NPS, "sem permissão")
    p1 = save_profile(env.db, ADMIN, "nps_api_v2", "nps", DEMO_NPS, "versão inicial", based_on="default")
    assert p1["version"] == 1 and not p1["builtin"]
    p2 = save_profile(env.db, ADMIN, "nps_api_v2", "nps",
                      {"fields": {**DEMO_NPS["fields"], "comment": {"from": ["comentario"], "type": "string"}}}, "inclui comentário")
    assert p2["version"] == 2 and [v["version"] for v in profile_versions(env.db, "nps_api_v2", "nps")] == [2, 1]
    assert_raises(ValidationError, update_source, env.db, ADMIN, "demo_nps",
                  config={"scenario": "basic10", "mapping_profile": "nao_existe"})
    update_source(env.db, ADMIN, "demo_nps", config={"scenario": "basic10", "seed": 42, "mapping_profile": "nps_api_v2"})
    res = run_pipeline(env.db, env.lake, ADMIN, sync=False)
    assert res["status"] == "success"
    silver = res["steps"][0]["output"]["datasets"]["silver_nps_evaluations"]
    assert silver["valid"] == 10 and "nps_api_v2:nps_api_v2-v2" in silver["mapping_versions"]
    assert any(p["profile_key"] == "nps_api_v2" and p["used_by"] == ["demo_nps"] for p in list_profiles(env.db))
