"""Proteções de segurança: credenciais de fontes, SSRF, custo de LLM sem preço e revogação de sessão."""
from helpers import ADMIN, assert_raises, make_env

from goops_core.errors import AuthenticationError, ValidationError


def test_source_credential_env_cannot_point_to_infrastructure_secrets():
    from data_platform.connectors.http_connector import validate_credential_env
    for bad in ("SECRET_KEY", "POSTGRES_PASSWORD", "ANTHROPIC_API_KEY", "DATABASE_URL", "DEMO_ADMIN_PASSWORD",
                "LLM_SMALL_MODEL", "path", "X"):
        assert_raises(ValidationError, validate_credential_env, bad)
    for good in ("ORDERS_API_TOKEN", "ERP_TOKEN", "SOURCE_CRM_KEY", "TRANSPORTADORA_USER", "TRANSPORTADORA_PASSWORD"):
        assert validate_credential_env(good) == good


def test_source_create_rejects_secret_exfiltration_and_internal_hosts():
    env = make_env("full")
    from data_platform.ingestion.service import create_source
    assert_raises(ValidationError, create_source, env.db, ADMIN, key="evil", name="Evil", entity="orders",
                  connector="http_json", config={"base_url": "https://api.exemplo.invalid",
                                                 "auth": {"type": "bearer", "token_env": "SECRET_KEY"}})
    for url in ("http://127.0.0.1:5432", "http://169.254.169.254/latest", "http://localhost:8000", "http://10.0.0.5",
                "http://db.internal", "https://user:pw@api.exemplo.invalid"):
        assert_raises(ValidationError, create_source, env.db, ADMIN, key="ssrf", name="SSRF", entity="orders",
                      connector="http_json", config={"base_url": url})


def test_private_host_allowlist(monkeypatch=None):
    import os
    from data_platform.connectors.http_connector import validate_outbound_url
    os.environ["SOURCE_ALLOWED_PRIVATE_HOSTS"] = "10.0.0.5"
    try:
        assert validate_outbound_url("http://10.0.0.5/api")
    finally:
        os.environ.pop("SOURCE_ALLOWED_PRIVATE_HOSTS")


def test_llm_cost_without_price_uses_conservative_estimate():
    env = make_env("full")
    from agents.routing.router import FALLBACK_PRICE, CostRouter
    r = CostRouter(env.db)
    cost = r._cost("modelo-sem-preco", 1_000_000, 0, "anthropic")
    assert cost == FALLBACK_PRICE["input_per_mtok"]
    assert r._cost("llama3.1", 1_000_000, 1_000_000, "ollama") == 0.0
    assert r._cost("modelo-sem-preco", None, None, "openai") > 0


def test_password_reset_invalidates_old_tokens():
    env = make_env("full")
    from goops_core.users import authenticate, create_user, principal_from_token, reset_password
    u = create_user(env.db, ADMIN, "sec.test@goops.local", "Teste Seg", "viewer", ["*"], "senha-inicial-1")
    tok = authenticate(env.db, "sec.test@goops.local", "senha-inicial-1")["access_token"]
    assert principal_from_token(env.db, tok).id == u["id"]
    reset_password(env.db, ADMIN, u["id"], "senha-nova-123")
    assert_raises(AuthenticationError, principal_from_token, env.db, tok)
