"""“Pergunte ao GoOps”: respostas com métricas oficiais, citações reais, permissões e fallback determinístico."""
import agents.ask as A
from helpers import ADMIN, assert_raises, make_env, user
from agents.routing.llm_clients import ChatTurn, ToolCall
from goops_core.errors import PermissionDenied, ValidationError
from goops_core.runtime_config import set_secret, update_section


def test_deterministic_answer_uses_official_metrics():
    env = make_env("full")
    r = A.ask(env.db, env.lake, ADMIN, "Por que o NPS de Copos é menor?")
    assert r["generated_by"] == "deterministic" and "Nenhum modelo" in r["fallback_reason"]
    metrics = [c for c in r["citations"] if c["type"] == "metric"]
    seg = next(c for c in metrics if c["filters"].get("product_line") == ["Copo"])
    assert seg["metric_key"] == "METRIC_NPS_001" and seg["version"] == "1.0"
    assert f"{seg['value']:.1f}".replace(".", ",") in r["answer"]         # o número exibido é o da métrica oficial
    assert any(c["type"] == "comments" for c in r["citations"])
    assert "causalidade" in r["answer"]


def test_deterministic_breakdown_and_monthly():
    env = make_env("full")
    assert "por transportadora" in A.ask(env.db, env.lake, ADMIN, "Qual o NPS por transportadora?")["answer"]
    monthly = A.ask(env.db, env.lake, ADMIN, "Como evoluiu o NPS mês a mês?")
    assert "2026-06" in monthly["answer"]


def test_assistant_respects_user_permissions():
    env = make_env("full")
    assert_raises(ValidationError, A.ask, env.db, env.lake, ADMIN, "oi")
    cx_analyst = user("data_analyst", ["cx"])
    r = A.ask(env.db, env.lake, cx_analyst, "Qual o NPS?")       # métrica corporativa: permitido
    assert r["citations"][0]["metric_key"] == "METRIC_NPS_001"
    tb = A.Toolbox(env.db, env.lake, cx_analyst)
    assert_raises(PermissionDenied, tb.run, "metric_value", {"metric_key": "LOG_ON_TIME_TOLERANCE_001"})  # domínio logística


def test_llm_tool_loop_with_citations_and_cost():
    env = make_env("basic10", shared=False)
    update_section(env.db, ADMIN, "llm", {"levels": {"3": {"provider": "anthropic", "model": "modelo-x", "alias": ""}},
                                          "pricing": {"modelo-x": {"input_per_mtok": 3, "output_per_mtok": 15}}})
    set_secret(env.db, ADMIN, "anthropic_api_key", "sk-ant-teste-1234567890")
    turns = iter([
        ChatTurn("", [ToolCall("a", "metric_value", {"metric_key": "METRIC_NPS_001"}),
                      ToolCall("b", "run_sql", {"sql": "DROP TABLE users"})], {"role": "assistant", "content": []},
                 1000, 50, 300, "anthropic", "modelo-x"),
        ChatTurn("O NPS é **40**.", [], {"role": "assistant", "content": []}, 1200, 30, 300, "anthropic", "modelo-x"),
    ])
    original = A.chat_with_tools
    A.chat_with_tools = lambda *a, **k: next(turns)
    try:
        r = A.ask(env.db, env.lake, ADMIN, "Qual o NPS?")
    finally:
        A.chat_with_tools = original
    assert r["generated_by"] == "llm:modelo-x" and r["answer"] == "O NPS é **40**."
    assert [c["value"] for c in r["citations"] if c["type"] == "metric"] == [40.0]
    assert [t["ok"] for t in r["tools_used"]] == [True, False]           # ferramenta inexistente bloqueada
    assert r["cost_usd"] and env.db.fetchone("SELECT COUNT(*) AS n FROM llm_calls WHERE agent_key = 'assistant'")["n"] == 2


def test_llm_that_skips_tools_falls_back():
    env = make_env("basic10", shared=False)
    update_section(env.db, ADMIN, "llm", {"levels": {"3": {"provider": "anthropic", "model": "modelo-x", "alias": ""}}})
    set_secret(env.db, ADMIN, "anthropic_api_key", "sk-ant-teste-1234567890")
    original = A.chat_with_tools
    A.chat_with_tools = lambda *a, **k: ChatTurn("O NPS é 99 (inventado).", [], {}, 10, 5, 10, "anthropic", "modelo-x")
    try:
        r = A.ask(env.db, env.lake, ADMIN, "Qual o NPS?")
    finally:
        A.chat_with_tools = original
    assert r["generated_by"] == "deterministic" and "99" not in r["answer"] and "40" in r["answer"]


def test_model_options_and_selection():
    env = make_env("basic10", shared=False)
    update_section(env.db, ADMIN, "llm", {"chat_models": [
        {"provider": "anthropic", "model": "modelo-y", "label": "Modelo Y"},
        {"provider": "ollama", "model": "llama3.1", "label": "Local"}]})
    assert_raises(ValidationError, update_section, env.db, ADMIN, "llm",
                  {"chat_models": [{"provider": "inexistente", "model": "x", "label": "x"}]})
    from goops_core.runtime_config import effective_settings
    opts = {o["id"]: o for o in A.chat_model_options(effective_settings(env.db))}
    assert opts["anthropic:modelo-y"]["credential"] is False   # sem chave: indisponível
    assert opts["ollama:llama3.1"]["credential"] is True                              # local: não exige chave
    assert_raises(ValidationError, A.ask, env.db, env.lake, ADMIN, "Qual o NPS?", None, "openai:nao-listado")
    set_secret(env.db, ADMIN, "anthropic_api_key", "sk-ant-teste-1234567890")
    original = A.chat_with_tools
    seen = []
    def fake(*a, **k):
        seen.append(1)
        return ChatTurn("O NPS é **40**.", [], {}, 10, 5, 10, "anthropic", "modelo-y") if len(seen) > 1 else \
            ChatTurn("", [ToolCall("a", "metric_value", {"metric_key": "METRIC_NPS_001"})], {"role": "assistant", "content": []},
                     10, 5, 10, "anthropic", "modelo-y")
    A.chat_with_tools = fake
    try:   # sem LangGraph instalado no ambiente de teste: usa o loop nativo com o modelo escolhido
        r = A.ask(env.db, env.lake, ADMIN, "Qual o NPS?", None, "anthropic:modelo-y")
    finally:
        A.chat_with_tools = original
    assert r["model"] == "modelo-y" and r["provider"] == "anthropic" and r["generated_by"] == "llm:modelo-y"


def test_model_catalog_and_discovery():
    import requests
    from agents.llm import providers as P
    from goops_core.runtime_config import config_view, effective_settings
    env = make_env("basic10", shared=False)
    status = {p["provider"]: p for p in config_view(env.db)["providers_status"]}
    assert [m["id"] for m in status["anthropic"]["models"]][:1] == ["claude-opus-5-5"] and status["ollama"]["models"]
    no_key = P.discover_models("anthropic", effective_settings(env.db))           # sem chave: catálogo + motivo
    assert no_key["source"] == "catalog" and "chave" in no_key["error"]
    set_secret(env.db, ADMIN, "openai_api_key", "sk-teste-1234567890")

    class Resp:
        def __init__(self, data, code=200): self._d, self.status_code = data, code
        def json(self): return self._d
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)
    original = requests.get
    try:
        requests.get = lambda url, **k: Resp({"data": [{"id": "gpt-x"}, {"id": "text-embedding-3"}, {"id": "gpt-x-mini"}]})
        ok_ = P.discover_models("openai", effective_settings(env.db))
        assert ok_["source"] == "provider" and [m["id"] for m in ok_["models"]] == ["gpt-x", "gpt-x-mini"]
        requests.get = lambda url, **k: Resp({"models": [{"name": "llama3.1:8b"}]})
        assert P.discover_models("ollama", effective_settings(env.db))["models"][0]["id"] == "llama3.1:8b"
        requests.get = lambda url, **k: Resp({}, 401)
        bad = P.discover_models("openai", effective_settings(env.db))
        assert bad["source"] == "catalog" and "401" in bad["error"] and "sk-" not in bad["error"]
    finally:
        requests.get = original
    assert_raises(ValidationError, P.discover_models, "inexistente", effective_settings(env.db))


def test_general_question_without_model_is_honest():
    env = make_env()
    r = A.ask(env.db, env.lake, ADMIN, "O que é a Gocase?")
    assert r["generated_by"] == "deterministic"
    assert "Net Promoter" not in r["answer"] and not r["citations"]
    assert "Modelos e chaves" in r["answer"]
    assert A.ask(env.db, env.lake, ADMIN, "O que o GoOps faz?")["answer"].startswith("O **GoOps**")


def test_llm_answer_without_tools_rejects_numbers():
    A._accept_without_tools("NPS é uma métrica de lealdade do cliente.")
    assert_raises(ValidationError, A._accept_without_tools, "A Gocase vende 10 mil capinhas.")
